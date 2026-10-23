import sys
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
DB_PATH = temp_db.name
os.environ["SQLITE_PATH"] = DB_PATH
os.environ["REDIS_URL"] = "redis://localhost:6379/0" 

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '05_CORE')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'core')))

redis_patcher = patch('redis.asyncio.from_url')
mock_redis_from_url = redis_patcher.start()
mock_redis_client = MagicMock()
mock_redis_client.ping.return_value = True
mock_redis_client.setex.return_value = True
mock_redis_from_url.return_value = mock_redis_client

from planner import ModelPlanner
from memory import MemoryManager
from main import app, init_db
from fastapi.testclient import TestClient

class TestPhase3Logic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db() # สร้างตารางพื้นฐาน
        
        # [FIX] สร้างตาราง Phase 3 ใน Temp DB สำหรับการทดสอบ
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS model_registry (canonical_slug TEXT PRIMARY KEY, model_name TEXT, provider TEXT, context_window INTEGER, input_price REAL, output_price REAL, last_synced_at DATETIME DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS memory_items (id TEXT PRIMARY KEY, type TEXT, content TEXT, confidence REAL, status TEXT, approved_by TEXT, version INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS worker_packets (task_id TEXT PRIMARY KEY, version INTEGER, objective TEXT, status TEXT, payload TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP);
            """)
            
            # Seed ข้อมูล
            c.execute("INSERT INTO model_registry (canonical_slug, model_name, provider, context_window, input_price, output_price) VALUES ('cheap-model', 'Cheap Model', 'test', 8192, 0.1, 0.2)")
            c.execute("INSERT INTO model_registry (canonical_slug, model_name, provider, context_window, input_price, output_price) VALUES ('big-model', 'Big Context', 'test', 128000, 1.0, 2.0)")
            conn.commit()

        cls.client = TestClient(app)
        cls.planner = ModelPlanner(db_path=DB_PATH)
        cls.memory = MemoryManager(db_path=DB_PATH)

    def test_1_planner_routing(self):
        print("\n--- Testing ModelPlanner ---")
        cheap_candidates = self.planner.get_routing_candidates(task_profile="simple")
        self.assertTrue(len(cheap_candidates) > 0)
        self.assertEqual(cheap_candidates[0]['canonical_slug'], 'cheap-model')
        print("✅ PASS: Simple task routed to cheapest model.")
        
        complex_candidates = self.planner.get_routing_candidates(task_profile="complex")
        self.assertTrue(len(complex_candidates) > 0)
        self.assertEqual(complex_candidates[0]['canonical_slug'], 'big-model')
        print("✅ PASS: Complex task routed to largest context model.")

    def test_2_memory_governance(self):
        print("\n--- Testing MemoryManager ---")
        mem_id = self.memory.add_candidate_memory(mem_type="fact", content="Guerrilla Trading is secret", confidence=0.9)
        context_candidate = self.memory.get_approved_context("Guerrilla")
        self.assertEqual(len(context_candidate), 0)
        print("✅ PASS: Candidate memory is invisible to context retrieval.")
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE memory_items SET status = 'approved' WHERE id = ?", (mem_id,))
            conn.commit()
            
        context_approved = self.memory.get_approved_context("Guerrilla")
        self.assertEqual(len(context_approved), 1)
        self.assertEqual(context_approved[0], "Guerrilla Trading is secret")
        print("✅ PASS: Approved memory is successfully retrieved.")

    def test_3_worker_state_machine(self):
        print("\n--- Testing Worker State Machine ---")
        task_id = "task-123"
        res_create = self.client.post("/v1/worker/task", json={"task_id": task_id, "objective": "Do something", "payload": {"data": "test"}})
        self.assertEqual(res_create.status_code, 200)
        
        res_invalid = self.client.post(f"/v1/worker/response?task_id={task_id}", json={"new_status": "COMPLETED", "response_payload": {"result": "done"}})
        self.assertEqual(res_invalid.status_code, 400)
        self.assertIn("Invalid transition", res_invalid.json()["detail"])
        print("✅ PASS: System blocked invalid state transition.")
        
        res_valid = self.client.post(f"/v1/worker/response?task_id={task_id}", json={"new_status": "UNDERSTANDING_RECEIVED", "response_payload": {"understanding": "yes"}})
        self.assertEqual(res_valid.status_code, 200)
        print("✅ PASS: System allowed valid state transition.")

    @classmethod
    def tearDownClass(cls):
        redis_patcher.stop()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

if __name__ == '__main__':
    print("==========================================")
    print("STARTING PHASE 3.3 LOCAL TESTS")
    print("==========================================")
    unittest.main(verbosity=2)
