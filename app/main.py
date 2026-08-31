import asyncio
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI

from app.api import main_router
from app.broker.publisher import OutboxPublisher
from app.broker.rabbit import (
    create_rabbit_broker,
    created_queue,
    domain_exchange,
    error_queue,
)
from app.core.config import settings
from app.db.db_helper import db_helper
from app.logger import configure_logging

configure_logging()

PUBLISHER_SHUTDOWN_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def lifespan(_: FastAPI):
    broker = create_rabbit_broker(settings.rabbitmq_url)
    await broker.connect()
    await broker.declare_exchange(domain_exchange)
    await broker.declare_queue(created_queue)
    await broker.declare_queue(error_queue)

    publisher = OutboxPublisher(broker=broker, poll_interval_seconds=settings.outbox_poll_interval_seconds)
    publisher_task = asyncio.create_task(publisher.run())

    try:
        yield
    finally:
        await publisher.stop()
        try:
            await asyncio.wait_for(publisher_task, timeout=PUBLISHER_SHUTDOWN_TIMEOUT_SECONDS)
        except TimeoutError:
            publisher_task.cancel()
            with suppress(asyncio.CancelledError):
                await publisher_task
        await broker.close()
        await db_helper.dispose()


app = FastAPI(title="Asynchronous Payment Processing Service", lifespan=lifespan)
app.include_router(main_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
