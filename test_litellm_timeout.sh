#!/bin/bash
echo "--- [TEST] LiteLLM Timeout & Fallback Resilience ---"
CONFIG_FILE="./litellm_config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then echo "[FAIL] ไม่พบไฟล์ $CONFIG_FILE"; exit 1; fi
cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
sed -i '/model_name: "hermes-brain-primary"/,/model_name: "hermes-brain-fallback"/ s|api_key: "os.environ/OPENROUTER_API_KEY"|api_key: "os.environ/OPENROUTER_API_KEY"\n      api_base: "http://10.255.255.1"\n      timeout: 3|' "$CONFIG_FILE"
if ! grep -q "timeout: 3" "$CONFIG_FILE"; then
    echo "[FAIL] sed ไม่สามารถแก้ไข Config ได้ - ยกเลิกการทดสอบ"
    mv "${CONFIG_FILE}.bak" "$CONFIG_FILE"
    exit 1
fi
docker restart litellm > /dev/null 2>&1
sleep 5
echo "[2] Sending request to blackholed endpoint (LiteLLM Internal Timeout: 3s)..."
START_TIME=$(date +%s)
RESPONSE=$(curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer sk-1234" \
  -d '{"model": "hermes-brain-primary", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}')
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
mv "${CONFIG_FILE}.bak" "$CONFIG_FILE"
docker restart litellm > /dev/null 2>&1
if [ $DURATION -gt 5 ]; then
    echo "[FAIL] Fallback ใช้เวลานานเกินไป ($DURATION วินาที) - Timeout/Fallback ทำงานช้ากว่าที่กำหนด"
    exit 1
fi
if echo "$RESPONSE" | grep -q '"choices"'; then
    echo "[PASS] LiteLLM Fallback สำเร็จ: ใช้เวลาเพียง ${DURATION}s (Timeout 3s + Fallback)"
else
    echo "[FAIL] LiteLLM ไม่สลับไป Fallback (ติด Timeout ที่ LiteLLM): $RESPONSE"
    exit 1
fi
