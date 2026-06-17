import logging
import uuid
from typing import Optional

import httpx

# pyrefly: ignore [missing-import]
from qdrant_client import QdrantClient
# pyrefly: ignore [missing-import]
from qdrant_client.http import models
from app.core.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "apartments"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 3072  # Dimension for gemini-embedding-001 (gemini-embedding-001 deprecated Jan 2026)

# ─────────────────────────────────────────────────────────────────────────────
# Qdrant Client Initialization
# ─────────────────────────────────────────────────────────────────────────────

try:
    qdrant_client = QdrantClient(url=settings.qdrant_url)
    logger.info(f"Connected to Qdrant at {settings.qdrant_url}")
except Exception as e:
    logger.error(f"Failed to connect to Qdrant: {e}")
    qdrant_client = None


def init_qdrant_collections():
    """
    Tạo hoặc kiểm tra collection 'apartments'.
    Nếu collection tồn tại nhưng sai dimension → xoá và tạo lại.
    """
    if not qdrant_client:
        logger.warning("Qdrant client not available — skipping collection init.")
        return

    try:
        collections = qdrant_client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)

        if exists:
            # Kiểm tra dimension hiện tại
            info = qdrant_client.get_collection(COLLECTION_NAME)
            current_size = info.config.params.vectors.size
            if current_size != EMBEDDING_DIMENSION:
                logger.warning(
                    f"Collection '{COLLECTION_NAME}' has dimension {current_size}, "
                    f"expected {EMBEDDING_DIMENSION}. Recreating..."
                )
                qdrant_client.delete_collection(COLLECTION_NAME)
                exists = False
            else:
                logger.info(f"Collection '{COLLECTION_NAME}' already exists with correct dimension {current_size}.")

        if not exists:
            logger.info(f"Creating Qdrant collection: '{COLLECTION_NAME}' (dim={EMBEDDING_DIMENSION})")
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Collection '{COLLECTION_NAME}' created successfully.")
    except Exception as e:
        logger.error(f"Error initializing Qdrant collection: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# Embeddings Generation — Google GenAI REST API (gemini-embedding-001)
# ─────────────────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    """
    Gọi Google GenAI Embeddings API để tạo vector cho text.
    Sử dụng REST API trực tiếp để đảm bảo tương thích tốt nhất.

    Args:
        text: Văn bản cần embed.

    Returns:
        list[float]: Vector embedding 768 chiều.

    Raises:
        RuntimeError: Nếu API call thất bại.
    """
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY chưa được cấu hình.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{EMBEDDING_MODEL}:embedContent?key={settings.gemini_api_key}"
    )
    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": text}]
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data["embedding"]["values"]
            logger.debug(f"Generated embedding with {len(embedding)} dimensions for text[:80]='{text[:80]}'")
            return embedding
    except httpx.HTTPStatusError as e:
        logger.error(f"Embedding API HTTP error {e.response.status_code}: {e.response.text[:200]}")
        raise RuntimeError(f"Embedding API lỗi: {e.response.status_code}") from e
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise RuntimeError(f"Không thể tạo embedding: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Upsert — Index một căn hộ vào Qdrant
# ─────────────────────────────────────────────────────────────────────────────

def upsert_apartment_vector(listing_data: dict) -> bool:
    """
    Index dữ liệu căn hộ vào Qdrant collection 'apartments'.
    Sử dụng UUID deterministic từ listing_id để đảm bảo idempotency.

    Args:
        listing_data: dict chứa các trường:
            - listing_id (str, required)
            - title (str)
            - description (str)
            - pricePerMonth (float)
            - roomNumber (str)
            - area (float)
            - amenities (list[str], optional)
            - search_vector_text (str, optional) — nếu có, dùng để embed thay vì tự build

    Returns:
        bool: True nếu thành công, False nếu thất bại.
    """
    if not qdrant_client:
        logger.error("Qdrant client not available — cannot upsert.")
        return False

    listing_id = listing_data.get("listing_id", "")
    if not listing_id:
        logger.error("upsert_apartment_vector: listing_id is required.")
        return False

    # Build search_vector_text nếu không được cung cấp
    search_text = listing_data.get("search_vector_text") or _build_search_text(listing_data)

    try:
        vector = get_embedding(search_text)
    except Exception as e:
        logger.error(f"Failed to generate embedding for listing {listing_id}: {e}")
        return False

    # Tạo UUID deterministic từ listing_id (namespace UUID5)
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"apartment-{listing_id}"))

    payload = {
        "listing_id": listing_id,
        "title": listing_data.get("title", ""),
        "description": listing_data.get("description", ""),
        "pricePerMonth": float(listing_data.get("price", listing_data.get("pricePerMonth", 0)) or 0),
        "roomNumber": str(listing_data.get("roomNumber", "")),
        "area": float(listing_data.get("area", 0) or 0),
        "amenities": listing_data.get("amenities", []),
    }

    try:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )
        logger.info(f"Upserted listing {listing_id} (point_id={point_id}) into Qdrant.")
        return True
    except Exception as e:
        logger.error(f"Qdrant upsert failed for listing {listing_id}: {e}")
        return False


def _build_search_text(listing_data: dict) -> str:
    """Xây dựng văn bản mô tả tổng hợp để embed từ các trường của listing."""
    amenities_str = ", ".join(listing_data.get("amenities", []))
    return (
        f"Tiêu đề: {listing_data.get('title', '')}. "
        f"Mô tả: {listing_data.get('description', '')}. "
        f"Phòng số: {listing_data.get('roomNumber', '')}, "
        f"diện tích {listing_data.get('area', '')} m2. "
        f"Giá: {listing_data.get('price', listing_data.get('pricePerMonth', ''))} VND/tháng. "
        f"Tiện ích: {amenities_str}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Search — Tìm kiếm vector + filter cứng
# ─────────────────────────────────────────────────────────────────────────────

def search_apartments(
    vector: list[float],
    max_price: Optional[float] = None,
    min_area: Optional[float] = None,
    top_k: int = 3,
) -> list[dict]:
    """
    Tìm kiếm căn hộ trong Qdrant bằng vector similarity + hard filters.

    Args:
        vector: Query embedding vector.
        max_price: Ngân sách tối đa (VND). None = không lọc giá.
        min_area: Diện tích tối thiểu (m²). None = không lọc diện tích.
        top_k: Số lượng kết quả tối đa.

    Returns:
        list[dict]: Danh sách payload của các căn hộ khớp, sắp xếp theo score giảm dần.
    """
    if not qdrant_client:
        logger.error("Qdrant client not available — cannot search.")
        return []

    # Xây dựng filter conditions
    must_conditions = []

    if max_price is not None:
        must_conditions.append(
            models.FieldCondition(
                key="pricePerMonth",
                range=models.Range(lte=max_price),
            )
        )

    if min_area is not None:
        must_conditions.append(
            models.FieldCondition(
                key="area",
                range=models.Range(gte=min_area),
            )
        )

    query_filter = models.Filter(must=must_conditions) if must_conditions else None

    try:
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        logger.info(
            f"Qdrant search returned {len(results)} results "
            f"(max_price={max_price}, min_area={min_area})"
        )
        return [hit.payload for hit in results]
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}")
        return []
