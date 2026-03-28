"""V2 pipeline handlers — /pipeline, /followup, /today, /search, /rag, /sop."""
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

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'pipeline'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language
    counts = await database_v2.get_pipeline_counts(staff.id)

    stale = await database_v2.get_stale_clients(staff.id, hours=72)
    followup_due = await database_v2.get_followup_due(staff.id)

    text = _build_pipeline_text(counts, staff.display_name, lang)
    if stale:
        text += f'\n\n⚠️ {t("stale_count", lang, count=len(stale))}'
    if followup_due:
        text += f'\n🔥 {t("followup_due_count", lang, count=len(followup_due))}'

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

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'followup'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
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

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'today'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language

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

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'search'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
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

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'rag'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
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


async def handle_me(task_data: Dict[str, Any]):
    """/me — ALL-IN-ONE: pipeline + today stats + followup + stale in one message."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'me'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language
    today = date.today()
    now = datetime.now()
    lines = []

    lines.append(f'🐉 **{staff.display_name}** — {today.strftime("%Y-%m-%d %H:%M")}')
    if staff.team:
        lines.append(f'👥 Team: {staff.team}')
    lines.append('')

    counts = await database_v2.get_pipeline_counts(staff.id)
    total = sum(counts.values())
    lines.append('━━━ 📊 PIPELINE ━━━')
    stages = [
        (ClientStatus.NEW, '🆕'), (ClientStatus.CONTACTED, '📱'),
        (ClientStatus.REPLIED, '💬'), (ClientStatus.REGISTERED, '✅'),
        (ClientStatus.TRAINING, '📚'), (ClientStatus.WITHDREW, '💰'),
        (ClientStatus.ORDERED, '🎯'),
    ]
    for status, emoji in stages:
        cnt = counts.get(status.value, 0)
        bar = '█' * min(cnt, 20)
        lines.append(f'{emoji} {status.value:<11} {cnt:>3}  {bar}')
    other = sum(counts.get(s.value, 0) for s in [ClientStatus.GHOSTED, ClientStatus.BLOCKED, ClientStatus.SCAMMED, ClientStatus.DEAD])
    if other:
        lines.append(f'💀 {"other":<11} {other:>3}')
    lines.append(f'   {"TOTAL":<11} {total:>3}')
    lines.append('')

    stat = await database_v2.calculate_daily_stats(staff.id)
    await database_v2.upsert_daily_stats(stat)
    lines.append('━━━ 📈 TODAY ━━━')
    lines.append(f'🆕 New: {stat.new_leads}  📱 Contacted: {stat.contacted}  💬 Replied: {stat.replied}')
    lines.append(f'✅ Registered: {stat.registered}  📚 Training: {stat.training}  🎯 Orders: {stat.new_orders}')
    if stat.contacted > 0:
        lines.append(f'📊 Reply rate: {stat.reply_rate}%  |  Conv rate: {stat.conversion_rate}%')
    if stat.total_deposit > 0:
        lines.append(f'💵 Deposits: ${stat.total_deposit:.2f}')
    lines.append('')

    followup_due = await database_v2.get_followup_due(staff.id)
    stale = await database_v2.get_stale_clients(staff.id, hours=48)
    all_urgent = {c.id: c for c in followup_due + stale}

    if all_urgent:
        lines.append(f'━━━ ⚠️ NEEDS ATTENTION ({len(all_urgent)}) ━━━')
        for c in list(all_urgent.values())[:8]:
            hours_ago = int((now - c.updated_at).total_seconds() / 3600) if c.updated_at else 999
            lines.append(f'{c.status_emoji()} {c.phone} — {c.status.value} ({hours_ago}h ago)')
            if c.status_note:
                lines.append(f'   📝 {c.status_note[:50]}')
        if len(all_urgent) > 8:
            lines.append(f'   ... +{len(all_urgent) - 8} more')
    else:
        lines.append('━━━ ✅ ALL CLEAR ━━━')
        lines.append('No stale clients or pending follow-ups!')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_overview(task_data: Dict[str, Any]):
    """/overview — ALL-IN-ONE for managers: all teams, all stats."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if not staff.is_manager_or_above():
        await telegram_handler.send_message(chat_id, t('err_manager_only', staff.language))
        return

    lang = staff.language
    today = date.today()
    now = datetime.now()
    lines = []

    lines.append(f'🏢 **TEAM OVERVIEW** — {today}')
    lines.append('')

    await database_v2.recalculate_all_today_stats()

    all_staff = await database_v2.get_all_staff()
    teams = {}
    for s in all_staff:
        if hasattr(s, 'maintenance_id') and s.maintenance_id:
            maint = await database_v2.get_staff_by_id(s.maintenance_id)
            team_name = maint.display_name if maint else 'Unassigned'
        elif s.team:
            team_name = s.team
        else:
            team_name = 'Unassigned'
        if s.role.value in ('frontdesk',):
            teams.setdefault(team_name, []).append(s)

    grand_totals = {'leads': 0, 'reg': 0, 'orders': 0, 'stale': 0}

    for team_name, members in teams.items():
        lines.append(f'━━━ 👥 {team_name} ━━━')
        team_leads = team_reg = team_orders = team_stale = 0
        for m in members:
            stat = await database_v2.get_daily_stats(m.id, today)
            stale_count = len(await database_v2.get_stale_clients(m.id, hours=72))
            nl = stat.new_leads if stat else 0
            reg = stat.registered if stat else 0
            orders = stat.new_orders if stat else 0
            stale_flag = f' 🔴{stale_count}' if stale_count > 0 else ''
            lines.append(f'  {m.display_name}: 🆕{nl} ✅{reg} 🎯{orders}{stale_flag}')
            team_leads += nl; team_reg += reg; team_orders += orders; team_stale += stale_count
        conv = f'{team_orders/team_reg*100:.0f}%' if team_reg > 0 else '—'
        lines.append(f'  **TOTAL**: 🆕{team_leads} ✅{team_reg} 🎯{team_orders} (Conv: {conv}) ⚠️{team_stale} stale')
        lines.append('')
        grand_totals['leads'] += team_leads
        grand_totals['reg'] += team_reg
        grand_totals['orders'] += team_orders
        grand_totals['stale'] += team_stale

    lines.append('━━━ 🏆 GRAND TOTAL ━━━')
    g_conv = f'{grand_totals["orders"]/grand_totals["reg"]*100:.0f}%' if grand_totals['reg'] > 0 else '—'
    lines.append(f'🆕 {grand_totals["leads"]} leads  ✅ {grand_totals["reg"]} registered  🎯 {grand_totals["orders"]} orders  (Conv: {g_conv})')
    if grand_totals['stale'] > 0:
        lines.append(f'⚠️ {grand_totals["stale"]} stale clients need attention')
    else:
        lines.append('✅ No stale clients!')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_sop(task_data: Dict[str, Any]):
    """/sop <topic> — search Obsidian vault for SOPs and training material."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'sop'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language
    if not args:
        await telegram_handler.send_message(chat_id, t('sop_usage', lang))
        return

    try:
        from engines.obsidian_brain import obsidian_brain
        content = await obsidian_brain.get_sop(args)
    except Exception as e:
        logger.error(f'/sop Obsidian search failed: {e}')
        content = ''

    if not content:
        # Fallback to RAG search
        try:
            from engines.rag_engine import search_similar
            results = await search_similar(args, top_k=3)
            if results:
                lines = [t('sop_rag_fallback', lang, query=args), '']
                for r in results:
                    if r['source_type'] in ('obsidian_doc', 'obsidian_sop', 'policy'):
                        lines.append(f'📖 {r["text_chunk"][:200]}')
                        lines.append('')
                content = '\n'.join(lines) if len(lines) > 2 else ''
        except Exception:
            pass

    if not content:
        await telegram_handler.send_message(chat_id, t('sop_not_found', lang, topic=args))
        return

    header = t('sop_results_title', lang, topic=args)
    await telegram_handler.send_message(chat_id, f'{header}\n\n{content[:2000]}')


PIPELINE_COMMANDS = {
    'me': handle_me,
    'overview': handle_overview,
    'pipeline': handle_pipeline,
    'followup': handle_followup,
    'today': handle_today,
    'search': handle_search,
    'rag': handle_rag_search,
    'sop': handle_sop,
}

PIPELINE_CALLBACKS = {}
PIPELINE_CONVERSATIONS = {}
