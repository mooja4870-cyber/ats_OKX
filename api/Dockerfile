# ═══════════════════════════════════════════════════
# CryptoAI Master — API Dockerfile
# FastAPI + Uvicorn 서버
# ═══════════════════════════════════════════════════

FROM python:3.11-slim AS base

# 시스템 의존성
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 의존성 설치 (캐시 레이어) ──
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── 소스 복사 ──
COPY . .

# ── 환경 변수 ──
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul

# ── 포트 ──
EXPOSE 8000

# ── 헬스체크 ──
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ── 실행 ──
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
