# 数据库 Database Schema

## 表结构 Tables

### staff — 员工表

| 字段 Column | 类型 Type | 说明 Description |
|---|---|---|
| id | INTEGER PK | 自增ID |
| tg_user_id | INTEGER UNIQUE | Telegram 用户ID (负数=占位符) |
| tg_chat_id | INTEGER | Telegram 聊天ID |
| tg_username | TEXT | @username |
| display_name | TEXT | 显示名 |
| role | TEXT | 角色 (admin/leader/manager/maintenance/frontdesk/customer_service/newbie/viewer) |
| team | TEXT | 团队 (全线/阿俊/何军/炒群) |
| phone | TEXT | 手机号 |
| language | TEXT | 语言 (zh/en) |
| is_active | INTEGER | 是否激活 |
| daily_target | INTEGER | 每日目标 |
| created_at | TIMESTAMP | 创建时间 |
| last_active_at | TIMESTAMP | 最后活跃 |
| maintenance_id | INTEGER | 对应维护人员ID |

### clients — 客户表

| 字段 Column | 类型 Type | 说明 Description |
|---|---|---|
| id | INTEGER PK | 自增ID |
| frontdesk_id | INTEGER FK | 负责前台ID |
| phone | TEXT | 手机号 |
| **account_id** | TEXT | **平台编号 (via /num)** |
| phone_remark | TEXT | 手机备注 |
| nickname | TEXT | 昵称 |
| source | TEXT | 来源 (飞机筛选/微信/WhatsApp) |
| recruiter | TEXT | 推荐人 |
| **status** | TEXT | **管道状态** |
| status_note | TEXT | 状态备注 |
| contacted_at | TIMESTAMP | 联系时间 |
| replied_at | TIMESTAMP | 回复时间 |
| registered_at | TIMESTAMP | 注册时间 |
| training_at | TIMESTAMP | 培训时间 |
| withdrew_at | TIMESTAMP | 出金时间 |
| first_order_at | TIMESTAMP | 下单时间 |
| next_followup | TIMESTAMP | 下次跟进 |
| followup_count | INTEGER | 跟进次数 |
| platform | TEXT | 平台 (MT5等) |
| total_deposited | REAL | 总入金额 |
| maintenance_id | INTEGER | 维护人员ID |
| handoff_at | TIMESTAMP | 交接时间 |
| handoff_note | TEXT | 交接备注 |

### daily_stats — 每日统计

| 字段 Column | 类型 Type | 说明 |
|---|---|---|
| staff_id | INTEGER | 员工ID |
| date | TEXT | 日期 (YYYY-MM-DD) |
| new_clients | INTEGER | 新增客户数 |
| contacted | INTEGER | 联系数 |
| replied | INTEGER | 回复数 |
| registered | INTEGER | 注册数 |
| training | INTEGER | 培训数 |
| withdrew | INTEGER | 出金数 |
| ordered | INTEGER | 下单数 |

### client_notes — 客户备注

| 字段 | 类型 | 说明 |
|---|---|---|
| client_id | INTEGER FK | 客户ID |
| staff_id | INTEGER FK | 操作员ID |
| note | TEXT | 备注内容 |
| created_at | TIMESTAMP | 创建时间 |

### deposits — 入金记录

| 字段 | 类型 | 说明 |
|---|---|---|
| client_id | INTEGER FK | 客户ID |
| staff_id | INTEGER FK | 操作员ID |
| amount | REAL | 金额 |
| knife_number | INTEGER | 刀数 (max 8) |
| note | TEXT | 备注 |

### reminders — 提醒

| 字段 | 类型 | 说明 |
|---|---|---|
| staff_id | INTEGER FK | 员工ID |
| client_id | INTEGER FK | 客户ID |
| reminder_type | TEXT | 类型 (manual/stale_client) |
| scheduled_time | TIMESTAMP | 提醒时间 |
| status | TEXT | 状态 (pending/sent/cancelled) |

### team_targets — 团队目标

| 字段 | 类型 | 说明 |
|---|---|---|
| team | TEXT | 团队名 |
| month | TEXT | 月份 |
| target_clients | INTEGER | 目标客户数 |
| target_registrations | INTEGER | 目标注册数 |
| target_orders | INTEGER | 目标下单数 |

### groups — 关联群组

| 字段 | 类型 | 说明 |
|---|---|---|
| tg_group_id | INTEGER UNIQUE | Telegram 群组ID |
| group_name | TEXT | 群名 |
| team | TEXT | 关联团队 |
| group_type | TEXT | 类型 (team/support) |
