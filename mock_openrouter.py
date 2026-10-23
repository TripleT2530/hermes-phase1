from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class MockOpenRouterHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        req = json.loads(post_data)
        model = req.get("model", "")

        if "429" in model:
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error": "Rate Limit Exceeded"}')
        elif "500" in model:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "Internal Server Error"}')
        elif "404" in model:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Model Not Found"}')
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 123456789,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": f"Mock response from {model}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
            self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    print("Starting Mock OpenRouter on port 8080...")
    server = HTTPServer(('0.0.0.0', 8080), MockOpenRouterHandler)
    server.serve_forever()