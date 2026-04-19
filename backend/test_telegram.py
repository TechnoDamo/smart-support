#!/usr/bin/env python3
"""Проверка polling-интеграции Telegram с конфигурацией из корневого `.env`."""

import asyncio
import sys
sys.path.append(".")

from app.config import get_settings
from app.services.telegram_integration import poll_telegram_updates


async def test_telegram_polling():
    """Test Telegram polling functionality."""
    settings = get_settings()

    print("=== Telegram Configuration ===")
    print(f"Bot Token: {'Set' if settings.telegram_bot_token else 'Not set'}")
    print(f"Token length: {len(settings.telegram_bot_token)}")
    print(f"Polling Enabled: {settings.telegram_polling_enabled}")
    print(f"Channel Provider: {settings.channel_telegram_provider}")
    print(f"Polling Interval: {settings.scheduler_telegram_polling_interval_seconds}s")
    print(f"API Base URL: {settings.telegram_api_base_url}")

    if not settings.telegram_bot_token:
        print("\n❌ ERROR: Telegram bot token is not set!")
        return False

    if settings.channel_telegram_provider != "telegram":
        print(
            f"\n⚠️ WARNING: Channel provider is '{settings.channel_telegram_provider}', not 'telegram'"
        )

    if not settings.telegram_polling_enabled:
        print("\n⚠️ WARNING: Telegram polling is not enabled")

    print("\n=== Testing Polling ===")
    try:
        import httpx
        import asyncio

        # Test direct API call first
        url = f"{settings.telegram_api_base_url.rstrip('/')}/bot{settings.telegram_bot_token}/getMe"
        print(f"Testing URL: {url[:50]}...")

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url)
                print(f"Response status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Bot info: {data}")
                else:
                    print(f"Response text: {response.text[:200]}")
            except httpx.ConnectTimeout:
                print("❌ Connection timeout to Telegram API")
                print("This could be due to:")
                print("1. Network connectivity issues")
                print("2. Firewall blocking Telegram API")
                print("3. DNS resolution problems")
                return False
            except Exception as e:
                print(f"❌ Error calling Telegram API: {type(e).__name__}: {e}")
                return False

        # Now test the polling function
        print("\nTesting poll_telegram_updates()...")
        processed = await poll_telegram_updates()
        print(f"Processed {processed} updates")

        if processed == 0:
            print("No updates processed. This could mean:")
            print("1. No new messages from Telegram")
            print("2. Bot token might be invalid")
            print("3. Network issue connecting to Telegram API")
            print("4. No offset stored (first run)")

        return True
    except Exception as e:
        print(f"\n❌ ERROR during polling: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_telegram_polling())
    sys.exit(0 if result else 1)
