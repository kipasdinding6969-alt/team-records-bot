"""Main menu and navigation handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime

from telethon import Button

from database import database
from telegram_handler import telegram_handler
from i18n import t

logger = logging.getLogger(__name__)


async def _get_lang(user_id: int) -> str:
    """Get user language, default zh."""
    lang = await database.get_user_language(user_id)
    return lang or 'zh'


async def handle_start_command(task_data: Dict[str, Any]):
    """Handle /start — show language picker first."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check if user already has a language set
    lang = await database.get_user_language(user_id)
    if lang:
        # Already chose language, go straight to menu
        await handle_menu_command(task_data)
        return

    # First time: show language picker
    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🇨🇳 中文', 'callback_data': 'set_lang_zh'},
            {'text': '🇬🇧 English', 'callback_data': 'set_lang_en'},
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        t('lang_picker'),
        reply_markup=keyboard
    )


async def handle_set_language(task_data: Dict[str, Any]):
    """Handle language selection callback."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    lang = 'zh' if callback_data == 'set_lang_zh' else 'en'

    # Make sure user exists in DB first
    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        from models import TeamMember
        new_member = TeamMember(
            user_id=user_id,
            chat_id=chat_id,
            username=task_data.get('username'),
            first_name=task_data.get('first_name'),
            last_name=task_data.get('last_name'),
            role='unregistered'
        )
        await database.create_team_member(new_member)

    await database.set_user_language(user_id, lang)

    # Show menu in chosen language
    await handle_menu_command(task_data)


async def handle_menu_command(task_data: Dict[str, Any]):
    """Handle /menu command — display main navigation menu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    lang = await _get_lang(user_id)

    menu_text = f"""{t('main_menu_title', lang)}

{t('main_menu_welcome', lang)}

{t('main_menu_today', lang)} {datetime.now().strftime('%Y-%m-%d %H:%M')}

{t('main_menu_select', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_today_overview', lang), 'callback_data': 'menu_today_overview'},
            {'text': t('btn_analytics', lang), 'callback_data': 'menu_analytics'}
        ],
        [
            {'text': t('btn_submit_report', lang), 'callback_data': 'menu_submit_report'},
            {'text': t('btn_team_manage', lang), 'callback_data': 'menu_team_manage'}
        ],
        [
            {'text': t('btn_reminders', lang), 'callback_data': 'menu_reminders'},
            {'text': t('btn_finance', lang), 'callback_data': 'menu_finance'}
        ],
        [
            {'text': t('btn_my_clients', lang), 'callback_data': 'menu_my_clients'},
            {'text': t('btn_settings', lang), 'callback_data': 'menu_settings'}
        ],
        [
            {'text': t('btn_help', lang), 'callback_data': 'menu_help'},
            {'text': t('btn_refresh', lang), 'callback_data': 'menu_refresh'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        menu_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def handle_today_overview(task_data: Dict[str, Any]):
    """Handle today overview from main menu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    lang = await _get_lang(user_id)

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(chat_id, t('err_not_registered', lang))
        return

    overview_data = await generate_today_overview(member)

    overview_text = f"""{t('today_overview_title', lang)}

{t('today_date', lang)} {datetime.now().strftime('%Y-%m-%d')}

{format_today_overview(overview_data, lang)}

{t('click_for_details', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_view_charts', lang), 'callback_data': 'analytics_daily_funnel'},
            {'text': t('btn_detailed_data', lang), 'callback_data': 'dashboard_today'}
        ],
        [
            {'text': t('btn_new_record', lang), 'callback_data': 'start_report_wizard'},
            {'text': t('btn_pending_reminders', lang), 'callback_data': 'dashboard_reminders'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'},
            {'text': t('btn_refresh', lang), 'callback_data': 'menu_today_overview'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        overview_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_today_overview(member) -> Dict[str, Any]:
    """Generate today's overview data."""
    today = datetime.now()
    today_str = today.strftime("%m月%d日")

    if member.role == 'frontdesk':
        frontdesk_name = member.frontdesk_name or member.first_name
        records = await database.get_client_records_by_frontdesk(frontdesk_name)
        today_records = [r for r in records if r.date == today_str]

        personal_stats = {
            'new_clients': len(today_records),
            'registered': len([r for r in today_records if r.first_day == '注册']),
            'pending': len([r for r in today_records if r.first_day == '待定']),
            'training': len([r for r in today_records if r.second_day == '注册'])
        }
    else:
        personal_stats = None

    async with database.get_connection() as db:
        cursor = await db.execute("""
            SELECT frontdesk_name FROM team_members
            WHERE role = 'frontdesk' AND is_active = TRUE
        """)
        frontdesks = [row[0] for row in await cursor.fetchall()]

    team_stats = {
        'total_new': 0, 'total_registered': 0,
        'total_pending': 0, 'total_training': 0,
        'active_frontdesks': len(frontdesks)
    }

    for frontdesk in frontdesks:
        records = await database.get_client_records_by_frontdesk(frontdesk)
        today_records = [r for r in records if r.date == today_str]
        team_stats['total_new'] += len(today_records)
        team_stats['total_registered'] += len([r for r in today_records if r.first_day == '注册'])
        team_stats['total_pending'] += len([r for r in today_records if r.first_day == '待定'])
        team_stats['total_training'] += len([r for r in today_records if r.second_day == '注册'])

    pending_reminders = await database.get_pending_reminders()
    if member.role == 'frontdesk':
        user_reminders = [r for r in pending_reminders if r.frontdesk_user_id == member.user_id]
        reminders_count = len(user_reminders)
    else:
        reminders_count = len(pending_reminders)

    return {
        'member': member,
        'personal_stats': personal_stats,
        'team_stats': team_stats,
        'reminders_count': reminders_count,
        'date': today
    }


