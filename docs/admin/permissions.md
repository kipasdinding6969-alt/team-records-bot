# 权限矩阵 Permission Matrix

## 角色 Roles

| 角色 Role | 说明 Description |
|---|---|
| `admin` | 🔑 超级管理员 — 全部权限 / Full access |
| `leader` | 👑 组长 — 团队全部权限 / Team full access |
| `manager` | 📋 经理 — 管理权限 / Management access |
| `maintenance` | 🔧 维护 — 管理+数据权限 / Ops access |
| `frontdesk` | 👤 前台 — 日常操作权限 / Daily operations |
| `customer_service` | 🛎️ 客服 — 查看+备注权限 / View + notes |
| `newbie` | 🌱 新人 — 有限权限 / Limited access |
| `viewer` | 👁️ 观察 — 只读权限 / Read-only |

## 完整权限表 Full Permission Table

| 命令 | admin | leader | manager | maint. | front. | CS | newbie | viewer |
|---|---|---|---|---|---|---|---|---|
| `/add` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `/u` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/num` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/info` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `/note` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/search` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `/pipeline` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `/today` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `/followup` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/remind` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/handoff` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/req` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/bind` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `/dashboard` | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ |
| `/team` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| `/target` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `/bulkupdate` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `/setteam` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `/linkgroup` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `/sync` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `/export` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `/rag` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| `/sop` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

## 团队隔离 Team Isolation

在群组中，命令自动限定在本团队：

| 场景 Scenario | 看到的数据 Data Shown |
|---|---|
| 前台在 DM 中用 `/pipeline` | 自己的客户 / Own clients |
| 前台在群组中用 `/pipeline` | 团队汇总 / Team totals |
| 组长在群组中用 `/info phone` | 可查看团队所有成员的客户 |
| 客服用 `/search` | 可搜索所有客户（只读） |
| 新人用 `/add` | 可添加，但不能 `/u` 更新状态 |

## 政策限制 Policy Limits

| 限制 Limit | 值 Value |
|---|---|
| 每日最大新增客户 | 50 |
| 提醒最短间隔 | 5 分钟 |
| 提醒最长时间 | 30 天 |
| 每客户最多提醒 | 5 个 |
| 每日最多备注 | 50 条 |
| 最小入金金额 | 1.0 |
| 最大刀数 | 8 |
| 超时警告 | 48 小时 |
| 超时严重 | 72 小时 |
| 自动标记死亡 | 14 天 |
| 工作时间 | 10:00-22:00 (Europe/Paris) |
