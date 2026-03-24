# Team Records Bot - Deployment Guide

## Prerequisites

1. Python 3.8+ installed
2. SQLite 3.x
3. Access to Telegram API (api_id, api_hash, phone)
4. Google Sheets API service account
5. Internet connection for external APIs

## Environment Variables

Create a `.env` file or set these environment variables:

```bash
# Telegram Configuration (REQUIRED)
TG_API_ID=your_telegram_api_id
TG_API_HASH=your_telegram_api_hash
TG_PHONE=+1234567890

# Google Sheets Configuration (REQUIRED)
SHEETS_ID=your_google_spreadsheet_id
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json

# Optional Configuration
DB_PATH=team_records.db
ADMIN_CHAT_IDS=123456,789012
MANAGER_CHAT_IDS=345678,901234

# Proxy (if needed)
PROXY_HOST=127.0.0.1
PROXY_PORT=9050
```

## Installation Steps

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd team-records-bot
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

3. **Setup Google Sheets API:**
   - Create a service account in Google Cloud Console
   - Download the JSON key file as `service_account.json`
   - Share your Google Sheets with the service account email

4. **Initialize database:**
   ```bash
   python3 -c "
   import asyncio
   from database import database
   asyncio.run(database.initialize())
   print('Database initialized successfully')
   "
   ```

## Running the Bot

### Development
```bash
python3 main.py
```

### Production (systemd)

1. **Create service file** `/etc/systemd/system/team-records-bot.service`:
   ```ini
   [Unit]
   Description=Team Records Bot
   After=network.target

   [Service]
   Type=simple
   User=baiwan
   WorkingDirectory=/home/baiwan/team-records-bot
   ExecStart=/home/baiwan/team-records-bot/.venv/bin/python main.py
   EnvironmentFile=/home/baiwan/team-records-bot/.env
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. **Start service:**
   ```bash
   sudo systemctl enable team-records-bot
   sudo systemctl start team-records-bot
   sudo systemctl status team-records-bot
   ```

## Health Monitoring

Check bot health:
```bash
python3 health_check.py
```

Exit codes:
- 0: Healthy
- 1: Degraded (some issues but functional)
- 2: Unhealthy (critical issues)

## Logs

- Application logs: `team_records_bot.log`
- System logs: `sudo journalctl -u team-records-bot -f`

## Database Management

### Backup
```bash
python3 -c "
import asyncio
from database import database
async def backup():
    path = await database.backup_database()
    print(f'Backup created: {path}')
asyncio.run(backup())
"
```

### Cleanup old data
```bash
python3 -c "
import asyncio
from database import database
async def cleanup():
    await database.cleanup_old_tasks(days_old=7)
    await database.cleanup_old_conversation_states(hours_old=24)
    print('Cleanup completed')
asyncio.run(cleanup())
"
```

## Troubleshooting

### Bot won't start
1. Check environment variables: `python3 -c "from config import config; print('Config loaded successfully')"`
2. Check database: `python3 -c "from database import database; print('Database imported successfully')"`
3. Check Telegram auth: Ensure phone number is registered and 2FA is handled

### Sync issues
1. Check Google Sheets permissions
2. Verify service account JSON file
3. Check API quotas in Google Cloud Console

### Performance issues
1. Monitor database size: `ls -lh team_records.db`
2. Check log file size: `ls -lh team_records_bot.log`
3. Monitor memory usage: `ps aux | grep python`

## Security Considerations

1. **Never commit secrets to git**
2. **Protect service account JSON file** (chmod 600)
3. **Use firewall** to restrict network access
4. **Regular backups** of database
5. **Monitor for suspicious activity** in logs

## Maintenance

### Regular tasks
- Weekly: Check logs for errors
- Monthly: Backup database
- Quarterly: Update dependencies
- Annually: Rotate API keys

### Updates
```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart team-records-bot
```