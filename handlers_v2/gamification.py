"""V2 gamification handlers — /leaderboard, /hot, /summary, /template, /contest."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)

_VALID_METRICS = ('leads', 'orders', 'deposits', 'reply_rate')


# ─── /leaderboard ─────────────────────────────────────────────────────────────

async def handle_leaderboard(task_data: Dict[str, Any]):
    """/leaderboard [today|week|month] — ranked stats for the period."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip().lower()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'leaderboard'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    period = args if args in ('today', 'week', 'month') else 'today'
    period_label_key = f'leaderboard_period_{period}'

    # Scope by team for non-managers
    team_filter = None
    if not staff.is_manager_or_above() and staff.team:
        team_filter = staff.team

    rows = await database_v2.get_leaderboard(period=period, team=team_filter)

    period_label = t(period_label_key, lang)
    lines = [f'{t("leaderboard_title", lang)} — {period_label}', '']

    if not rows:
        lines.append(t('leaderboard_empty', lang))
    else:
        for i, row in enumerate(rows, 1):
            lines.append(t('leaderboard_row', lang,
                           rank=i,
                           name=row['display_name'],
                           leads=int(row['total_leads']),
                           orders=int(row['total_orders']),
                           deposits=float(row['total_deposits'])))

    await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed leaderboard ({period})')


# ─── /hot ─────────────────────────────────────────────────────────────────────

async def handle_hot_leads(task_data: Dict[str, Any]):
    """/hot — top 10 scored hot leads for this user (or team for managers)."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'hot'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    if staff.is_manager_or_above():
        # Managers see all team leads
        team_ids = None
        if staff.team:
            all_staff = await database_v2.get_all_staff()
            team_ids = [s.id for s in all_staff if s.team == staff.team]
        leads = await database_v2.get_hot_leads(team_staff_ids=team_ids)
    else:
        leads = await database_v2.get_hot_leads(frontdesk_id=staff.id)

    lines = [t('hot_leads_title', lang), '']

    if not leads:
        lines.append(t('hot_leads_empty', lang))
    else:
        for i, lead in enumerate(leads, 1):
            name = lead.get('nickname') or '—'
            lines.append(t('hot_leads_row', lang,
                           rank=i,
                           phone=lead['phone'],
                           name=name,
                           status=lead['status'],
                           score=lead['score']))

    await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed hot leads')


# ─── /summary ─────────────────────────────────────────────────────────────────

async def handle_summary(task_data: Dict[str, Any]):
    """/summary [today|week|month] — aggregated team performance summary."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip().lower()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'summary'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    period = args if args in ('today', 'week', 'month') else 'today'
    period_label = t(f'leaderboard_period_{period}', lang)

    team_filter = None
    if not staff.is_manager_or_above() and staff.team:
        team_filter = staff.team

    rows = await database_v2.get_leaderboard(period=period, team=team_filter)

    total_leads = sum(int(r['total_leads']) for r in rows)
    total_orders = sum(int(r['total_orders']) for r in rows)
    total_deposits = sum(float(r['total_deposits']) for r in rows)
    avg_reply_rate = (
        sum(float(r['avg_reply_rate']) for r in rows) / len(rows)
        if rows else 0.0
    )

    lines = [
        t('summary_title', lang),
        t('summary_period', lang, period=period_label),
        '',
        t('summary_leads', lang, count=total_leads),
        t('summary_orders', lang, count=total_orders),
        t('summary_deposits', lang, amount=total_deposits),
        t('summary_reply_rate', lang, rate=avg_reply_rate * 100),
    ]

    await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')
    logger.info(f'Staff {staff.display_name} viewed summary ({period})')


# ─── /template ────────────────────────────────────────────────────────────────

