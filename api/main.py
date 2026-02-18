"""
CryptoAI Master — FastAPI 메인 애플리케이션

■ 엔드포인트 구조:
    /                       → 루트 (API 정보)
    /health                 → 헬스체크
    /api/coins/scores       → AI 스코어링 결과
    /api/coins/prices/{sym} → 실시간 현재가
    /api/trades/order       → 수동 매수/매도 주문
    /api/trades/history     → 매매 이력
    /api/trades/positions   → 보유 포지션
    /api/system/status      → 시스템 상태
    /api/system/scheduler   → 스케줄러 상태
    /api/system/config      → 설정값

■ 실행:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

■ Swagger 문서:
    http://localhost:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

# ════════════════════════════════════════════════════
# 로깅 설정
# ════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cryptoai.api")


# ════════════════════════════════════════════════════
# 라이프사이클 (시작/종료 시 리소스 관리)
# ════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 DB 풀·캐시 초기화, 종료 시 정리"""
    logger.info("🚀 CryptoAI API 시작")
    # TODO: DB 커넥션 풀, Redis 연결 등 초기화
    # app.state.db = await create_db_pool()
    # app.state.redis = await create_redis()
    yield
    logger.info("🛑 CryptoAI API 종료")
    # TODO: 리소스 정리
    # await app.state.db.close()


# ════════════════════════════════════════════════════
# FastAPI 앱 생성
# ════════════════════════════════════════════════════

app = FastAPI(
    title="CryptoAI Master API",
    description=(
        "멀티팩터 AI 스코어링 기반 암호화폐 자동매매 시스템 API.\n\n"
        "## 주요 기능\n"
        "- 🤖 **AI 스코어링**: 5팩터(기술·모멘텀·변동·거래량·심리) 종합 분석\n"
        "- 💰 **자동 매매**: 스코어 기반 매수/매도 자동 실행\n"
        "- 📊 **실시간 데이터**: 업비트 실시간 시세 연동\n"
        "- 🛡️ **리스크 관리**: 손절/익절/트레일링 스탑 자동 적용\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ════════════════════════════════════════════════════
# 미들웨어
# ════════════════════════════════════════════════════

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Next.js 개발
        "http://localhost:3001",      # 대체 포트
        "http://127.0.0.1:3000",
        # TODO: 운영 도메인 추가
        # "https://yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 요청 로깅 + 실행시간 미들웨어 ──
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000  # ms

    # 헬스체크 로그 제외
    if request.url.path not in ("/health", "/favicon.ico"):
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )

    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    return response


# ════════════════════════════════════════════════════
# 글로벌 예외 핸들러
# ════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "내부 서버 오류",
            "detail": str(exc) if app.debug else "서버 내부 오류가 발생했습니다",
            "path": str(request.url.path),
        },
    )


# ════════════════════════════════════════════════════
# 라우터 등록
# ════════════════════════════════════════════════════

try:
    from api.routes import coins, trades, system  # noqa: E402  — 로컬 (PYTHONPATH=.)
except ImportError:
    from routes import coins, trades, system  # noqa: E402  — Docker (WORKDIR=/app)

app.include_router(coins.router, prefix="/api/coins", tags=["🪙 코인"])
app.include_router(trades.router, prefix="/api/trades", tags=["💰 매매"])
app.include_router(system.router, prefix="/api/system", tags=["⚙️ 시스템"])


# ════════════════════════════════════════════════════
# 루트 엔드포인트
# ════════════════════════════════════════════════════

@app.get("/", tags=["📋 기본"])
async def root():
    """API 루트 — 기본 정보 반환"""
    return {
        "name": "CryptoAI Master API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "coins": "/api/coins/scores",
            "trades": "/api/trades/order",
            "system": "/api/system/status",
        },
    }


@app.get("/health", tags=["📋 기본"])
async def health():
    """헬스체크 — 로드밸런서·모니터링 용"""
    return {
        "status": "healthy",
        "service": "cryptoai-api",
        "version": "1.0.0",
    }
