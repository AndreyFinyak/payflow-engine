from fastapi import APIRouter

from app.api.v1 import payments_router_v1

main_router = APIRouter()
main_router.include_router(payments_router_v1, prefix="/api/v1")

__all__ = ["main_router"]