# 🔑 OKX API 키 설정 가이드

## 1. API 키 발급

1. [OKX](https://www.okx.com) 로그인
2. **설정** → **API** 이동
3. **API 키 생성** 클릭

### 권한 설정 (중요!)

✅ 체크할 항목:
- **읽기(Read)** — 잔고/포지션 조회용
- **거래(Trade)** — 주문 실행용

❌ **절대 체크하지 않을 항목:**
- ~~출금(Withdraw)~~ — 보안상 절대 불필요

### Passphrase

OKX API 키 생성 시 **Passphrase**를 직접 입력합니다. 이 값을 반드시 기억해야 합니다.

### IP 허용목록

봇을 실행할 서버의 IP를 반드시 등록하세요:
- 로컬 개발: 공인 IP
- 클라우드: 서버 공인 IP

## 2. .env 파일 설정

```bash
# 프로젝트 루트에서
cp .env.example .env
```

`.env` 파일 편집:
```
OKX_API_KEY=발급받은_API_Key
OKX_SECRET_KEY=발급받은_Secret_Key
OKX_PASSPHRASE=생성_시_입력한_Passphrase
```

## 3. 연결 테스트

```bash
python -c "
import ccxt
exchange = ccxt.okx({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'password': 'YOUR_PASSPHRASE',
})
print(exchange.fetch_balance())
"
```

## 4. 주의사항

- API 키는 **절대** 코드에 직접 입력하지 마세요
- `.env` 파일은 `.gitignore`에 반드시 포함
- 주기적으로 키를 갱신하세요
- OKX API Rate Limit: 초당 20회 (주문 API 별도)
- **선물 거래는 원금 이상의 손실이 발생할 수 있습니다**
