from fastapi import APIRouter

from .router import router as export_router
from .impression import router as print_router

router = APIRouter()
router.include_router(export_router)
router.include_router(print_router)
