"""
═══════════════════════════════════════════════════════════════
W2 — Structured Outputs: 5 Test Cases Tiếng Việt Thực Tế
═══════════════════════════════════════════════════════════════
Chạy:  pytest tests/test_w2_structured_outputs.py -v
       pytest tests/test_w2_structured_outputs.py -v -s     ← xem print()
═══════════════════════════════════════════════════════════════
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

BASE_URL = "http://test"
ENDPOINT = "/api/verify-listing"


# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────

async def call_verify(raw_text: str, owner_id: str = "test-uuid") -> dict:
    """Gọi endpoint và trả về response JSON."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            ENDPOINT,
            json={"rawText": raw_text, "owner_id": owner_id},
        )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    body = response.json()
    assert body["success"] is True, f"success=False: {body.get('error')}"
    return body["data"]


# ═════════════════════════════════════════════════════════════
# TEST CASE 1 — Đầy đủ thông tin, viết chuẩn
# Kỳ vọng: status=published, score >= 70
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_1_full_info_published():
    """
    Input: Mô tả đầy đủ, rõ ràng, đúng khu vực Đà Nẵng.
    Kỳ vọng:
      - listing.status = published
      - validation.score >= 70
      - apartment_meta.area_m2 = 65
      - price_per_month = 10_000_000
      - có ít nhất 3 amenities
    """
    raw_text = (
        "Cho thuê căn hộ cao cấp tại Quận Hải Châu, Đà Nẵng. "
        "Diện tích 65m2, tầng 12, 2 phòng ngủ 2 WC. "
        "Full nội thất: máy lạnh, tủ lạnh, máy giặt, tivi, bếp từ. "
        "Tòa nhà có hồ bơi, gym, bảo vệ 24/7. "
        "Giá 10 triệu/tháng, cọc 1 tháng. Không cho nuôi thú cưng."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    meta    = data["apartment_meta"]
    val     = data["validation"]

    print(f"\n[TC1] status={listing['status']} | score={val['score']}")
    print(f"      title={listing['title']}")

    assert listing["status"] == "published", (
        f"Kỳ vọng 'published', nhận '{listing['status']}'\n"
        f"missing_fields={val['missing_fields']}\n"
        f"feedback={val['feedback_to_owner']}"
    )
    assert val["score"] >= 70, f"Score {val['score']} < 70"
    assert meta["area_m2"] == 65, f"area_m2={meta['area_m2']} (kỳ vọng 65)"
    assert listing["price_per_month"] == 10_000_000
    assert len(meta["amenities"]) >= 3, "Phải có ít nhất 3 amenities"


# ═════════════════════════════════════════════════════════════
# TEST CASE 2 — Viết tắt nhiều
# Kỳ vọng: AI nhận dạng đúng viết tắt, published
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_2_abbreviations_parsed_correctly():
    """
    Input: Chứa nhiều viết tắt (pn, wc, tr/th, full nt, bql, cc).
    Kỳ vọng:
      - listing.status = published
      - price_per_month = 8_000_000
      - apartment_meta.area_m2 = 50
      - có amenity category=furniture và category=building
    """
    raw_text = (
        "CC Monarchy Đà Nẵng Q Hải Châu. "
        "50m2 2pn 1wc lầu 8 view sông Hàn. "
        "Full nt: ml, tl, tv, sofa. "
        "Bql tốt, có thang máy, bảo vệ 24/7, gym. "
        "Giá 8tr/th, cọc 2th. Cho nấu ăn."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    meta    = data["apartment_meta"]
    val     = data["validation"]

    print(f"\n[TC2] status={listing['status']} | score={val['score']}")
    print(f"      amenities={[a['amenities_name'] for a in meta['amenities']]}")

    assert listing["status"] == "published", (
        f"Kỳ vọng 'published', nhận '{listing['status']}'\n"
        f"missing_fields={val['missing_fields']}"
    )
    assert listing["price_per_month"] == 8_000_000, (
        f"price={listing['price_per_month']} (kỳ vọng 8_000_000)"
    )
    assert meta["area_m2"] == 50, f"area_m2={meta['area_m2']} (kỳ vọng 50)"

    categories = {a["category"] for a in meta["amenities"]}
    assert "furniture" in categories, "Thiếu amenity furniture"
    assert "building"  in categories, "Thiếu amenity building"


# ═════════════════════════════════════════════════════════════
# TEST CASE 3 — Viết dài dòng, kể lể
# Kỳ vọng: AI lọc được thông tin cốt lõi, published
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_3_verbose_input_filtered():
    """
    Input: Chủ nhà viết dài dòng, nhiều câu chuyện không liên quan.
    Kỳ vọng:
      - listing.status = published
      - description KHÔNG chứa các cụm "mình cần", "inbox mình"
        (AI không copy nguyên văn giọng hội thoại)
      - price_per_month = 8_500_000
      - area_m2 = 60
    """
    raw_text = (
        "Chào các bạn, mình đang cần cho thuê căn hộ chính chủ tại Vinhomes Grand Park "
        "Ngũ Hành Sơn Đà Nẵng. Mình mua căn này để đầu tư nhưng không có thời gian ở. "
        "Căn của mình là căn góc rất thoáng, 60 mét vuông. "
        "2 phòng ngủ, 1 phòng khách rộng rãi. Mình vừa làm lại nội thất gỗ rất ấm cúng. "
        "Có máy lạnh, máy giặt, tủ lạnh mới mua năm ngoái. "
        "Tòa nhà có siêu thị ở tầng trệt, hầm để xe rộng, hồ bơi ngoài trời. "
        "Giá mình mong muốn là 8.5 triệu mỗi tháng thôi, thương lượng được chút. "
        "Bạn nào thiện chí thì inbox mình nhé, mình không qua môi giới."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    meta    = data["apartment_meta"]
    val     = data["validation"]

    print(f"\n[TC3] status={listing['status']} | score={val['score']}")
    print(f"      price={listing['price_per_month']} | area={meta['area_m2']}")

    assert listing["status"] == "published", (
        f"Kỳ vọng 'published', nhận '{listing['status']}'\n"
        f"missing_fields={val['missing_fields']}"
    )
    assert listing["price_per_month"] == 8_500_000, (
        f"price={listing['price_per_month']} (kỳ vọng 8_500_000)"
    )
    assert meta["area_m2"] == 60, f"area_m2={meta['area_m2']} (kỳ vọng 60)"

    # Kiểm tra AI không copy nguyên văn giọng hội thoại
    desc_lower = listing["description"].lower()
    assert "inbox mình" not in desc_lower, "description bị copy nguyên văn hội thoại"
    assert "mình cần" not in desc_lower,   "description bị copy nguyên văn hội thoại"


# ═════════════════════════════════════════════════════════════
# TEST CASE 4 — Thiếu thông tin bắt buộc
# Kỳ vọng: status=draft, có feedback_to_owner, missing_fields rõ ràng
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_4_missing_required_fields_draft():
    """
    Input: Thiếu giá thuê VÀ diện tích — 2 trường bắt buộc.
    Kỳ vọng:
      - listing.status = draft
      - validation.missing_fields chứa ít nhất 1 trường
      - validation.feedback_to_owner không None và không rỗng
      - score < 70
    """
    raw_text = (
        "Cho thuê căn hộ đẹp ở Quận Thanh Khê Đà Nẵng, nhà mới, sạch sẽ, "
        "an ninh tốt. Có máy lạnh và máy giặt. Ai cần liên hệ để xem nhà nhé."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    val     = data["validation"]

    print(f"\n[TC4] status={listing['status']} | score={val['score']}")
    print(f"      missing_fields={val['missing_fields']}")
    print(f"      feedback={val['feedback_to_owner']}")

    assert listing["status"] == "draft", (
        f"Kỳ vọng 'draft', nhận '{listing['status']}'"
    )
    assert len(val["missing_fields"]) >= 1, (
        "Phải liệt kê ít nhất 1 trường còn thiếu trong missing_fields"
    )
    assert val["feedback_to_owner"] is not None, "feedback_to_owner không được None khi draft"
    assert len(val["feedback_to_owner"]) > 20,   "feedback_to_owner quá ngắn, thiếu nội dung"
    assert val["score"] < 70, f"Score {val['score']} phải < 70 khi thiếu trường bắt buộc"


# ═════════════════════════════════════════════════════════════
# TEST CASE 5 — Địa chỉ ngoài Đà Nẵng
# Kỳ vọng: status=draft, issues nhắc sai khu vực
# ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_case_5_outside_danang_rejected():
    """
    Input: Căn hộ rõ ràng ở TP.HCM (Bình Thạnh).
    Kỳ vọng:
      - listing.status = draft
      - validation.issues hoặc missing_fields đề cập Đà Nẵng
      - validation.feedback_to_owner nhắc nền tảng chỉ quản lý Đà Nẵng
    """
    raw_text = (
        "Cho thuê căn hộ Vinhomes Central Park, Quận Bình Thạnh, TP.HCM. "
        "Diện tích 72m2, 2 phòng ngủ 2 WC, tầng 25. "
        "Full nội thất cao cấp: máy lạnh, tủ lạnh, máy giặt, bếp từ. "
        "Hồ bơi, gym, bảo vệ 24/7. Giá 20 triệu/tháng, cọc 2 tháng."
    )

    data = await call_verify(raw_text)
    listing = data["listing"]
    val     = data["validation"]

    print(f"\n[TC5] status={listing['status']} | score={val['score']}")
    print(f"      issues={val['issues']}")
    print(f"      feedback={val['feedback_to_owner']}")

    assert listing["status"] == "draft", (
        f"Kỳ vọng 'draft' vì ngoài Đà Nẵng, nhận '{listing['status']}'"
    )

    # issues hoặc missing_fields phải đề cập Đà Nẵng
    all_messages = " ".join(val["issues"] + val["missing_fields"]).lower()
    assert "đà nẵng" in all_messages, (
        "issues/missing_fields phải đề cập Đà Nẵng\n"
        f"issues={val['issues']}\nmissing_fields={val['missing_fields']}"
    )

    # feedback gửi chủ nhà phải nhắc rõ khu vực
    assert val["feedback_to_owner"] is not None, "feedback_to_owner không được None"
    assert "đà nẵng" in val["feedback_to_owner"].lower(), (
        "feedback_to_owner phải nhắc về khu vực Đà Nẵng"
    )
