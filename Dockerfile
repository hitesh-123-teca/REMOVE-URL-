FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create health check endpoint
RUN echo "from http.server import BaseHTTPRequestHandler, HTTPServer\n\
class Handler(BaseHTTPRequestHandler):\n\
    def do_GET(self):\n\
        self.send_response(200)\n\
        self.end_headers()\n\
        self.wfile.write(b'OK')\n\
\n\
def run_server():\n\
    server = HTTPServer(('0.0.0.0', 8080), Handler)\n\
    server.serve_forever()\n\
\n\
if __name__ == '__main__':\n\
    run_server()" > health_check.py &

CMD ["python", "bot.py"]
