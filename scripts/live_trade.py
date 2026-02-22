# scripts/live_trade.py
"""
실전 거래 실행 스크립트 (OKX)

⚠️ 주의: 실제 자금이 투입됩니다!
반드시 종이거래로 충분히 테스트한 후 소액으로 시작하세요.

실행:
    python scripts/live_trade.py
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from src.main import MainController
from src.utils.helpers import load_config, get_env


def setup_live_logging():
    """실전 거래 전용 로깅"""
    log_path = PROJECT_ROOT / "data" / "logs" / "live_trade_{time}.log"

    logger.remove()
    logger.add(
        sys.stdout,
        format="<red><bold>{time:HH:mm:ss}</bold></red> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    logger.add(
        str(log_path),
        rotation="1 day",
        retention="90 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )


def check_live_config():
    """실전 모드 설정 검증"""
    config = load_config()

    if config["trading"]["mode"] != "live":
        logger.error("❌ config/settings.yaml에서 trading.mode를 'live'로 설정해주세요!")
        sys.exit(1)

    # OKX API 키 확인
    try:
        api_key = get_env("OKX_API_KEY")
        secret_key = get_env("OKX_SECRET_KEY")
        passphrase = get_env("OKX_PASSPHRASE")

        if not api_key or not secret_key or not passphrase:
            raise ValueError("API 키가 비어있습니다")

        if len(api_key) < 10 or len(secret_key) < 10:
            raise ValueError("API 키 형식이 올바르지 않습니다")

    except Exception as e:
        logger.error(f"❌ OKX API 키 확인 실패: {e}")
        logger.error("   .env 파일에 OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE를 설정해주세요.")
        sys.exit(1)

    # Discord Webhook 확인
    try:
        webhook_signal = get_env("DISCORD_WEBHOOK_SIGNAL")
        if not webhook_signal.startswith("https://discord.com/api/webhooks/"):
            raise ValueError("Discord Webhook URL 형식이 올바르지 않습니다")
    except Exception as e:
        logger.error(f"❌ Discord Webhook 확인 실패: {e}")
        sys.exit(1)

    logger.info("✅ 설정 검증 완료")
    return config


def print_warning_banner():
    """경고 배너 출력"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🔴 OKX 선물+현물 자동매매 - 실전 모드 🔴          ║
    ║                                                           ║
    ║   ⚠️⚠️⚠️  경고: 실제 자금이 투입됩니다!  ⚠️⚠️⚠️         ║
    ║                                                           ║
    ║   📌 시작 전 체크리스트:                                 ║
    ║      ✅ 종이거래 2주 이상 테스트 완료                    ║
    ║      ✅ 백테스트 승률 55% 이상 확인                      ║
    ║      ✅ OKX API 키 권한 확인 (출금 권한 OFF)             ║
    ║      ✅ 소액(50~100 USDT)으로 시작                       ║
    ║      ✅ 디스코드 알림 정상 작동 확인                     ║
    ║                                                           ║
    ║   💡 투자의 책임은 본인에게 있습니다                     ║
    ║   ⚡ 선물 거래는 원금 이상의 손실이 발생할 수 있습니다   ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def confirm_start():
    """사용자 확인 받기"""
    print("\n🚨 정말로 실전 거래를 시작하시겠습니까?")
    print("   계속하려면 'START LIVE TRADING'을 정확히 입력하세요.")
    print("   취소하려면 'N' 또는 Ctrl+C를 누르세요.\n")

    user_input = input(">>> ").strip()

    if user_input != "START LIVE TRADING":
        logger.info("❌ 사용자 취소")
        sys.exit(0)

    print("\n⏳ 5초 후 시작합니다...")
    import time
    for i in range(5, 0, -1):
        print(f"   {i}...", flush=True)
        time.sleep(1)
    print()


async def run_live_trade():
    """실전 거래 실행"""
    print_warning_banner()
    setup_live_logging()

    logger.info("🔍 실전 모드 설정 검증 중...")
    config = check_live_config()

    logger.info(f"📊 거래 페어: {', '.join(config['trading']['pairs'])}")
    logger.info(f"🏦 거래소: OKX ({config['trading'].get('market_type', 'swap')})")
    logger.info(f"⚡ 레버리지: {config['trading'].get('leverage', 1)}x")
    logger.info(f"💰 1회 리스크: {config['risk']['risk_per_trade_pct'] * 100:.2f}%")
    logger.info(f"🛑 하루 최대 손실: {config['risk']['max_daily_loss_pct'] * 100:.1f}%")

    confirm_start()

    logger.warning("🔴 실전 거래 시작!")
    logger.warning("⏸️  종료하려면 Ctrl+C를 누르세요\n")

    try:
        controller = MainController()
        await controller.run()
    except KeyboardInterrupt:
        logger.warning("\n\n⏹️  사용자 종료 요청")
    except Exception as e:
        logger.critical(f"❌ 치명적 오류: {e}", exc_info=True)
    finally:
        logger.warning("🏁 실전 거래 종료")


if __name__ == "__main__":
    asyncio.run(run_live_trade())
