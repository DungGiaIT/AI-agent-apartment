import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.route_verifier import router as listings_router
from app.api.routes.route_broker import router as broker_router
from app.services.qdrant_service import init_qdrant_collections
from app.services.redis_consumer import start_consumer, stop_consumer

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} đang khởi động...")
    logger.info(f"   Debug mode: {settings.debug}")
    logger.info(f"   Gemini API key: {'✓ đã cấu hình' if settings.gemini_api_key else '✗ THIẾU'}")

    # Khởi tạo Qdrant collection 'apartments' cho Agent 2
    logger.info("🗄️  Khởi tạo Qdrant collections...")
    init_qdrant_collections()

    # Khởi động background consumer (indexing listing.approved → Qdrant)
    logger.info("📡 Khởi động Redis Stream consumer...")
    start_consumer()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("🛑 Dừng Redis Stream consumer...")
    stop_consumer()
    logger.info("👋 Service đang tắt...")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI Agent kiểm duyệt, chuẩn hoá bài đăng cho thuê căn hộ (Agent 1) "
        "và Trợ lý Tìm kiếm Ngữ cảnh 24/7 (Agent 2 — Super Broker)"
    ),
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

# Agent 1 — Listing Verifier
app.include_router(listings_router)

# Agent 2 — Super Broker (Semantic Search & Booking)
app.include_router(broker_router)

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "agents": {
            "agent1": "POST /api/verify-listing",
            "agent2": "POST /api/search",
        },
    }