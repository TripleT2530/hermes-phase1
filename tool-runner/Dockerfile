FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic
COPY tool-runner/main.py .

# [FIX] สร้าง Non-root User ชื่อ sandbox (UID 1001)
RUN useradd -m -u 1001 sandbox
# ให้สิทธิ์ sandbox เป็นเจ้าของโฟลเดอร์ /app
RUN chown -R sandbox:sandbox /app

# [FIX] สลับไปรันด้วย User sandbox แทน root
USER sandbox

EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
