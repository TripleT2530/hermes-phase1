import os, uuid, time, random
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "hermes_test_collection"
VECTOR_SIZE = 1536
def run_test():
    client = QdrantClient(url=QDRANT_URL)
    if client.collection_exists(collection_name=COLLECTION_NAME):
        client.delete_collection(collection_name=COLLECTION_NAME)
    client.create_collection(collection_name=COLLECTION_NAME, vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))
    vector_target = [random.uniform(0, 1) for _ in range(VECTOR_SIZE)]
    vector_other = [random.uniform(0, 1) for _ in range(VECTOR_SIZE)]
    client.upsert(collection_name=COLLECTION_NAME, points=[
        PointStruct(id=str(uuid.uuid4()), vector=vector_target, payload={"content": "Guerrilla Trading Strategy"}),
        PointStruct(id=str(uuid.uuid4()), vector=vector_other, payload={"content": "Unrelated Document"})
    ])
    time.sleep(0.5)
    search_result = client.search(collection_name=COLLECTION_NAME, query_vector=vector_target, limit=1)
    if not search_result: print("[FAIL] Qdrant Quality Gate: ไม่พบข้อมูล"); exit(1)
    if search_result[0].payload.get("content") == "Guerrilla Trading Strategy": print("[PASS] Qdrant Quality Gate: Retrieve ถูกต้อง")
    else: print("[FAIL] Qdrant Quality Gate: ดึงข้อมูลผิด"); exit(1)
if __name__ == "__main__": run_test()
