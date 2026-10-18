"""
Hermes Core — Phase 1
Blueprint v5.1 | Zero Trust | Fail Closed
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
import os, json, time, hashlib, sqlite3, logging, base64
from contextlib import contextmanager
import redis, httpx

REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379/0")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/hermes.db")
TOOL_URL    = os.getenv("TOOL_RUNNER_URL", "http://tool-runner:9000")
REGISTRY    = os.getenv("SCRIPT_HASH_REGISTRY", "/data/script_hashes.json")
SESSION_TTL = int(os.getenv("SESSION_TTL", "3600"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("hermes-core")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL, actor TEXT NOT NULL,
  score_delta REAL NOT NULL, trust_score REAL NOT NULL,
  reason TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lessons_learned (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  context TEXT NOT NULL, mistake TEXT NOT NULL,
  correction TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
  last_seen INTEGER NOT NULL, metadata TEXT);
CREATE TABLE IF NOT EXISTS tool_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  script_hash TEXT NOT NULL, approved INTEGER NOT NULL,
  output TEXT, error TEXT, created_at INTEGER NOT NULL);
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

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def load_registry() -> Dict[str, str]:
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY) as f:
        return json.load(f)

def verify_script(name: str, data: bytes) -> bool:
    reg = load_registry()
    if name not in reg:
        log.warning(f"REJECT — script not registered: {name}")
        return False
    if sha256_bytes(data) != reg[name]:
        log.error(f"REJECT — hash mismatch: {name}")
        return False
    return True

def record_trust(event: str, actor: str, delta: float, reason: str) -> float:
    with db() as c:
        row = c.execute(
            "SELECT trust_score FROM trust_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        cur = row["trust_score"] if row else 0.5
        new = max(0.0, min(1.0, cur + delta))
        c.execute(
            "INSERT INTO trust_ledger "
            "(event_type,actor,score_delta,trust_score,reason,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (event, actor, delta, new, reason, int(time.time()))
        )
        return new

def current_trust() -> float:
    with db() as c:
        row = c.execute(
            "SELECT trust_score FROM trust_ledger ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["trust_score"] if row else 0.5

app = FastAPI(title="Hermes Core", version="5.1.0")

@app.on_event("startup")
async def _start():
    init_db()
    log.info(f"Core up | SQLite={SQLITE_PATH} | Redis={REDIS_URL}")

@app.get("/healthz")
async def healthz():
    out = {"status": "ok", "trust": current_trust()}
    try:
        redis_client.ping(); out["redis"] = "ok"
    except Exception as e:
        out["redis"] = f"fail:{e}"; out["status"] = "degraded"
    return out

# ── OpenAI-compatible models ────────────────────────────
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

    # Cache session (token savings)
    redis_client.setex(key, SESSION_TTL, json.dumps([m.dict() for m in req.messages[-5:]]))

    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)",
            (sid, "commander", int(time.time()), json.dumps({"model": req.model}))
        )

    text = (
        f"[Hermes Core v5.1 — Phase 1 scaffold] "
        f"recv={len(req.messages)} msgs, trust={current_trust():.2f}. "
        f"LLM routing activates Phase 2 (LiteLLM)."
    )
    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": sum(len(m.content.split()) for m in req.messages),
                  "completion_tokens": len(text.split()),
                  "total_tokens": sum(len(m.content.split()) for m in req.messages) + len(text.split())}
    }

# ── Tool execution (Zero Trust: hash-verified before dispatch) ──
class ToolReq(BaseModel):
    script_name: str
    script_b64: str
    args: List[str] = []

@app.post("/v1/tools/execute")
async def tool(req: ToolReq):
    try:
        data = base64.b64decode(req.script_b64)
    except Exception:
        raise HTTPException(400, "invalid base64")

    if not verify_script(req.script_name, data):
        record_trust("tool_rejected", "system", -0.10, f"hash: {req.script_name}")
        raise HTTPException(403, "hash verification failed — Fail Closed")

    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{TOOL_URL}/run",
                             json={"script_b64": req.script_b64, "args": req.args})
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        record_trust("tool_error", "tool-runner", -0.05, str(e))
        raise HTTPException(502, f"tool runner: {e}")

    with db() as c:
        c.execute(
            "INSERT INTO tool_runs (script_hash,approved,output,error,created_at) "
            "VALUES (?,?,?,?,?)",
            (sha256_bytes(data), 1, json.dumps(result.get("stdout")), None, int(time.time()))
        )
    record_trust("tool_approved", "system", 0.01, f"run: {req.script_name}")
    return result

# ── Trust API ───────────────────────────────────────────
@app.get("/v1/trust/score")
async def ts(): return {"trust_score": current_trust()}

@app.get("/v1/trust/ledger")
async def tl(limit: int = 100):
    with db() as c:
        rows = c.execute(
            "SELECT * FROM trust_ledger ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"current": current_trust(), "entries": [dict(r) for r in rows]}

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = int(time.time())
    owned_by: str = "cmdr-tum"

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [ModelInfo(id="hermes-v5")]
    }
