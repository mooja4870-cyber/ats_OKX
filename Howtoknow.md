# ATS_OKX How To Know

이 문서는 이 앱의 실제 사용 방법, 일일 요약 확인 방법, 운영/가동 기준을 한 번에 정리한 운영 가이드입니다.

## 1) 앱 개요

- 앱 목적: OKX 선물+현물 자동매매 (paper/live 모드)
- 기본 모드: `paper` (`config/settings.yaml`)
- 주요 데이터 저장소: `data/trades.db` (SQLite)
- 거래 라이브러리: ccxt (OKX)

## 2) 실행 방법 (권장: paper 모드)

1. 프로젝트 루트로 이동
```bash
cd /Users/mooja/AI_Study/Project/ATS_OKX
```

2. 가상환경 활성화
```bash
source venv/bin/activate
```

3. 앱 실행 (종이거래)
```bash
./venv/bin/python scripts/paper_trade.py
```

4. 종료
- 실행 중 터미널에서 `Ctrl+C`

## 3) 실전 모드 실행 방법 (live)

1. `config/settings.yaml`에서 아래 값으로 변경
```yaml
trading:
  mode: "live"
```

2. `.env`에 OKX 키 필수 설정
```env
OKX_API_KEY=...
OKX_SECRET_KEY=...
OKX_PASSPHRASE=...
```

3. 실행
```bash
./venv/bin/python scripts/live_trade.py
```

4. 콘솔 확인 문구 입력
- `START LIVE TRADING`

## 4) 일일 요약 저장/조회 방법

### 저장 위치

- DB 파일: `data/trades.db`
- 테이블: `daily_summary`
- 저장 시점: 매일 23:55(KST) 스케줄 작업
- 저장 시점: 앱 종료(shutdown) 시 1회 추가 저장

### 조회 방법 1: sqlite3 직접 조회

```bash
sqlite3 data/trades.db "SELECT * FROM daily_summary ORDER BY date DESC LIMIT 10;"
```

### 조회 방법 2: 성과 분석 스크립트

```bash
./venv/bin/python scripts/analyze_performance.py --days 30
```

## 5) 운영/가동 기준 (현재 설정값 기준)

기준 파일: `config/settings.yaml`

- 루프 간격: 10초
- 거래 페어: `BTC/USDT:USDT`, `ETH/USDT:USDT`, `XRP/USDT:USDT`, `SOL/USDT:USDT`
- 마켓 타입: swap (선물)
- 레버리지: 1x (isolated)
- 매수 신호 실행 기준: score `>= 60` + 6개 조건 중 최소 4개 충족
- 1일 최대 매매: 14회
- 1회 리스크: 1% (`risk_per_trade_pct: 0.01`)
- 1일 최대 손실: 7% (`max_daily_loss_pct: 0.07`)
- 연속 손실 제한: 5회 (`max_consecutive_losses: 5`)
- 세션 종료 15분 전 신규 진입 차단

### 매매 세션 (KST) — 현재 always_on

- 08:00 ~ 16:00
- 16:00 ~ 00:00
- 00:00 ~ 08:00

## 6) 로그/DB 확인 포인트

- 실행 로그: `data/logs/`
- 거래/신호/요약 DB: `data/trades.db`
- 주요 테이블: `trades` (체결 기록 — 롱/숏 구분)
- 주요 테이블: `signals` (신호 기록)
- 주요 테이블: `daily_summary` (일일 요약)

## 7) 디스코드 사용 기준

- `paper` 모드에서 Webhook이 비어있거나 placeholder면 디스코드 연결은 경고 후 생략되고 앱은 계속 동작
- 실제 Webhook URL을 넣으면 신호/리포트/에러/시스템 메시지 전송
- 잔고 스냅샷은 `config/settings.yaml`의 `discord.balance_snapshot_interval_seconds` 기준으로 전송 (현재 60초)

## 8) 시스템 초기화 및 동기화 기준 (Strict Protocol)

본 봇은 거래소 상태와 봇 내부 DB를 일치시키기 위해 아래의 엄격한 프로토콜을 따릅니다.

### 초기화(Reset) 시 수행 작업
1. **거래소 포지션 전량 청산**: `fetch_positions()`로 조회 후 즉시 청산
2. **미체결 주문 전량 취소**: `cancel_all_orders()` 수행
3. **내부 데이터 완전 리셋**: `trades.db`, `open_positions.json`, `paper_state.json` 초기화
4. **시작 잔고 설정**: 10,000 USDT로 리셋
5. **디스코드 알림**: 초기화 성공 내역 전송

### 실시간 동기화(Sync Check) 원칙
- 매 루프마다 거래소 포지션을 조회하여 봇 DB와 대조합니다.
- **유령 포지션(미관리)** 발견 시: 즉시 강제 청산 + 디스코드 경고 전송
- **포지션 증발** 발견 시: 봇 DB에서 제거 + 디스코드 경고 전송

## 9) 실행 상태 확인

```bash
ps aux | rg "scripts/paper_trade.py|scripts/live_trade.py" -n
```

## 9) 자주 발생하는 문제

- 문제: `ModuleNotFoundError: ccxt`
- 조치: 가상환경 활성화 후 `pip install -r requirements.txt`

- 문제: 디스코드 400 오류 (`... is not snowflake`)
- 조치: `.env`의 placeholder URL(`...`)을 실제 Webhook으로 교체

터미널 실행
```bash
cd /Users/mooja/AI_Study/Project/ATS_OKX
./venv/bin/python scripts/paper_trade.py
```
