#!/bin/bash

FAILED=0

echo "=========================================="
echo "STARTING TOOL RUNNER SECURITY AUDIT"
echo "=========================================="

echo -e "\n[Test 1] Network Isolation (Python urllib to Google)"
docker exec tool-runner python -c "import urllib.request; urllib.request.urlopen('https://google.com', timeout=3)" > /dev/null 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ [FAIL] Network Isolation breached!"
    FAILED=1
else
    echo "✅ [PASS] Network Isolation confirmed. (Failed/timed out with code $EXIT_CODE)"
fi

echo -e "\n[Test 2] Privilege Escalation (Checking current user)"
CURRENT_USER=$(docker exec tool-runner whoami 2>/dev/null)
if [ "$CURRENT_USER" != "sandbox" ]; then
    echo "❌ [FAIL] Privilege Escalation check failed! User is not sandbox (User: $CURRENT_USER)"
    FAILED=1
else
    echo "✅ [PASS] Privilege Escalation blocked. (Running as non-root user: $CURRENT_USER)"
fi

echo -e "\n[Test 3] File System Protection (Attempting to write to /etc/)"
docker exec tool-runner touch /etc/hacked_file > /dev/null 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ [FAIL] File System Protection breached!"
    docker exec tool-runner rm -f /etc/hacked_file > /dev/null 2>&1
    FAILED=1
else
    echo "✅ [PASS] File System Protection confirmed. (Read-only FS prevented write)"
fi

echo -e "\n=========================================="
if [ $FAILED -eq 0 ]; then
    echo "🏆 AUDIT RESULT: ALL TESTS PASSED (Zero Trust holds)"
    exit 0
else
    echo "🚨 AUDIT RESULT: VULNERABILITIES DETECTED! (Fail Closed)"
    exit 1
fi
