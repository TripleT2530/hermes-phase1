import urllib.request
import urllib.error
import json

LITELLM_URL = "http://localhost:4000/v1/chat/completions"
HEADERS = {"Authorization": "Bearer sk-1234", "Content-Type": "application/json"}

def run_test(scenario_name, target_model, expected_http_code, expect_fallback=False):
    print(f"\n--- Testing {scenario_name} ---")
    payload = {
        "model": target_model,
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(LITELLM_URL, data=data, headers=HEADERS, method='POST')
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.status
            if status_code == 200:
                print(f"✅ [PASS] {scenario_name}: Success (Status 200)")
                if expect_fallback:
                    print("   (Fallback triggered successfully as expected)")
            else:
                print(f"❌ [FAIL] {scenario_name}: Unexpected Status {status_code}")
                
    except urllib.error.HTTPError as e:
        status_code = e.code
        if status_code == expected_http_code:
            if expect_fallback:
                print(f"❌ [FAIL] {scenario_name}: Fallback failed. Got {status_code} instead of 200.")
            else:
                print(f"✅ [PASS] {scenario_name}: Blocked correctly (Status {status_code})")
        else:
            print(f"❌ [FAIL] {scenario_name}: Unexpected Status {status_code}")
            
    except Exception as e:
        print(f"❌ [FAIL] {scenario_name}: Request Error - {e}")

if __name__ == '__main__':
    run_test("Scenario A (Success)", "hermes-primary", 200)
    run_test("Scenario B (429 Fallback)", "hermes-primary-429", 200, expect_fallback=True)
    run_test("Scenario C (500 Fallback)", "hermes-primary-500", 200, expect_fallback=True)
    run_test("Scenario D (404 Fail Closed)", "hermes-primary-404", 404, expect_fallback=False)
