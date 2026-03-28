"""Financial management handlers."""
import logging
from typing import Dict, Any, List
from datetime import datetime, date, timedelta

from telethon import Button

from database import database
from i18n import t
from models import FinancialRecord
from telegram_handler import telegram_handler
from utils.formatting import format_financial_record, format_currency
from utils.validators import validate_amount, validate_account_id

logger = logging.getLogger(__name__)


async def _get_lang(user_id):
    """Get user language preference."""
    from database import database
    return (await database.get_user_language(user_id)) or 'zh'


async def handle_finance_command(task_data: Dict[str, Any]):
    """Handle /finance command for financial overview."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    args = task_data.get('args', [])

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        lang = await _get_lang(user_id)
        await telegram_handler.send_message(
            chat_id,
            t('err_manager_only', lang)
        )
        return

    # Parse date filter
    target_date = date.today()
    if args:
        try:
            target_date = datetime.strptime(args[0], '%Y-%m-%d').date()
        except ValueError:
            lang = await _get_lang(user_id)
            await telegram_handler.send_message(
                chat_id,
                t('err_invalid_date_format', lang)
            )
            return

    # Generate financial overview
    finance_data = await generate_financial_overview(target_date)

    lang = await _get_lang(user_id)
    overview_text = f"""
{t('finance_title', lang)}

{t('finance_date_label', lang)} {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%m月%d日')})

{format_financial_overview(finance_data, lang)}

{t('finance_click_buttons', lang)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_today_details', lang), 'callback_data': f'finance_details_{target_date}'},
            {'text': t('btn_trend_analysis', lang), 'callback_data': f'finance_trends_{target_date}'}
        ],
        [
            {'text': t('btn_by_frontdesk', lang), 'callback_data': f'finance_by_frontdesk_{target_date}'},
            {'text': t('btn_by_platform', lang), 'callback_data': f'finance_by_platform_{target_date}'}
        ],
        [
            {'text': t('btn_add_record', lang), 'callback_data': 'add_financial_record'},
            {'text': t('btn_refresh', lang), 'callback_data': f'refresh_finance_{target_date}'}
        ]
    ])

    await telegram_handler.send_message(
        chat_id,
        overview_text,
        parse_mode='markdown',
        reply_markup=keyboard
    )


async def generate_financial_overview(target_date: date) -> Dict[str, Any]:
    """Generate financial overview data."""
    date_str = target_date.strftime('%m月%d日')

    # Get financial records for the date
    records = await database.get_financial_records_by_date(date_str)

    # Calculate totals
    total_new_orders = sum(r.new_order_amount or 0 for r in records)
    total_pressure = sum(r.pressure_amount or 0 for r in records)
    total_knives = sum(
        (r.knife_1 or 0) + (r.knife_2 or 0) + (r.knife_3 or 0) + (r.knife_4 or 0) +
        (r.knife_5 or 0) + (r.knife_6 or 0) + (r.knife_7 or 0) + (r.knife_8 or 0)
        for r in records
    )
    total_income = sum(r.total_in or 0 for r in records)

    # Group by frontdesk
    by_frontdesk = {}
    for record in records:
        if record.frontdesk not in by_frontdesk:
            by_frontdesk[record.frontdesk] = {
                'count': 0,
                'new_orders': 0,
                'pressure': 0,
                'knives': 0,
                'total_in': 0
            }

        by_frontdesk[record.frontdesk]['count'] += 1
        by_frontdesk[record.frontdesk]['new_orders'] += record.new_order_amount or 0
        by_frontdesk[record.frontdesk]['pressure'] += record.pressure_amount or 0
        by_frontdesk[record.frontdesk]['knives'] += (
            (record.knife_1 or 0) + (record.knife_2 or 0) + (record.knife_3 or 0) + (record.knife_4 or 0) +
            (record.knife_5 or 0) + (record.knife_6 or 0) + (record.knife_7 or 0) + (record.knife_8 or 0)
        )
        by_frontdesk[record.frontdesk]['total_in'] += record.total_in or 0

    # Group by platform
    by_platform = {}
    for record in records:
        if record.platform not in by_platform:
            by_platform[record.platform] = {
                'count': 0,
                'total_amount': 0
            }

        by_platform[record.platform]['count'] += 1
        by_platform[record.platform]['total_amount'] += record.total_in or 0

    return {
        'date': target_date,
        'records_count': len(records),
        'totals': {
            'new_orders': total_new_orders,
            'pressure': total_pressure,
            'knives': total_knives,
            'total_income': total_income
        },
        'by_frontdesk': by_frontdesk,
        'by_platform': by_platform,
        'records': records[:10]  # Show first 10 records
    }


