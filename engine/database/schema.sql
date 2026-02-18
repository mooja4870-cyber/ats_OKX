-- ==============================================
-- CryptoAI Master — Database Schema (PostgreSQL)
-- Supabase 호환
-- ==============================================

-- 코인 마스터 테이블
CREATE TABLE IF NOT EXISTS coins (
    symbol          VARCHAR(10) PRIMARY KEY,       -- 'BTC', 'ETH', 'XRP', 'SOL'
    name            VARCHAR(50) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- OHLCV 캔들 데이터
CREATE TABLE IF NOT EXISTS ohlcv (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL REFERENCES coins(symbol),
    timestamp       TIMESTAMPTZ NOT NULL,
    open            NUMERIC(20, 8) NOT NULL,
    high            NUMERIC(20, 8) NOT NULL,
    low             NUMERIC(20, 8) NOT NULL,
    close           NUMERIC(20, 8) NOT NULL,
    volume          NUMERIC(20, 8) NOT NULL,
    interval        VARCHAR(10) DEFAULT '5m',      -- '1m', '5m', '15m', '1h', '1d'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (symbol, timestamp, interval)
);

-- 기술지표 결과
CREATE TABLE IF NOT EXISTS technical_indicators (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL REFERENCES coins(symbol),
    timestamp       TIMESTAMPTZ NOT NULL,
    indicator_name  VARCHAR(50) NOT NULL,           -- 'RSI', 'MACD', 'BB_UPPER' 등
    value           NUMERIC(20, 8),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 멀티팩터 스코어링 결과
CREATE TABLE IF NOT EXISTS scoring_results (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL REFERENCES coins(symbol),
    timestamp       TIMESTAMPTZ NOT NULL,
    total_score     NUMERIC(5, 2) NOT NULL,         -- 0.00 ~ 100.00
    trend_score     NUMERIC(5, 2),
    momentum_score  NUMERIC(5, 2),
    volatility_score NUMERIC(5, 2),
    volume_score    NUMERIC(5, 2),
    sentiment_score NUMERIC(5, 2),
    llm_score       NUMERIC(5, 2),
    recommendation  VARCHAR(20),                    -- 'STRONG_BUY', 'BUY', 'HOLD', 'SELL'
    details         JSONB,                          -- 서브팩터 상세
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 매매 주문
CREATE TABLE IF NOT EXISTS trade_orders (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL REFERENCES coins(symbol),
    order_type      VARCHAR(10) NOT NULL,           -- 'BUY', 'SELL'
    order_method    VARCHAR(20) NOT NULL,            -- 'LIMIT', 'MARKET'
    price           NUMERIC(20, 8),
    volume          NUMERIC(20, 8) NOT NULL,
    total_krw       NUMERIC(20, 2),
    status          VARCHAR(20) DEFAULT 'PENDING',   -- 'PENDING', 'FILLED', 'CANCELLED'
    trigger_reason  VARCHAR(50),                     -- 'SCORE_70+', 'STOP_LOSS', 'TAKE_PROFIT'
    score_at_trade  NUMERIC(5, 2),
    upbit_order_id  VARCHAR(100),
    filled_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 포지션 (현재 보유 현황)
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(10) NOT NULL REFERENCES coins(symbol),
    avg_buy_price   NUMERIC(20, 8) NOT NULL,
    volume          NUMERIC(20, 8) NOT NULL,
    current_price   NUMERIC(20, 8),
    pnl_pct         NUMERIC(10, 4),                 -- 손익률 (%)
    pnl_krw         NUMERIC(20, 2),                 -- 손익 (KRW)
    status          VARCHAR(20) DEFAULT 'OPEN',      -- 'OPEN', 'CLOSED'
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 포트폴리오 스냅샷 (자산 추이)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    total_krw       NUMERIC(20, 2) NOT NULL,        -- 총 자산 (KRW)
    cash_krw        NUMERIC(20, 2) NOT NULL,         -- 현금
    invested_krw    NUMERIC(20, 2) NOT NULL,         -- 투자금
    total_pnl_pct   NUMERIC(10, 4),                  -- 전체 수익률
    details         JSONB,                           -- 코인별 상세
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 트레이딩 전략 설정
CREATE TABLE IF NOT EXISTS trading_strategies (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    description     TEXT,
    buy_threshold   NUMERIC(5, 2) DEFAULT 70.00,     -- 매수 기준 스코어
    sell_threshold  NUMERIC(5, 2) DEFAULT 30.00,     -- 매도 기준 스코어
    stop_loss_pct   NUMERIC(5, 2) DEFAULT -3.00,
    take_profit_pct NUMERIC(5, 2) DEFAULT 5.00,
    is_active       BOOLEAN DEFAULT TRUE,
    config          JSONB,                           -- 추가 전략 파라미터
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 시스템 이벤트 로그
CREATE TABLE IF NOT EXISTS system_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(50) NOT NULL,            -- 'ENGINE_START', 'TRADE_EXEC', 'ERROR'
    severity        VARCHAR(10) DEFAULT 'INFO',      -- 'INFO', 'WARN', 'ERROR', 'CRITICAL'
    message         TEXT,
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ===== 인덱스 =====
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_ts ON ohlcv (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_scoring_symbol_ts ON scoring_results (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trade_orders (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trade_orders (status);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions (status);
CREATE INDEX IF NOT EXISTS idx_portfolio_ts ON portfolio_snapshots (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON system_events (event_type, created_at DESC);

-- ===== 초기 데이터 =====
INSERT INTO coins (symbol, name) VALUES
    ('BTC', 'Bitcoin'),
    ('ETH', 'Ethereum'),
    ('XRP', 'XRP'),
    ('SOL', 'Solana')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO trading_strategies (name, description, buy_threshold, stop_loss_pct, take_profit_pct)
VALUES (
    'Default Multi-Factor',
    '기본 멀티팩터 스코어링 전략: 스코어 70점 이상 매수, 손절 -3%, 익절 +5%',
    70.00, -3.00, 5.00
)
ON CONFLICT DO NOTHING;
