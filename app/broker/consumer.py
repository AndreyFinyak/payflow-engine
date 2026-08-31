import asyncio
import logging
import random
from datetime import UTC, datetime
from uuid import UUID

import aiohttp
from faststream import FastStream
from faststream.rabbit import RabbitMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.rabbit import (
    RabbitSettings,
    create_rabbit_broker,
    created_queue,
    domain_exchange,
    error_queue,
)
from app.core.config import settings
from app.db.db_helper import db_helper
from app.db.models import Payment, PaymentStatus
from app.logger import configure_logging

logger = logging.getLogger(__name__)

configure_logging()

broker = create_rabbit_broker(settings.rabbitmq_url)
application = FastStream(broker)

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
WEBHOOK_BACKOFF_DELAYS_SECONDS = (1.0, 2.0, 4.0)

_webhook_session: aiohttp.ClientSession | None = None


@application.after_startup
async def create_webhook_session() -> None:
    global _webhook_session
    timeout = aiohttp.ClientTimeout(
        total=settings.webhook_total_timeout_seconds,
        connect=settings.webhook_connect_timeout_seconds,
    )
    _webhook_session = aiohttp.ClientSession(timeout=timeout)
    logger.info("Shared webhook HTTP session created")


@application.after_startup
async def declare_dlq_binding() -> None:
    exchange = await broker.declare_exchange(domain_exchange)
    queue = await broker.declare_queue(error_queue)
    await queue.bind(exchange, routing_key=RabbitSettings.dlq_routing_key, robust=error_queue.robust)
    logger.info("DLQ queue bound to exchange with routing key %s", RabbitSettings.dlq_routing_key)


@application.on_shutdown
async def close_webhook_session() -> None:
    if _webhook_session is not None:
        await _webhook_session.close()
        logger.info("Shared webhook HTTP session closed")


async def _send_webhook_with_retries(payment_id: UUID, payment_status: PaymentStatus, webhook_url: str) -> bool:
    if _webhook_session is None:
        raise RuntimeError("Webhook HTTP session is not initialised")

    payload = {"payment_id": str(payment_id), "status": payment_status.value}

    for attempt_index, backoff_delay_seconds in enumerate(WEBHOOK_BACKOFF_DELAYS_SECONDS, start=1):
        try:
            async with _webhook_session.post(webhook_url, json=payload) as response:
                if response.status < 400:
                    return True
                if response.status not in RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Webhook for payment %s rejected with status %s, giving up",
                        payment_id,
                        response.status,
                    )
                    return False
                logger.warning(
                    "Webhook for payment %s failed with retryable status %s",
                    payment_id,
                    response.status,
                )
        except (aiohttp.ClientError, TimeoutError):
            logger.exception("Webhook attempt %s failed for payment %s", attempt_index, payment_id)

        if attempt_index < len(WEBHOOK_BACKOFF_DELAYS_SECONDS):
            await asyncio.sleep(backoff_delay_seconds)

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

    payment.status = PaymentStatus.SUCCEEDED

    payment.processed_at = datetime.now(UTC)
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

    try:
        payment_id = UUID(str(payment_id_raw))
    except ValueError:
        logger.error("Message contains invalid payment_id %r: %s", payment_id_raw, message)
        await _move_to_dlq(message)
        await raw_message.ack()
        return

    async with db_helper.session_factory() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            logger.error("Payment %s not found", payment_id)
            await _move_to_dlq(message)
            await raw_message.ack()
            return

        if payment.status != PaymentStatus.PENDING:
            logger.info(
                "Payment %s already processed with status %s, skipping redelivered message",
                payment_id,
                payment.status.value,
            )
            await raw_message.ack()
            return

        try:
            final_status = await _process_payment(session, payment)
        except Exception:
            logger.exception("Processing failed for payment %s", payment_id)
            payment.status = PaymentStatus.FAILED
            payment.processed_at = datetime.now(UTC)
            await session.commit()
            final_status = payment.status

        webhook_sent = await _send_webhook_with_retries(
            payment_id=payment.id,
            payment_status=final_status,
            webhook_url=payment.webhook_url,
        )
        if not webhook_sent:
            logger.error("Moving payment %s message to DLQ after retries", payment.id)
            await _move_to_dlq(message)

    await raw_message.ack()


if __name__ == "__main__":
    asyncio.run(application.run())
