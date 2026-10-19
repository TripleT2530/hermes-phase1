#!/bin/bash
echo "--- [TEST] RAM Enforcer / OOM Killer Quality Gate ---"
docker run --name oom-test --rm --memory="50m" python:3.12-slim python -c "a = ' ' * 100 * 1024 * 1024; print(len(a))"
EXIT_CODE=$?
if [ $EXIT_CODE -eq 137 ]; then echo "[PASS] RAM Enforcer Quality Gate: Container ถูก Force-Kill (OOM) สำเร็จ"; else echo "[FAIL] RAM Enforcer ไม่ทำงาน"; exit 1; fi
