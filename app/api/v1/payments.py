from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.api.v1.dependencies import RequireApiKey, get_payment_service
from app.schemas.payment import (
    CreatePaymentRequest,
    PaymentCreateResponse,
    PaymentResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[RequireApiKey])


@router.post("", response_model=PaymentCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_payment(
        payload: CreatePaymentRequest,
        response: Response,
        payment_service: PaymentService = Depends(get_payment_service),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> PaymentCreateResponse:
    result = await payment_service.create_payment(payload=payload, idempotency_key=idempotency_key)

    if not result.created:
        response.status_code = status.HTTP_200_OK

    return PaymentCreateResponse(
        payment_id=result.payment.id,
        status=result.payment.status,
        created_at=result.payment.created_at,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
        payment_id: UUID,
        payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentResponse:
    payment = await payment_service.get_payment(payment_id)

    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return PaymentResponse.model_validate(payment)
