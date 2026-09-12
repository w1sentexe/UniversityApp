from datetime import datetime

from pydantic import BaseModel


class SnapshotStatusModel(BaseModel):
    version: str
    committed_at: datetime | None = None
    source: str
    parsing_year: str
    parsing_semester: str
    rating_rows: int
    grade_rows: int
    group_rows: int
