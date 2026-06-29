FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    qt6-wayland \
    libqt6gui6 \
    libqt6widgets6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" enot
USER enot

ENTRYPOINT ["python", "enot_translator.py"]