def format_financial_overview(data: Dict[str, Any], lang: str = 'zh') -> str:
    """Format financial overview for display."""
    totals = data['totals']

    overview = f"""
{t('today_summary_title', lang)}
{t('finance_records_count', lang)} {data['records_count']}
{t('finance_new_orders_total', lang)} ${totals['new_orders']:.2f}
{t('finance_pressure_total', lang)} ${totals['pressure']:.2f}
{t('finance_knives_total', lang)} ${totals['knives']:.2f}
{t('finance_income_total', lang)} ${totals['total_income']:.2f}

{t('by_frontdesk_title', lang)}
"""

    for frontdesk, stats in data['by_frontdesk'].items():
        overview += f"• {frontdesk}: {stats['count']}单, ${stats['total_in']:.2f}\n"

    overview += f"\n{t('by_platform_title', lang)}\n"
    for platform, stats in data['by_platform'].items():
        overview += f"• {platform}: {stats['count']}单, ${stats['total_amount']:.2f}\n"

    return overview.strip()


async def handle_add_financial_record(task_data: Dict[str, Any]):
    """Handle adding new financial record."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    # Check permissions
    member = await database.get_team_member_by_user_id(user_id)
    if not member or member.role not in ['manager', 'admin']:
        lang = await _get_lang(user_id)
        await telegram_handler.send_message(
            chat_id,
            t('err_manager_only', lang)
        )
        return

    lang = await _get_lang(user_id)
    # Start financial record wizard
    wizard_text = f"""
{t('add_financial_record_title', lang)}

{t('add_financial_record_desc', lang)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': t('btn_start_filling', lang), 'callback_data': 'start_financial_wizard'}],
        [{'text': t('btn_cancel', lang), 'callback_data': 'cancel_financial'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        wizard_text,
        reply_markup=keyboard
    )


async def handle_start_financial_wizard(task_data: Dict[str, Any]):
    """Start financial record wizard."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message_id = task_data['message_id']

    # Initialize wizard state
    wizard_state = {
        'step': 'date',
        'record_data': {}
    }

    telegram_handler.set_conversation_state(user_id, wizard_state)

    lang = await _get_lang(user_id)
    date_text = f"""
{t('finance_step_date', lang)}

{t('finance_enter_date', lang)}

{t('finance_current_time', lang)}{datetime.now().strftime('%m月%d日')}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [{'text': f'{t("finance_use_today", lang)} ({datetime.now().strftime("%m月%d日")})', 'callback_data': 'use_today_financial_date'}],
        [{'text': t('btn_cancel', lang), 'callback_data': 'cancel_financial'}]
    ])

    await telegram_handler.edit_message(
        chat_id,
        message_id,
        date_text,
        reply_markup=keyboard
    )


async def handle_financial_wizard_conversation(task_data: Dict[str, Any]):
    """Handle financial wizard conversation."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    message = task_data['message']
    state = task_data['state']

    step = state.get('step')

    if step == 'date':
        await handle_financial_date_input(user_id, chat_id, message, state)
    elif step == 'account_id':
        await handle_financial_account_input(user_id, chat_id, message, state)
    elif step == 'group_id':
        await handle_financial_group_input(user_id, chat_id, message, state)
    elif step == 'frontdesk':
        await handle_financial_frontdesk_input(user_id, chat_id, message, state)
    elif step == 'platform':
        await handle_financial_platform_input(user_id, chat_id, message, state)
    elif step == 'amounts':
        await handle_financial_amounts_input(user_id, chat_id, message, state)


async def handle_financial_date_input(user_id: int, chat_id: int, date_input: str, state: Dict[str, Any]):
    """Handle financial date input."""
    # Simplified date validation for demo
    state['record_data']['date'] = date_input
    state['step'] = 'account_id'
    telegram_handler.set_conversation_state(user_id, state)

    lang = await _get_lang(user_id)
    account_text = f"""
{t('finance_step_account', lang)}

