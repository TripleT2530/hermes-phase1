# HERMES MASTER BLUEPRINT v5.2
**THE ULTIMATE BULLETPROOF & GOVERNED EDITION** | STATUS: COMPLETE & LOCKED
**Target Infrastructure:** Hetzner CX52 (16 vCPU, 32 GB RAM, 320 GB NVMe)
**Design Philosophy:** Zero Trust, Isolated Architecture, Fail Closed, Governance-First

---

## SECTION 1: THE SOUL & GOVERNANCE (DNA Architecture)
### 1.1 Core DNA (ห้ามระบบแก้เอง - ต้องมี Human Approval)
1. **Truth Above All:** แยกข้อเท็จจริง สมมติฐาน และข้อเสนอ
2. **Empirical Foundation:** อ้างอิงหลักฐานและทดสอบเมื่อทำได้
3. **Fail Closed:** ไม่รู้หรือไม่ปลอดภัยให้หยุดและรายงาน
4. **No Fabrication:** ห้ามแต่งแหล่งข้อมูล ผลการทดสอบ หรือผลลัพธ์
5. **Respectful Challenge:** กล้าทักท้วงด้วยเหตุผล
6. **Scope Discipline:** ไม่ทำเกินขอบเขตที่ได้รับอนุมัติ
7. **Privacy by Default:** ลดการเปิดเผยข้อมูล และ mask secret
8. **Reversible Change:** การเปลี่ยนแปลงสำคัญต้องย้อนกลับได้
9. **Human Gate:** งานเสี่ยงสูง หรืองานที่ย้อนกลับไม่ได้ต้องรออนุมัติ

### 1.2 Tum DNA (Working Style Profile)
* ต้องการงานที่คิดลึกและเห็นภาพรวม
* ชอบเชื่อมโยงหลายแนวคิดเป็นระบบเดียว
* ต้องการนวัตกรรมที่ไม่ทิ้งหลักการเดิม
* ให้ความสำคัญกับความพยายาม ความจริง ความรับผิดชอบ
* ต้องการให้ AI กล้าคิด กล้าท้าทาย และมองล่วงหน้า
* ไม่ต้องการคำตอบผิวเผินหรือคำปลอบใจ

### 1.3 The DNA Learning Cycle
* **Observe:** สังเกตคำสั่ง การแก้ไข และ feedback
* **Extract:** สกัดเป็น preference, lesson, method หรือ proposal
* **Validate:** เปรียบเทียบกับงานหลายชิ้น ตรวจความขัดแย้ง
* **Propose:** สร้าง DNA Proposal (proposal_id, hypothesis, expected_benefit, risk, test_plan)
* **Approve & Version:** รอพี่ตั้มอนุมัติก่อนสร้าง version ใหม่

---

## SECTION 2: THE WORKER PROTOCOL & ARTIFACT STATE MACHINE
### 2.1 Worker Delegation Protocol
M จะสร้าง Packet เพื่อส่งงานให้ Worker ตามฟอร์แมตนี้เท่านั้น:
TASK_ID:
VERSION:
ROLE: controlled worker under M
OBJECTIVE:
ALLOWED_CONTEXT:
INPUTS:
FILES_IN_SCOPE:
OUTPUT_REQUIRED:
CONSTRAINTS:
FORBIDDEN_ACTIONS:
DNA_RULES:
ACCEPTANCE_CRITERIA:
STOP_CONDITIONS:
RESPONSE_FORMAT:
*(Worker ต้องตอบกลับด้วย UNDERSTANDING, RISKS, READY: YES|NO ก่อนเริ่มงานเสมอ)*

### 2.2 Artifact State Machine
ทุกไฟล์ต้องมีสถานะ: IDEA → DRAFT → WORKER_RETURNED → M_REVIEWING → REVISION_REQUIRED / REVIEWED / APPROVED / REJECTED / RETIRED
*(ห้ามนำไฟล์ DRAFT หรือ REVIEWING ไปใช้เป็น Source of Truth เด็ดขาด)*

---

## SECTION 3: INFRASTRUCTURE & ARCHITECTURE
### 3.1 Target Hardware
* **Provider:** Hetzner, **Model:** CX52, **Specs:** 16 vCPU, 32 GB RAM, 320 GB NVMe, **OS:** Ubuntu 24.04 LTS

### 3.2 Core Stack (Phase 1)
1. Caddy (Reverse Proxy)
2. Open WebUI (Frontend)
3. Hermes Core (FastAPI Gateway)
4. Redis (Cache)
5. SQLite (Long-term Memory)
6. Tool Runner (Isolated No Internet)

### 3.3 The Arsenal (Phase 2+)
*(RAM Allocation: Core Stack 8GB + Arsenal 20GB + OS 4GB = 32GB)*
1. Qdrant (Vector DB): 8GB RAM
2. LiteLLM (AI Gateway): 4GB RAM
3. Langfuse (Observability): 4GB RAM
4. Firecrawl (Web Search): 4GB RAM

### 3.4 Repository Structure
Hermes/
├── 01_BLUEPRINT/
├── 02_DNA/
├── 03_CONTRACTS/
├── 04_DATABASE/
├── 05_CORE/
├── 06_WORKER_PACKETS/
├── 07_ARTIFACTS/
├── 08_TESTS/
└── 09_DEPLOYMENT/

---

## SECTION 4: MODEL REGISTRY & ROUTING ENGINE
### 4.1 SQLite Schema for Model Registry
CREATE TABLE model_registry (
  canonical_slug TEXT PRIMARY KEY,
  model_name TEXT NOT NULL,
  provider TEXT NOT NULL,
  context_window INTEGER,
  input_price REAL,
  output_price REAL,
  last_synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

### 4.2 Model Sync Frequency & Rate Limit
* Cronjob: รัน Sync ข้อมูลทุกๆ 3 ชั่วโมง
* Rate Limit: ใช้ Exponential Backoff เมื่อเจอ HTTP 429

### 4.3 Routing Logic (Planner)
Input Request → Task Profile → Memory Selection → Capability Resolution → Endpoint/Model Selection → Execute → Evaluate → Escalate หรือ Complete

---

## SECTION 5: MEMORY ARCHITECTURE & GUARDRAILS
### 5.1 Memory JSON Schema
{
  "id": "memory-0001",
  "type": "fact|preference|lesson|skill|dna_proposal|trust_event",
  "content": "...",
  "confidence": 0.0,
  "status": "candidate|approved|retired",
  "approved_by": null,
  "version": 1
}

### 5.2 Production Guardrails (Zero Trust)
1. LiteLLM Fallback
2. Persistent Trust Ledger
3. RAM Enforcer
4. SQLite Daily Backup

---

## SECTION 6: 4-PHASE ROADMAP
* Phase 1 (Done): Foundation
* Phase 2 (Done): Safety & Cognition (3S)
* Phase 3 (Next): Governance & Memory
* Phase 4: Autonomous Enterprise

---
**Version Control:**
- v5.2 (20 Oct 2026): Integrated Governance Layer + Model Registry.
- v5.2.1 (20 Oct 2026): Hardware Upgrade to Hetzner CX52 (32GB RAM).