async def handle_template(task_data: Dict[str, Any]):
    """/template [list|view <id>|add <name> <content>|del <id>]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'template'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 2)
    subcommand = parts[0].lower() if parts else 'list'

    if subcommand == 'list' or not parts:
        templates = await database_v2.get_templates()
        lines = [t('template_list_title', lang), '']
        if not templates:
            lines.append(t('template_list_empty', lang))
        else:
            for tmpl in templates:
                default_marker = ' ⭐' if tmpl['is_default'] else ''
                lines.append(t('template_row', lang,
                               id=tmpl['id'],
                               category=tmpl['category'],
                               name=tmpl['name']) + default_marker)
        await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')

    elif subcommand == 'view':
        if len(parts) < 2 or not parts[1].isdigit():
            await telegram_handler.send_message(chat_id, t('template_usage', lang))
            return
        tmpl = await database_v2.get_template_by_id(int(parts[1]))
        if not tmpl:
            await telegram_handler.send_message(chat_id, t('template_not_found', lang, id=parts[1]))
            return
        msg = t('template_view', lang,
                name=tmpl['name'],
                category=tmpl['category'],
                content=tmpl['content'])
        await telegram_handler.send_message(chat_id, msg, parse_mode='markdown')

    elif subcommand == 'add':
        if len(parts) < 3:
            await telegram_handler.send_message(chat_id, t('template_usage', lang))
            return
        name = parts[1]
        content = parts[2]
        category = 'custom'
        tmpl_id = await database_v2.create_template(name, content, category, staff.id)
        await telegram_handler.send_message(chat_id, t('template_added', lang, name=name, id=tmpl_id))
        logger.info(f'Staff {staff.display_name} created template "{name}" (id={tmpl_id})')

    elif subcommand == 'del':
        if not staff.is_manager_or_above():
            await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
            return
        if len(parts) < 2 or not parts[1].isdigit():
            await telegram_handler.send_message(chat_id, t('template_usage', lang))
            return
        tmpl_id = int(parts[1])
        deleted = await database_v2.delete_template(tmpl_id)
        if deleted:
            await telegram_handler.send_message(chat_id, t('template_deleted', lang, id=tmpl_id))
            logger.info(f'Staff {staff.display_name} deleted template {tmpl_id}')
        else:
            await telegram_handler.send_message(chat_id, t('template_not_found', lang, id=tmpl_id))

    else:
        await telegram_handler.send_message(chat_id, t('template_usage', lang))


# ─── /contest ─────────────────────────────────────────────────────────────────

async def handle_contest(task_data: Dict[str, Any]):
    """/contest [new <title> <metric> <days> | end]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'contest'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 3)
    subcommand = parts[0].lower() if parts else 'view'

    if subcommand == 'new':
        if not staff.is_manager_or_above():
            await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
            return
        # /contest new <title> <metric> <days>
        if len(parts) < 4:
            await telegram_handler.send_message(chat_id, t('contest_usage', lang))
            return
        title = parts[1]
        metric = parts[2].lower()
        days_str = parts[3]
        if metric not in _VALID_METRICS:
            await telegram_handler.send_message(chat_id, t('contest_invalid_metric', lang))
            return
        try:
            days = int(days_str)
            if days <= 0:
                raise ValueError
        except ValueError:
            await telegram_handler.send_message(chat_id, t('contest_invalid_days', lang))
            return
        end_date = datetime.now() + timedelta(days=days)
        team_scope = staff.team if not staff.is_manager_or_above() else None
        contest_id = await database_v2.create_contest(
            title=title,
            metric=metric,
            target=None,
            team=team_scope,
            end_date=end_date,
            created_by=staff.id,
        )
        await telegram_handler.send_message(chat_id, t('contest_created', lang,
                                                        title=title,
                                                        id=contest_id,
                                                        end_date=end_date.strftime('%Y-%m-%d')))
        logger.info(f'Staff {staff.display_name} created contest "{title}" metric={metric} days={days}')

    elif subcommand == 'end':
        if not staff.is_manager_or_above():
            await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
            return
        contest = await database_v2.get_active_contest(team=staff.team)
        if not contest:
            await telegram_handler.send_message(chat_id, t('contest_not_found', lang))
            return
        winner = await database_v2.end_contest(contest['id'])
        if winner:
            await telegram_handler.send_message(chat_id, t('contest_ended', lang,
                                                             winner=winner['display_name']))
        else:
            await telegram_handler.send_message(chat_id, t('contest_ended_no_winner', lang))
        logger.info(f'Staff {staff.display_name} ended contest {contest["id"]}')

    else:
        # Default: view current contest + scores
        contest = await database_v2.get_active_contest(team=staff.team)
        if not contest:
            await telegram_handler.send_message(chat_id, t('contest_no_active', lang))
            return

        end_str = contest['end_date'][:10] if contest.get('end_date') else '—'
        lines = [t('contest_active', lang,
                   title=contest['title'],
                   metric=contest['metric'],
                   end_date=end_str)]
        scores = await database_v2.get_contest_scores(contest['id'])
        if scores:
            lines.append(t('contest_scores_header', lang))
            for i, row in enumerate(scores, 1):
                lines.append(t('contest_score_row', lang,
                               rank=i,
                               name=row['display_name'],
                               score=float(row['score'])))
        await telegram_handler.send_message(chat_id, '\n'.join(lines), parse_mode='markdown')
        logger.info(f'Staff {staff.display_name} viewed contest {contest["id"]}')


# ─── Handler registry ─────────────────────────────────────────────────────────

GAMIFICATION_COMMANDS = {
    'leaderboard': handle_leaderboard,
    'hot':         handle_hot_leads,
    'summary':     handle_summary,
    'template':    handle_template,
    'contest':     handle_contest,
}

GAMIFICATION_CALLBACKS: dict = {}
GAMIFICATION_CONVERSATIONS: dict = {}
