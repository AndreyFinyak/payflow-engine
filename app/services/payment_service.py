from uuid import UUID

from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OutboxEvent, Payment, PaymentStatus
from app.schemas.payment import CreatePaymentRequest


@dataclass(slots=True)
class CreatePaymentResult:
    payment: Payment
    created: bool


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_payment(self, payload: CreatePaymentRequest, idempotency_key: str) -> CreatePaymentResult:
        async with self.db.begin():
            existing = await self.db.scalar(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            if existing:
                return CreatePaymentResult(payment=existing, created=False)

            payment = Payment(
                amount=payload.amount,
                currency=payload.currency,
                description=payload.description,
                metadata_json=payload.metadata,
                status=PaymentStatus.PENDING,
                idempotency_key=idempotency_key,
                webhook_url=str(payload.webhook_url),
            )
            self.db.add(payment)
            await self.db.flush()

            event = OutboxEvent(
                event_type="payment.created",
                event_payload={"payment_id": str(payment.id)},
            )
            self.db.add(event)

        await self.db.refresh(payment)
        return CreatePaymentResult(payment=payment, created=True)

    async def get_payment(self, payment_id: UUID) -> Payment | None:
        return await self.db.get(Payment, payment_id)
