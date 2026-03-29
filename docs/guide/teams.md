# 团队与群组 Teams & Groups

## 组织架构 Organization

```
📢 QianHub 总频道 (广播 Broadcast)
│
├── 🏢 全线小组 | 阿毛 (Leader)
│   ├── TINO
│   └── KUYA
│
├── 🏢 阿俊小组 | 阿俊 (Maintenance)
│   ├── 阿YIM
│   ├── ODDY
│   ├── 燕燕
│   └── MEYMEY
│
├── 🏢 何军小组 | 何军 (Maintenance)
│   ├── 大杰
│   ├── 阿勇
│   ├── 小龙
│   └── 小宏
│
├── 🔥 炒群小组 | Juan Juan (Leader)
│   └── (跨组成员 Cross-team)
│
├── 🎯 管理层 (Leadership Only)
│
├── 🛎️ 客服中心 (Support)
│   ├── 客服阿毛
│   └── 小白Dyson
│
└── 📢 总频道 (All Staff)
```

## Telegram 群组结构 Group Structure

每个团队群组是 **论坛超级群** (Forum Supergroup)，包含多个话题：

Each team group is a **Forum Supergroup** with organized topics:

| 话题 Topic | 用途 Purpose |
|---|---|
| 📊 日报 Daily Reports | 机器人自动推送团队日报 / Bot auto-posts daily reports |
| 💬 讨论 Discussion | 团队日常讨论 / Team chat |
| ❓ 问题 Issues | 问题和求助 / Issues & help |
| 📋 任务 Tasks | 任务分配 / Task assignments |
| 🔔 通知 Notices | 管理层通知 / Management notices |

### 为什么用论坛？Why Forums?

| 旧方式 Old Way | 新方式 New Way |
|---|---|
| 一个群所有消息混在一起 | 话题分类，日报不会淹没讨论 |
| 需要4-5个群 | 一个群搞定 |
| 找不到之前的报表 | 在📊日报话题里翻就行 |
| 消息太多人不看 | 可以单独关注/静音某个话题 |

## 自动检测 Auto-Detection

当你在团队群组中发命令时，机器人 **自动知道你在哪个组**：

When you send a command in a team group, the bot **auto-detects which team**:

```
你在 🏢 阿俊小组 中输入 /pipeline
→ 机器人自动识别 chat_id → 映射到 "ajun" 团队
→ 显示阿俊组的团队数据

You type /pipeline in 🏢 阿俊小组
→ Bot detects chat_id → maps to "ajun" team
→ Shows 阿俊 team data
```

**不需要手动指定团队！No need to specify team manually!**

## 加入流程 How to Join

1. 向组长要邀请链接 / Get invite link from leader
2. 点击链接加入 Telegram 群组
3. 在私聊中 `/bind 你的名字` 绑定账号
4. 在群组中发命令即可 / Start using commands in group

## 管理层群组 Management Group

🎯 管理层群组是领导专用，包含：

| 话题 Topic | 用途 |
|---|---|
| 📊 总报表 Summary | 全公司汇总报表 |
| 💰 财务 Finance | 财务数据讨论 |
| 🔑 决策 Decisions | 重要决策 |
| 📋 会议 Meetings | 会议记录 |
| 🚨 紧急 Urgent | 紧急事项 + `/req` 支持请求 |

## 客服中心 Support Center

🛎️ 快速响应群（不是论坛，是普通群聊）：

- 所有 `/req` 请求会自动发到这里
- 客服阿毛 + 小白Dyson 负责响应
- 同时也会发到管理层的 🚨紧急 话题
