FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir aider-chat requests ccxt==4.3.95 pandas==2.2.2 numpy==1.26.4 matplotlib==3.9.0

COPY . .

CMD ["python", "main.py"]
