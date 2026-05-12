from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator

class listingStatus(str, Enum):
    Draft     = "draft"
    Published = "published"
    Rented    = "rented"
class amenityCategory(str, Enum):
    Furniture = "furniture"
    Building  = "building"
    Policy    = "policy"

class amenityStatus(str, Enum):
    Working     = "working"
    Broken      = "broken"
    Unavailable = "unavailable"

class validationStatus(str, Enum):
    Pass = "pass"
    Fail = "fail"


# ─────────────────────────────────────────────
# INPUT — Dữ liệu thô nhận từ NestJS
# ─────────────────────────────────────────────

class rawListingInput(BaseModel):
    rawText: str = Field(
        ...,
        min_length=20,
        max_length=1000,
        description="Mô tả thô từ chủ nhà, chưa được xử lý bởi AI agent",
        examples=[
            # Ví dụ 1: Đầy đủ thông tin, viết chuẩn — kỳ vọng Published
            (
                "Cho thuê căn hộ cao cấp tại Quận Hải Châu, Đà Nẵng. "
                "Diện tích 65m2, tầng 12, 2 phòng ngủ 2 WC. "
                "Full nội thất: máy lạnh, tủ lạnh, máy giặt, tivi, bếp từ. "
                "Tòa nhà có hồ bơi, gym, bảo vệ 24/7. "
                "Giá 10 triệu/tháng, cọc 1 tháng. Không cho nuôi thú cưng."
            ),
            # Ví dụ 2: Viết tắt nhiều — kỳ vọng AI nhận dạng đúng
            (
                "CC Monarchy Đà Nẵng Q Hải Châu. 50m2 2pn 1wc lầu 8 view sông Hàn. "
                "Full nt: ml, tl, tv, sofa. Bql tốt, có thang máy, bảo vệ 24/7, gym. "
                "Giá 8tr/th, cọc 2th. Cho nấu ăn."
            ),
            # Ví dụ 3: Viết dài dòng, kể lể — kỳ vọng AI lọc thông tin cốt lõi
            (
                "Chào các bạn, mình cần cho thuê căn hộ chính chủ tại Vinhomes "
                "Ngũ Hành Sơn Đà Nẵng. Căn góc rất thoáng, khoảng 60 mét vuông. "
                "Có 2 phòng ngủ, mình vừa làm lại nội thất gỗ rất ấm cúng. "
                "Có máy lạnh, máy giặt, tủ lạnh. Tòa có siêu thị, hầm xe, hồ bơi. "
                "Giá 8.5 triệu/tháng. Bạn nào thiện chí inbox mình nhé, không qua môi giới."
            ),
            # Ví dụ 4: Thiếu giá + diện tích — kỳ vọng Draft + feedback rõ ràng
            (
                "Cho thuê căn hộ đẹp ở Quận Thanh Khê Đà Nẵng, nhà mới sạch sẽ, "
                "an ninh tốt. Có máy lạnh và máy giặt. Ai cần liên hệ để xem nhà nhé."
            ),
        ],
    )

    owner_id: str = Field(
        ...,
        description="UUID của chủ nhà — khớp với User.id trong database",
    )

    db_apartment_data: Optional[dict] = Field(
        None,
        description=(
            "Dữ liệu gốc của căn hộ từ bảng Apartment trong DB. "
            "NestJS gửi kèm để Agent có thể đối soát thông tin từ rawText. "
            "Cấu trúc: {id, owner_id, room_number, floor, area, note, createdAt, updatedAt}. "
            "Ví dụ: {'id': 'uuid-xxx', 'room_number': 'A1204', 'floor': 15, 'area': 71.5, 'note': 'Góc, view hồ'}. "
            "Trường area là DECIMAL(5,2) → khớp với area_m2 trích từ rawText. "
            "Nếu không có, Agent sẽ không thể xác minh dữ liệu (is_verified_by_db = False)."
        ),
    )


# ─────────────────────────────────────────────
# OUTPUT — Kết quả trả về từ AI Agent
# ─────────────────────────────────────────────

class listingCoreOutput(BaseModel):
    title: str = Field(
        ...,
        min_length=10,
        max_length=100,
        description=(
            "Tiêu đề bài đăng chuẩn SEO, 60-100 ký tự tiếng Việt. "
            "Format: '[Loại] [Diện tích]m² [Quận Đà Nẵng] - [Điểm nổi bật]'. "
            "VD: 'Cho thuê căn hộ 65m² Quận Hải Châu Đà Nẵng - Full nội thất, gần cầu Rồng'"
        ),
    )

    description: str = Field(
        ...,
        min_length=100,
        description=(
            "Mô tả chi tiết đã chuẩn hoá, viết đúng chính tả, KHÔNG copy nguyên văn input. "
            "Cấu trúc 5 đoạn: "
            "1-Tổng quan căn hộ | 2-Nội thất & tiện nghi trong căn | "
            "3-Tiện ích toà nhà | 4-Vị trí & lân cận | 5-Chính sách & liên hệ"
        ),
    )

    price_per_month: Optional[float] = Field(
        None,
        gt=0,
        description=(
            "Giá thuê mỗi tháng, đơn vị VND, kiểu số thực. "
            "Khớp với Listings.price_per_month DECIMAL(12,2). "
            "VD: 12000000.0 (tức 12 triệu đồng). "
            "Để null nếu chủ nhà không đề cập giá — KHÔNG được đoán mò."
        ),
    )

    status: listingStatus = Field(
        ...,
        description=(
            "Published nếu score >= 70 VÀ có đủ: giá + diện tích + quận Đà Nẵng. "
            "Draft nếu thiếu bất kỳ trường bắt buộc nào hoặc vị trí ngoài Đà Nẵng."
        ),
    )