def format_today_overview(data: Dict[str, Any], lang: str = 'zh') -> str:
    """Format today's overview for display."""
    member = data['member']
    personal_stats = data['personal_stats']
    team_stats = data['team_stats']
    reminders_count = data['reminders_count']

    lines = []

    if personal_stats:
        name = member.frontdesk_name or member.first_name
        conv = (personal_stats['registered'] / personal_stats['new_clients'] * 100) if personal_stats['new_clients'] > 0 else 0
        lines.append(t('personal_stats_title', lang, name=name))
        lines.append(f"• {t('new_clients', lang)}: {personal_stats['new_clients']}")
        lines.append(f"• {t('registered', lang)}: {personal_stats['registered']} ({conv:.1f}%)")
        lines.append(f"• {t('pending', lang)}: {personal_stats['pending']}")
        lines.append(f"• {t('training', lang)}: {personal_stats['training']}")
        lines.append("")

    team_conv = (team_stats['total_registered'] / team_stats['total_new'] * 100) if team_stats['total_new'] > 0 else 0
    lines.append(t('team_stats_title', lang))
    lines.append(f"• {t('active_frontdesks', lang)}: {team_stats['active_frontdesks']}")
    lines.append(f"• {t('team_new_clients', lang)}: {team_stats['total_new']}")
    lines.append(f"• {t('team_registered', lang)}: {team_stats['total_registered']} ({team_conv:.1f}%)")
    lines.append(f"• {t('team_pending', lang)}: {team_stats['total_pending']}")
    lines.append(f"• {t('team_training', lang)}: {team_stats['total_training']}")
    lines.append("")
    lines.append(t('reminders_title', lang))
    lines.append(f"• {t('pending_reminders', lang)}: {reminders_count}")

    return "\n".join(lines)


async def handle_menu_callbacks(task_data: Dict[str, Any]):
    """Handle menu-related callback queries."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']
    lang = await _get_lang(user_id)

    if callback_data in ('menu_main', 'menu_refresh'):
        await handle_menu_command(task_data)

    elif callback_data == 'menu_today_overview':
        await handle_today_overview(task_data)

    elif callback_data == 'menu_analytics':
        await show_analytics_submenu(task_data)

    elif callback_data == 'menu_submit_report':
        from handlers.reporting import handle_report_command
        await handle_report_command(task_data)

    elif callback_data == 'menu_team_manage':
        await show_team_management_submenu(task_data)

    elif callback_data == 'menu_reminders':
        from handlers.reminders import handle_remind_command
        await handle_remind_command(task_data)

    elif callback_data == 'menu_finance':
        from handlers.finance import handle_finance_command
        await handle_finance_command(task_data)

    elif callback_data == 'menu_my_clients':
        await show_my_clients(task_data)

    elif callback_data == 'menu_settings':
        await show_settings_submenu(task_data)

    elif callback_data == 'menu_help':
        from handlers.help_guide import handle_help_command
        await handle_help_command(task_data)


async def show_analytics_submenu(task_data: Dict[str, Any]):
    """Show analytics submenu."""
    chat_id = task_data['chat_id']
    lang = await _get_lang(task_data['user_id'])

    text = f"""{t('analytics_title', lang)}

