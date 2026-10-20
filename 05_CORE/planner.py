import sqlite3
import os
from typing import List, Dict
from datetime import datetime, timedelta

class ModelPlanner:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("SQLITE_PATH", "/data/hermes.db")

    def get_routing_candidates(self, task_profile: str, require_vision: bool = False) -> List[Dict]:
        """เลือกโมเดลจาก Registry ตาม Profile และราคา (คืนค่าเป็น List เพื่อทำ Fallback)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 1. Base Query: กรองข้อมูลที่ Sync ภายใน 24 ชม. (ป้องกัน Deprecated Models)
            base_query = "SELECT * FROM model_registry WHERE last_synced_at >= datetime('now', '-1 day')"
            
            # 2. กรอง Vision (ใช้ LIKE ไปก่อนตามที่ Safe Harbor อนุมัติ)
            if require_vision:
                base_query += " AND (canonical_slug LIKE '%vision%' OR model_name LIKE '%vision%' OR canonical_slug LIKE '%vl%')"

            # 3. กรองตาม Profile
            if task_profile == "complex":
                base_query += " ORDER BY context_window DESC"
            else:
                # งานง่าย: เอาราคาถูกสุดขึ้นก่อน
                base_query += " ORDER BY input_price ASC"
            
            # 4. จำกัดแค่ 3 ตัวเพื่อทำ Fallback
            base_query += " LIMIT 3"

            cursor.execute(base_query)
            models = cursor.fetchall()

            # [DNA 26: Fail Closed]
            if not models:
                raise ValueError("[FATAL] No valid models found in registry (outdated or missing). Fail Closed.")
            
            return [dict(m) for m in models]

        finally:
            conn.close()
