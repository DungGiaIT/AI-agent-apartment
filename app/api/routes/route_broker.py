import logging

from fastapi import APIRouter, HTTPException, status
from openai import BadRequestError, PermissionDeniedError, RateLimitError

from app.agents.agent_broker import run_broker_agent
from app.schemas.schema_broker import SearchBrokerResponse, SearchQueryInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Agent 2 - Super Broker"])


@router.post(
    "/search",
    response_model=SearchBrokerResponse,
    status_code=status.HTTP_200_OK,
    summary="Tìm kiếm căn hộ bằng ngôn ngữ tự nhiên (Agent 2 — Super Broker)",
    description="""
**Agent 2 — Super Broker**

Nhận câu hỏi tự nhiên từ khách thuê (văn bản hoặc URL giọng nói) → phân tích ý định → tìm kiếm vector Qdrant → trả về:
- `bot_response`: Câu trả lời thân thiện bằng tiếng Việt.
- `recommendations`: Tối đa 3 căn hộ phù hợp nhất với lý giải thuyết phục.
- `next_action`: Hành động tiếp theo (`CONTINUE_CHAT` / `PROPOSE_BOOKING` / `EMIT_BOOKING_EVENT`).
- `booking_details`: Thông tin lịch xem nhà nếu khách đã xác nhận.

**Tính năng nổi bật:**
- Hỗ trợ hội thoại đa lượt (multi-turn) với context lịch sử.
- Phân tích giọng nói đa phương thức (multimodal audio) nếu truyền `audio_url`.
- Tự động nới lỏng ràng buộc tìm kiếm (Constraint Relaxation) khi không tìm thấy kết quả.
- Phát hiện và từ chối lịch hẹn xem nhà phi lý (3h sáng, ngày quá khứ).
    """,
)
async def search_endpoint(payload: SearchQueryInput) -> SearchBrokerResponse:
    try:
        result = run_broker_agent(payload)
        return SearchBrokerResponse(success=True, data=result)

    except PermissionDeniedError as e:
        logger.error(
            f"[search] Google API Permission Denied: {e}\n"
            "Solution: Check Google Cloud project, enable Gemini API, verify billing"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key không có quyền truy cập. Kiểm tra cấu hình Google Cloud.",
        )

    except BadRequestError as e:
        logger.error(f"[search] Google API BadRequest: {e}")
        error_msg = str(e)
        if "location is not supported" in error_msg.lower():
            detail = "API không hỗ trợ vị trí của bạn. Kiểm tra cấu hình VPN hoặc region."
        else:
            detail = f"Google API lỗi: {error_msg[:150]}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    except ValueError as e:
        logger.error(f"[search] ValueError: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI không thể xử lý nội dung này: {str(e)}",
        )

    except RateLimitError:
        logger.error("[search] Rate limit exceeded")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Đã vượt quá giới hạn API, vui lòng thử lại sau vài phút.",
        )

    except RuntimeError as e:
        logger.error(f"[search] RuntimeError: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dịch vụ tạm thời không khả dụng: {str(e)[:100]}",
        )

    except Exception as e:
        logger.error(f"[search] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi hệ thống, vui lòng thử lại sau.",
        )


@router.get("/search/health", summary="Kiểm tra Agent 2 còn sống không")
async def search_health():
    return {"status": "ok", "service": "agent2-super-broker"}
