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


class imageRoomTag(str, Enum):
    phong_khach = "phong_khach"
    phong_ngu = "phong_ngu"
    phong_tam = "phong_tam"
    bep = "bep"
    ban_cong = "ban_cong"
    hanh_lang = "hanh_lang"
    view_thanh_pho = "view_thanh_pho"
    view_bien = "view_bien"
    view_song = "view_song"
    noi_that_chung = "noi_that_chung"
    tien_ich_toa_nha = "tien_ich_toa_nha"
    khac = "khac"

class rawListingImageInput(BaseModel):
    """Một ảnh đính kèm: URL công khai hoặc base64 (khi CDN chưa public)."""

    image_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="ID duy nhất do client/NestJS gán — dùng để khớp với kết quả vision.",
    )
    url: Optional[str] = Field(
        None,
        max_length=2048,
        description="HTTPS URL ảnh (bucket/CDN public).",
    )
    media_type: str = Field(
        default="image/jpg",
        description="MIME type khi dùng base64, ví dụ image/jpg, image/png, image/webp.",
    )
    base64_data: Optional[str] = Field(
        None,
        description="Nội dung ảnh base64 (không gồm tiền tố data:...). Bắt buộc nếu không có url.",
    )

    @model_validator(mode="after")
    def url_or_base64(self) -> "rawListingImageInput":
        if not (self.url or self.base64_data):
            raise ValueError("Mỗi ảnh cần có url hoặc base64_data.")
        return self


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

    images: list[rawListingImageInput] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "Danh sách ảnh minh họa (tối đa 12). NestJS gửi URL public hoặc base64. "
            "Agent 1 chạy Vision để auto-tag, chấm chất lượng và cảnh báo watermark."
        ),
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


class listingImageAnalysis(BaseModel):
    """Kết quả Vision cho một ảnh — lưu Listing_images / bộ lọc."""

    image_id: str = Field(
        ...,
        description="Khớp rawListingImageInput.image_id.",
    )
    primary_tag: imageRoomTag = Field(
        ...,
        description="Nhãn chính (một không gian nổi bật nhất trong khung hình).",
    )
    secondary_tags: list[imageRoomTag] = Field(
        default_factory=list,
        max_length=5,
        description="Các nhãn phụ (tối đa 5), không trùng primary_tag.",
    )
    brightness_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Độ sáng tổng thể 0-100 (100=rất sáng, dễ xem).",
    )
    sharpness_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Độ nét 0-100 (0=rất mờ/mất nét, 100=rất sắc).",
    )
    watermark_or_branding_suspected: bool = Field(
        ...,
        description="True nếu thấy logo/watermark/text đối thủ hoặc branding lạ.",
    )
    duplicate_or_stock_photo_suspected: bool = Field(
        ...,
        description="True nếu giống ảnh stock/generic hoặc nghi ngờ copy từ site khác.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của phân loại primary_tag (0-1).",
    )
    notes_vi: Optional[str] = Field(
        None,
        max_length=500,
        description="Ghi chú ngắn tiếng Việt (ví dụ: 'chỉnh sáng quá mức', 'có chữ mờ góc phải').",
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
            "Nhãn ảnh gợi ý suy ra từ mô tả chữ (NER / ngữ cảnh), không thay thế vision. "
            "VD: ['phong_khach', 'phong_ngu', 'bep', 'ban_cong']. "
            "Khi có images, nên đồng bộ với image_analyses trong ứng dụng."
        ),
    )

    image_analyses: list[listingImageAnalysis] = Field(
        default_factory=list,
        description=(
            "Phân tích từng ảnh: tag phòng/cảnh, điểm sáng/nét, nghi watermark/stock. "
            "Rỗng nếu request không gửi images."
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