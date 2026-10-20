from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import os, json, time, hashlib, sqlite3, logging, base64
from contextlib import contextmanager
import redis, httpx
import sys

# เพิ่ม Path เพื่อให้ Import ไฟล์ใน 05_CORE ได้
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '05_CORE')))
from planner import ModelPlanner
from memory import MemoryManager

REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379/0")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/hermes.db")
TOOL_URL    = os.getenv("TOOL_RUNNER_URL", "http://tool-runner:9000")
REGISTRY    = os.getenv("SCRIPT_HASH_REGISTRY", "/data/script_hashes.json")
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hermes-core")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, actor TEXT NOT NULL, score_delta REAL NOT NULL, trust_score REAL NOT NULL, reason TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lessons_learned (id INTEGER PRIMARY KEY AUTOINCREMENT, context TEXT NOT NULL, mistake TEXT NOT NULL, correction TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, last_seen INTEGER NOT NULL, metadata TEXT);
CREATE TABLE IF NOT EXISTS tool_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, script_hash TEXT NOT NULL, approved INTEGER NOT NULL, output TEXT, error TEXT, created_at INTEGER NOT NULL);
"""

@contextmanager
def db():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn; conn.commit()
    finally:
        conn.close()

def init_db():
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)
app = FastAPI(title="Hermes Core", version="5.2.1")

@app.on_event("startup")
async def _start():
    init_db()
    log.info(f"Core up | SQLite={SQLITE_PATH} | Redis={REDIS_URL}")

@app.get("/healthz")
async def healthz():
    out = {"status": "ok", "trust": 0.5}
    try:
        redis_client.ping(); out["redis"] = "ok"
    except Exception as e:
        out["redis"] = f"fail:{e}"; out["status"] = "degraded"
    return out

# ... [ส่วน API เดิม: Chat, Tools, Trust คงไว้เหมือนเดิม] ...

# ==========================================
# [NEW] Phase 3.2: Worker Delegation Protocol
# ==========================================
VALID_TRANSITIONS = {
    "SENT": ["UNDERSTANDING_RECEIVED", "REJECTED"],
    "UNDERSTANDING_RECEIVED": ["APPROVED_TO_EXECUTE", "REJECTED"],
    "APPROVED_TO_EXECUTE": ["COMPLETED", "FAILED"]
}

class WorkerPacket(BaseModel):
    task_id: str
    objective: str
    payload: dict

class WorkerResponse(BaseModel):
    new_status: str
    response_payload: dict

@app.post("/v1/worker/task")
def create_worker_task(packet: WorkerPacket):
    """M ส่ง Task ให้ Worker (บันทึกลง DB)"""
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO worker_packets (task_id, objective, payload, status)
            VALUES (?, ?, ?, 'SENT')
        """, (packet.task_id, packet.objective, json.dumps(packet.payload)))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Task ID already exists")
    finally:
        conn.close()
    return {"status": "TASK_DISPATCHED", "task_id": packet.task_id}

@app.post("/v1/worker/response")
def receive_worker_response(task_id: str, res: WorkerResponse):
    """Worker ส่งผลลัพธ์กลับมา (เช็ค State Machine อย่างเคร่งครัด)"""
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    
    try:
        # 1. เช็คสถานะปัจจุบัน
        cursor.execute("SELECT status FROM worker_packets WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        
        current_status = row[0]
        
        # 2. ตรวจสอบ State Transition
        allowed_next_states = VALID_TRANSITIONS.get(current_status, [])
        if res.new_status not in allowed_next_states:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid transition from '{current_status}' to '{res.new_status}'. Fail Closed."
            )

        # 3. อัปเดต State และ Payload
        cursor.execute("""
            UPDATE worker_packets 
            SET status = ?, payload = json_patch(payload, ?) 
            WHERE task_id = ?
        """, (res.new_status, json.dumps(res.response_payload), task_id))
        conn.commit()
        return {"status": "STATE_UPDATED", "new_state": res.new_status}
    finally:
        conn.close()
