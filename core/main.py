from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import os, json, time, hashlib, sqlite3, logging, base64
from contextlib import contextmanager
import httpx
import redis.asyncio as aioredis
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '05_CORE')))
from planner import ModelPlanner
from memory import MemoryManager

REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379/0")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/hermes.db")
TOOL_URL    = os.getenv("TOOL_RUNNER_URL", "http://tool-runner:9000")
REGISTRY    = os.getenv("SCRIPT_HASH_REGISTRY", "/data/script_hashes.json")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hermes-core")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, actor TEXT, score_delta REAL, trust_score REAL, reason TEXT, created_at INTEGER);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT, last_seen INTEGER, metadata TEXT);
CREATE TABLE IF NOT EXISTS tool_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, script_hash TEXT, approved INTEGER, output TEXT, error TEXT, created_at INTEGER);
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
    with db() as c: c.executescript(SCHEMA)

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
app = FastAPI(title="Hermes Core", version="5.2.1")

@app.on_event("startup")
async def _start():
    init_db()

@app.get("/healthz")
async def healthz():
    out = {"status": "ok"}
    try:
        await redis_client.ping(); out["redis"] = "ok"
    except Exception as e:
        out["redis"] = "fail"; out["status"] = "degraded"
    return out
class Msg(BaseModel):
    role: str; content: str

class ChatReq(BaseModel):
    model: str = "hermes-core"
    messages: List[Msg]
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    session_id: Optional[str] = None

@app.post("/v1/chat/completions")
async def chat(req: ChatReq):
    sid = req.session_id or f"s-{int(time.time()*1000)}"
    key = f"session:{sid}"
    await redis_client.setex(key, 3600, json.dumps([m.dict() for m in req.messages[-5:]]))
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)",
            (sid, "commander", int(time.time()), json.dumps({"model": req.model}))
        )
    text = f"[Hermes Core v5.2.1] recv={len(req.messages)} msgs."
    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
    }

class ToolReq(BaseModel):
    script_name: str
    script_b64: str
    args: List[str] = []

def load_registry() -> Dict[str, str]:
    if not os.path.exists(REGISTRY): return {}
    with open(REGISTRY) as f: return json.load(f)

def sha256_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()

@app.post("/v1/tools/execute")
async def tool(req: ToolReq):
    try:
        data = base64.b64decode(req.script_b64)
    except Exception:
        raise HTTPException(400, "invalid base64")
    reg = load_registry()
    if req.script_name not in reg or sha256_bytes(data) != reg[req.script_name]:
        raise HTTPException(403, "hash verification failed — Fail Closed")
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{TOOL_URL}/run", json={"script_b64": req.script_b64, "args": req.args})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"tool runner: {e}")
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
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO worker_packets (task_id, objective, payload, status) VALUES (?, ?, ?, 'SENT')", (packet.task_id, packet.objective, json.dumps(packet.payload)))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Task ID already exists")
    finally:
        conn.close()
    return {"status": "TASK_DISPATCHED", "task_id": packet.task_id}

@app.post("/v1/worker/response")
def receive_worker_response(task_id: str, res: WorkerResponse):
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM worker_packets WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if not row: raise HTTPException(status_code=404, detail="Task not found")
        current_status = row[0]
        allowed_next_states = VALID_TRANSITIONS.get(current_status, [])
        if res.new_status not in allowed_next_states:
            raise HTTPException(status_code=400, detail=f"Invalid transition from '{current_status}' to '{res.new_status}'. Fail Closed.")
        cursor.execute("UPDATE worker_packets SET status = ?, payload = json_patch(payload, ?) WHERE task_id = ?", (res.new_status, json.dumps(res.response_payload), task_id))
        conn.commit()
        return {"status": "STATE_UPDATED", "new_state": res.new_status}
    finally:
        conn.close()
