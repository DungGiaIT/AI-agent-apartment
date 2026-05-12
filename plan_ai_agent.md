# 🏢 AI-Integrated Apartments — 4-Agent System Design

> **Status:** Design Phase — Pending Implementation Approval  
> **Scale:** 100 căn hộ / 1,000 users  
> **LLM:** gemini-1.5-flash | **Event Bus:** Redis Streams | **Vector DB:** Qdrant

---

## 📐 PHẦN 1 — System Architecture Overview

### Triết lý kiến trúc

Bốn agent hoạt động **độc lập** (loosely coupled) nhưng **phối hợp** qua Redis Streams event bus.  
Mỗi agent là một **FastAPI service riêng** (hoặc module riêng trong monorepo), có thể deploy và scale độc lập.

```
┌─────────────────────────────────────────────────────────┐
│                    CLIENT LAYER                         │
│  Landlord App     Tenant Chat     Admin Dashboard       │
└────────────┬────────────┬─────────────┬────────────────┘
             │            │             │
             ▼            ▼             ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Gateway (Shared)                   │
│         Auth · Rate Limit · Request Routing             │
└──┬─────────────┬──────────────┬──────────────┬──────────┘
   │             │              │              │
   ▼             ▼              ▼              ▼
┌──────┐    ┌──────┐      ┌──────┐      ┌──────┐
│Agent1│    │Agent2│      │Agent3│      │Agent4│
│Listing    │Super │      │Smart │      │Contract
│Verif.│    │Broker│      │Conci.│      │&Admin│
└──┬───┘    └──┬───┘      └──┬───┘      └──┬───┘
   │           │              │              │
   └─────────────────┬────────────────────────┘
                     ▼
         ┌───────────────────────┐
         │   Redis Streams       │
         │   (Shared Event Bus)  │
         └───────────┬───────────┘
                     │
        ┌────────────┴───────────┐
        ▼                        ▼
┌───────────────┐      ┌──────────────────┐
│  PostgreSQL   │      │  Qdrant Vector   │
│  (Main DB)    │      │  (Agent 2 only)  │
└───────────────┘      └──────────────────┘
```

---

## 🌳 PHẦN 2 — Full Workflow Tree