{t('finance_enter_account', lang)}
    """.strip()

    await telegram_handler.send_message(chat_id, account_text)


async def handle_financial_account_input(user_id: int, chat_id: int, account_input: str, state: Dict[str, Any]):
    """Handle account ID input."""
    state['record_data']['account_id'] = account_input
    state['step'] = 'group_id'
    telegram_handler.set_conversation_state(user_id, state)

    lang = await _get_lang(user_id)
    group_text = f"""
{t('finance_step_group', lang)}

{t('finance_enter_group', lang)}
    """.strip()

    await telegram_handler.send_message(chat_id, group_text)


async def handle_financial_group_input(user_id: int, chat_id: int, group_input: str, state: Dict[str, Any]):
    """Handle group ID input."""
    state['record_data']['group_id'] = group_input
    state['step'] = 'frontdesk'
    telegram_handler.set_conversation_state(user_id, state)

    lang = await _get_lang(user_id)
    frontdesk_text = f"""
{t('finance_step_frontdesk', lang)}

{t('finance_enter_frontdesk', lang)}
    """.strip()

    await telegram_handler.send_message(chat_id, frontdesk_text)


async def handle_financial_frontdesk_input(user_id: int, chat_id: int, frontdesk_input: str, state: Dict[str, Any]):
    """Handle frontdesk input."""
    state['record_data']['frontdesk'] = frontdesk_input
    state['step'] = 'platform'
    telegram_handler.set_conversation_state(user_id, state)

    lang = await _get_lang(user_id)
    platform_text = f"""
{t('finance_step_platform', lang)}

{t('finance_select_platform', lang)}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': 'Iconnect', 'callback_data': 'platform_iconnect'},
            {'text': 'MetaTrader', 'callback_data': 'platform_metatrader'}
        ],
        [
            {'text': 'TradingView', 'callback_data': 'platform_tradingview'},
            {'text': t('btn_platform_other', lang), 'callback_data': 'platform_other'}
        ],
        [{'text': t('btn_cancel', lang), 'callback_data': 'cancel_financial'}]
    ])

    await telegram_handler.send_message(chat_id, platform_text, reply_markup=keyboard)


async def handle_platform_selection(task_data: Dict[str, Any]):
    """Handle platform selection."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']
    callback_data = task_data['callback_data']

    state = telegram_handler.get_conversation_state(user_id)
    if not state:
        return

    platform = callback_data.split('platform_')[1]
    if platform == 'other':
        # Ask for custom platform
        lang = await _get_lang(user_id)
        await telegram_handler.send_message(
            chat_id,
            t('finance_enter_platform_name', lang)
        )
        return

    state['record_data']['platform'] = platform.capitalize()
    state['step'] = 'amounts'
    telegram_handler.set_conversation_state(user_id, state)

    lang = await _get_lang(user_id)
    amounts_text = f"""
{t('finance_step_amounts', lang)}

{t('finance_amounts_desc', lang)}

{t('finance_amounts_format', lang)}
    """.strip()

    await telegram_handler.send_message(chat_id, amounts_text)


async def handle_financial_amounts_input(user_id: int, chat_id: int, amounts_input: str, state: Dict[str, Any]):
    """Handle amounts input and show confirmation."""
    try:
        if amounts_input.lower() != 'skip':
            parts = amounts_input.split(',')
            if len(parts) >= 3:
                state['record_data']['new_order_amount'] = float(parts[0]) if parts[0] != '0' else None
                state['record_data']['pressure_amount'] = float(parts[1]) if parts[1] != '0' else None
                state['record_data']['total_in'] = float(parts[2]) if parts[2] != '0' else None
            else:
                lang = await _get_lang(user_id)
                await telegram_handler.send_message(
                    chat_id,
                    t('finance_amounts_format_error', lang)
                )
                return
    except ValueError:
        lang = await _get_lang(user_id)
        await telegram_handler.send_message(
            chat_id,
            t('finance_amounts_number_error', lang)
        )
        return

    # Show confirmation
    await show_financial_confirmation(user_id, chat_id, state)


async def show_financial_confirmation(user_id: int, chat_id: int, state: Dict[str, Any]):
    """Show financial record confirmation."""
    record_data = state['record_data']

    lang = await _get_lang(user_id)
    confirmation_text = f"""
{t('finance_confirm_title', lang)}

{t('finance_confirm_desc', lang)}

