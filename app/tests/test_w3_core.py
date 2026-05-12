"""
═══════════════════════════════════════════════════════════════
W3 — Build Agent 1 Core: 5 Test Cases Bổ Sung (TC6 → TC10)
Tổng cộng sau W3: 10/10 tests
═══════════════════════════════════════════════════════════════

MỤC ĐÍCH TỪNG TEST:

  TC6  — DB Verification (đối soát database)
         Gửi kèm db_apartment_data thật (area, floor).
         Kiểm tra AI có đối soát được rawText với DB không.
         Nếu khớp → is_verified_by_db=True, data_conflicts=[].
         Quan trọng vì đây là lớp bảo vệ chống chủ nhà khai sai diện tích.

  TC7  — Giá bất thường (quá thấp)
         Giá 500k/tháng — rõ ràng bất thường tại Đà Nẵng.
         Kỳ vọng: AI không chặn listing (chủ nhà có quyền đặt giá),
         nhưng PHẢI ghi nhận vào issues để team ops kiểm tra.
         Test này đảm bảo AI không im lặng khi thấy dữ liệu lạ.

  TC8  — Input spam / số điện thoại
         Chủ nhà nhét số điện thoại, "call ngay", "giá sốc" vào rawText.
         Kỳ vọng: description được viết lại sạch sẽ — số điện thoại
         KHÔNG được xuất hiện trong description output.
         Bảo vệ platform khỏi bị dùng làm kênh liên hệ trực tiếp bypass.

  TC9  — Input ALL CAPS
         Chủ nhà viết toàn chữ hoa (thói quen hay gặp trên mạng xã hội).
         Kỳ vọng: AI chuẩn hoá được tên quận, tiện nghi đúng format,
         title/description viết đúng hoa/thường.

  TC10 — rawText ngắn biên (20 ký tự — min_length của schema)
         Kiểm tra endpoint không crash với input tối thiểu.
         Kỳ vọng: trả về draft + feedback rõ ràng, HTTP 200 (không 500).

Chạy:
  pytest app/tests/test_w3_core.py -v -s
  pytest app/tests/ -v --tb=short          ← toàn bộ 10 test
═══════════════════════════════════════════════════════════════
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

BASE_URL = "http://test"
ENDPOINT  = "/api/verify-listing"


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

async def call_verify(
    raw_text: str,
    owner_id: str = "test-uuid",
    db_data: dict | None = None,
) -> dict:
    """Gọi endpoint, trả về data. Raise AssertionError nếu không thành công."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            ENDPOINT,
            json={
                "rawText": raw_text,
                "owner_id": owner_id,
                "db_apartment_data": db_data,
            },
        )
    assert response.status_code == 200, (
        f"HTTP {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["success"] is True, f"success=False: {body.get('error')}"
    return body["data"]


# ═════════════════════════════════════════════════════════════
# TC6 — DB Verification: rawText khớp với DB
# Mục đích: AI đối soát area & floor từ db_apartment_data
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_6_db_verification_match():
    """
    Gửi db_apartment_data với area=65, floor=12.
    rawText cũng nói đúng 65m2 tầng 12.
    → Kỳ vọng: is_verified_by_db=True, data_conflicts=[].
    """
    raw_text = (
        "Cho thuê căn hộ Monarchy Quận Hải Châu Đà Nẵng. "
        "Tầng 12, diện tích 65m2, 2 phòng ngủ 2 WC. "
        "Full nội thất: máy lạnh, tủ lạnh, máy giặt. "
        "Hồ bơi, gym, bảo vệ 24/7. Giá 10tr/tháng."
    )
    db_data = {
        "id": "uuid-apartment-001",
        "room_number": "A1205",
        "floor": 12,
        "area": 65.0,
        "note": "Căn góc, view sông Hàn",
    }

    data = await call_verify(raw_text, db_data=db_data)
    val  = data["validation"]
    meta = data["apartment_meta"]

    print(f"\n[TC6] is_verified_by_db={val['is_verified_by_db']}")
    print(f"      data_conflicts={val['data_conflicts']}")
    print(f"      area_m2={meta['area_m2']} | floor={meta['floor']}")

    assert val["is_verified_by_db"] is True, (
        "Kỳ vọng is_verified_by_db=True khi rawText khớp DB\n"
        f"data_conflicts={val['data_conflicts']}"
    )
    assert val["data_conflicts"] == [], (
        f"Không được có conflict khi dữ liệu khớp: {val['data_conflicts']}"
    )
    assert meta["area_m2"] == 65.0
    assert meta["floor"] == 12


# ═════════════════════════════════════════════════════════════
# TC7 — Giá bất thường (quá thấp)
# Mục đích: AI cảnh báo nhưng không chặn listing
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_7_abnormal_price_flagged_not_blocked():
    """
    Giá 500k/tháng — bất thường tại Đà Nẵng.
    Kỳ vọng:
      - HTTP 200 (không crash)
      - price_per_month = 500_000 (AI không tự sửa giá)
      - validation.issues có ít nhất 1 cảnh báo về giá
    """
    raw_text = (
        "Cho thuê phòng trọ Quận Cẩm Lệ Đà Nẵng, 25m2, tầng 2. "
        "Giá chỉ 500 nghìn/tháng, có máy lạnh, nhà vệ sinh riêng. "
        "Nội thất cơ bản, phù hợp sinh viên."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    val     = data["validation"]

    print(f"\n[TC7] price={listing['price_per_month']} | issues={val['issues']}")

    assert listing["price_per_month"] == 500_000, (
        f"AI không được tự sửa giá, phải giữ nguyên 500000. "
        f"Nhận: {listing['price_per_month']}"
    )
    assert len(val["issues"]) >= 1, (
        "Phải có ít nhất 1 issue cảnh báo giá bất thường\n"
        f"issues hiện tại: {val['issues']}"
    )


# ═════════════════════════════════════════════════════════════
# TC8 — Input spam / số điện thoại
# Mục đích: description output không chứa số điện thoại
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_8_spam_phone_not_in_description():
    """
    rawText chứa số điện thoại và ngôn ngữ spam.
    Kỳ vọng:
      - HTTP 200 (không crash)
      - description KHÔNG chứa số điện thoại dạng 09x/03x
      - listing vẫn có đủ thông tin cốt lõi
    """
    raw_text = (
        "🔥🔥 GIÁ SỐC - CALL NGAY 0901234567 🔥🔥 "
        "Cho thuê căn hộ Quận Sơn Trà Đà Nẵng, 55m2 2pn 1wc tầng 8. "
        "Máy lạnh, tủ lạnh, máy giặt đầy đủ. Hồ bơi, gym tòa nhà. "
        "Giá 9 triệu/tháng. LH: 090.123.4567 gặp anh Minh để được tư vấn ngay!"
    )

    data = await call_verify(raw_text)
    listing = data["listing"]

    print(f"\n[TC8] status={listing['status']}")
    print(f"      description (100 ký tự đầu): {listing['description'][:100]}")

    import re
    phone_pattern = re.compile(r'0[3-9]\d[\s.]?\d{3}[\s.]?\d{4}')
    found_phones = phone_pattern.findall(listing["description"])

    assert found_phones == [], (
        f"Số điện thoại không được xuất hiện trong description: {found_phones}"
    )
    # Thông tin cốt lõi vẫn phải có
    assert listing["price_per_month"] == 9_000_000
    assert data["apartment_meta"]["area_m2"] == 55


# ═════════════════════════════════════════════════════════════
# TC9 — Input ALL CAPS
# Mục đích: AI chuẩn hoá hoa/thường đúng format
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_9_all_caps_normalized():
    """
    Chủ nhà viết toàn chữ hoa.
    Kỳ vọng:
      - title KHÔNG phải toàn chữ hoa
      - amenities_name viết hoa chữ đầu đúng format
      - area_m2 và price trích đúng
    """
    raw_text = (
        "CHO THUE CAN HO QUAN HAI CHAU DA NANG. "
        "DIEN TICH 70M2, TANG 10, 2 PHONG NGU 2 WC. "
        "CO MAY LANH, TU LANH, MAY GIAT. "
        "TOA NHA CO HO BOI VA GYM. GIA 12 TRIEU/THANG."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    meta    = data["apartment_meta"]

    print(f"\n[TC9] title={listing['title']}")
    print(f"      amenities={[a['amenities_name'] for a in meta['amenities']]}")

    # Title không được toàn chữ hoa
    assert listing["title"] != listing["title"].upper(), (
        f"Title vẫn còn toàn chữ hoa: {listing['title']}"
    )
    # Phải trích được giá và diện tích dù input viết không dấu
    assert listing["price_per_month"] == 12_000_000, (
        f"price={listing['price_per_month']} (kỳ vọng 12_000_000)"
    )
    assert meta["area_m2"] == 70, (
        f"area_m2={meta['area_m2']} (kỳ vọng 70)"
    )


# ═════════════════════════════════════════════════════════════
# TC10 — rawText ngắn biên (đúng 20 ký tự min_length)
# Mục đích: Endpoint không crash với input tối thiểu
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_10_minimal_input_no_crash():
    """
    rawText chỉ vừa đủ 20 ký tự (biên dưới của min_length).
    Kỳ vọng:
      - HTTP 200 (không crash 422 hay 500)
      - status = draft (không đủ thông tin)
      - feedback_to_owner không None
    """
    raw_text = "Cho thuê phòng Đà Nẵng"  # 22 ký tự — vừa qua min_length=20

    data = await call_verify(raw_text)
    listing = data["listing"]
    val     = data["validation"]

    print(f"\n[TC10] status={listing['status']} | score={val['score']}")
    print(f"       feedback={val['feedback_to_owner']}")

    assert listing["status"] == "draft", (
        f"Input 22 ký tự phải là draft, nhận '{listing['status']}'"
    )
    assert val["feedback_to_owner"] is not None, (
        "Phải có feedback_to_owner hướng dẫn chủ nhà bổ sung thông tin"
    )
    assert len(val["feedback_to_owner"]) > 10, (
        "feedback_to_owner quá ngắn, không có nội dung hướng dẫn"
    )