"""V2 pipeline handlers — /pipeline, /followup, /today, /search, /rag."""
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import ClientStatus, Staff
from i18n import t
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)


async def _get_staff(user_id: int):
    return await database_v2.get_staff_by_tg_id(user_id)


def _build_pipeline_text(counts: Dict[str, int], staff_name: str, lang: str) -> str:
    total = sum(counts.values())

    lines = [t('pipeline_title', lang, name=staff_name), '']

    stages = [
        (ClientStatus.NEW, '🆕'),
        (ClientStatus.CONTACTED, '📱'),
        (ClientStatus.REPLIED, '💬'),
        (ClientStatus.REGISTERED, '✅'),
        (ClientStatus.TRAINING, '📚'),
        (ClientStatus.WITHDREW, '💰'),
        (ClientStatus.ORDERED, '🎯'),
    ]
    for status, emoji in stages:
        cnt = counts.get(status.value, 0)
        lines.append(f'{emoji} {status.value.capitalize()} ({cnt})')

    other_statuses = [ClientStatus.GHOSTED, ClientStatus.BLOCKED, ClientStatus.SCAMMED, ClientStatus.DEAD]
    other_count = sum(counts.get(s.value, 0) for s in other_statuses)
    if other_count:
        lines.append(f'💀 Other ({other_count})')

    lines.append('')
    lines.append(t('pipeline_total', lang, total=total))
    return '\n'.join(lines)


async def handle_pipeline(task_data: Dict[str, Any]):
    """/pipeline — funnel view of own clients."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    counts = await database_v2.get_pipeline_counts(staff.id)

    # Get stale + followup counts
    stale = await database_v2.get_stale_clients(staff.id, hours=72)
    followup_due = await database_v2.get_followup_due(staff.id)

    text = _build_pipeline_text(counts, staff.display_name, lang)
    if stale:
        text += f'\n\n⚠️ {t("stale_count", lang, count=len(stale))}'
    if followup_due:
        text += f'\n🔥 {t("followup_due_count", lang, count=len(followup_due))}'

    # Quick-action hint
    text += f'\n\n/followup  /today  /add'

    await telegram_handler.send_message(chat_id, text)


async def handle_followup(task_data: Dict[str, Any]):
    """/followup — list clients needing follow-up with hours-since-last-update."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    stale = await database_v2.get_stale_clients(staff.id, hours=48)
    due = await database_v2.get_followup_due(staff.id)

    all_clients = {c.id: c for c in stale + due}

    if not all_clients:
        await telegram_handler.send_message(chat_id, t('no_followup', lang))
        return

    now = datetime.now()
    lines = [t('followup_title', lang), '']
    for c in list(all_clients.values())[:20]:
        emoji = c.status_emoji()
        if c.updated_at:
            hours_ago = int((now - c.updated_at).total_seconds() / 3600)
            staleness = f'{hours_ago}h ago'
        else:
            staleness = '?'
        lines.append(f'{emoji} {c.phone} — {c.status.value} ({staleness})')
        if c.status_note:
            lines.append(f'   📝 {c.status_note}')
    if len(all_clients) > 20:
        lines.append(t('and_more_clients', lang, count=len(all_clients) - 20))

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_today(task_data: Dict[str, Any]):
    """/today — auto-calculated today stats with yesterday comparison."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Recalculate fresh for today
    stat = await database_v2.calculate_daily_stats(staff.id)
    await database_v2.upsert_daily_stats(stat)

    today_str = date.today().strftime('%Y-%m-%d')
    lines = [
        t('today_stats_title', lang, name=staff.display_name, date=today_str),
        '',
        f'🆕 {t("new_leads_label", lang)}: {stat.new_leads}',
        f'📱 {t("contacted_label", lang)}: {stat.contacted}',
        f'💬 {t("replied_label", lang)}: {stat.replied}',
        f'✅ {t("registered_label", lang)}: {stat.registered}',
        f'📚 {t("training_label", lang)}: {stat.training}',
        f'💰 {t("withdrew_label", lang)}: {stat.withdrew}',
        f'🎯 {t("orders_label", lang)}: {stat.new_orders}',
        '',
        f'📊 {t("reply_rate_label", lang)}: {stat.reply_rate}%',
        f'📊 {t("conversion_rate_label", lang)}: {stat.conversion_rate}%',
    ]
    if stat.total_deposit:
        lines.append(f'💵 {t("total_deposit_label", lang)}: ${stat.total_deposit:.2f}')

    # Yesterday comparison
    yesterday = date.today() - timedelta(days=1)
    y_stat = await database_v2.get_daily_stats(staff.id, yesterday)
    if y_stat:
        lines.append('')
        lines.append(t('yesterday_comparison', lang))
        def _delta(today_val: int, yest_val: int) -> str:
            diff = today_val - yest_val
            return f'+{diff}' if diff >= 0 else str(diff)
        lines.append(f'  🆕 {_delta(stat.new_leads, y_stat.new_leads)}  '
                     f'✅ {_delta(stat.registered, y_stat.registered)}  '
                     f'🎯 {_delta(stat.new_orders, y_stat.new_orders)}')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_search(task_data: Dict[str, Any]):
    """/search <query> — keyword search clients."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    if not args:
        await telegram_handler.send_message(chat_id, t('search_usage', lang))
        return

    results = await database_v2.search_clients(staff.id, args)
    if not results:
        await telegram_handler.send_message(chat_id, t('search_no_results', lang, query=args))
        return

    lines = [t('search_results_title', lang, query=args, count=len(results)), '']
    for c in results[:10]:
        lines.append(f'{c.status_emoji()} {c.phone} | {c.source} | {c.status.value}')
        if c.status_note:
            lines.append(f'   📝 {c.status_note[:60]}')
    if len(results) > 10:
        lines.append(t('and_more_clients', lang, count=len(results) - 10))

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_rag_search(task_data: Dict[str, Any]):
    """/rag <query> — semantic search via RAG engine."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    if not args:
        await telegram_handler.send_message(chat_id, t('rag_usage', lang))
        return

    try:
        from engines.rag_engine import search_similar
        results = await search_similar(args, top_k=5)
    except Exception as e:
        logger.error(f'RAG search failed: {e}')
        await telegram_handler.send_message(chat_id, t('rag_unavailable', lang))
        return

    if not results:
        await telegram_handler.send_message(chat_id, t('rag_no_results', lang, query=args))
        return

    lines = [t('rag_results_title', lang, query=args), '']
    for r in results:
        score_pct = int(r['score'] * 100)
        lines.append(f'🔍 [{r["source_type"]}:{r["source_id"]}] ({score_pct}%)')
        lines.append(f'   {r["text_chunk"][:100]}')
        lines.append('')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


PIPELINE_COMMANDS = {
    'pipeline': handle_pipeline,
    'followup': handle_followup,
    'today': handle_today,
    'search': handle_search,
    'rag': handle_rag_search,
}

PIPELINE_CALLBACKS = {}
PIPELINE_CONVERSATIONS = {}
