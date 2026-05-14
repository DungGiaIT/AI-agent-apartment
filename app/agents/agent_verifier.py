import logging
from typing import Any

import instructor
from openai import OpenAI

from app.core.config import settings
from app.schemas.schema_verifier import (
    listingStatus,
    listingVerifiedOutput,
    rawListingImageInput,
    rawListingInput,
    validationStatus,
)
from app.prompts.prompt_verifier import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


GEMINI_MODEL = "gemini-2.5-flash"
_MAX_IMAGES = 10


def build_instructor_client() -> instructor.Instructor:

    openai_client = OpenAI(
        api_key=settings.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    return instructor.from_openai(
        client=openai_client,
        mode=instructor.Mode.JSON,
    )


def image_url_for_api(img: rawListingImageInput) -> str:
    if img.url:
        return img.url.strip()
    b64 = (img.base64_data or "").strip()
    mt = (img.media_type or "image/jpeg").strip()
    return f"data:{mt};base64,{b64}"


def build_user_content_parts(
    text_block: str,
    images: list[rawListingImageInput],
) -> str | list[dict[str, Any]]:
    """OpenAI-compatible multimodal: text + image_url parts for Gemini."""
    slice_ = images[:_MAX_IMAGES]
    if not slice_:
        return text_block

    parts: list[dict[str, Any]] = [{"type": "text", "text": text_block}]
    for img in slice_:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": image_url_for_api(img)},
            }
        )
    return parts


def apply_image_post_processing(
    result: listingVerifiedOutput,
    images_in_request: list[rawListingImageInput],
) -> None:
    """Chuẩn hoá output ảnh + hậu kiểm nghiêm (watermark / chất lượng thấp)."""
    if not images_in_request:
        result.image_analyses = []
        return

    allowed_ids = {im.image_id for im in images_in_request}
    result.image_analyses = [
        row for row in result.image_analyses if row.image_id in allowed_ids
    ]

    v = result.validation
    for row in result.image_analyses:
        if row.watermark_or_branding_suspected:
            v.issues.append(
                f"Ảnh {row.image_id}: nghi ngờ watermark/logo bên thứ ba — "
                "vui lòng dùng ảnh chụp thật căn hộ, không che logo đối thủ."
            )
            v.score = max(0, v.score - 12)
        if row.duplicate_or_stock_photo_suspected:
            v.issues.append(
                f"Ảnh {row.image_id}: có dấu hiệu ảnh stock/catalogue — "
                "nên thay bằng ảnh thực tế để tăng tin cậy."
            )
            v.score = max(0, v.score - 8)
        if row.sharpness_score < 25:
            v.issues.append(
                f"Ảnh {row.image_id}: độ nét thấp ({row.sharpness_score}/100) — "
                "chụp lại hoặc tải bản gốc độ phân giải cao hơn."
            )
            v.score = max(0, v.score - 5)

    if v.score < 70:
        result.listing.status = listingStatus.Draft
        if v.status == validationStatus.Pass:
            v.status = validationStatus.Fail
        hint = (
            "Điểm chất lượng giảm do ảnh (watermark/stock/chất lượng thấp). "
            "Vui lòng cập nhật ảnh và gửi duyệt lại."
        )
        v.feedback_to_owner = (
            f"{v.feedback_to_owner}\n\n{hint}" if v.feedback_to_owner else hint
        )


def verify_listing(payload: rawListingInput) -> listingVerifiedOutput:
    """
    Sync function that calls the Gemini API via OpenAI compatible endpoint.
    Uses instructor to enforce structured output.
    """
    client = build_instructor_client()

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

    images = payload.images[:_MAX_IMAGES]
    image_manifest = ""
    if images:
        lines = [
            "ẢNH ĐÍNH KÈM (phân tích vision — giữ đúng image_id):",
            *[f"  - image_id={im.image_id}" for im in images],
            "",
            "Với MỖI image_id ở trên, trả về đúng một phần tử trong image_analyses "
            "(primary_tag, secondary_tags, brightness_score, sharpness_score, ...).",
        ]
        image_manifest = "\n".join(lines)

    user_text = f"""
Hãy phân tích và chuẩn hoá mô tả bất động sản sau đây:

---
{payload.rawText}
---
{db_info}

{image_manifest}

Trả về dữ liệu có cấu trúc theo đúng schema được yêu cầu.
Lưu ý đặc biệt:
- Mỗi tiện nghi phải có đúng 2 trường: amenities_name (string) và category (furniture/building/policy).
- Phát hiện các vấn đề (giá bất thường, v.v.) và thêm vào issues.
- image_tags_suggested: suy ra từ mô tả chữ (slug snake_case).
- image_analyses: chỉ điền khi có ảnh đính kèm trong request; khớp image_id.
""".strip()

    user_content = build_user_content_parts(user_text, images)

    logger.info(
        f"[Agent1] Bắt đầu xử lý — owner_id={payload.owner_id}, "
        f"input_length={len(payload.rawText)} ký tự, "
        f"images={len(images)}, "
        f"has_db_data={payload.db_apartment_data is not None}"
    )

    try:
        result: listingVerifiedOutput = client.chat.completions.create(
            model=GEMINI_MODEL,
            response_model=listingVerifiedOutput,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_retries=0,
        )

        apply_image_post_processing(result, images)

        logger.info(
            f"[Agent1] Hoàn tất — "
            f"status={result.listing.status.value}, "
            f"score={result.validation.score}/100, "
            f"amenities={len(result.apartment_meta.amenities)} items, "
            f"is_verified={result.validation.is_verified_by_db}, "
            f"issues={len(result.validation.issues)}, "
            f"image_rows={len(result.image_analyses)}, "
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