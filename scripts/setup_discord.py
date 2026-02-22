# scripts/setup_discord.py
"""
디스코드 Webhook 설정 가이드 및 테스트

실행:
    python scripts/setup_discord.py
"""

import sys
from pathlib import Path
import asyncio

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# discord-webhook 패키지가 없을 경우의 에러 방지
try:
    from discord_webhook import DiscordWebhook, DiscordEmbed
except ImportError:
    print("discord-webhook 패키지가 설치되어 있지 않습니다. pip install discord-webhook 명령어로 설치해주세요.")
    sys.exit(1)

from loguru import logger
from src.utils.helpers import get_env


def print_setup_guide():
    """디스코드 설정 가이드 출력"""
    guide = """
    ╔═══════════════════════════════════════════════════════════╗
    ║        📱 디스코드 Webhook 설정 가이드                    ║
    ╚═══════════════════════════════════════════════════════════╝

    1️⃣  디스코드 서버 생성
       - 디스코드 앱에서 "서버 추가" 클릭
       - 서버 이름: "트레이딩봇" (원하는 이름)

    2️⃣  채널 생성 (4개 권장)
       - #매매신호    (매수/매도 알림)
       - #일일리포트  (일일 성과 요약)
       - #에러로그    (오류 알림)
       - #시스템상태  (하트비트)

    3️⃣  Webhook URL 생성 (각 채널마다)
       - 채널 설정(⚙️) → 연동 → Webhook → 새 Webhook
       - Webhook URL 복사

    4️⃣  .env 파일에 추가
       DISCORD_WEBHOOK_SIGNAL=https://discord.com/api/webhooks/xxxxx
       DISCORD_WEBHOOK_REPORT=https://discord.com/api/webhooks/xxxxx
       DISCORD_WEBHOOK_ERROR=https://discord.com/api/webhooks/xxxxx
       DISCORD_WEBHOOK_SYSTEM=https://discord.com/api/webhooks/xxxxx

    ───────────────────────────────────────────────────────────
    """
    print(guide)


def test_webhook(webhook_url: str, channel_name: str):
    """Webhook 테스트"""
    try:
        webhook = DiscordWebhook(url=webhook_url)
        
        embed = DiscordEmbed(
            title=f"✅ Webhook 테스트 성공",
            description=f"**{channel_name}** 채널이 정상적으로 연결되었습니다!",
            color=0x00FF00
        )
        embed.add_embed_field(name="시간", value="테스트 메시지", inline=False)
        
        webhook.add_embed(embed)
        response = webhook.execute()
        
        if response.status_code in (200, 204):
            logger.info(f"✅ {channel_name} 테스트 성공!")
            return True
        else:
            logger.error(f"❌ {channel_name} 테스트 실패: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ {channel_name} 오류: {e}")
        return False


def main():
    """메인 함수"""
    logger.remove()
    logger.add(sys.stdout, format="<level>{message}</level>", level="INFO")
    
    print_setup_guide()
    
    print("🔍 .env 파일에서 Webhook URL을 확인합니다...\n")
    
    webhooks = {
        "매매신호": "DISCORD_WEBHOOK_SIGNAL",
        "일일리포트": "DISCORD_WEBHOOK_REPORT",
        "에러로그": "DISCORD_WEBHOOK_ERROR",
        "시스템상태": "DISCORD_WEBHOOK_SYSTEM",
    }
    
    success_count = 0
    
    for channel_name, env_key in webhooks.items():
        try:
            webhook_url = get_env(env_key)
            if webhook_url:
                if test_webhook(webhook_url, channel_name):
                    success_count += 1
            else:
                 logger.warning(f"⚠️  {channel_name} ({env_key}) 설정되지 않음")
        except Exception as e:
            logger.warning(f"⚠️  {channel_name} ({env_key}) 확인 중 오류 발생: {e}")
    
    print(f"\n{'='*60}")
    print(f"테스트 결과: {success_count}/{len(webhooks)} 성공")
    print(f"{'='*60}\n")
    
    if success_count == len(webhooks):
        logger.info("🎉 모든 Webhook이 정상적으로 설정되었습니다!")
    else:
        logger.warning("⚠️  일부 Webhook 설정이 필요합니다. 위 가이드를 참고하세요.")


if __name__ == "__main__":
    main()
