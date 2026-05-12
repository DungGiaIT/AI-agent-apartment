import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.route_verifier import router as listings_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info(f"🚀 {settings.app_name} v{settings.app_version} đang khởi động...")
    logger.info(f"   Debug mode: {settings.debug}")
    logger.info(f"   Gemini API key: {'✓ đã cấu hình' if settings.gemini_api_key else '✗ THIẾU'}")

    yield

    logger.info("👋 Service đang tắt...")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Agent kiểm duyệt và chuẩn hoá bài đăng cho thuê căn hộ",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings_router)

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }