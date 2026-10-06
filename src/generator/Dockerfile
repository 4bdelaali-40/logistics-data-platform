FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY src/generator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/generator ./src/generator
