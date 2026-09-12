from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.entities.models import GradeRecord, RatingRecord, SnapshotMeta, StudentGroup, utcnow
from app.entities.schemas.snapshot import SnapshotStatusModel
from app.logging_config import get_logger

log = get_logger(__name__)

_RATING_META_ID = "rating"


class SnapshotMetaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def status(self) -> SnapshotStatusModel:
        row = await self._session.scalar(select(SnapshotMeta).where(SnapshotMeta.id == _RATING_META_ID))
        if row is not None:
            return SnapshotStatusModel(
                version=row.version,
                committed_at=row.committed_at,
                source=row.source,
                parsing_year=row.parsing_year,
                parsing_semester=row.parsing_semester,
                rating_rows=row.rating_rows,
                grade_rows=row.grade_rows,
                group_rows=row.group_rows,
            )

        # Legacy state after first deploy of this table: the data can already
        # exist, but no committed version has been written yet.
        counts = await self._counts()
        return SnapshotStatusModel(
            version=f"legacy:{counts['rating_rows']}:{counts['grade_rows']}:{counts['group_rows']}",
            committed_at=None,
            source="legacy",
            parsing_year=settings.parsing.year,
            parsing_semester=settings.parsing.semester,
            **counts,
        )

    async def mark_updated(self, *, source: str, version: str | None = None) -> str:
        version = version or f"{source}-{uuid4().hex}"
        counts = await self._counts()
        row = await self._session.scalar(select(SnapshotMeta).where(SnapshotMeta.id == _RATING_META_ID))
        if row is None:
            row = SnapshotMeta(
                id=_RATING_META_ID,
                version=version,
                source=source,
                parsing_year=settings.parsing.year,
                parsing_semester=settings.parsing.semester,
                **counts,
            )
            self._session.add(row)
        else:
            row.version = version
            row.source = source
            row.parsing_year = settings.parsing.year
            row.parsing_semester = settings.parsing.semester
            row.rating_rows = counts["rating_rows"]
            row.grade_rows = counts["grade_rows"]
            row.group_rows = counts["group_rows"]
            row.committed_at = utcnow()

        log.info("Snapshot metadata updated", version=version, source=source, **counts)
        return version

    async def _counts(self) -> dict[str, int]:
        rating_rows = await self._session.scalar(select(func.count()).select_from(RatingRecord))
        grade_rows = await self._session.scalar(select(func.count()).select_from(GradeRecord))
        group_rows = await self._session.scalar(select(func.count()).select_from(StudentGroup))
        return {
            "rating_rows": int(rating_rows or 0),
            "grade_rows": int(grade_rows or 0),
            "group_rows": int(group_rows or 0),
        }
