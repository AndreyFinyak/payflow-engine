from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.db_helper import db_helper
from app.security import require_api_key
from app.services.payment_service import PaymentService


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async with db_helper.session_factory() as session:
        yield session


async def get_payment_service(
        db: AsyncSession = Depends(get_db_session)
) -> PaymentService:
    return PaymentService(db=db)


RequireApiKey = Depends(require_api_key)