{t('finance_date_field', lang)} {record_data['date']}
{t('finance_account_field', lang)} {record_data['account_id']}
{t('finance_group_field', lang)} {record_data['group_id']}
{t('finance_frontdesk_field', lang)} {record_data['frontdesk']}
{t('finance_platform_field', lang)} {record_data['platform']}
{t('finance_new_order_field', lang)} ${record_data.get('new_order_amount', 0):.2f}
{t('finance_pressure_field', lang)} ${record_data.get('pressure_amount', 0):.2f}
{t('finance_total_field', lang)} ${record_data.get('total_in', 0):.2f}
    """.strip()

    keyboard = telegram_handler.create_inline_keyboard([
        [
            {'text': t('btn_confirm_submit', lang), 'callback_data': 'confirm_financial_record'},
            {'text': t('btn_edit', lang), 'callback_data': 'edit_financial_record'}
        ],
        [{'text': t('btn_cancel', lang), 'callback_data': 'cancel_financial'}]
    ])

    await telegram_handler.send_message(
        chat_id,
        confirmation_text,
        reply_markup=keyboard
    )


async def handle_confirm_financial_record(task_data: Dict[str, Any]):
    """Handle financial record confirmation and submission."""
    user_id = task_data['user_id']
    chat_id = task_data['chat_id']

    state = telegram_handler.get_conversation_state(user_id)
    if not state:
        return

    record_data = state['record_data']

    try:
        # Create financial record
        financial_record = FinancialRecord(
            date=record_data['date'],
            account_id=record_data['account_id'],
            group_id=record_data['group_id'],
            frontdesk=record_data['frontdesk'],
            maintenance='',  # This could be added to wizard
            frontdesk_number='',  # Could be auto-filled from member data
            platform=record_data['platform'],
            new_order_amount=record_data.get('new_order_amount'),
            pressure_amount=record_data.get('pressure_amount'),
            total_in=record_data.get('total_in')
        )

        record_id = await database.create_financial_record(financial_record)

        # Clear conversation state
        telegram_handler.clear_conversation_state(user_id)

        lang = await _get_lang(user_id)
        success_text = f"""
{t('finance_success_title', lang)}

记录ID: {record_id}
账户: {record_data['account_id']}
平台: {record_data['platform']}
总金额: ${record_data.get('total_in', 0):.2f}

{t('finance_success_thanks', lang)}
        """.strip()

        await telegram_handler.send_message(chat_id, success_text)

        # Notify managers
        manager_notification = f"""
{t('finance_new_record_notification', lang)}

前台: {record_data['frontdesk']}
平台: {record_data['platform']}
总金额: ${record_data.get('total_in', 0):.2f}
        """.strip()

        await telegram_handler.broadcast_to_managers(manager_notification)

        logger.info(f"New financial record created: {record_id} by user {user_id}")

    except Exception as e:
        logger.error(f"Failed to create financial record: {e}")
        error_text = """
❌ 财务记录添加失败，请稍后重试。
Financial record creation failed, please try again later.
        """.strip()

        await telegram_handler.send_message(chat_id, error_text)


# Command mapping for finance module
FINANCE_COMMANDS = {
    'finance': handle_finance_command
}

FINANCE_CALLBACKS = {
    'add_financial_record': handle_add_financial_record,
    'start_financial_wizard': handle_start_financial_wizard,
    'use_today_financial_date': lambda task_data: handle_financial_date_input(
        task_data['user_id'],
        task_data['chat_id'],
        datetime.now().strftime("%m月%d日"),
        telegram_handler.get_conversation_state(task_data['user_id'])
    ),
    'platform_iconnect': handle_platform_selection,
    'platform_metatrader': handle_platform_selection,
    'platform_tradingview': handle_platform_selection,
    'platform_other': handle_platform_selection,
    'confirm_financial_record': handle_confirm_financial_record,
    'cancel_financial': lambda task_data: telegram_handler.send_message(
        task_data['chat_id'], "操作已取消。 / Operation cancelled."
    )
}

FINANCE_CONVERSATIONS = {
    'date': handle_financial_wizard_conversation,
    'account_id': handle_financial_wizard_conversation,
    'group_id': handle_financial_wizard_conversation,
    'frontdesk': handle_financial_wizard_conversation,
    'platform': handle_financial_wizard_conversation,
    'amounts': handle_financial_wizard_conversation
}