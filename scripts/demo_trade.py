# scripts/demo_trade.py
"""
OKX 데모(모의) 거래 실행 스크립트

OKX 데모 계정 API 키를 사용해 주문/포지션 로직을 실제 거래소 모의환경에서 검증합니다.

실행:
    python3 scripts/demo_trade.py
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from src.main import MainController
from src.utils.helpers import create_okx_exchange, get_okx_credentials, load_config


def setup_demo_logging():
    """데모 거래 전용 로깅"""
    log_path = PROJECT_ROOT / "data" / "logs" / "demo_trade_{time}.log"

    logger.remove()
    logger.add(
        sys.stdout,
        format="<cyan>{time:HH:mm:ss}</cyan> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    logger.add(
        str(log_path),
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )


def check_demo_config():
    """demo 모드 및 데모 API 키 검증"""
    config = load_config()

    if config["trading"]["mode"] != "demo":
        logger.error("config/settings.yaml에서 trading.mode를 'demo'로 설정해주세요.")
        sys.exit(1)

    try:
        creds = get_okx_credentials("demo")
        if any(len(v.strip()) < 10 for v in creds.values()):
            raise ValueError("데모 API 키 형식이 올바르지 않습니다.")
    except Exception as e:
        logger.error(f"OKX 데모 API 키 확인 실패: {e}")
        logger.error(
            ".env 파일에 OKX_DEMO_API_KEY, OKX_DEMO_SECRET_KEY, OKX_DEMO_PASSPHRASE를 설정해주세요."
        )
        sys.exit(1)

    # 시작 전에 데모 계정 인증/잔고 조회 테스트
    market_type = config["trading"].get("market_type", "swap")
    params = {"type": market_type} if market_type in ("swap", "spot") else {}

    exchange = create_okx_exchange("demo")
    try:
        balance = exchange.fetch_balance(params)
        usdt_total = float(balance.get("USDT", {}).get("total", 0) or 0)
        logger.info(f"OKX 데모 인증 성공 | USDT 총잔고: {usdt_total:,.4f}")
    except Exception as e:
        logger.error(f"OKX 데모 계정 연결 실패: {e}")
        logger.error("OKX API 설정에서 Demo Trading 권한 및 IP 화이트리스트를 다시 확인하세요.")
        sys.exit(1)
    finally:
        try:
            exchange.close()
        except Exception:
            pass

    pairs = config["trading"]["pairs"]
    logger.info(f"거래 페어: {', '.join(pairs)}")
    logger.info(f"마켓: {market_type}")
    logger.info(f"레버리지: {config['trading'].get('leverage', 1)}x")
    logger.info(f"루프 간격: {config['trading']['loop_interval_seconds']}초")

    return config


def print_banner():
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║              OKX 자동매매 - DEMO 모드                    ║
    ║                                                           ║
    ║   이 모드는 OKX 데모 거래소에서만 주문을 실행합니다.      ║
    ║   실계좌 주문은 실행되지 않습니다.                        ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


async def run_demo_trade():
    print_banner()
    setup_demo_logging()
    check_demo_config()

    logger.info("데모 거래를 시작합니다. 종료하려면 Ctrl+C를 누르세요.")
    try:
        controller = MainController()
        await controller.run()
    except KeyboardInterrupt:
        logger.info("사용자 종료 요청")
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}", exc_info=True)
    finally:
        logger.info("데모 거래 종료")


if __name__ == "__main__":
    asyncio.run(run_demo_trade())
