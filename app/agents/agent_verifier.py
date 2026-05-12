import logging
import instructor
from openai import OpenAI

from app.core.config import settings
from app.schemas.schema_verifier import (
    rawListingInput,
    listingVerifiedOutput,
)
from app.prompts.prompt_verifier import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


GEMINI_MODEL = "gemini-2.5-flash"

def _build_instructor_client() -> instructor.Instructor:

    openai_client = OpenAI(
        api_key=settings.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    return instructor.from_openai(
        client=openai_client,
        mode=instructor.Mode.JSON,
    )

def verify_listing(payload: rawListingInput) -> listingVerifiedOutput:
    """
    Sync function that calls the Gemini API via OpenAI compatible endpoint.
    Uses instructor to enforce structured output.
    """
    client = _build_instructor_client()

    # Build database info section if provided
    db_info = ""
    if payload.db_apartment_data:
        db_info = f"""

DỮ LIỆU TỪ DATABASE (để đối soát):
---
ID: {payload.db_apartment_data.get('id')}
Diện tích: {payload.db_apartment_data.get('area')} m²
Tầng: {payload.db_apartment_data.get('floor')}
Số phòng: {payload.db_apartment_data.get('room_number')}
Ghi chú: {payload.db_apartment_data.get('note')}
---

HƯỚNG DẪN: So sánh area (diện tích) và floor (tầng) được trích từ rawText với dữ liệu DB.
- Nếu khớp 100% → set is_verified_by_db=True, data_conflicts=[]
- Nếu có sai lệch → ghi vào data_conflicts, set is_verified_by_db=False
"""

    user_message = f"""
Hãy phân tích và chuẩn hoá mô tả bất động sản sau đây:

---
{payload.rawText}
---
{db_info}

Trả về dữ liệu có cấu trúc theo đúng schema được yêu cầu.
Lưu ý đặc biệt:
- mỗi tiện nghi trong apartment_meta.amenities phải có đúng 2 trường:
amenities_name (string) và category (furniture/building/policy)
- Phát hiện các vấn đề (giá bất thường, v.v.) và thêm vào issues
""".strip()

    logger.info(
        f"[Agent1] Bắt đầu xử lý — owner_id={payload.owner_id}, "
        f"input_length={len(payload.rawText)} ký tự, "
        f"has_db_data={payload.db_apartment_data is not None}"
    )

    try:
        result: listingVerifiedOutput = client.chat.completions.create(
            model=GEMINI_MODEL,
            response_model=listingVerifiedOutput,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_retries=0,
        )

        logger.info(
            f"[Agent1] Hoàn tất — "
            f"status={result.listing.status.value}, "
            f"score={result.validation.score}/100, "
            f"amenities={len(result.apartment_meta.amenities)} items, "
            f"is_verified={result.validation.is_verified_by_db}, "
            f"issues={len(result.validation.issues)}, "
            f"owner_id={payload.owner_id}"
        )

        return result
    except Exception as e:
        logger.error(
            f"[Agent1] API Error - {type(e).__name__}: {str(e)}\n"
            f"API Key status: {'***' if settings.gemini_api_key else 'NOT SET'}\n"
            f"Model: {GEMINI_MODEL}"
        )
        raise