```mermaid
graph TD
    ROOT["🏢 AI Apartment System"] --> INFRA
    ROOT --> A1
    ROOT --> A2
    ROOT --> A3
    ROOT --> A4

    %% SHARED INFRASTRUCTURE
    INFRA["⚙️ Shared Infrastructure"]
    INFRA --> REDIS["Redis Streams\n(Event Bus)"]
    INFRA --> PG["PostgreSQL\n(Main Database)"]
    INFRA --> GW["FastAPI Gateway\n(Auth + Routing)"]

    %% AGENT 1
    A1["🔍 Agent 1\nListing Verifier"]
    A1 --> A1_T["Trigger: POST /listings\n(Landlord submits raw data)"]
    A1_T --> A1_NLP["NLP Pipeline\n(gemini-1.5-flash)"]
    A1_NLP --> A1_EXT["Named Entity Extraction\nDiện tích, Giá, Phòng, Thú cưng"]
    A1_EXT --> A1_COPY["Auto-Copywriting\nSEO Title + Description"]
    A1_T --> A1_VIS["Vision AI Pipeline"]
    A1_VIS --> A1_TAG["Auto-tagging\nPhòng khách, Bếp, Balcony"]
    A1_VIS --> A1_QUAL["Quality Check\nĐộ sáng, Độ nét"]
    A1_VIS --> A1_WMARK["Watermark Detection\nPhát hiện ảnh sao chép"]
    A1_COPY --> A1_GATE["Validation Gate"]
    A1_TAG --> A1_GATE
    A1_QUAL --> A1_GATE
    A1_GATE --> A1_PASS["✅ PASS\nSave JSON to PostgreSQL"]
    A1_GATE --> A1_FAIL["❌ FAIL\nSet Draft + Email Landlord"]
    A1_PASS --> A1_EVENT["Emit Event:\nlisting.approved"]

    %% AGENT 2
    A2["💬 Agent 2\nSuper Broker"]
    A1_EVENT --> A2_IDX["Index Listing\nvào Qdrant Vector DB"]
    A2 --> A2_T["Trigger: Tenant Query\n(Chat / Voice)"]
    A2_T --> A2_INT["Intent Extraction\n(gemini-1.5-flash)"]
    A2_INT --> A2_CONST["Constraint Parsing\nMax_Price, Pet_Friendly,\nMax_Commute_Time"]
    A2_CONST --> A2_VEC["Vector Search\nQdrant Similarity Search"]
    A2_IDX --> A2_VEC
    A2_VEC --> A2_RAG["RAG Reasoning\nTop 3 + Giải thích lý do"]
    A2_RAG --> A2_OUT["Output:\nPersonalized Recommendations\n+ Schedule Viewing Link"]

    %% AGENT 3
    A3["🛠️ Agent 3\nSmart Concierge"]
    A3 --> A3_T["Trigger: POST /maintenance\n(Tenant báo sự cố)"]
    A3_T --> A3_TRI["Triage Engine\n(gemini-1.5-flash)"]
    A3_TRI --> A3_URG["🚨 URGENT\nVỡ ống, Cháy nổ"]
    A3_TRI --> A3_NRM["📋 NORMAL\nBóng đèn, Điều hoà"]
    A3_URG --> A3_DISP["Immediate Dispatch\nEmail to Technician"]
    A3_NRM --> A3_QUEUE["Queue Assign\nNext Available Slot"]
    A3_DISP --> A3_SYNC["Multi-party Sync\nUpdate: Tenant + Landlord"]
    A3_QUEUE --> A3_SYNC
    A3_SYNC --> A3_STATUS["Status Tracking\nTiếp nhận → Đang sửa → Hoàn thành"]
    A3_STATUS --> A3_CSAT["CSAT Survey\nAuto-send on ticket close"]

    %% AGENT 4
    A4["💰 Agent 4\nContract & Admin"]
    A4 --> A4_T1["Trigger 1: Monthly Cron\nBilling Cycle"]
    A4 --> A4_T2["Trigger 2: Bank Webhook\nPayment Received"]
    A4 --> A4_T3["Trigger 3: Manual Input\nĐiện/Nước readings"]
    A4_T1 --> A4_CALC["Dynamic Calculation\nĐiện + Nước + Phí QL"]
    A4_T3 --> A4_CALC
    A4_CALC --> A4_PDF["PDF Generation\nHóa đơn + VietQR Code"]
    A4_PDF --> A4_EMAIL["Email Invoice\nto Tenant"]
    A4_T2 --> A4_RECON["Payment Reconciliation\nMatch Invoice ID → Gạch nợ"]
    A4_RECON --> A4_DUNNING{"Paid?"}
    A4_DUNNING --> |"Yes"| A4_CLOSE["Close Invoice\nUpdate DB"]
    A4_DUNNING --> |"No - Day 3"| A4_D1["Reminder Email\n(Lịch sự)"]
    A4_DUNNING --> |"No - Day 7"| A4_D2["Warning Email\n(Cảnh báo)"]
    A4_DUNNING --> |"No - Day 14"| A4_D3["Escalate to\nLandlord"]
    A4_CLOSE --> A4_REPORT["Cash Flow Report\ngửi Landlord cuối tháng"]
```

---

## 📡 PHẦN 3 — Redis Streams Event Map

Đây là bản đồ tất cả các **events** lưu chuyển qua Redis Streams:

| Stream Name | Producer | Consumer | Payload |
|---|---|---|---|
| `listing.approved` | Agent 1 | Agent 2 | `{listing_id, embedding_data, metadata}` |
| `listing.rejected` | Agent 1 | — | `{listing_id, reason, landlord_email}` |
| `viewing.scheduled` | Agent 2 | Agent 3 | `{tenant_id, listing_id, datetime}` |
| `maintenance.created` | Agent 3 | — | `{ticket_id, severity, unit_id}` |
| `maintenance.completed` | Agent 3 | Agent 4 | `{ticket_id, cost, unit_id}` |
| `invoice.generated` | Agent 4 | — | `{invoice_id, tenant_id, amount, pdf_url}` |
| `payment.received` | Agent 4 | — | `{invoice_id, amount, timestamp}` |

---

## 🗂️ PHẦN 4 — Folder Structure (Monorepo)

