import logging
import base64
import httpx
import time
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
    listingCoreOutput,
    apartmentMetaOutput,
    listingImageAnalysis,
    validationOutput,
)
import concurrent.futures
from pydantic import BaseModel, Field

class ContentTaskOutput(BaseModel):
    listing: listingCoreOutput

class MetaTaskOutput(BaseModel):
    apartment_meta: apartmentMetaOutput
    image_tags_suggested: list[str] = Field(default_factory=list)
    image_analyses: list[listingImageAnalysis] = Field(default_factory=list)
    validation: validationOutput

from app.prompts.prompt_verifier import (
    SYSTEM_PROMPT_CONTENT,
    SYSTEM_PROMPT_META_AND_VISION,
)

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.1-flash-lite"
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


def imageUrl_for_api(img: rawListingImageInput) -> str:
    b64_val = (img.base64_data or "").strip()
    url_val = (img.url or "").strip()

    # 1. Ưu tiên base64 nếu nó có giá trị thực (không phải chuỗi "string" mặc định của tool test)
    if b64_val and b64_val.lower() != "string":
        mt = (img.media_type or "image/jpg").strip()
        return f"data:{mt};base64,{b64_val}"
        
    # 2. Tiếp theo là URL (nếu không phải chuỗi "string" và bắt đầu bằng http)
    if url_val and url_val.lower() != "string" and url_val.startswith("http"):
        try:
            start_t = time.time()
            with httpx.Client() as client:
                response = client.get(url_val, timeout=10.0)
                response.raise_for_status()
                b64 = base64.b64encode(response.content).decode("utf-8")
                mt = response.headers.get("Content-Type", "image/jpg")
                logger.info(f"Đã tải ảnh {url_val} thành công trong {time.time() - start_t:.2f}s")
                return f"data:{mt};base64,{b64}"
        except Exception as e:
            logger.warning(f"Failed to fetch image {url_val}: {e}")
            raise ValueError(f"Không thể tải ảnh từ URL: {url_val}")
            
    raise ValueError("Thiếu dữ liệu ảnh hợp lệ (url hoặc base64_data).")


def build_user_content_parts(
    text_block: str,
    images: list[rawListingImageInput],
) -> str | list[dict[str, Any]]:
    """OpenAI-compatible multimodal: text + imageUrl parts for Gemini."""
    slice_ = images[:_MAX_IMAGES]
    if not slice_:
        return text_block

    parts: list[dict[str, Any]] = [{"type": "text", "text": text_block}]
    for img in slice_:
        parts.append(
            {
                "type": "imageUrl",
                "imageUrl": {"url": imageUrl_for_api(img)},
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
Số phòng: {payload.db_apartment_data.get('roomNumber')}
Ghi chú: {payload.db_apartment_data.get('note')}
---

HƯỚNG DẪN: So sánh area (diện tích) và floor (tầng) được trích từ rawText với dữ liệu DB.
- Nếu khớp 100% → set is_verified_by_db=True, data_conflicts=[]
- Nếu có sai lệch → ghi vào data_conflicts, set is_verified_by_db=False
"""

    images = payload.images[:_MAX_IMAGES]
    logger.info(
        f"[Agent1] Bắt đầu xử lý song song (Multi-thread) — owner_id={payload.owner_id}, "
        f"input_length={len(payload.rawText)} ký tự, "
        f"images={len(images)}, "
        f"has_db_data={payload.db_apartment_data is not None}"
    )

    try:
        t0 = time.time()
        
        def run_task_content():
            text_prompt = f"""
Hãy chuẩn hoá mô tả bất động sản sau đây để viết tiêu đề và mô tả:
---
{payload.rawText}
---
Nhiệm vụ: Tập trung sinh nội dung Title, Description 5 đoạn và Price. BỎ QUA phân tích ảnh và đối soát database.
"""
            content_parts = build_user_content_parts(text_prompt, [])
            return client.chat.completions.create(
                model=MODEL_NAME,
                response_model=ContentTaskOutput,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_CONTENT},
                    {"role": "user", "content": content_parts},
                ],
                max_retries=2,
            )

        def run_task_meta_and_vision():
            text_prompt = f"""
Hãy phân tích và đối soát mô tả bất động sản sau đây:
---
{payload.rawText}
---
{db_info}

Nhiệm vụ: Tập trung trích xuất thông số, tiện ích (amenities), phân tích ảnh và đối soát dữ liệu (validation). BỎ QUA việc sinh Title và Description.
"""
            content_parts = build_user_content_parts(text_prompt, images)
            return client.chat.completions.create(
                model=MODEL_NAME,
                response_model=MetaTaskOutput,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_META_AND_VISION},
                    {"role": "user", "content": content_parts},
                ],
                max_retries=2,
            )

        # Sử dụng 2 workers chạy song song luồng Content và luồng Meta+Vision (an toàn Rate Limit)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_content = executor.submit(run_task_content)
            future_meta = executor.submit(run_task_meta_and_vision)

            res_content = future_content.result()
            res_meta = future_meta.result()

        # Gộp 2 luồng kết quả lại thành 1 output như cũ
        result = listingVerifiedOutput(
            listing=res_content.listing,
            apartment_meta=res_meta.apartment_meta,
            image_tags_suggested=res_meta.image_tags_suggested,
            image_analyses=res_meta.image_analyses,
            validation=res_meta.validation
        )
        
        t1 = time.time()

        apply_image_post_processing(result, images)

        logger.info(
            f"[Agent1] Hoàn tất dùng model {MODEL_NAME} (Parallel) trong {t1 - t0:.2f}s — "
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
            f"Model: {MODEL_NAME}"
        )
        raise