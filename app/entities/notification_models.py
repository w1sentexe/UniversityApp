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


class NotificationDebugModel(BaseModel):
    zach_number: str
    enabled_subscriptions: int
    disabled_subscriptions: int
    watch_states: int
    pending_outbox: int
    sent_outbox: int
    failed_outbox: int


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


class ControlPointMutationRequest(BaseModel):
    zach_number: str
    ved_type: VedType
    subject_name: str
    kt_num: int = Field(..., ge=1, examples=[1])
    total: str | int = Field(..., examples=[8])


class ControlPointMutationResponse(BaseModel):
    zach_number: str
    ved_type: str
    subject_name: str
    kt_num: int
    total: str
    queued_notifications: int
