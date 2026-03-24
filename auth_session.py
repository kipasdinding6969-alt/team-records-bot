"""One-time Telegram session authentication script."""
import asyncio
from telethon import TelegramClient

API_ID = 32326218
API_HASH = "2f44dfd151f291c8a4ec5c405eb51e94"
PHONE = "+31651036582"
SESSION_FILE = "team_records_bot"

async def main():
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