```
fastapi-ai-engine/
├── app/
│   ├── core/
│   │   ├── config.py          # Settings, env vars
│   │   ├── database.py        # PostgreSQL connection
│   │   ├── redis_streams.py   # Event bus client (shared)
│   │   └── gemini_client.py   # Shared Gemini client
│   │
│   ├── agents/
│   │   ├── listing_verifier/  # Agent 1 (đang xây)
│   │   │   ├── router.py
│   │   │   ├── nlp_pipeline.py
│   │   │   ├── vision_pipeline.py
│   │   │   └── service.py
│   │   │
│   │   ├── super_broker/      # Agent 2
│   │   │   ├── router.py
│   │   │   ├── intent_extractor.py
│   │   │   ├── qdrant_service.py
│   │   │   ├── rag_engine.py
│   │   │   └── service.py
│   │   │
│   │   ├── smart_concierge/   # Agent 3
│   │   │   ├── router.py
│   │   │   ├── triage_engine.py
│   │   │   ├── dispatcher.py  # Email SMTP
│   │   │   └── service.py
│   │   │
│   │   └── contract_admin/    # Agent 4
│   │       ├── router.py
│   │       ├── billing_engine.py
│   │       ├── pdf_generator.py
│   │       ├── vietqr_service.py
│   │       ├── reconciliation.py
│   │       ├── dunning.py
│   │       └── service.py
│   │
│   ├── models/                # SQLAlchemy models (shared)
│   │   ├── listing.py
│   │   ├── tenant.py
│   │   ├── invoice.py
│   │   └── maintenance.py
│   │
│   └── main.py                # FastAPI app entry
│
├── workers/
│   ├── stream_consumer.py     # Redis Streams consumer worker
│   └── cron_scheduler.py      # Monthly billing cron
│
├── docker-compose.yml         # PostgreSQL + Redis + Qdrant
└── requirements.txt
```

---

## ⚙️ PHẦN 5 — Tech Stack Summary

| Layer | Technology | Ghi chú |
|---|---|---|
| API Framework | FastAPI | Đang dùng |
| LLM | gemini-1.5-flash | Tất cả 4 agents |
| Agent Framework | Google Gemini Agent | Agents 2, 3, 4 |
| Vector Database | Qdrant | Agent 2 only |
| Main Database | PostgreSQL | Shared |
| Event Bus | Redis Streams | Shared |
| PDF Generation | WeasyPrint / ReportLab | Agent 4 |
| QR Code | VietQR standard | Agent 4 |
| Email | SMTP (smtplib / FastMail) | Agents 3, 4 |
| Container | Docker Compose | Local dev |

---

## 🔐 PHẦN 6 — Non-Functional Requirements

| Requirement | Value | Notes |
|---|---|---|
| Availability | 99% | Không cần HA phức tạp ở scale này |
| Response time (Agent 2) | < 3s | Chat UX yêu cầu |
| Response time (Agent 1) | < 30s | Vision AI + NLP pipeline |
| Data retention | 5 years | Hợp đồng, hóa đơn |
| Security | JWT Auth | Phân quyền landlord/tenant/admin |
| Privacy | Dữ liệu khách thuê | Không share giữa chủ nhà khác nhau |

---

## 📝 Decision Log

| # | Quyết định | Thay thế đã xét | Lý do chọn |
|---|---|---|---|
| D1 | Redis Streams làm event bus | Celery, Google Pub/Sub | Nhẹ nhất, đủ scale, không over-engineer |
| D2 | Qdrant làm vector DB | pgvector, Pinecone | Dedicated vector DB, dễ self-host, free |
| D3 | gemini-1.5-flash | GPT-4, Claude | Đồng bộ Google ecosystem, cost-effective |
| D4 | Email SMTP cho Agent 3 | Zalo OA, Telegram | Đơn giản nhất, đủ dùng giai đoạn đầu |
| D5 | Monorepo | Microservices riêng | Scale 100 căn → không cần complexity của microservices |

---

## 🚀 Implementation Roadmap

### Phase 1 — Foundation (Tuần 1–2)
- [x] Agent 1: Listing Verifier (đang xây)
- [ ] Setup Redis Streams client (shared)
- [ ] Setup Qdrant (Docker)
- [ ] Emit `listing.approved` event từ Agent 1

### Phase 2 — Agent 2 (Tuần 3–4)
- [ ] Qdrant indexing consumer (nhận `listing.approved`)
- [ ] Intent extraction với gemini-1.5-flash
- [ ] Vector search + RAG reasoning
- [ ] Chat API endpoint

### Phase 3 — Agent 3 (Tuần 5–6)
- [ ] Triage engine với Gemini
- [ ] Email SMTP dispatcher
- [ ] Ticket status tracking
- [ ] CSAT auto-send

### Phase 4 — Agent 4 (Tuần 7–8)
- [ ] Billing calculation engine
- [ ] PDF generation + VietQR
- [ ] Bank webhook receiver
- [ ] Dunning automation (3-7-14 day sequence)

