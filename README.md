# 🤖 CryptoAI Master

> **멀티팩터 AI 스코어링 기반 암호화폐 자동매매 시스템**

5가지 요소(기술·모멘텀·변동성·거래량·심리)를 종합 분석하여 최적의 매매 시점을 자동으로 판단하고 실행합니다.

---

## 📸 스크린샷

| 대시보드 | API 문서 |
|----------|----------|
| ![Dashboard](web/public/screenshot-dashboard.png) | ![Swagger](web/public/screenshot-swagger.png) |

---

## 🏗️ 아키텍처

```
┌──────────────────────────────────────────────────┐
│                  CryptoAI Master                  │
├──────────┬──────────┬──────────┬────────────────┤
│  Engine  │   API    │   Web    │     Redis      │
│ (Python) │(FastAPI) │(Next.js) │   (캐시/PubSub) │
│          │          │          │                │
│ 스코어링  │ REST API │ 대시보드  │ 상태 캐시       │
│ 스케줄러  │ WebSocket│ 실시간 UI │ 잡 큐          │
│ 주문 실행 │ Swagger  │ 차트     │                │
└──────────┴──────────┴──────────┴────────────────┘
     │           │           │           │
     └───────────┴───────────┴───────────┘
                      │
              docker-compose.yml
```

---

## 🚀 빠른 시작

### 1. 환경변수 설정

```bash
cp shared/.env.example shared/.env
# shared/.env 파일을 열어 API 키 등을 설정하세요
```

### 2. Docker Compose 실행 (권장)

```bash
# 전체 시스템 빌드 + 시작
docker-compose up -d --build

# 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f engine     # 엔진 로그
docker-compose logs -f api        # API 로그
docker-compose logs -f web        # 웹 로그

# 종료
docker-compose down

# 전체 초기화 (볼륨 + 이미지 삭제)
docker-compose down -v --rmi local
```

### 3. 로컬 개발 (Docker 없이)

```bash
# ── 엔진 ──
cd engine
pip install -r requirements.txt
python main.py --test-run        # 테스트 실행

# ── API ──
cd api
pip install -r requirements.txt
PYTHONPATH=. uvicorn main:app --reload --port 8000

# ── 웹 ──
cd web
npm install
npm run dev                      # → http://localhost:3000
```

---

## 🌐 접속 URL

| 서비스 | URL | 설명 |
|--------|-----|------|
| 🖥️ 대시보드 | http://localhost:3000 | 실시간 대시보드 |
| 📡 API | http://localhost:8000 | REST API |
| 📄 Swagger | http://localhost:8000/docs | API 문서 (자동 생성) |
| 📘 ReDoc | http://localhost:8000/redoc | 대체 API 문서 |
| 🔴 Redis | localhost:6379 | 캐시 서버 |

---

## 📁 프로젝트 구조

```
ATS/
├── engine/                    # 자동매매 엔진 (Python)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               # 엔트리포인트 (스케줄러)
│   ├── layer1_data/           # 데이터 수집
│   ├── layer2_indicators/     # 기술적 지표 계산
│   ├── layer3_scoring/        # AI 스코어링
│   ├── layer4_execution/      # 주문 실행 + 리스크
│   └── layer5_feedback/       # LLM 피드백
│
├── api/                       # FastAPI 백엔드
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py               # FastAPI 앱
│   └── routes/
│       ├── coins.py          # 스코어링 API
│       ├── trades.py         # 매매 API
│       └── system.py         # 시스템 API
│
├── web/                       # Next.js 대시보드
│   ├── Dockerfile
│   ├── package.json
│   ├── app/                  # App Router
│   │   ├── page.tsx          # 메인 대시보드
│   │   ├── layout.tsx
│   │   ├── globals.css       # Tailwind v4 테마
│   │   └── api/              # Next.js API Routes
│   ├── components/
│   │   ├── ui/               # GlassCard, NeonButton
│   │   └── dashboard/        # AIRecommendationCards
│   └── lib/
│       └── design-system/    # 디자인 토큰
│
├── shared/                    # 공유 설정
│   └── .env.example
│
├── docker-compose.yml         # 통합 실행
└── README.md
```

---

## 🔌 API 엔드포인트

### 🪙 코인 (`/api/coins`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/coins/scores` | 전체 코인 AI 점수 |
| GET | `/api/coins/scores/{symbol}` | 단일 코인 점수 |
| GET | `/api/coins/prices/{symbol}` | 현재가 조회 |
| GET | `/api/coins/prices` | 전체 현재가 |

### 💰 매매 (`/api/trades`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/trades/order` | 수동 매수/매도 |
| GET | `/api/trades/history` | 매매 이력 |
| GET | `/api/trades/positions` | 보유 포지션 |
| GET | `/api/trades/balance` | 계좌 잔고 |

### ⚙️ 시스템 (`/api/system`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/system/status` | 시스템 상태 |
| GET | `/api/system/scheduler` | 스케줄러 잡 |
| GET | `/api/system/config` | 설정값 |
| GET | `/api/system/logs` | 최근 로그 |

---

## 🧠 AI 스코어링 엔진

5가지 팩터를 가중 합산하여 종합 점수를 계산합니다:

| 팩터 | 가중치 | 분석 내용 |
|------|--------|----------|
| 📈 기술적 분석 | 30% | RSI, MACD, 볼린저 밴드, 이동평균 |
| 🚀 모멘텀 | 25% | 가격 변화율, 추세 강도 |
| 📊 변동성 | 15% | ATR, 볼린저 밴드 폭 |
| 💹 거래량 | 15% | 거래량 변화, OBV |
| 💭 심리 | 15% | Fear & Greed, 소셜 분석 |

### 시그널 기준

| 점수 | 시그널 | 행동 |
|------|--------|------|
| 80+ | 🟢 STRONG_BUY | 적극 매수 |
| 65-79 | 🔵 BUY | 매수 |
| 35-64 | 🟡 HOLD | 관망 |
| 0-34 | 🔴 SELL | 매도 |

---

## 🛡️ 리스크 관리

| 매개변수 | 기본값 | 설명 |
|----------|--------|------|
| 손절 | -3% | 자동 손절 |
| 익절 | +5% | 자동 익절 |
| 트레일링 스탑 | -2% | 고점 대비 하락 시 |
| 최대 보유 | 72h | 시간 초과 시 자동 매도 |
| 일일 한도 | -5% | 일일 최대 손실 |

---

## ⚠️ 주의사항

> **이 시스템은 교육 및 연구 목적으로 제작되었습니다.**

- 📝 **모의투자 모드**(paper)로 시작하세요
- 💰 실제 투자금은 감당 가능한 범위 내에서 설정하세요
- 🔐 API 키는 `.env`에 보관하고, 절대 커밋하지 마세요
- 📊 과거 수익률이 미래 수익을 보장하지 않습니다

---

## 🛠️ 기술 스택

| 영역 | 기술 |
|------|------|
| 엔진 | Python 3.11, pandas, numpy, ta, APScheduler |
| API | FastAPI, Pydantic v2, Uvicorn |
| 프론트 | Next.js 16, React, TypeScript, Tailwind v4 |
| UI | Framer Motion, TanStack Query, Lucide Icons |
| 인프라 | Docker Compose, Redis 7 |
| 거래소 | Upbit (pyupbit) |
| AI | OpenAI GPT-4o |

---

## 📜 라이선스

MIT License
