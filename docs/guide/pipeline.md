# 客户管道 Client Pipeline

## 管道流程 Pipeline Flow

```
🆕 new ──→ 📱 contacted ──→ 💬 replied ──→ ✅ registered ──→ 📚 training ──→ 🎯 ordered
                                                                    │
                                                                    ↓
                                                               💰 withdrew ──→ (可回到 contacted)
```

## 状态说明 Status Guide

| 状态 Status | Emoji | 含义 Meaning | 触发条件 Trigger |
|---|---|---|---|
| `new` | 🆕 | 新客户 New | `/add` 添加后自动 |
| `contacted` | 📱 | 已联系 Contacted | `/u phone contacted` 主动联系后 |
| `replied` | 💬 | 已回复 Replied | 客户有回应后 |
| `registered` | ✅ | 已注册 Registered | 客户完成平台注册 |
| `training` | 📚 | 培训中 Training | 注册后进入培训 |
| `withdrew` | 💰 | 已出金 Withdrew | 客户完成出金 |
| `ordered` | 🎯 | 已下单 Ordered | 客户完成下单 ✨ |

## 转换规则 Transition Rules

**不能跳步！Can't Skip Steps!**

| 当前状态 From | 可转到 Allowed To |
|---|---|
| `new` | `contacted` |
| `contacted` | `replied`, `ghosted`, `blocked` |
| `replied` | `registered`, `contacted` |
| `registered` | `training`, `withdrew` |
| `training` | `ordered`, `withdrew` |
| `withdrew` | `ordered`, `contacted` (回来了) |
| `ordered` | ✅ 终点 Terminal |

**示例 Examples:**
```
✅ /u 46123456789 contacted     ← new → contacted (允许)
❌ /u 46123456789 registered    ← new → registered (不允许！跳步)
✅ /u 46123456789 replied       ← contacted → replied (允许)
```

## 超时提醒 Stale Alerts

| 时间 Duration | 级别 Level | 动作 Action |
|---|---|---|
| 48小时未跟进 | ⚠️ 警告 | 提醒前台跟进 |
| 72小时未跟进 | 🔴 严重 | 通知维护组 |
| 14天未跟进 | ☠️ 自动标记 | 标记为 dead |

## 转化率计算 Conversion Rates

- **回复率 Reply Rate** = `replied / contacted`
- **注册率 Registration Rate** = `registered / replied`
- **转化率 Conversion Rate** = `ordered / registered`

## 在群组中查看 In Group Context

当你在团队群组中输入 `/pipeline`：
When you type `/pipeline` in a team group:

- **前台** → 看到自己的数据 (personal)
- **组长/维护** → 看到全团队汇总 (team totals)
- **管理员** → 看到全团队汇总 (team totals)

```
📊 阿俊 团队 的客户管道

🆕 新客户:    12
📱 已联系:    8
💬 已回复:    5
✅ 已注册:    3
📚 培训中:    1
💰 已出金:    0
🎯 已下单:    0

👥 团队成员: 5 人
```
