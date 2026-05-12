import logging
from fastapi import APIRouter, HTTPException, status
from openai import RateLimitError, BadRequestError, PermissionDeniedError

from app.schemas.schema_verifier import rawListingInput, verifyListingResponse
from app.agents.agent_verifier import verify_listing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Agent 1 - Listing Verifier"])


@router.post(
    "/verify-listing",
    response_model=verifyListingResponse,
    status_code=status.HTTP_200_OK,
    summary="Kiểm duyệt và chuẩn hoá bài đăng từ chủ nhà",
    description="""
    **Agent 1 — Listing Verifier**

    Nhận mô tả thô từ chủ nhà → phân tích bằng Gemini AI → trả về:
    - Bài đăng đã chuẩn hoá (title, description, price)
    - Metadata căn hộ (diện tích, phòng ngủ, tiện nghi...)
    - Kết quả kiểm duyệt (Published / Draft + lý do)
    - Nhãn ảnh gợi ý cho Vision AI xử lý ở bước sau

    **Quy tắc tự động:**
    - `score >= 70` + có đủ giá/diện tích/quận → `status = Published`
    - Thiếu thông tin quan trọng → `status = Draft` + phản hồi cho chủ nhà
    """,
)
async def verify_listing_endpoint(payload: rawListingInput) -> verifyListingResponse:
    try:
        result = verify_listing(payload)

        return verifyListingResponse(
            success=True,
            data=result,
        )

    except PermissionDeniedError as e:
        logger.error(
            f"[verify_listing] Google API Permission Denied: {e}\n"
            "Solution: Check Google Cloud project, enable Gemini API, verify billing"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key không có quyền truy cập. Kiểm tra cấu hình Google Cloud.",
        )

    except BadRequestError as e:
        logger.error(f"[verify_listing] Google API BadRequest: {e}")
        error_msg = str(e)
        if "location is not supported" in error_msg.lower():
            detail = "API không hỗ trợ vị trí của bạn. Kiểm tra cấu hình VPN hoặc region."
        else:
            detail = f"Google API lỗi: {error_msg[:100]}"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )

    except ValueError as e:
        logger.error(f"[verify_listing] ValueError: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI không thể xử lý nội dung này: {str(e)}",
        )

    except RateLimitError:
        logger.error("[verify_listing] Rate limit exceeded")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Đã vượt quá giới hạn API, vui lòng thử lại sau vài phút.",
        )

    except Exception as e:
        logger.error(f"[verify_listing] Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi hệ thống, vui lòng thử lại sau.",
        )


@router.get("/health", summary="Kiểm tra service còn sống không")
async def health_check():
    return {"status": "ok", "service": "agent1-listing-verifier"}