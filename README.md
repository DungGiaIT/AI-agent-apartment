# 🏠 AI Integrated Apartments
> **Agent 1 — Listing Verifier** | FastAPI · Gemini AI · Pydantic · Instructor

Hệ thống AI tự động kiểm duyệt và chuẩn hoá thông tin bất động sản cho thuê tại **Đà Nẵng**.  
Nhận mô tả thô từ chủ nhà → phân tích → trả về JSON chuẩn hoá sẵn sàng lưu database.

---

## 📁 Cấu Trúc Project

```
AI-integrated-apartments/
├── app/
│   ├── agents/          ← AI agent logic
│   ├── api/             ← FastAPI routes
│   ├── core/            ← Config, exceptions
│   ├── prompts/         ← System prompts
│   ├── schemas/         ← Pydantic models
│   ├── services/        ← LLM, vector DB clients
│   ├── tests/           ← 10 test cases
│   ├── __init__.py
│   └── main.py          ← Entry point
├── .env                 ← Biến môi trường (tự tạo, xem bên dưới)
├── .gitignore
├── pytest.ini
└── requirements.txt
```

---

## ⚙️ Cài Đặt & Chạy

### Bước 1 — Clone repo

```bash
git clone https://github.com/DungGiaIT/AI-integrated-apartments.git
cd AI-integrated-apartments
```

### Bước 2 — Tạo và kích hoạt môi trường ảo

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### Bước 3 — Cài đặt dependencies

```bash
pip install -r app/requirements.txt
```

### Bước 4 — Tạo file `.env`

Tạo file `.env` tại **thư mục gốc** của project (cùng cấp với `pytest.ini`):

```
AI-integrated-apartments/
├── .env        ← TẠO FILE NÀY
├── pytest.ini
└── app/
```

Nội dung file `.env`:

```dotenv
GEMINI_API_KEY=API_KEY_HERE

# Cấu hình server
APP_NAME="Agent 1 - Listing Verifier"
APP_VERSION="1.0.0"
DEBUG=true
HOST=0.0.0.0
PORT=8000
```

> 🔑 Lấy Gemini API Key tại: https://aistudio.google.com/app/apikey  
> Thay `API_KEY_HERE` bằng key thật của bạn.

### Bước 5 — Khởi động server

```bash
python -m uvicorn app.main:app --reload
```

Server chạy tại: **http://127.0.0.1:8000**

---

## 🧪 Chạy Tests

```bash
# Toàn bộ 10 test cases
pytest app/tests/ -v --tb=short

# Chỉ W2 (TC1–TC5)
pytest app/tests/test_w2_structured_outputs.py -v -s

# Chỉ W3 (TC6–TC10) — có delay 22s giữa mỗi test
pytest app/tests/test_w3_core.py -v -s
```

> ⚠️ **Gemini Free Tier** giới hạn 20 request/ngày.  
> Nếu gặp lỗi 429, chờ sang ngày hôm sau hoặc nâng lên Paid plan.

---

## 📖 API Documentation

Sau khi server chạy, truy cập Swagger UI tự động sinh:

```
http://127.0.0.1:8000/docs
```

### Ví dụ gọi API

```bash
curl -X POST http://127.0.0.1:8000/api/verify-listing \
  -H "Content-Type: application/json" \
  -d '{
    "rawText": "Cho thuê căn hộ Quận Hải Châu Đà Nẵng, 65m2, 2pn 2wc tầng 12. Full nội thất: máy lạnh, tủ lạnh, máy giặt. Hồ bơi, gym, bảo vệ 24/7. Giá 10 triệu/tháng.",
    "owner_id": "uuid-owner-001"
  }'
```

---

## 🗂️ Agents

| Agent | File | Chức năng | Status |
|---|---|---|---|
| Agent 1 | `agent_verifier.py` | Kiểm duyệt & chuẩn hoá listing | ✅ Done |
| Agent 2 | `agent_broker.py` | RAG chatbot tư vấn người thuê | 🔜 Tháng 2 |
| Agent 3 | `agent_concierge.py` | Phân loại & xử lý sự cố | 🔜 Tháng 2 |
| Agent 4 | `agent_admin.py` | Tạo invoice & báo cáo | 🔜 Tháng 2 |

---

## 🛠️ Tech Stack

| Công nghệ | Version | Mục đích |
|---|---|---|
| FastAPI | latest | Web framework |
| Gemini AI | gemini-2.5-flash | LLM backend |
| Instructor | latest | Structured outputs |
| Pydantic v2 | ≥2.0 | Data validation |
| pytest-asyncio | latest | Async testing |
| httpx | latest | HTTP client cho tests |

---

## 📄 License

MIT © 2026 DungGiaIT