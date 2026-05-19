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
    image_id: str = Field(..., min_length=1, max_length=128)
    url: Optional[str] = Field(None, max_length=2048)
    media_type: str = Field(default="image/jpg")
    base64_data: Optional[str] = None

    @model_validator(mode="after")
    def url_or_base64(self) -> "rawListingImageInput":
        if not (self.url or self.base64_data):
            raise ValueError("Mỗi ảnh cần có url hoặc base64_data.")
        return self


class rawListingInput(BaseModel):
    rawText: str = Field(..., min_length=20, max_length=1000)
    images: list[rawListingImageInput] = Field(default_factory=list, max_length=12)
    owner_id: str
    db_apartment_data: Optional[dict] = None


# ─────────────────────────────────────────────
# OUTPUT — Kết quả trả về từ AI Agent
# ─────────────────────────────────────────────

class listingCoreOutput(BaseModel):
    title: str = Field(..., min_length=10, max_length=100)
    description: str = Field(..., min_length=100)
    price_per_month: Optional[float] = Field(None, gt=0)
    status: listingStatus


class amenityItem(BaseModel):
    amenities_name: str
    category: amenityCategory


class apartmentMetaOutput(BaseModel):
    area_m2: Optional[float] = Field(None, gt=0)
    floor: Optional[int] = Field(None, ge=1)
    room_number: Optional[str] = None
    note: Optional[str] = None
    amenities: list[amenityItem] = Field(default_factory=list)


class listingImageAnalysis(BaseModel):
    image_id: str
    primary_tag: imageRoomTag
    secondary_tags: list[imageRoomTag] = Field(default_factory=list, max_length=5)
    brightness_score: int = Field(..., ge=0, le=100)
    sharpness_score: int = Field(..., ge=0, le=100)
    watermark_or_branding_suspected: bool
    duplicate_or_stock_photo_suspected: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes_vi: Optional[str] = Field(None, max_length=500)


class validationOutput(BaseModel):
    status: validationStatus
    score: int = Field(..., ge=0, le=100)
    data_conflicts: list[dict] = Field(default_factory=list)
    is_verified_by_db: bool = Field(default=False)
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    feedback_to_owner: Optional[str] = None

class listingVerifiedOutput(BaseModel):
    listing:        listingCoreOutput
    apartment_meta: apartmentMetaOutput
    image_tags_suggested: list[str] = Field(default_factory=list)
    image_analyses: list[listingImageAnalysis] = Field(default_factory=list)
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