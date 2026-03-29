# 部署运维 Deployment

## 系统要求 Requirements

- Python 3.12+
- SQLite 3
- Docker (for NocoDB + Tor proxy)
- Ollama (for RAG embeddings)
- Telegram Bot Token + User Session

## 启动 Start

```bash
# 1. Docker services
docker compose up -d    # NocoDB + Postgres + Tor

# 2. Bot
systemctl start team-records-bot

# Check status
systemctl status team-records-bot
journalctl -u team-records-bot -f
```

## 环境变量 Environment Variables

```env
# Telegram
API_ID=32326218
API_HASH=xxxx
BOT_TOKEN=xxxx:yyyy
SESSION_NAME=team_records_bot

# NocoDB
NOCODB_URL=http://localhost:8080
NOCODB_TOKEN=xxxx

# Team Structure
BROADCAST_CHANNEL_ID=-100xxxxx
TEAM_QUANXIAN_CHAT_ID=-100xxxxx
TEAM_QUANXIAN_DAILY_TOPIC=3
TEAM_AJUN_CHAT_ID=-100xxxxx
TEAM_HEJUN_CHAT_ID=-100xxxxx
TEAM_CHAOQUN_CHAT_ID=-100xxxxx
MANAGEMENT_CHAT_ID=-100xxxxx
MANAGEMENT_SUMMARY_TOPIC=3
KEFU_CHAT_ID=-100xxxxx

# Google Sheets (read-only import)
GOOGLE_CREDS_FILE=credentials.json
SPREADSHEET_ID=xxxx
```

## 测试 Testing

```bash
# All tests
python -m pytest tests/ -q

# Human-view tests only
python -m pytest tests/test_human_view.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=html
```

## 数据库备份 Database Backup

```bash
# Manual backup
cp team_records_v2.db backups/team_records_v2_$(date +%Y%m%d).db

# NocoDB data is in Docker volume (postgres)
docker exec nocodb-postgres pg_dump -U nocodb nocodb > backup.sql
```

## 日志 Logs

```bash
# Live logs
journalctl -u team-records-bot -f

# Errors only
journalctl -u team-records-bot --since today | grep ERROR

# NocoDB sync logs
journalctl -u team-records-bot | grep nocodb
```

## 健康检查 Health Check

机器人每30分钟自动运行健康检查：
Bot runs health check every 30 minutes:

- ✅ Database connection
- ✅ Telegram client
- ✅ NocoDB sync status
- ✅ Ollama embeddings
- ✅ Obsidian vault
