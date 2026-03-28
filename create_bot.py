"""Create a bot via BotFather using the existing user session."""
import asyncio
import socks
from telethon import TelegramClient, events
import time

API_ID = 32326218
API_HASH = "2f44dfd151f291c8a4ec5c405eb51e94"
SESSION = "team_records_bot"
PROXY = (socks.SOCKS5, "127.0.0.1", 9050)

BOT_NAME = "Team Records Bot"
BOT_USERNAME = "qianhub_records_bot"

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH, proxy=PROXY)
    await client.start()
    
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username})")
    
    botfather = await client.get_entity("@BotFather")
    
    # Step 1: Send /newbot
    print("\n--- Sending /newbot ---")
    await client.send_message(botfather, "/newbot")
    await asyncio.sleep(3)
    
    # Read response
    messages = await client.get_messages(botfather, limit=1)
    print(f"BotFather: {messages[0].text[:200]}")
    
    # Step 2: Send bot display name
    print(f"\n--- Sending name: {BOT_NAME} ---")
    await client.send_message(botfather, BOT_NAME)
    await asyncio.sleep(3)
    
    messages = await client.get_messages(botfather, limit=1)
    print(f"BotFather: {messages[0].text[:200]}")
    
    # Step 3: Send bot username
    print(f"\n--- Sending username: {BOT_USERNAME} ---")
    await client.send_message(botfather, BOT_USERNAME)
    await asyncio.sleep(5)
    
    messages = await client.get_messages(botfather, limit=1)
    response = messages[0].text
    print(f"BotFather: {response[:500]}")
    
    # Extract token
    if "HTTP API" in response:
        # Token is between ` characters
        import re
        token_match = re.search(r'(\d+:[A-Za-z0-9_-]+)', response)
        if token_match:
            token = token_match.group(1)
            print(f"\n✅ BOT TOKEN: {token}")
            
            # Save to file
            with open("bot_token.txt", "w") as f:
                f.write(token)
            print("Token saved to bot_token.txt")
        else:
            print("❌ Could not extract token from response")
    elif "Sorry" in response or "already" in response:
        print("❌ Username might be taken, check response above")
    
    await client.disconnect()

asyncio.run(main())
