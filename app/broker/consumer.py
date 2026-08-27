import asyncio
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

import aiohttp
from faststream import FastStream
from faststream.rabbit import RabbitMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.rabbit import (
    RabbitSettings,
    domain_exchange,
    created_queue,
    error_queue,
    create_rabbit_broker,
)
from app.core.config import settings
from app.db.db_helper import db_helper
from app.db.models import Payment, PaymentStatus
from app.logger import configure_logging

logger = logging.getLogger(__name__)

configure_logging()

broker = create_rabbit_broker(settings.rabbitmq_url)
application = FastStream(broker)


async def _send_webhook_with_retries(payment_id: UUID, status: PaymentStatus, webhook_url: str) -> bool:
    payload = {"payment_id": str(payment_id), "status": status.value}
    backoff = [1, 2, 4]

    timeout = aiohttp.ClientTimeout(
        total=settings.webhook_total_timeout_seconds, connect=settings.webhook_connect_timeout_seconds
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt, delay in enumerate(backoff, start=1):
            try:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status >= 400:
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"Webhook failed with status {response.status}"
                        )
                    return True
            except Exception:
                logger.exception("Webhook attempt %s failed for payment %s", attempt, payment_id)
                if attempt < len(backoff):
                    await asyncio.sleep(delay)

    return False


async def _move_to_dlq(payload: dict) -> None:
    await broker.publish(
        payload,
        queue=error_queue,
        exchange=domain_exchange,
        routing_key=RabbitSettings.dlq_routing_key,
    )


async def _process_payment(session: AsyncSession, payment: Payment) -> PaymentStatus:
    await asyncio.sleep(random.uniform(2, 5))

    if random.random() < 0.1:
        raise RuntimeError("Simulation error processing payment!")

    if random.random() < 0.9:
        payment.status = PaymentStatus.SUCCEEDED
    else:
        payment.status = PaymentStatus.FAILED

    payment.processed_at = datetime.now(timezone.utc)
    await session.commit()
    return payment.status


@broker.subscriber(created_queue, exchange=domain_exchange)
async def handle_payment_event(message: dict, raw_message: RabbitMessage) -> None:
    payment_id_raw = message.get("payment_id")
    if not payment_id_raw:
        logger.error("Incoming message does not include payment_id: %s", message)
        await _move_to_dlq(message)
        await raw_message.ack()
        return

    payment_id = UUID(payment_id_raw)
    async with db_helper.session_factory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            logger.error("Payment %s not found", payment_id)
            await _move_to_dlq(message)
            await raw_message.ack()
            return

        try:
            final_status = await _process_payment(session, payment)
        except Exception:
            logger.exception("Processing failed for payment %s", payment_id)
            payment.status = PaymentStatus.FAILED
            payment.processed_at = datetime.now(timezone.utc)
            await session.commit()
            final_status = payment.status

        webhook_sent = await _send_webhook_with_retries(
            payment_id=payment.id,
            status=final_status,
            webhook_url=payment.webhook_url,
        )
        if not webhook_sent:
            logger.error("Moving payment %s message to DLQ after retries", payment.id)
            await _move_to_dlq(message)

    await raw_message.ack()


if __name__ == "__main__":
    asyncio.run(application.run())
