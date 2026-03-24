"""One-time Telegram session authentication script."""
import asyncio
from telethon import TelegramClient

import os
API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")
SESSION_FILE = "team_records_bot"

async def main():
    if not API_ID or not API_HASH or not PHONE:
        print("❌ Error: Missing required environment variables:")
        print("- TG_API_ID: Telegram API ID")
        print("- TG_API_HASH: Telegram API Hash")
        print("- TG_PHONE: Phone number (+1234567890)")
        return

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Sending code request to Telegram...")
        await client.send_code_request(PHONE)
        print("CODE SENT! Check your Telegram app for the login code.")
        print("Waiting for code input...")
        code = input("Enter the code: ")
        try:
            await client.sign_in(PHONE, code)
        except Exception as e:
            if "Two-step verification" in str(e) or "password" in str(e).lower():
                pw = input("2FA password required. Enter password: ")
                await client.sign_in(password=pw)
            else:
                raise
    
    me = await client.get_me()
    print(f"\n✅ Successfully authenticated as: {me.first_name} (@{me.username})")
    print(f"Session saved to: {SESSION_FILE}.session")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
