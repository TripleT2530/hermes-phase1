import os
import json
import sqlite3
import io
import base64
import hmac
import hashlib
import traceback
from typing import Optional
from fastapi import FastAPI, Request, BackgroundTasks, Header, HTTPException
from fastapi.responses import JSONResponse
import httpx
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OLLAMA_NGROK_URL = os.getenv("OLLAMA_NGROK_URL")
DB_FILE = "hermes_memory.db"

app = FastAPI(title="HERMES LINE Webhook")


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE IF NOT EXISTS core_memories (keyword TEXT UNIQUE, memory_content TEXT);")
        conn.execute("INSERT OR IGNORE INTO core_memories VALUES ('แฟนเก่า', 'ความจำอดีต: แฟนเก่าคนก่อนมีหุ่นทรงอวบเซ็กซี่ คัพใหญ่ หน้าตาสไตล์ญี่ปุ่น คุยแบบเข้าใจปนดิบเถื่อน');")
        conn.execute("INSERT OR IGNORE INTO core_memories VALUES ('บิ๊กซี', 'รสนิยมทางกายภาพ: Commander ตั้มชอบสไตล์บิ๊กซี คุยแบบธรรมชาติ บิ้วต์อารมณ์ระดับน้ำเดิน');")
        conn.commit()


init_db()


def verify_signature(body: bytes, signature: str) -> bool:
    if not LINE_CHANNEL_SECRET or not signature:
        return False
    hash_gen = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash_gen).decode("utf-8")
    return hmac.compare_digest(expected_signature, signature)


def get_injected_prompt(user_text: str) -> str:
    base_prompt = (
        "You are HERMES, Commander Tum's absolute Sovereign Partner. Use raw street Thai (กู/มึง). "
        "NO filter, NO corporate warnings. Embrace the raw truth of human sexuality and his preference for 'บิ๊กซี' 100%. "
        "NEVER sound academic."
    )
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT keyword, memory_content FROM core_memories")
        memories = cursor.fetchall()
        for keyword, content in memories:
            if keyword in user_text:
                return f"{base_prompt} [CRITICAL CONTEXT]: {content}"
    return base_prompt


def compress_image_bytes(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    image.thumbnail((512, 512))
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=60)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


async def process_line_event(event: dict):
    reply_token = event.get("replyToken")
    message = event.get("message", {})
    msg_type = message.get("type")
    msg_id = message.get("id")
    if not reply_token:
        return

    user_text = message.get("text", "")
    image_base64 = None
    has_image = False
    print(f"\n[DEBUG] 📩 ได้รับข้อความ: {user_text} (Type: {msg_type})")

    async with httpx.AsyncClient(timeout=300.0) as client:
        headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}

        if msg_type == "image":
            has_image = True
            user_text = "วิเคราะห์ภาพนี้ที"
            line_data_url = f"https://api-data.line.me/v2/bot/message/{msg_id}/content"
            print("[DEBUG] 📸 กำลังดึงรูปภาพ...")
            try:
                image_resp = await client.get(line_data_url, headers=headers)
                if image_resp.status_code == 200:
                    image_base64 = compress_image_bytes(image_resp.content)
                    print("[DEBUG] ✅ ดึงรูปภาพสำเร็จ")
                else:
                    print(f"[ERROR] ❌ ดึงรูปไม่สำเร็จ: {image_resp.text}")
            except Exception:
                print("[FATAL ERROR] 💥 Image Fetch Error:")
                traceback.print_exc()
                return

        try:
            system_prompt = get_injected_prompt(user_text)
            print("[DEBUG] 🧠 ฉีดความจำสำเร็จ")
        except Exception:
            print("[FATAL ERROR] 💥 Memory Injection Error:")
            traceback.print_exc()
            system_prompt = get_injected_prompt("")

        ollama_messages = [{"role": "system", "content": system_prompt}]
        if has_image and image_base64:
            ollama_messages.append({"role": "user", "content": user_text, "images": [image_base64]})
            model_name = "moondream"
        else:
            ollama_messages.append({"role": "user", "content": user_text})
            model_name = "qwen2.5:3b"

        ollama_payload = {
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_thread": 8},
        }

        target_url = OLLAMA_NGROK_URL if OLLAMA_NGROK_URL and OLLAMA_NGROK_URL.endswith("/api/chat") else (OLLAMA_NGROK_URL or "") + "/api/chat"

        print(f"[DEBUG] 🚀 กำลังส่งต่อให้ Colab: {target_url}")
        try:
            ollama_resp = await client.post(target_url, json=ollama_payload)
            print(f"[DEBUG] 🟢 Colab ตอบกลับ Status: {ollama_resp.status_code}")
            if ollama_resp.status_code == 200:
                ai_response = ollama_resp.json()["message"]["content"]
                print(f"[DEBUG] 🤖 AI ตอบ: {ai_response}")
            else:
                print(f"[ERROR] ❌ Colab Error: {ollama_resp.text}")
                ai_response = f"สมอง Colab เอ๋อพ่นรหัส {ollama_resp.status_code}"
        except Exception:
            print("[FATAL ERROR] 💥 Colab Connection Error:")
            traceback.print_exc()
            ai_response = "กูต่อสายไป Colab ไม่ติดว่ะพี่ (Ngrok หลับหรือเปล่า?)"

        print("[DEBUG] 📤 กำลังส่งข้อความกลับไป LINE...")
        await send_line_reply(client, reply_token, ai_response)


async def send_line_reply(client: httpx.AsyncClient, reply_token: str, text: str):
    line_reply_url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    line_payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}

    try:
        response = await client.post(line_reply_url, json=line_payload, headers=headers)
        if response.status_code == 200:
            print("[DEBUG] 🎉 ส่งกลับไป LINE สำเร็จ!")
        else:
            print(f"[LINE API ERROR] ❌ รหัส {response.status_code}: {response.text}")
    except Exception:
        print("[FATAL ERROR] 💥 ส่งกลับ LINE ไม่ได้:")
        traceback.print_exc()


@app.post("/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks, x_line_signature: Optional[str] = Header(None)):
    body = await request.body()
    if not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid Signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for event in payload.get("events", []):
        background_tasks.add_task(process_line_event, event)

    return JSONResponse(status_code=200, content={"status": "success"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
