FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY src/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

COPY src/ /app/

ENV FLASK_APP=flask_server.py
EXPOSE 5010

# Serve the Flask app wrapped as ASGI using uvicorn
CMD ["uvicorn", "asgi_app:asgi_app", "--host", "0.0.0.0", "--port", "5010"]
