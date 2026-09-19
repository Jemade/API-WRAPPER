"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.generate import router as generate_router

api_v1_router = APIRouter()
api_v1_router.include_router(generate_router, prefix="/v1")
