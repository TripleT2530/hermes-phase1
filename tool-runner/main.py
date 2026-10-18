from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import base64, subprocess, tempfile, os
app = FastAPI(title="Tool Runner", version="5.1.0")

class RunReq(BaseModel):
    script_b64: str
    args: List[str] = []

@app.get("/healthz")
async def hz(): return {"status": "ok"}

@app.post("/run")
async def run(req: RunReq):
    try: data = base64.b64decode(req.script_b64)
    except Exception: raise HTTPException(400, "invalid base64")
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="wb") as f:
        f.write(data); path = f.name
    try:
        p = subprocess.run(["python", path, *req.args],
                           capture_output=True, text=True, timeout=25)
        return {"returncode": p.returncode,
                "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "timeout")
    finally:
        try: os.unlink(path)
        except Exception: pass
