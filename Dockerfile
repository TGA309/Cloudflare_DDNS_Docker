FROM python:3.10-slim

LABEL maintainer="tga309"
LABEL version="1.0.0"
LABEL description="Cloudflare DDNS IP Updater"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application files
COPY update_cloudflare_ip.py .

# Set entrypoint
CMD ["python", "update_cloudflare_ip.py"]