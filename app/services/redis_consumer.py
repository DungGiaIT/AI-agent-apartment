"""
Redis Consumer — Background worker tiêu thụ sự kiện `listing.approved` từ Redis Stream.

Luồng hoạt động:
1. Khởi động → đọc từ ID `0-0` để đồng bộ toàn bộ lịch sử đã duyệt vào Qdrant.
2. Sau khi catch-up xong → poll tin nhắn mới liên tục với blocking read (XREAD BLOCK).
3. Mỗi message → extract payload → gọi upsert_apartment_vector() → ACK.

Consumer này chạy trong một daemon Thread, được khởi động trong lifespan của FastAPI.
"""

import json
import logging
import threading
import time
from typing import Optional

from app.core.redis_client import redis_client
from app.services.qdrant_service import upsert_apartment_vector

logger = logging.getLogger(__name__)

STREAM_NAME = "listing.approved"
CONSUMER_GROUP = "fastapi-broker-indexer"
CONSUMER_NAME = "worker-1"
_BLOCK_MS = 5000  # Blocking read timeout (ms)
_RETRY_SLEEP = 10  # Giây nghỉ khi gặp lỗi kết nối


# ─────────────────────────────────────────────────────────────────────────────
# Payload Parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_stream_message(fields: dict, msg_id: str = "") -> Optional[dict]:
    """
    Chuyển đổi raw Redis Stream fields sang dict có cấu trúc để upsert vào Qdrant.
    Tất cả giá trị trong Redis stream đều là string, cần deserialize.

    Args:
        fields: Các trường dữ liệu từ Redis Stream message.
        msg_id: Stream message ID (dùng làm fallback listing_id khi không có).
    """
    try:
        # Parse metadata nếu là JSON string
        raw_metadata = fields.get("metadata", "{}")
        try:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        except json.JSONDecodeError:
            metadata = {}

        # Lấy listing_id theo thứ tự ưu tiên:
        # 1. Trường listing_id trực tiếp (NestJS gửi)
        # 2. Từ metadata JSON
        # 3. Ghép từ owner_id + title hash (Agent 1 không gửi listing_id)
        # 4. Fallback dùng Redis msg_id để đảm bảo idempotency
        owner_id = fields.get("owner_id", "")
        listing_id = (
            fields.get("listing_id")
            or metadata.get("listing_id")
            or metadata.get("data", {}).get("listing", {}).get("id")
        )
        if not listing_id:
            # Tạo ID ổn định từ owner_id + title để tránh duplicate khi index lại
            title = fields.get("title", "")
            if owner_id and title:
                import hashlib
                listing_id = hashlib.md5(f"{owner_id}:{title}".encode()).hexdigest()[:16]
                logger.debug(f"Generated listing_id from owner+title hash: {listing_id}")
            else:
                # Dùng msg_id như last resort
                listing_id = msg_id.replace("-", "_")
                logger.debug(f"Using msg_id as listing_id: {listing_id}")

        # Lấy amenities từ metadata nếu có
        amenities: list[str] = []
        if metadata:
            apt_meta = metadata.get("apartment_meta") or metadata.get("data", {}).get("apartment_meta", {})
            if apt_meta and isinstance(apt_meta, dict):
                raw_amenities = apt_meta.get("amenities", [])
                amenities = [
                    a.get("amenities_name", "") if isinstance(a, dict) else str(a)
                    for a in raw_amenities
                ]

        listing_data = {
            "listing_id": listing_id,
            "title": fields.get("title", ""),
            "description": _extract_description(metadata, fields),
            "price": _safe_float(fields.get("price", 0)),
            "area": _safe_float(fields.get("area", 0)),
            "roomNumber": fields.get("roomNumber", ""),
            "amenities": amenities,
        }
        return listing_data
    except Exception as e:
        logger.error(f"Failed to parse stream message fields: {e} — fields={fields}")
        return None


