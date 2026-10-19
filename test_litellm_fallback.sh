#!/bin/bash
CONFIG_FILE="./litellm_config.yaml"
LITELLM_URL="http://localhost:4000/v1/chat/completions"
AUTH_HEADER="Authorization: Bearer sk-1234"
echo "--- [TEST] LiteLLM Fallback Quality Gate (Real Error) ---"
if [ ! -f "$CONFIG_FILE" ]; then echo "[FAIL] ไม่พบไฟล์ $CONFIG_FILE"; exit 1; fi
cp "$CONFIG_FILE" "${CONFIG_FILE}.bak"
sed -i 's|api_key: "os.environ/OPENROUTER_API_KEY"|api_key: "sk-fake-key-to-force-401-error"|g' "$CONFIG_FILE"
if ! grep -q "sk-fake-key-to-force-401-error" "$CONFIG_FILE"; then echo "[FAIL] sed ไม่สามารถแก้ไข API Key ได้"; mv "${CONFIG_FILE}.bak" "$CONFIG_FILE"; exit 1; fi
echo "[PASS] sed ทำงานสำเร็จ: พบ API Key ปลอมใน Config"
docker restart litellm > /dev/null 2>&1
sleep 5
RESPONSE=$(curl -s -X POST $LITELLM_URL -H "Content-Type: application/json" -H "$AUTH_HEADER" -d '{"model": "hermes-brain-primary", "messages": [{"role": "user", "content": "Hello, this is a fallback test."}], "max_tokens": 10}')
mv "${CONFIG_FILE}.bak" "$CONFIG_FILE"
docker restart litellm > /dev/null 2>&1
if echo "$RESPONSE" | grep -q '"error"'; then echo "[FAIL] LiteLLM ไม่สลับไป Fallback: $RESPONSE"; exit 1
elif echo "$RESPONSE" | grep -q '"choices"'; then echo "[PASS] LiteLLM Fallback สำเร็จ"; else echo "[FAIL] ไม่ได้รับ Response: $RESPONSE"; exit 1; fi
