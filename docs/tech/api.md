# API & NocoDB

## NocoDB 数据面板

**URL:** `http://localhost:8080`
**API Token:** 在 `.env` 文件中的 `NOCODB_TOKEN`

### API 基本路径

```
GET  /api/v1/db/data/noco/{base_id}/{table_id}
POST /api/v1/db/data/noco/{base_id}/{table_id}
```

**注意：NocoDB v0.301 使用 v1 API，不是 v2！**

### 表 ID 映射

| 表 Table | Table ID | 说明 |
|---|---|---|
| Staff | m86ezootd5q5uvk | 员工 |
| Clients | m0eyp4lqlj15r59 | 客户 |
| Client Notes | msd72gbqcc2a2s9 | 备注 |
| Daily Stats | mptkw0nsybv51wa | 日统计 |
| Deposits | mr9t5h1k9bybx4w | 入金 |
| Reminders | mra0q5brw3rtrv7 | 提醒 |
| Team Targets | m69g56oto3q6up1 | 目标 |

### 字段映射 Field Mapping

NocoDB 使用字段标题（不是 column_name）查询！
NocoDB uses field **titles** (not column_names) in queries!

```json
{
  "staff": {
    "tg_user_id": "Telegram ID",
    "display_name": "Display Name",
    "role": "Role",
    "team": "Team"
  }
}
```

完整映射见 `nocodb_config.json`。

### API 示例 Examples

```bash
# 获取所有员工 Get all staff
curl -s "http://localhost:8080/api/v1/db/data/noco/pq3jgqmclgw0ila/m86ezootd5q5uvk" \
  -H "xc-token: YOUR_TOKEN"

# 按团队筛选 Filter by team
curl -s "http://localhost:8080/api/v1/db/data/noco/pq3jgqmclgw0ila/m86ezootd5q5uvk?where=(Team,eq,阿俊)" \
  -H "xc-token: YOUR_TOKEN"

# 手动同步 Manual sync
cd ~/repos/team-records-bot-v2
python engines/nocodb_writer.py --sync team_records_v2.db
```

### Webhook 同步

NocoDB webhook 在端口 8765 运行，支持双向同步：
- NocoDB 修改 → webhook → SQLite 更新
- SQLite 修改 → Ralph Loop → NocoDB 更新

## Google Sheets

**模式:** 只读导入（NocoDB 是主数据库）
**Mode:** Read-only import (NocoDB is primary)

Google Sheets 用于历史数据导入，不再作为主数据源。

## Obsidian Vault

**端口:** `http://localhost:27123`
**Vault:** 刷单

用于 RAG 搜索的文档源：
- `docs/` — 项目文档 (5 files)
- `workspace/` — SOP 操作手册 (11 files)

```bash
# 搜索 SOP
/sop <关键词>
/rag <问题>
```

## Telegram Bot API

**Bot:** @qianhub_records_bot
**Token:** 在 `.env` 的 `BOT_TOKEN`
**User Session:** team_records_bot.session (Telethon MTProto)

**双模式 Dual Mode:**
- Bot client → 接收命令、发送回复、内联键盘
- User client → 创建群组、管理权限、高级操作
