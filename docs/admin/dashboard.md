# 仪表板 Dashboard

## `/dashboard` — 管理仪表板

**权限 Access:** manager, leader, maintenance, customer_service, viewer, admin

显示全面的运营数据：
Shows comprehensive operations data:

```
📊 管理仪表板 / Dashboard

📈 今日数据 Today:
• 新增客户: 15
• 完成联系: 12
• 已注册: 3
• 已下单: 1

👥 团队排名 Team Ranking:
🥇 阿俊组 — 8单注册
🥈 何军组 — 5单注册
🥉 全线组 — 2单注册

⚠️ 待处理 Pending:
• 48h未跟进: 5个客户
• 72h未跟进: 2个客户
• 待交接: 1个客户
```

## `/team` — 团队管理

**权限 Access:** maintenance, manager, leader, admin

```
/team
```

查看团队成员列表、各成员今日数据。

## `/target` — 团队目标

**权限 Access:** manager, leader, admin

```
/target <team> <target_number>
```

设置团队的周/月目标。

## 自动报表 Auto Reports

机器人每3小时自动推送报表到：

| 目标 Target | 话题 Topic | 内容 Content |
|---|---|---|
| 📢 总频道 | — | 全公司汇总 |
| 🏢 各团队群 | 📊 日报 | 本组数据+排名 |
| 🎯 管理层 | 📊 总报表 | 管理层汇总+全组对比 |

**推送时间 Schedule:**
- 工作时间内（10:00-22:00 Europe/Paris）
- 每3小时一次
- 日终18:00发送完整日报

## NocoDB 数据面板

除了 Telegram 内的命令，你也可以通过 NocoDB 查看数据：

**地址 URL:** `http://localhost:8080`

| 表 Table | 内容 Content |
|---|---|
| Staff | 所有员工信息 |
| Clients | 所有客户+管道状态 |
| Daily Stats | 每日统计 |
| Deposits | 入金记录 |
| Reminders | 提醒记录 |
| Team Targets | 团队目标 |

NocoDB 和 SQLite 双向同步 — 在任一端修改都会反映到另一端。
