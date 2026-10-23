import sqlite3
import requests
import time
from datetime import datetime

DB_PATH = "09_DEPLOYMENT/hermes_registry.db" 
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models"

def sync_models():
    retries = 3
    backoff = 2
    for attempt in range(retries):
        try:
            response = requests.get(OPENROUTER_API_URL, timeout=10)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", backoff))
                print(f"⚠️ Rate limited. Retrying in {retry_after}s...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            models = response.json().get("data", [])
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS model_registry (
                    canonical_slug TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    context_window INTEGER,
                    input_price REAL,
                    output_price REAL,
                    last_synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            for m in models:
                canonical_slug = m.get("id", "")
                model_name = m.get("name", canonical_slug)
                provider = canonical_slug.split("/")[0] if "/" in canonical_slug else "openrouter"
                context_window = m.get("context_length", 0)
                pricing = m.get("pricing", {})
                input_price = float(pricing.get("prompt", 0.0))
                output_price = float(pricing.get("completion", 0.0))
                cursor.execute('''
                    INSERT OR REPLACE INTO model_registry 
                    (canonical_slug, model_name, provider, context_window, input_price, output_price, last_synced_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (canonical_slug, model_name, provider, context_window, input_price, output_price, now))
            conn.commit()
            conn.close()
            print(f"[{now}] ✅ Model registry synced successfully.")
            break
        except Exception as e:
            print(f"❌ [FAIL CLOSED] Sync failed: {e}")
            break

if __name__ == "__main__":
    sync_models()
