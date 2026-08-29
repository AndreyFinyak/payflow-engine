import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress

import uvicorn
from fastapi import FastAPI

from app.api import main_router
from app.broker.publisher import OutboxPublisher
from app.broker.rabbit import create_rabbit_broker, domain_exchange, created_queue, error_queue
from app.core.config import settings
from app.logger import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    broker = create_rabbit_broker(settings.rabbitmq_url)
    await broker.connect()
    await broker.declare_exchange(domain_exchange)
    await broker.declare_queue(created_queue)
    await broker.declare_queue(error_queue)

    publisher = OutboxPublisher(broker=broker, poll_interval_seconds=settings.outbox_poll_interval_seconds)
    task = asyncio.create_task(publisher.run())

    try:
        yield
    finally:
        await publisher.stop()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await broker.close()


app = FastAPI(title="Asynchronous Payment Processing Service", lifespan=lifespan)
app.include_router(main_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
