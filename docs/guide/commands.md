# 所有命令 All Commands

## 客户管理 Client Management

### `/add` — 添加客户 Add Client

```
/add <手机号> <来源> [编号]
/add <phone> <source> [account_id]
```

**示例 Examples:**
```
/add 46123456789 飞机筛选
/add 46123456789 微信 888
/add 46999888777 WhatsApp 1024
```

**规则 Rules:**
- 手机号不能重复（同一前台）/ Phone must be unique per staff
- 每日最多添加50个客户 / Max 50 clients per day
- 新客户状态自动设为 `new`

---

### `/num` — 设置编号 Set Account ID

```
/num <手机号> <编号>
/num <phone> <account_id>
```

**示例 Examples:**
```
/num 46123456789 763
/num 46999888777 ACC-2026
```

用于客户注册平台后，绑定其平台账号编号。
Set the platform account number after client registers.

---

### `/u` — 更新状态 Update Status

```
/u <手机号> <新状态>
/u <phone> <new_status>
```

**状态值 Status Values:**

| 状态 Status | 中文 | 说明 Description |
|---|---|---|
| `new` | 🆕 新客户 | 刚添加 / Just added |
| `contacted` | 📱 已联系 | 已主动联系 / Reached out |
| `replied` | 💬 已回复 | 客户有回复 / Client replied |
| `registered` | ✅ 已注册 | 完成注册 / Registered |
| `training` | 📚 培训中 | 正在培训 / In training |
| `withdrew` | 💰 已出金 | 已出金 / Withdrew funds |
| `ordered` | 🎯 已下单 | 完成下单 / Placed order |

**管道规则 Pipeline Rules:**
- 不能跳步！`new` → 只能到 `contacted`，不能直接到 `registered`
- Can't skip steps! `new` → only `contacted`, not directly `registered`
- `withdrew` 可以回到 `contacted`（客户回来了）
- `withdrew` can go back to `contacted` (client returned)

---

### `/info` — 客户详情 Client Info

```
/info <手机号>
/info <phone>
```

显示完整客户卡片：
Shows full client card:
- 📱 手机号 Phone
- 🆔 编号 Account ID
- 状态 + 时间戳 Status + timestamps
- 📡 来源 Source
- 👤 前台 Staff
- 💰 入金 Deposits
- 📝 备注 Notes

**组长权限 Leader Access:**
在群组中，组长可以查看团队所有成员的客户。
In group, leaders can view all team members' clients.

---

### `/note` — 添加备注 Add Note

```
/note <手机号> <备注内容>
/note <phone> <note text>
```

**示例 Examples:**
```
/note 46123456789 客户说周五再联系
/note 46123456789 Client wants to deposit next week
```

---

### `/search` — 搜索客户 Search Clients

```
/search <关键词>
/search <keyword>
```

搜索手机号、备注、来源等。
Searches phone, notes, source, etc.

---

## 管道与报表 Pipeline & Reports

### `/pipeline` — 管道视图

```
/pipeline
```

- **私聊 DM** → 显示你的个人管道
- **群组 Group** → 显示团队汇总管道

```
📊 TINO 的客户管道

🆕 新客户:    5
📱 已联系:    3
💬 已回复:    2
✅ 已注册:    1
📚 培训中:    0
💰 已出金:    0
🎯 已下单:    0

⚠️ 3个客户超过72小时未跟进
🔥 2个客户需要今日跟进
```

### `/today` — 今日汇总

```
/today
```

显示今天的操作统计：新增、联系、注册等。

### `/followup` — 待跟进

```
/followup
```

列出所有需要跟进的客户。

---

## 提醒与交接 Reminders & Handoff

### `/remind` — 设置提醒

```
/remind <手机号> <时间>
```

**时间格式 Time Format:**
- `30m` = 30分钟 / minutes
- `2h` = 2小时 / hours
- `1d` = 1天 / day

**限制 Limits:**
- 最短5分钟 / Min 5 minutes
- 最长30天 / Max 30 days
- 每个客户最多5个提醒 / Max 5 reminders per client

### `/handoff` — 交接客户

```
/handoff <手机号>
```

将客户交接给维护组（客户状态必须为 `registered`）。
Hand off client to maintenance (must be `registered` status).

---

## 支持与个人 Support & Personal

### `/req` — 请求支持

```
/req <你的问题>
/req <your question>
```

消息自动发送到：
Message auto-sent to:
1. 🛎️ 客服中心群
2. 🎯 管理层 → 🚨紧急 话题

### `/profile` — 个人信息

```
/profile
```

查看你的角色、团队、注册时间等。

### `/lang` — 切换语言

```
/lang zh
/lang en
```

### `/bind` — 绑定账号

```
/bind <你的名字>
/bind <your name>
```

用于绑定已由管理员创建的账号。
Link your Telegram to a pre-seeded staff record.
