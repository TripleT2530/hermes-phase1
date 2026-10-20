import sqlite3
import uuid
import os
from typing import List

class MemoryManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("SQLITE_PATH", "/data/hermes.db")

    def add_candidate_memory(self, mem_type: str, content: str, confidence: float) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            new_id = f"mem-{str(uuid.uuid4())}"
            cursor.execute("""
                INSERT INTO memory_items (id, type, content, confidence, status)
                VALUES (?, ?, ?, ?, 'candidate')
            """, (new_id, mem_type, content, confidence))
            conn.commit()
            return new_id
        finally:
            conn.close()

    def get_approved_context(self, query_keyword: str) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT content FROM memory_items 
                WHERE status = 'approved' AND content LIKE ?
            """, (f"%{query_keyword}%",))
            results = cursor.fetchall()
            return [r[0] for r in results]
        finally:
            conn.close()