from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# INPUT — Yêu cầu từ Tenant / NestJS
# ─────────────────────────────────────────────

class ChatMessage(BaseModel):
    """Một tin nhắn trong lịch sử hội thoại."""
    role: Literal["user", "assistant"]
    content: str


class SearchQueryInput(BaseModel):
    """Payload gửi từ NestJS vào POST /api/search."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Câu hỏi tự nhiên của khách thuê hoặc văn bản giọng nói đã chuyển ngữ",
    )
    tenant_id: str = Field(..., description="ID của khách thuê để quản lý phiên hội thoại")
    conversation_history: List[ChatMessage] = Field(
        default=[],
        max_length=10,
        description="Lịch sử tối đa 5-10 câu hội thoại gần nhất để giữ ngữ cảnh",
    )
    audio_url: Optional[str] = Field(
        None,
        max_length=2048,
        description="URL audio nếu khách gửi tin nhắn thoại (mp3/wav/ogg)",
    )


# ─────────────────────────────────────────────
# INTERNAL — Kết quả phân tích ý định từ Gemini (Stage 1)
# ─────────────────────────────────────────────

class QueryIntentConstraints(BaseModel):
    """
    Kết quả trích xuất ràng buộc từ query của khách thuê.
    Dùng nội bộ để gọi Qdrant + build RAG prompt.
    """
    semantic_query: str = Field(
        ...,
        description="Câu truy vấn ngữ nghĩa sạch để embed (loại bỏ số điện thoại, số cụ thể không liên quan)",
    )
    max_price: Optional[float] = Field(
        None,
        gt=0,
        description="Ngân sách tối đa của khách (VND). VD: 8000000",
    )
    min_area: Optional[float] = Field(
        None,
        gt=0,
        description="Diện tích tối thiểu (m²). VD: 30",
    )
    pet_friendly: Optional[bool] = Field(
        None,
        description="True nếu khách cần cho nuôi thú cưng",
    )
    parking_required: Optional[bool] = Field(
        None,
        description="True nếu khách cần chỗ đậu xe",
    )
    preferred_district: Optional[str] = Field(
        None,
        description="Quận ưu tiên nếu khách đề cập (vd: 'Hải Châu', 'Sơn Trà')",
    )
    is_booking_request: bool = Field(
        default=False,
        description="True nếu khách đang xác nhận lịch xem nhà",
    )
    booking_listing_id: Optional[str] = Field(
        None,
        description="listing_id mà khách muốn đặt lịch (nếu có)",
    )
    booking_date: Optional[str] = Field(
        None,
        description="Ngày muốn xem nhà (YYYY-MM-DD) nếu khách đề cập",
    )
    booking_time: Optional[str] = Field(
        None,
        description="Giờ muốn xem nhà (HH:MM) nếu khách đề cập",
    )
    needs_clarification: bool = Field(
        default=False,
        description="True nếu query quá mơ hồ, cần hỏi thêm trước khi tìm kiếm",
    )


# ─────────────────────────────────────────────
# OUTPUT — Kết quả trả về cho NestJS / Tenant
# ─────────────────────────────────────────────

class RecommendedListing(BaseModel):
    """Thông tin một căn hộ được đề xuất."""
    listing_id: str = Field(..., description="ID của tin đăng khớp từ Qdrant")
    title: str = Field(..., description="Tiêu đề căn hộ")
    pricePerMonth: float = Field(..., description="Giá thuê mỗi tháng (VND)")
    imageUrl: Optional[str] = Field(None, description="Ảnh đại diện chính của căn hộ")
    roomNumber: str = Field(..., description="Mã số phòng")
    area: float = Field(..., description="Diện tích căn hộ (m²)")
    reason: str = Field(
        ...,
        description="Lập luận thuyết phục tại sao căn này hợp với nhu cầu và các ràng buộc của khách",
    )


class SearchResponseOutput(BaseModel):
    """Payload trả về sau khi Agent 2 xử lý xong."""
    bot_response: str = Field(
        ...,
        description="Câu trả lời phản hồi tự nhiên, thân thiện bằng tiếng Việt của Agent",
    )
    recommendations: List[RecommendedListing] = Field(
        default=[],
        max_length=3,
        description="Tối đa 3 căn hộ phù hợp nhất xếp theo độ tương đồng",
    )
    next_action: Literal["CONTINUE_CHAT", "PROPOSE_BOOKING", "EMIT_BOOKING_EVENT"] = Field(
        ...,
        description="Hành động tiếp theo hệ thống cần thực hiện",
    )
    booking_details: Optional[dict] = Field(
        None,
        description="Thông tin đặt lịch chốt xem phòng (listing_id, date, time) nếu có",
    )


class SearchBrokerResponse(BaseModel):
    """Wrapper response chuẩn cho route /api/search."""
    success: bool
    data: Optional[SearchResponseOutput] = None
    error: Optional[str] = None
