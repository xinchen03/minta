# Minta — Memory That Checks Itself
# All-in-one container: Data API (:8772) + MCP HTTP (:18721)
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY run.py .

VOLUME /data
ENV MINTA_DATABASE_URL=sqlite:////data/minta.db
ENV MINTA_ENV=production
ENV MINTA_EXPERT_ENABLED=true
ENV MINTA_AUTOPILOT_ENABLED=true

EXPOSE 8772 18721

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8772/health || exit 1

CMD ["python", "run.py"]
