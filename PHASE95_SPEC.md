# Phase 9.5: Zero-Learning UX Overhaul

## Problem
51 commands, zero team usage. Workers won't learn slash commands. Need tap-only interface.

## Solution: 3-Layer UX

### Layer 1: Persistent Reply Keyboard (PRIMARY)

On `/start` and EVERY bot response, attach a `ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)`:

```
┌─────────────┬─────────────┐
│ 📋 我的客户  │ ➕ 添加客户  │
├─────────────┼─────────────┤
│ 🔥 待跟进    │ 📊 看板     │
├─────────────┼─────────────┤
│ 🎤 语音更新  │ 🏆 排行榜   │
└─────────────┴─────────────┘
```

These 6 buttons are ALWAYS visible at the bottom of the chat.

### Button → Action Mapping

| Button Text | Action | Implementation |
|-------------|--------|----------------|
| 📋 我的客户 | Show my assigned clients with status + inline action buttons per client | Reuse pipeline handler, add inline buttons per client |
| ➕ 添加客户 | Start add-client flow with inline source selection (FB/TG/WA/朋友) | Reuse inline_flows add flow |
| 🔥 待跟进 | Show overdue follow-ups with one-tap update buttons | Reuse followup handler + inline buttons |
| 📊 看板 | Open Mini App (WebApp button) | Reuse mini_app handler |
| 🎤 语音更新 | Show instructions: "发送语音消息，说出客户名字和更新内容" | New small handler |
| 🏆 排行榜 | XP leaderboard + my stats | Reuse gamification_v2 handler |

### Layer 2: Menu Button → Mini App

On bot startup, call Telegram API to set the Menu Button:

```python
from telethon.tl.functions.bots import SetBotMenuButtonRequest
from telethon.tl.types import BotMenuButtonWebApp, DataJSON

await bot_client(SetBotMenuButtonRequest(
    user_id=...,  # InputUserEmpty for all users
    button=BotMenuButtonWebApp(
        text='📊 CRM看板',
        url=MINI_APP_URL
    )
))
```

This replaces the ☰ menu icon with a permanent "📊 CRM看板" button.

### Layer 3: Improved /start Welcome

Replace current /start with personalized dashboard:

```
👋 你好 {name}！

📊 今日统计
├ 我的客户: 12
├ 待跟进: 3 ⚠️
├ 今日新增: 1
└ 🔥 连续 5 天

💡 点击下方按钮开始工作
   或发送🎤语音消息更新客户
```

+ persistent keyboard below

### BotFather Commands: Cut to 6

```
start - 🚀 开始
me - 📊 我的仪表板
add - ➕ 添加客户
app - 📊 打开看板
search - 🔍 搜索客户
help - ❓ 帮助
```

All other commands still work but are NOT registered in BotFather menu.

## Files to Create/Modify

### New Files
- `handlers_v2/persistent_keyboard.py` — Keyboard definition + text-button handlers
- `tests/test_persistent_keyboard.py` — Tests for button text → action routing

### Modified Files
- `main.py` — Register text message handlers for button texts, set Menu Button on startup
- `handlers_v2/menu.py` — /start shows personalized dashboard + keyboard
- `telegram_handler.py` — Helper to attach persistent keyboard to any message (if needed)

## Technical Details

### Text Message Routing
When a user taps a persistent keyboard button, Telegram sends it as a regular text message.
The bot needs to intercept messages matching button texts BEFORE the NL handler.

In main.py's message processing:
```python
KEYBOARD_ROUTES = {
    '📋 我的客户': handle_my_clients,
    '➕ 添加客户': handle_add_client_flow,
    '🔥 待跟进': handle_followup_list,
    '📊 看板': handle_app,
    '🎤 语音更新': handle_voice_instructions,
    '🏆 排行榜': handle_xp_leaderboard,
}

# In message handler, check KEYBOARD_ROUTES first
text = message.text.strip()
if text in KEYBOARD_ROUTES:
    await KEYBOARD_ROUTES[text](task_data)
    return
```

### Keyboard Helper
```python
def get_persistent_keyboard(lang='zh'):
    """Return the always-visible reply keyboard."""
    if lang == 'zh':
        buttons = [
            ['📋 我的客户', '➕ 添加客户'],
            ['🔥 待跟进', '📊 看板'],
            ['🎤 语音更新', '🏆 排行榜'],
        ]
    else:
        buttons = [
            ['📋 My Clients', '➕ Add Client'],
            ['🔥 Follow-up', '📊 Dashboard'],
            ['🎤 Voice Update', '🏆 Leaderboard'],
        ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)
```

### Every Response Gets Keyboard
Modify `telegram_handler.send_message()` or add a wrapper so that DM messages always include the persistent keyboard unless explicitly suppressed.

## Tests (minimum 10)
1. Test keyboard button text → correct handler routing (6 tests)
2. Test /start shows personalized stats + keyboard
3. Test keyboard in Chinese and English
4. Test Menu Button is set on startup
5. Test unknown text still falls through to NL handler

## Commit Message
```
feat(ux): Phase 9.5 — persistent keyboard, zero-learning UX overhaul
```
