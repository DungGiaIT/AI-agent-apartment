"""
Agent 2 — Super Broker: Core RAG Pipeline

Luồng xử lý 3 stage:
  Stage 1 — Intent Analysis  : Gemini phân tích query + audio → QueryIntentConstraints
  Stage 2 — Hybrid Search    : embed semantic_query → Qdrant search với hard filters
                               Nếu 0 kết quả → Relax Constraints → retry
  Stage 3 — RAG Synthesis    : Gemini tổng hợp SearchResponseOutput từ listings + context
"""

import logging
import time
from datetime import datetime
from typing import Optional

import httpx
import instructor
from openai import OpenAI

from app.core.config import settings
from app.core.redis_client import emit_event
from app.prompts.prompt_broker import INTENT_EXTRACTION_PROMPT, SYSTEM_INSTRUCTION
from app.schemas.schema_broker import (
    QueryIntentConstraints,
    SearchQueryInput,
    SearchResponseOutput,
)
from app.services.qdrant_service import get_embedding, search_apartments

logger = logging.getLogger(__name__)

# Model tốc độ cao nhất cho cả intent parsing và RAG synthesis
MODEL_NAME = "gemini-3.1-flash-lite"
_AUDIO_DOWNLOAD_TIMEOUT = 10.0  # giây
_MAX_HISTORY_TURNS = 5          # Giữ tối đa 5 turns gần nhất


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI-compat client (dùng cho instructor structured output)
# ─────────────────────────────────────────────────────────────────────────────

def _build_instructor_client() -> instructor.Instructor:
    openai_client = OpenAI(
        api_key=settings.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    return instructor.from_openai(client=openai_client, mode=instructor.Mode.JSON)


# ─────────────────────────────────────────────────────────────────────────────
# Audio Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_audio_bytes(audio_url: str) -> Optional[bytes]:
    """Tải audio từ URL. Trả về None nếu thất bại."""
    if not audio_url or not audio_url.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=_AUDIO_DOWNLOAD_TIMEOUT) as client:
            resp = client.get(audio_url)
            resp.raise_for_status()
            logger.info(f"Downloaded audio {len(resp.content)} bytes from {audio_url}")
            return resp.content
    except Exception as e:
        logger.warning(f"Failed to download audio from {audio_url}: {e}")
        return None


def _detect_audio_mime(url: str) -> str:
    """Phát hiện MIME type từ đuôi file URL."""
    url_lower = url.lower()
    if ".ogg" in url_lower:
        return "audio/ogg"
    if ".wav" in url_lower:
        return "audio/wav"
    return "audio/mpeg"  # mặc định mp3


# ─────────────────────────────────────────────────────────────────────────────
# History Formatter
# ─────────────────────────────────────────────────────────────────────────────

