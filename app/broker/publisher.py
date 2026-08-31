import asyncio
import logging

from faststream.rabbit import RabbitBroker
from sqlalchemy import select

from app.broker.rabbit import RabbitSettings, created_queue, domain_exchange
from app.db.db_helper import db_helper
from app.db.models import OutboxEvent, OutboxStatus

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, broker: RabbitBroker, poll_interval_seconds: float = 1.0, batch_size: int = 1000) -> None:
        self.broker = broker
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        logger.info("Outbox publisher start")
        while not self._stop_event.is_set():
            try:
                await self.publish_pending_events()
            except Exception:
                logger.exception("Outbox publisher loop failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue

    async def stop(self) -> None:
        logger.info("Outbox publisher shutdown")
        self._stop_event.set()

    async def publish_pending_events(self) -> None:
        async with db_helper.session_factory() as session:
            result = await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.id)
                .limit(self.batch_size)
                .with_for_update(skip_locked=True)
            )
            events = result.scalars().all()

            if not events:
                return

            published_events_count = 0
            for event in events:
                await self.broker.publish(
                    event.event_payload,
                    queue=created_queue,
                    exchange=domain_exchange,
                    routing_key=RabbitSettings.routing_key,
                )
                event.status = OutboxStatus.PROCESSED
                await session.commit()
                published_events_count += 1

            logger.info("Published %s outbox events", published_events_count)
