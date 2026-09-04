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
COPY scripts/fetch_eval_models.py ./scripts/fetch_eval_models.py

# AMC eval mode: bake the embedding model into the image (mirror fallback:
# huggingface.co -> hf-mirror.com). Override the repo via --build-arg.
ARG MINTA_EVAL_MODEL_REPO=sentence-transformers/all-mpnet-base-v2
RUN python scripts/fetch_eval_models.py \
        --repo ${MINTA_EVAL_MODEL_REPO} \
        --dest /models/${MINTA_EVAL_MODEL_REPO}
ENV MINTA_EVAL_EMBED_MODEL=/models/${MINTA_EVAL_MODEL_REPO}
# Business app embedding uses the same baked weights (fixes the previous
# Windows-path default that broke semantic search inside containers).
ENV MINTA_EMBEDDING_MODEL=/models/${MINTA_EVAL_MODEL_REPO}
# AMC cycle-2 default config (round-3/4 evidence, refined textual n=861):
# 1) rerank ON — 88MB cross-encoder (ms-marco), zero-LLM; best single-channel
#    proxy score 0.7422 over base 0.7329 / temporal-only 0.7375.
# 2) temporal boost ON — zero-LLM retrieval re-rank; temporal cat +2.8pt.
# Both env-off-able for A/B or Full#2 fallback.
ARG MINTA_EVAL_RERANK_REPO=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python scripts/fetch_eval_models.py \
        --kind ce --repo ${MINTA_EVAL_RERANK_REPO} \
        --dest /models/${MINTA_EVAL_RERANK_REPO}
ENV MINTA_EVAL_RERANK=1
ENV MINTA_EVAL_RERANK_MODEL=/models/${MINTA_EVAL_RERANK_REPO}
ENV MINTA_EVAL_TEMPORAL=1

VOLUME /data
ENV MINTA_DATABASE_URL=sqlite:////data/minta.db
ENV MINTA_EVAL_DB=sqlite:////data/eval.db
ENV MINTA_ENV=production
ENV MINTA_EXPERT_ENABLED=true
ENV MINTA_AUTOPILOT_ENABLED=true

EXPOSE 8772 18721

# Main app exposes /ping (the Dockerfile previously probed /health which only
# the MCP app and the eval app expose — the data API was always "unhealthy").
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8772/ping || exit 1

CMD ["python", "run.py"]
