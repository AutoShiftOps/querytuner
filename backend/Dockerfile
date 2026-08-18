FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app ./app

# Expose port
EXPOSE 8000

# Run app
#
# --proxy-headers + --forwarded-allow-ips='*': Render terminates the client
# connection at its own edge/load balancer and forwards to this container,
# so without these flags Starlette's request.client is Render's internal
# proxy address on every request, not the real visitor's IP — silently
# breaking the per-IP rate limits in app/main.py (they'd all key off the
# same address instead of the actual caller). '*' is safe here because
# Render's edge is the only thing that can reach this container directly;
# nothing else can inject a spoofed X-Forwarded-For upstream of it.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