class amenityItem(BaseModel):
    amenities_name: str = Field(
        ...,
        description=(
            "Tên tiện nghi chuẩn hoá, viết hoa chữ đầu. "
            "Khớp với Amenities.amenities_name. "
            "VD: 'Máy lạnh', 'Hồ bơi', 'Cho nuôi thú cưng'"
        ),
    )

    category: amenityCategory = Field(
        ...,
        description=(
            "furniture = tiện nghi trong căn (máy lạnh, tủ lạnh...). "
            "building  = tiện ích toà nhà (hồ bơi, gym...). "
            "policy    = chính sách chủ nhà (cho nuôi thú, cho hút thuốc...)."
        ),
    )


class apartmentMetaOutput(BaseModel):
    area_m2: Optional[float] = Field(
        None,
        gt=0,
        description="Diện tích m². Khớp với Apartment.area DECIMAL(5,2).",
    )

    floor: Optional[int] = Field(
        None,
        ge=1,
        description="Tầng. Khớp với Apartment.floor INT.",
    )

    room_number: Optional[str] = Field(
        None,
        description=(
            "Số phòng / mã căn hộ nếu chủ nhà đề cập. "
            "Khớp với Apartment.room_number varchar. "
            "VD: 'A1204', 'Phòng 12'"
        ),
    )

    note: Optional[str] = Field(
        None,
        description=(
            "Ghi chú thêm không thuộc các trường khác. "
            "Khớp với Apartment.note varchar. "
            "VD: 'Hướng Đông Nam, view trực diện sông Hàn'"
        ),
    )

    amenities: list[amenityItem] = Field(
        default_factory=list,
        description=(
            "Toàn bộ tiện nghi trích xuất, đã phân loại theo category. "
            "Mỗi item → 1 row trong Amenities + 1 row trong Apartment_amenities. "
            "Gộp cả 3 loại: furniture, building, policy vào đây. "
            "VD: ["
            "  {amenities_name: 'Máy lạnh', category: 'furniture'}, "
            "  {amenities_name: 'Hồ bơi',   category: 'building'}, "
            "  {amenities_name: 'Cho nuôi thú cưng', category: 'policy'}"
            "]"
        ),
    )


class validationOutput(BaseModel):
    status: validationStatus = Field(
        ...,
        description=(
            "pass nếu thông tin khớp hoàn toàn với DB. "
            "fail nếu có sai lệch hoặc thiếu thông tin quan trọng."
        ),
    )

    score: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Điểm chất lượng tổng hợp 0-100. Bị trừ điểm nặng nếu thông tin sai lệch so với DB. "
            "Thang điểm: giá (+30), diện tích (+25), quận (+20), "
            "số phòng ngủ/WC (+15), mô tả nội thất (+10)."
        ),
    )

    data_conflicts: list[dict] = Field(
        default_factory=list,
        description=(
            "Danh sách các sai lệch dữ liệu phát hiện được. "
            "Ví dụ: [{'field': 'area', 'provided': 72, 'actual': 71, 'message': 'Diện tích không khớp'}]"
        ),
    )

    is_verified_by_db: bool = Field(
        default=False,
        description=(
            "Xác nhận rằng tất cả thông số kỹ thuật (diện tích, tầng, phòng) "
            "đã khớp 100% với database."
        ),
    )

    missing_fields: list[str] = Field(
        default_factory=list,
        description="Trường bắt buộc còn thiếu. VD: ['Giá thuê', 'Diện tích']",
    )

    issues: list[str] = Field(
        default_factory=list,
        description=(
            "Vấn đề phát hiện. "
            "VD: ['Giá thấp bất thường so với khu vực', 'Vị trí không thuộc Đà Nẵng']"
        ),
    )

    feedback_to_owner: Optional[str] = Field(
        None,
        description=(
            "Phản hồi thân thiện bằng tiếng Việt gửi chủ nhà khi status=Draft. "
            "Nêu rõ thiếu gì và tại sao thông tin đó quan trọng với người thuê. "
            "Null khi Published."
        ),
    )

class listingVerifiedOutput(BaseModel):
    listing:        listingCoreOutput
    apartment_meta: apartmentMetaOutput

    image_tags_suggested: list[str] = Field(
        default_factory=list,
        description=(
            "Nhãn ảnh gợi ý cho Vision AI xử lý ở bước upload ảnh. "
            "Dùng để pre-tag Listing_images khi chủ nhà tải ảnh lên. "
            "VD: ['phong_khach', 'phong_ngu', 'bep', 'ban_cong', 'ho_boi']"
        ),
    )

    validation: validationOutput

    @model_validator(mode="after")
    def sync_status_with_validation(self) -> listingVerifiedOutput:
        if self.validation.status == validationStatus.Fail:
            self.listing.status = listingStatus.Draft
        return self


class verifyListingResponse(BaseModel):
    success: bool
    data:    Optional[listingVerifiedOutput] = None
    error:   Optional[str] = None