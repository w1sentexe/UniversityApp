from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session, session_scope
from app.entities.enums import VedType
from app.entities.not_rating_ved_model import NotRatingVedModel
from app.entities.notification_models import RatingMutationRequest, RatingMutationResponse
from app.entities.rating_ved_model import RatingVedModel
from app.repository.notification_repository import NotificationRepository
from app.services.notification_service import NotificationService
from app.services.rating_mutation_service import RatingMutationService
from app.services.rating_service import RatingService, get_rating_service

router = APIRouter(prefix="/rating", tags=["rating"])

# Зачёт и экзамен возвращают записи обеих форм: ведомость без колонок КТ парсер
# относит к оценочному формату независимо от вида (см. app/parser/html_parser.py).


@router.get("/{zach_number}/zachet")
async def zachet(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[RatingVedModel | NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.ZACHET)
    return result


@router.get("/{zach_number}/ekzamen")
async def ekzamen(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[RatingVedModel | NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.EKZAMEN)
    return result


@router.get("/{zach_number}/vypusknaya-rabota")
async def vypusknaya_rabota(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.VYPUSKNAYA_RABOTA)
    return result


@router.get("/{zach_number}/gosekzamen")
async def gosekzamen(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.GOSEKZAMEN)
    return result


@router.get("/{zach_number}/kontrolnaya-rabota")
async def kontrolnaya_rabota(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.KONTROLNAYA_RABOTA)
    return result


@router.get("/{zach_number}/kursovaya-rabota")
async def kursovaya_rabota(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.KURSOVAYA_RABOTA)
    return result


@router.get("/{zach_number}/kursovoy-proekt")
async def kursovoy_proekt(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.KURSOVOY_PROEKT)
    return result


@router.get("/{zach_number}/praktika")
async def praktika(
    zach_number: str,
    rating_service: RatingService = Depends(get_rating_service),
) -> list[NotRatingVedModel]:
    result = await rating_service.get_by_ved_type(zach_number, VedType.PRAKTIKA)
    return result


@router.patch("/test/final-rating")
async def update_final_rating_for_test(
    request: RatingMutationRequest,
    x_test_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> RatingMutationResponse:
    if not settings.test.mutation_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test mutation endpoint is disabled")
    if x_test_token != settings.test.mutation_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid test token")

    response = await RatingMutationService(session).update_final_rating(request)
    async with session_scope() as dispatch_session:
        await NotificationService(NotificationRepository(dispatch_session)).dispatch_pending()
    return response
