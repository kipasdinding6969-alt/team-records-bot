# 快速入门 Quick Start

## 第一步：绑定账号 Step 1: Link Your Account

### 新员工 New Staff
在 Telegram 私聊 @qianhub_records_bot：
In Telegram, DM @qianhub_records_bot:

```
/start
```

机器人会引导你选择：Bot will guide you through:
1. **语言 Language** → `zh` 或 `en`
2. **角色 Role** → `1` 前台 / `2` 经理 / `3` 管理员
3. **名字 Name** → 你的显示名

### 已有账号 Existing Staff
如果管理员已经创建了你的记录：
If admin already seeded your record:

```
/bind 你的名字
```

例如 Example:
```
/bind 阿YIM
/bind Juan Juan
/bind TINO
```

✅ 绑定成功后，你就可以使用所有命令了
✅ After binding, all commands are available

---

## 第二步：加入你的团队群 Step 2: Join Your Team Group

向你的组长要邀请链接，加入对应的 Telegram 群组：
Ask your team leader for the invite link and join:

| 小组 Team | 组长 Leader |
|---|---|
| 🏢 全线小组 | 阿毛 |
| 🏢 阿俊小组 | 阿俊 |
| 🏢 何军小组 | 何军 |
| 🔥 炒群小组 | Juan Juan |

每个群有这些话题（像论坛一样）：
Each group has these topics (like a forum):

- 📊 **日报** — 机器人自动发每日报表
- 💬 **讨论** — 团队讨论
- ❓ **问题** — 问题和求助
- 📋 **任务** — 任务分配
- 🔔 **通知** — 管理层通知

---

## 第三步：开始工作 Step 3: Start Working

### 添加客户 Add Client
```
/add 46123456789 飞机筛选
/add 46123456789 微信 888
```
- 参数：手机号 + 来源 + 编号（可选）
- Args: phone + source + account_id (optional)

### 设置编号 Set Account ID
```
/num 46123456789 763
```

### 查看客户信息 View Client Info
```
/info 46123456789
```
显示完整客户卡片：手机、编号、状态、来源、时间戳、入金、备注

### 更新状态 Update Status
```
/u 46123456789 contacted
/u 46123456789 registered
```

### 添加备注 Add Note
```
/note 46123456789 客户说明天回电话
```

### 查看管道 View Pipeline
```
/pipeline
```
- 私聊 DM → 显示你的个人数据
- 群组 Group → 显示团队汇总数据

### 请求帮助 Request Support
```
/req 客户46123456789注册有问题
```
消息会自动发送到客服中心和管理层

---

## 常用命令速查 Quick Reference

| 命令 Command | 说明 Description | 示例 Example |
|---|---|---|
| `/start` | 注册新账号 Register | `/start` |
| `/bind` | 绑定已有账号 Link account | `/bind 阿毛` |
| `/add` | 添加客户 Add client | `/add 4612345 飞机` |
| `/num` | 设置编号 Set account ID | `/num 4612345 763` |
| `/u` | 更新状态 Update status | `/u 4612345 registered` |
| `/info` | 查看详情 Client info | `/info 4612345` |
| `/note` | 添加备注 Add note | `/note 4612345 备注内容` |
| `/pipeline` | 管道视图 Pipeline view | `/pipeline` |
| `/today` | 今日汇总 Today's summary | `/today` |
| `/followup` | 待跟进 Follow-ups due | `/followup` |
| `/search` | 搜索客户 Search clients | `/search 关键词` |
| `/remind` | 设置提醒 Set reminder | `/remind 4612345 2h` |
| `/req` | 请求支持 Request support | `/req 需要帮助` |
| `/handoff` | 交接客户 Hand off client | `/handoff 4612345` |
| `/profile` | 个人信息 Your profile | `/profile` |
| `/lang` | 切换语言 Switch language | `/lang en` |