{t('analytics_select', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_daily_charts', lang), 'callback_data': 'analytics_daily_charts'},
            {'text': t('btn_trends', lang), 'callback_data': 'analytics_trends'}
        ],
        [
            {'text': t('btn_leaderboard', lang), 'callback_data': 'analytics_leaderboard'},
            {'text': t('btn_funnel', lang), 'callback_data': 'analytics_funnel'}
        ],
        [
            {'text': t('btn_comparison', lang), 'callback_data': 'analytics_comparison'},
            {'text': t('btn_heatmap', lang), 'callback_data': 'analytics_heatmap'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(chat_id, text, parse_mode='markdown', reply_markup=keyboard)


async def show_team_management_submenu(task_data: Dict[str, Any]):
    """Show team management submenu."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    lang = await _get_lang(user_id)

    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        await telegram_handler.send_message(chat_id, t('err_manager_only', lang))
        return

    text = f"""{t('team_manage_title', lang)}

{t('team_manage_select', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_team_dashboard', lang), 'callback_data': 'dashboard_main'},
            {'text': t('btn_daily_summary', lang), 'callback_data': 'generate_summary'}
        ],
        [
            {'text': t('btn_team_assessment', lang), 'callback_data': 'team_assessment'},
            {'text': t('btn_individual_perf', lang), 'callback_data': 'individual_performance'}
        ],
        [
            {'text': t('btn_active_members', lang), 'callback_data': 'active_members'},
            {'text': t('btn_permissions', lang), 'callback_data': 'permission_management'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(chat_id, text, parse_mode='markdown', reply_markup=keyboard)


async def show_my_clients(task_data: Dict[str, Any]):
    """Show user's client list."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    lang = await _get_lang(user_id)

    member = await database.get_team_member_by_user_id(user_id)
    if not member:
        await telegram_handler.send_message(chat_id, t('err_not_registered', lang))
        return

    if member.role not in ['frontdesk', 'manager', 'admin']:
        await telegram_handler.send_message(chat_id, t('err_frontdesk_only', lang))
        return

    frontdesk_name = member.frontdesk_name or member.first_name
    records = await database.get_client_records_by_frontdesk(frontdesk_name)

    today = datetime.now()
    recent_records = []
    for record in records:
        try:
            record_date = datetime.strptime(f"2024年{record.date}", "%Y年%m月%d日")
            if (today - record_date).days <= 30:
                recent_records.append(record)
        except:
            continue

    total = len(recent_records)
    reg = len([r for r in recent_records if r.first_day == '注册'])
    not_reg = len([r for r in recent_records if r.first_day == '不注册'])
    pend = len([r for r in recent_records if r.first_day == '待定'])

    text = f"""{t('my_clients_title', lang)}

{t('frontdesk_label', lang)} {frontdesk_name}
{t('time_range', lang)}

{t('stats_summary', lang)}
• {t('total_clients', lang)}: {total}
• {t('registered', lang)}: {reg}
• {t('not_registered', lang)}: {not_reg}
• {t('pending', lang)}: {pend}

{t('click_for_details', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_new_client', lang), 'callback_data': 'start_report_wizard'},
            {'text': t('btn_search_client', lang), 'callback_data': 'search_clients'}
        ],
        [
            {'text': t('btn_client_stats', lang), 'callback_data': 'client_statistics'},
            {'text': t('btn_followup', lang), 'callback_data': 'followup_list'}
        ],
        [
            {'text': t('btn_my_charts', lang), 'callback_data': 'my_charts'},
            {'text': t('btn_export', lang), 'callback_data': 'export_my_data'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(chat_id, text, parse_mode='markdown', reply_markup=keyboard)


async def show_settings_submenu(task_data: Dict[str, Any]):
    """Show settings submenu."""
    chat_id = task_data['chat_id']
    lang = await _get_lang(task_data['user_id'])

    text = f"""{t('settings_title', lang)}

{t('settings_select', lang)}"""

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_notifications', lang), 'callback_data': 'settings_notifications'},
            {'text': t('btn_language', lang), 'callback_data': 'settings_language'}
        ],
        [
            {'text': t('btn_timezone', lang), 'callback_data': 'settings_timezone'},
            {'text': t('btn_report_prefs', lang), 'callback_data': 'settings_reports'}
        ],
        [
            {'text': t('btn_profile', lang), 'callback_data': 'settings_profile'},
            {'text': t('btn_privacy', lang), 'callback_data': 'settings_privacy'}
        ],
        [
            {'text': t('btn_back_main', lang), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(chat_id, text, parse_mode='markdown', reply_markup=keyboard)


async def handle_change_language(task_data: Dict[str, Any]):
    """Show language picker from settings."""
    chat_id = task_data['chat_id']

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': '🇨🇳 中文', 'callback_data': 'set_lang_zh'},
            {'text': '🇬🇧 English', 'callback_data': 'set_lang_en'},
        ],
        [
            {'text': t('btn_back_main', await _get_lang(task_data['user_id'])), 'callback_data': 'menu_main'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        t('lang_picker'),
        reply_markup=keyboard
    )


# Command and callback mappings
MENU_COMMANDS = {
    'start': handle_start_command,
    'menu': handle_menu_command,
}

MENU_CALLBACKS = {
    'set_lang_zh': handle_set_language,
    'set_lang_en': handle_set_language,
    'menu_main': handle_menu_callbacks,
    'menu_refresh': handle_menu_callbacks,
    'menu_today_overview': handle_menu_callbacks,
    'menu_analytics': handle_menu_callbacks,
    'menu_submit_report': handle_menu_callbacks,
    'menu_team_manage': handle_menu_callbacks,
    'menu_reminders': handle_menu_callbacks,
    'menu_finance': handle_menu_callbacks,
    'menu_my_clients': handle_menu_callbacks,
    'menu_settings': handle_menu_callbacks,
    'menu_help': handle_menu_callbacks,
    'settings_language': handle_change_language,
}

MENU_CONVERSATIONS = {}