def _extract_description(metadata: dict, fields: dict) -> str:
    """Cố gắng lấy description từ nhiều nguồn."""
    # 1. Từ metadata.data.listing.description (nếu NestJS gửi model_dump_json đầy đủ)
    if metadata:
        listing_obj = metadata.get("listing") or metadata.get("data", {}).get("listing", {})
        if isinstance(listing_obj, dict):
            desc = listing_obj.get("description", "")
            if desc:
                return desc

    # 2. Từ field trực tiếp
    return fields.get("description", "")


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Consumer Group Setup
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_consumer_group():
    """Tạo consumer group nếu chưa tồn tại."""
    if not redis_client:
        return False
    try:
        redis_client.xgroup_create(
            name=STREAM_NAME,
            groupname=CONSUMER_GROUP,
            id="0",          # Bắt đầu từ đầu stream
            mkstream=True,   # Tạo stream nếu chưa có
        )
        logger.info(f"Consumer group '{CONSUMER_GROUP}' created for stream '{STREAM_NAME}'.")
        return True
    except Exception as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group '{CONSUMER_GROUP}' already exists.")
            return True
        logger.error(f"Failed to create consumer group: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main Worker Loop
# ─────────────────────────────────────────────────────────────────────────────

def _process_messages(messages: list) -> int:
    """Xử lý một batch messages từ XREADGROUP. Trả về số lượng processed."""
    count = 0
    for stream, entries in messages:
        for msg_id, fields in entries:
            try:
                listing_data = _parse_stream_message(fields, msg_id=msg_id)
                if listing_data and listing_data.get("listing_id"):
                    success = upsert_apartment_vector(listing_data)
                    if success:
                        # ACK message sau khi xử lý thành công
                        redis_client.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
                        logger.info(
                            f"[Consumer] Indexed listing '{listing_data['listing_id']}' "
                            f"from msg {msg_id}"
                        )
                        count += 1
                    else:
                        logger.warning(
                            f"[Consumer] Upsert failed for msg {msg_id}, "
                            f"listing_id='{listing_data.get('listing_id')}' — will retry later."
                        )
                else:
                    logger.warning(
                        f"[Consumer] Skipping msg {msg_id}: missing listing_id. fields={fields}"
                    )
                    # ACK để không bị stuck, nhưng log warning
                    redis_client.xack(STREAM_NAME, CONSUMER_GROUP, msg_id)
            except Exception as e:
                logger.error(f"[Consumer] Error processing msg {msg_id}: {e}", exc_info=True)
    return count


def _consumer_loop(stop_event: threading.Event):
    """Vòng lặp chính của consumer worker."""
    logger.info(f"[Consumer] Starting background indexer for stream '{STREAM_NAME}'")

    if not redis_client:
        logger.error("[Consumer] Redis client is not available. Worker will not start.")
        return

    # Khởi tạo consumer group
    while not stop_event.is_set():
        if _ensure_consumer_group():
            break
        logger.warning("[Consumer] Retrying consumer group creation in 10s...")
        stop_event.wait(timeout=_RETRY_SLEEP)

    if stop_event.is_set():
        return

    logger.info("[Consumer] Consumer group ready. Starting message polling...")

    # Phase 1: Catch-up — đọc pending messages (chưa ACK từ lần chạy trước)
    logger.info("[Consumer] Phase 1: Catching up pending messages (id='0')...")
    while not stop_event.is_set():
        try:
            pending = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_NAME: "0"},  # "0" = đọc tất cả pending
                count=50,
            )
            if not pending or all(len(entries) == 0 for _, entries in pending):
                logger.info("[Consumer] Phase 1 complete. No more pending messages.")
                break
            processed = _process_messages(pending)
            logger.info(f"[Consumer] Phase 1: Processed {processed} pending messages.")
        except Exception as e:
            logger.error(f"[Consumer] Phase 1 error: {e}")
            stop_event.wait(timeout=_RETRY_SLEEP)
            break

    # Phase 2: Real-time polling — đọc messages mới
    logger.info("[Consumer] Phase 2: Polling for new messages (id='>')...")
    while not stop_event.is_set():
        try:
            messages = redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_NAME: ">"},  # ">" = chỉ messages chưa được deliver
                count=10,
                block=_BLOCK_MS,  # Blocking read
            )
            if messages:
                processed = _process_messages(messages)
                if processed > 0:
                    logger.debug(f"[Consumer] Processed {processed} new messages.")
        except Exception as e:
            logger.error(f"[Consumer] Phase 2 polling error: {e}", exc_info=True)
            stop_event.wait(timeout=_RETRY_SLEEP)

    logger.info("[Consumer] Worker stopped gracefully.")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Khởi động và dừng consumer thread
# ─────────────────────────────────────────────────────────────────────────────

_stop_event: Optional[threading.Event] = None
_worker_thread: Optional[threading.Thread] = None


def start_consumer():
    """Khởi động background consumer thread. Gọi trong FastAPI lifespan startup."""
    global _stop_event, _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        logger.warning("[Consumer] Worker thread is already running.")
        return

    _stop_event = threading.Event()
    _worker_thread = threading.Thread(
        target=_consumer_loop,
        args=(_stop_event,),
        daemon=True,  # Tự động dừng khi main process kết thúc
        name="listing-approved-consumer",
    )
    _worker_thread.start()
    logger.info("[Consumer] Background indexer thread started.")


def stop_consumer():
    """Dừng consumer thread. Gọi trong FastAPI lifespan shutdown."""
    global _stop_event, _worker_thread

    if _stop_event:
        _stop_event.set()

    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=15)
        logger.info("[Consumer] Background indexer thread stopped.")
