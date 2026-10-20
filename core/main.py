from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import os, json, time, hashlib, sqlite3, logging, base64
from contextlib import contextmanager
import redis, httpx
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '05_CORE')))
from planner import ModelPlanner
from memory import MemoryManager

REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379/0")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/hermes.db")
TOOL_URL    = os.getenv("TOOL_RUNNER_URL", "http://tool-runner:9000")
REGISTRY    = os.getenv("SCRIPT_HASH_REGISTRY", "/data/script_hashes.json")
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %hmessage)s")
log = logging.getLogger("hermes-core")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, actor TEXT NOT NULL, score_delta REAL NOT NULL, trust_score REAL NOT NULL, reason TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lessons_learned (id INTEGER PRIMARY KEY AUTOINCREMENT, context TEXT NOT NULL, mistake TEXT NOT NULL, correction TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, last_seen INTEGER NOT NULL, metadata TEXT);
CREATE TABLE IF NOT EXISTS tool_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, script_hash TEXT NOT NULL, approved INTEGER NOT NULL, output TEXT, error TEXT, created_at INTEGER NOT NULL);
CCREATE TABLE IF NOT EXISTS memory_items (id TEXT PRIMARY KEY, type TEXT NOT NULL CHECK(type IN ('fact', 'preference', 'lesson', 'skill', 'dna_proposal', 'trust_event')), content TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.0 CHECK(confidence >= 0.0 AND confidence <= 1.0), status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate', 'approved', 'retired')), approved_by TEXT DEFAULT NULL, version INTEGER NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'IDEA' CHECK(status IN ('IDEA', 'DRAFT', 'WORKER_RETURNED', 'M_REVIEWING', 'REVISION_REQUIRED', 'REVIEWED', 'APPROVED', 'REJECTED', 'RETIRED')), hash TEXT NOT NULL, author TEXT NOT NULL, parent_artifact_id TEXT DEFAULT NULL, parent_version INTEGER NOT NULL, related_task TEXT DEFAULT NULL, test_status TEXT DEFAULT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (artifact_id, version), FOREIGN KEY (parent_artifact_id, parent_version) REFERENCES artifacts(artifact_id, version) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS worker_packets (task_id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 1, objective TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT', 'SENT', 'UNDERSTANDING_RECEIVED', 'APPROVED_TO_EXECUTE', 'COMPLETED', 'FAILED', 'REJECTED')), payload TEXT NOT NULL CHECK(json_valid(payload)), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
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
    redis_client.setex(key, SESSION_TTL, json.dumps([m.dict() for m in req.messages[-5]]))
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,,?)",
            (sid, "commander", int(time.time()), json.dumps({"model": req.model}))
        )
    text = f"[Hermes Core v5.2.1] recv={len(req.messages)} msgs."
    return {
        "id": f"chatcmplm{int(time.time()*1000)}",
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
        raise HTTPException(403, "hash verification failed - Fail Closed")
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
        cursor.execute("SELECT status FROM worker_packets WHERE \Ú×ÚYHÈ‹
\Ú×ÚY
JBˆ›İÈHİ\œÛÜ‹™™]ÚÛ™J
BˆYˆ›İ›İÎˆ˜Z\ÙH^Ù\[ÛŠİ]\×ØÛÙOM]Z[H•\ÚÈ›İ›İ[™ŠBˆİ\œ™[Üİ]\ÈH›İÖÌBˆ[İÙYÛ™^Üİ]\ÈHSQÕS”ÒUSÓ”Ë™Ù]
İ\œ™[Üİ]\Ë×JBˆYˆ™\Ë›™]×Üİ]\È›İ[ˆ[İÙYÛ™^Üİ]\Î‚ˆ˜Z\ÙH^Ù\[ÛŠİ]\×ØÛÙOM]Z[Yˆ’[˜[Y˜[œÚ][Ûˆœ›ÛH	ŞØİ\œ™[Üİ]\ßIÈÈ	ŞÜ™\Ë›™]×Üİ]\ßIËˆ˜Z[ÛÜÙYˆŠBˆİ\œÛÜ‹™^Xİ]J•TUHÛÜšÙ\—ÜXÚÙ]ÈÑUİ]\ÈHË^[ØYHœÛÛ—Ü]Ú
^[ØYÊHÒT‘H\Ú×ÚYHÈ‹
™\Ë›™]×Üİ]\ËœÛÛ‹™[\Ê™\Ëœ™\ÜÛœÙWÜ^[ØY
K\Ú×ÚY
JBˆÛÛ›‹˜ÛÛ[Z]

Bˆ™]\›ˆÈœİ]\Èˆ”ÕUWÕTUQ‹›™]×Üİ]Hˆ™\Ë›™]×Üİ]\ßBˆš[˜[N‚ˆÛÛ›‹˜ÛÜÙJ
