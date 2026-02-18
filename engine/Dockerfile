# ═══════════════════════════════════════════════════
# CryptoAI Master — Engine Dockerfile
# Python 3.11 기반 자동매매 엔진
# ═══════════════════════════════════════════════════

FROM python:3.11-slim AS base

# 시스템 의존성 (psycopg2-binary 빌드용)
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

# ── 소스 복사 (패키지 구조 유지) ──
COPY . ./engine

# ── 로그 디렉토리 ──
RUN mkdir -p /app/logs

# ── 환경 변수 ──
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul \
    PYTHONPATH=/app

# ── 헬스체크 ──
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "print('engine alive')" || exit 1

# ── 실행 (모듈 방식) ──
CMD ["python", "-m", "engine.main"]
