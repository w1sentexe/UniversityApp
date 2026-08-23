from pydantic import BaseModel, Field

from app.entities.enums import VedType


class PushKeysModel(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionModel(BaseModel):
    endpoint: str
    keys: PushKeysModel


class SubscribeRequest(BaseModel):
    zach_number: str
    subscription: PushSubscriptionModel


class UnsubscribeRequest(BaseModel):
    endpoint: str


class NotificationStatusModel(BaseModel):
    supported: bool
    enabled: bool
    reason: str | None = None


class VapidPublicKeyModel(BaseModel):
    public_key: str


class RatingMutationRequest(BaseModel):
    zach_number: str
    ved_type: VedType
    subject_name: str
    final_rating: str | int = Field(..., examples=[90])


class RatingMutationResponse(BaseModel):
    zach_number: str
    ved_type: str
    subject_name: str
    final_rating: str
    queued_notifications: int