def _format_history(payload: SearchQueryInput) -> str:
    """Định dạng lịch sử hội thoại thành chuỗi text ngắn gọn."""
    history = payload.conversation_history[-_MAX_HISTORY_TURNS:]
    if not history:
        return ""
    lines = []
    for msg in history:
        role_label = "Khách" if msg.role == "user" else "Agent"
        lines.append(f"{role_label}: {msg.content}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Intent Extraction
# ─────────────────────────────────────────────────────────────────────────────

def _stage1_extract_intent(
    payload: SearchQueryInput,
    client: instructor.Instructor,
) -> QueryIntentConstraints:
    """
    Gọi Gemini để phân tích query + lịch sử → QueryIntentConstraints.
    Nếu có audio_url, tải audio và gửi kèm như multimodal input.
    """
    history_text = _format_history(payload)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    user_content_text = (
        f"Thời gian hiện tại: {current_time}\n\n"
        f"Lịch sử hội thoại:\n{history_text}\n\n" if history_text else
        f"Thời gian hiện tại: {current_time}\n\n"
    ) + f"Tin nhắn mới nhất của khách: {payload.query}"

    # Multimodal: thêm audio nếu có
    user_content: str | list
    audio_bytes = None
    if payload.audio_url:
        audio_bytes = _fetch_audio_bytes(payload.audio_url)

    if audio_bytes:
        import base64
        mime = _detect_audio_mime(payload.audio_url)
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        user_content = [
            {"type": "text", "text": user_content_text},
            {
                "type": "imageUrl",  # Gemini multimodal via OpenAI compat uses imageUrl for all media
                "imageUrl": {"url": f"data:{mime};base64,{b64_audio}"},
            },
        ]
        logger.info(f"[Stage1] Sending audio ({mime}, {len(audio_bytes)} bytes) to Gemini.")
    else:
        user_content = user_content_text

    constraints = client.chat.completions.create(
        model=MODEL_NAME,
        response_model=QueryIntentConstraints,
        messages=[
            {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_retries=2,
    )
    logger.info(
        f"[Stage1] Intent extracted — "
        f"semantic_query='{constraints.semantic_query[:60]}...', "
        f"max_price={constraints.max_price}, "
        f"min_area={constraints.min_area}, "
        f"is_booking={constraints.is_booking_request}, "
        f"needs_clarification={constraints.needs_clarification}"
    )
    return constraints


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Hybrid Vector Search (with Constraint Relaxation fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _stage2_search(constraints: QueryIntentConstraints) -> list[dict]:
    """
    Embed semantic_query → tìm kiếm Qdrant với hard filters.
    Nếu 0 kết quả → nới lỏng filter price/area → retry 1 lần.
    """
    vector = get_embedding(constraints.semantic_query)

    # Lần 1: tìm kiếm với đầy đủ constraints
    results = search_apartments(
        vector=vector,
        max_price=constraints.max_price,
        min_area=constraints.min_area,
        top_k=3,
    )

    if results:
        logger.info(f"[Stage2] Found {len(results)} listings with full constraints.")
        return results

    # Lần 2: Relax constraints nếu không tìm thấy
    logger.info("[Stage2] Zero results with full constraints — relaxing price/area filters.")
    relaxed_price = (constraints.max_price * 1.15) if constraints.max_price else None  # +15%
    relaxed_area = (constraints.min_area * 0.8) if constraints.min_area else None       # -20%

    results = search_apartments(
        vector=vector,
        max_price=relaxed_price,
        min_area=relaxed_area,
        top_k=3,
    )
    logger.info(f"[Stage2] Relaxed search found {len(results)} listings.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — RAG Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def _build_rag_prompt(
    payload: SearchQueryInput,
    constraints: QueryIntentConstraints,
    listings: list[dict],
) -> str:
    """Xây dựng user prompt cho lần gọi RAG cuối."""
    history_text = _format_history(payload)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    listings_section = ""
    if listings:
        listing_items = []
        for i, lst in enumerate(listings, 1):
            amenities_str = ", ".join(lst.get("amenities", []))
            listing_items.append(
                f"--- Căn {i} ---\n"
                f"listing_id: {lst.get('listing_id', '')}\n"
                f"Tiêu đề: {lst.get('title', '')}\n"
                f"Phòng số: {lst.get('roomNumber', '')}\n"
                f"Diện tích: {lst.get('area', 0)} m²\n"
                f"Giá thuê: {lst.get('pricePerMonth', 0):,.0f} VND/tháng\n"
                f"Tiện ích: {amenities_str or 'Không có thông tin'}\n"
                f"Mô tả: {lst.get('description', '')[:300]}..."
            )
        listings_section = (
            f"\n\nDANH SÁCH CĂN HỘ GỢI Ý TỪ HỆ THỐNG (dùng để tư vấn):\n"
            + "\n".join(listing_items)
        )
    else:
        listings_section = "\n\nKHÔNG TÌM THẤY CĂN HỘ NÀO PHÙ HỢP trong cơ sở dữ liệu."

    booking_context = ""
    if constraints.is_booking_request and constraints.booking_listing_id:
        booking_context = (
            f"\n\nNGỮ CẢNH ĐẶT LỊCH: Khách đang xác nhận lịch xem nhà.\n"
            f"  - listing_id: {constraints.booking_listing_id}\n"
            f"  - Ngày: {constraints.booking_date or 'Chưa xác định'}\n"
            f"  - Giờ: {constraints.booking_time or 'Chưa xác định'}\n"
            f"Quy tắc: Giờ hợp lệ là 8h00–20h00. Ngày phải sau {current_time.split()[0]}."
        )

    return (
        f"Thời gian hiện tại: {current_time}\n"
        f"Tenant ID: {payload.tenant_id}\n"
        f"\nLịch sử hội thoại:\n{history_text}\n" if history_text else
        f"Thời gian hiện tại: {current_time}\n"
        f"Tenant ID: {payload.tenant_id}\n"
    ) + (
        f"\nTin nhắn hiện tại của khách: {payload.query}"
        f"{listings_section}"
        f"{booking_context}"
        f"\n\nYêu cầu: Soạn phản hồi hoàn hảo bằng tiếng Việt theo format JSON SearchResponseOutput đã định nghĩa."
    )


def _stage3_rag_synthesis(
    payload: SearchQueryInput,
    constraints: QueryIntentConstraints,
    listings: list[dict],
    client: instructor.Instructor,
) -> SearchResponseOutput:
    """
    Gọi Gemini với SYSTEM_INSTRUCTION + context đầy đủ → SearchResponseOutput.
    """
    # Build RAG prompt  
    history_text = _format_history(payload)
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    listings_section = ""
    if listings:
        listing_items = []
        for i, lst in enumerate(listings, 1):
            amenities_str = ", ".join(lst.get("amenities", []))
            listing_items.append(
                f"--- Căn {i} ---\n"
                f"listing_id: {lst.get('listing_id', '')}\n"
                f"Tiêu đề: {lst.get('title', '')}\n"
                f"Phòng số: {lst.get('roomNumber', '')}\n"
                f"Diện tích: {lst.get('area', 0)} m²\n"
                f"Giá thuê: {lst.get('pricePerMonth', 0):,.0f} VND/tháng\n"
                f"Tiện ích: {amenities_str or 'Không có'}\n"
                f"Mô tả: {lst.get('description', '')[:300]}"
            )
        listings_section = "\n\nCĂN HỘ GỢI Ý:\n" + "\n".join(listing_items)
    else:
        listings_section = "\n\nKHÔNG TÌM THẤY căn hộ khớp trong database."

    booking_context = ""
    if constraints.is_booking_request and constraints.booking_listing_id:
        booking_context = (
            f"\n\nĐẶT LỊCH: listing={constraints.booking_listing_id}, "
            f"ngày={constraints.booking_date}, giờ={constraints.booking_time}. "
            f"Giờ hợp lệ: 8h00–20h00."
        )

    user_prompt = (
        f"Thời gian: {current_time}\n"
        + (f"Lịch sử:\n{history_text}\n\n" if history_text else "")
        + f"Khách hỏi: {payload.query}"
        + listings_section
        + booking_context
    )

    response = client.chat.completions.create(
        model=MODEL_NAME,
        response_model=SearchResponseOutput,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_prompt},
        ],
        max_retries=2,
    )

    logger.info(
        f"[Stage3] RAG synthesis done — "
        f"next_action={response.next_action}, "
        f"recommendations={len(response.recommendations)}"
    )
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Booking Event Emitter
# ─────────────────────────────────────────────────────────────────────────────

def _emit_booking_event(tenant_id: str, result: SearchResponseOutput) -> None:
    """Phát sự kiện `appointment.requested` lên Redis Stream nếu cần."""
    if result.next_action != "EMIT_BOOKING_EVENT":
        return

    booking = result.booking_details or {}
    event_payload = {
        "tenant_id": tenant_id,
        "listing_id": booking.get("listing_id", ""),
        "date": booking.get("date", ""),
        "time": booking.get("time", ""),
        "bot_response_snippet": result.bot_response[:200],
    }
    success = emit_event("appointment.requested", event_payload)
    if success:
        logger.info(
            f"[Booking] Emitted appointment.requested for tenant={tenant_id}, "
            f"listing={booking.get('listing_id')}"
        )
    else:
        logger.error(f"[Booking] Failed to emit appointment.requested for tenant={tenant_id}")


# ─────────────────────────────────────────────────────────────────────────────
# Public Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def run_broker_agent(payload: SearchQueryInput) -> SearchResponseOutput:
    """
    Điểm vào chính của Agent 2. Điều phối toàn bộ 3-stage pipeline.

    Args:
        payload: SearchQueryInput từ NestJS.

    Returns:
        SearchResponseOutput với bot_response, recommendations, next_action.

    Raises:
        Exception: Bất kỳ lỗi nghiêm trọng nào từ Gemini/Qdrant.
    """
    t0 = time.time()
    client = _build_instructor_client()

    logger.info(
        f"[BrokerAgent] Bắt đầu xử lý — tenant_id={payload.tenant_id}, "
        f"query='{payload.query[:80]}', "
        f"history={len(payload.conversation_history)} turns, "
        f"has_audio={bool(payload.audio_url)}"
    )

    # ── Stage 1: Intent Analysis ──────────────────────────────────────────────
    constraints = _stage1_extract_intent(payload, client)

    # ── Stage 2: Hybrid Search ────────────────────────────────────────────────
    # Nếu cần clarification → trả về response yêu cầu làm rõ mà không search
    if constraints.needs_clarification:
        logger.info("[BrokerAgent] needs_clarification=True — skipping search, asking clarification.")
        return SearchResponseOutput(
            bot_response=(
                "Dạ, để mình tìm căn hộ chính xác nhất cho bạn, "
                "bạn có thể cho mình biết thêm một số thông tin không ạ?\n"
                "- Ngân sách thuê tầm bao nhiêu triệu/tháng?\n"
                "- Cần diện tích khoảng bao nhiêu m²?\n"
                "- Ưu tiên quận nào ở Đà Nẵng? 😊"
            ),
            recommendations=[],
            next_action="CONTINUE_CHAT",
        )

    listings: list[dict] = []
    if not constraints.is_booking_request:
        listings = _stage2_search(constraints)

    # ── Stage 3: RAG Synthesis ────────────────────────────────────────────────
    result = _stage3_rag_synthesis(payload, constraints, listings, client)

    # ── Booking Event ─────────────────────────────────────────────────────────
    _emit_booking_event(payload.tenant_id, result)

    elapsed = time.time() - t0
    logger.info(
        f"[BrokerAgent] Hoàn tất trong {elapsed:.2f}s — "
        f"next_action={result.next_action}, "
        f"listings_found={len(listings)}, "
        f"recommendations={len(result.recommendations)}"
    )

    return result
