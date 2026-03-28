"""5-tab Google Sheets dashboard — auto-refreshed after each sync cycle.

Tabs written:
  1. 📊 Pipeline Dashboard  — status counts per frontdesk, grouped by team
  2. 🔥 Live Clients        — all active clients sorted by staleness
  3. 💰 Revenue Tracker     — deposits per client grouped by maintenance team
  4. 📈 Team Scoreboard     — today + cumulative stats per frontdesk
  5. ⚠️ Action Required     — stale, no-followup, handoff-needed alerts
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import gspread

from database_v2 import database_v2 as db

logger = logging.getLogger(__name__)

TEAM_STRUCTURE = {
    '阿俊': ['阿YIM', 'ODDY', '燕燕', 'MEYMEY'],
    '何军': ['大杰', '阿勇', '小龙', '小宏'],
}

STATUS_EMOJIS = {
    'new': '🆕', 'contacted': '📱', 'replied': '💬', 'registered': '✅',
    'training': '📚', 'withdrew': '💰', 'ordered': '🎯', 'ghosted': '👻',
    'blocked': '🚫', 'scammed': '⚠️', 'scheduled': '📅', 'dead': '💀',
}

ACTIVE_STATUSES = ['new', 'contacted', 'replied', 'registered', 'training', 'scheduled']
TERMINAL_STATUSES = ['blocked', 'scammed', 'dead']
PIPELINE_STATUSES = ['new', 'contacted', 'replied', 'registered', 'training', 'withdrew', 'ordered']
DEAD_STATUSES = ['ghosted', 'blocked', 'scammed', 'dead']


class DashboardSheets:
    """Writes 5 auto-generated dashboard tabs to the Google Spreadsheet."""

    def __init__(self, writer):
        """writer: GSheetWriter instance with .spreadsheet attribute."""
        self.writer = writer

    @property
    def spreadsheet(self):
        return self.writer.spreadsheet

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _get_or_create_ws(self, title: str, rows: int = 200, cols: int = 20):
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def _fmt_pct(self, num: float, den: float) -> str:
        if not den:
            return '0%'
        return f'{round(num / den * 100, 1)}%'

    def _days_since(self, ts_str: Optional[str]) -> int:
        if not ts_str:
            return 999
        try:
            ts = datetime.fromisoformat(ts_str)
            return max(0, (datetime.now() - ts).days)
        except Exception:
            return 999

    def _fmt_date(self, ts_str: Optional[str], fmt: str = '%b %d') -> str:
        if not ts_str:
            return ''
        try:
            return datetime.fromisoformat(ts_str).strftime(fmt)
        except Exception:
            return ''

    # ─── Tab 1: Pipeline Dashboard ───────────────────────────────────────────

    async def refresh_tab1_pipeline(self):
        ws = self._get_or_create_ws('📊 Pipeline Dashboard', rows=200, cols=14)
        now = datetime.now()
        cutoff_72 = (now - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S')
        active_ph = ','.join(['?'] * len(ACTIVE_STATUSES))

        async with db.get_connection() as conn:
            # Staff with maintenance mapping
            cur = await conn.execute(
                'SELECT id, display_name FROM staff WHERE is_active=1')
            staff_by_name = {r['display_name']: r['id'] for r in await cur.fetchall()}

            # Counts per frontdesk per status
            cur = await conn.execute(
                'SELECT frontdesk_id, status, COUNT(*) as cnt FROM clients GROUP BY frontdesk_id, status')
            counts: Dict[int, Dict[str, int]] = {}
            for r in await cur.fetchall():
                fid = r['frontdesk_id']
                counts.setdefault(fid, {})[r['status']] = r['cnt']

            # Stale counts
            cur = await conn.execute(
                f"""SELECT frontdesk_id, COUNT(*) as cnt FROM clients
                    WHERE status IN ({active_ph}) AND updated_at < ?
                    GROUP BY frontdesk_id""",
                (*ACTIVE_STATUSES, cutoff_72))
            stale_map: Dict[int, int] = {r['frontdesk_id']: r['cnt'] for r in await cur.fetchall()}

        HEADERS = [
            'FRONTDESK', '🆕 New', '📱 Contacted', '💬 Replied', '✅ Registered',
            '📚 Training', '💰 Withdrew', '🎯 Ordered', '💀 Dead/Other', 'TOTAL', 'Conv%', 'Stale',
        ]

        date_str = now.strftime('%Y-%m-%d %H:%M')
        rows = [
            [f'📊 PIPELINE DASHBOARD — Auto-generated {date_str}'],
            [],
        ]

        grand = dict.fromkeys(PIPELINE_STATUSES + ['dead_other', 'total', 'stale'], 0)

        for maint_name, fd_names in TEAM_STRUCTURE.items():
            rows.append([f'TEAM {maint_name}'])
            rows.append(HEADERS)

            team = dict.fromkeys(PIPELINE_STATUSES + ['dead_other', 'total', 'stale'], 0)

            for fd_name in fd_names:
                fid = staff_by_name.get(fd_name)
                if fid is None:
                    continue
                fc = counts.get(fid, {})

                vals = {s: fc.get(s, 0) for s in PIPELINE_STATUSES}
                dead_other = sum(fc.get(s, 0) for s in DEAD_STATUSES)
                total = sum(fc.values())
                stale = stale_map.get(fid, 0)
                ordered = vals['ordered']
                conv = self._fmt_pct(ordered, total)

                rows.append([
                    fd_name,
                    vals['new'], vals['contacted'], vals['replied'], vals['registered'],
                    vals['training'], vals['withdrew'], vals['ordered'],
                    dead_other, total, conv, stale,
                ])

                for s in PIPELINE_STATUSES:
                    team[s] += vals[s]
                team['dead_other'] += dead_other
                team['total'] += total
                team['stale'] += stale

            team_conv = self._fmt_pct(team['ordered'], team['total'])
            rows.append([
                f'{maint_name} TOTAL',
                team['new'], team['contacted'], team['replied'], team['registered'],
                team['training'], team['withdrew'], team['ordered'],
                team['dead_other'], team['total'], team_conv, team['stale'],
            ])
            rows.append([])

            for k in grand:
                grand[k] += team[k]

        grand_conv = self._fmt_pct(grand['ordered'], grand['total'])
        rows.append([
            'GRAND TOTAL',
            grand['new'], grand['contacted'], grand['replied'], grand['registered'],
            grand['training'], grand['withdrew'], grand['ordered'],
            grand['dead_other'], grand['total'], grand_conv, grand['stale'],
        ])

        ws.clear()
        ws.update('A1', rows)

        # Bold title
        try:
            ws.format('A1', {'textFormat': {'bold': True, 'fontSize': 11}})
        except Exception:
            pass

    # ─── Tab 2: Live Clients ─────────────────────────────────────────────────

    async def refresh_tab2_live_clients(self):
        ws = self._get_or_create_ws('🔥 Live Clients', rows=500, cols=10)
        terminal_ph = ','.join(['?'] * len(TERMINAL_STATUSES))

        async with db.get_connection() as conn:
            cur = await conn.execute(
                f"""SELECT c.phone, c.status, c.source, c.next_followup, c.updated_at,
                           c.status_note,
                           s.display_name AS frontdesk_name,
                           m.display_name AS maintenance_name
                    FROM clients c
                    JOIN staff s ON c.frontdesk_id = s.id
                    LEFT JOIN staff m ON s.maintenance_id = m.id
                    WHERE c.status NOT IN ({terminal_ph})
                    ORDER BY c.updated_at ASC
                    LIMIT 500""",
                (*TERMINAL_STATUSES,))
            client_rows = [dict(r) for r in await cur.fetchall()]

        count = len(client_rows)
        rows = [
            [f'🔥 LIVE CLIENT TRACKER — {count} active clients'],
            [],
            ['PHONE', 'FRONTDESK', 'MAINTENANCE', 'STATUS', 'SOURCE',
             'DAYS IN STAGE', 'LAST UPDATE', 'FOLLOW-UP', 'NOTES'],
        ]

        for c in client_rows:
            days = self._days_since(c.get('updated_at'))
            status_str = f"{STATUS_EMOJIS.get(c['status'], '❓')} {c['status']}"
            rows.append([
                c['phone'],
                c.get('frontdesk_name', ''),
                c.get('maintenance_name', ''),
                status_str,
                c.get('source', ''),
                f'{days}d' if days < 999 else '?',
                self._fmt_date(c.get('updated_at')),
                self._fmt_date(c.get('next_followup'), '%b %d %H:%M'),
                c.get('status_note', '') or '',
            ])

        ws.clear()
        ws.update('A1', rows)

        try:
            ws.format('A1', {'textFormat': {'bold': True, 'fontSize': 11}})
        except Exception:
            pass

    # ─── Tab 3: Revenue Tracker ───────────────────────────────────────────────

    async def refresh_tab3_revenue(self):
        ws = self._get_or_create_ws('💰 Revenue Tracker', rows=300, cols=16)

        async with db.get_connection() as conn:
            cur = await conn.execute(
                """SELECT c.phone, c.platform, c.status,
                          s.display_name AS frontdesk_name,
                          m.display_name AS maintenance_name,
                          d.amount, d.knife_number
                   FROM clients c
                   JOIN staff s ON c.frontdesk_id = s.id
                   LEFT JOIN staff m ON s.maintenance_id = m.id
                   JOIN deposits d ON d.client_id = c.id
                   ORDER BY m.display_name, s.display_name, c.phone, d.knife_number""")
            dep_rows = [dict(r) for r in await cur.fetchall()]

        # Aggregate by client
        client_data: Dict[tuple, dict] = {}
        for r in dep_rows:
            key = (r['phone'], r.get('maintenance_name') or '', r.get('frontdesk_name') or '')
            if key not in client_data:
                client_data[key] = {
                    'phone': r['phone'],
                    'frontdesk': r.get('frontdesk_name', ''),
                    'maintenance': r.get('maintenance_name', ''),
                    'platform': r.get('platform', ''),
                    'status': r.get('status', ''),
                    'knives': {},
                    'total': 0.0,
                }
            knife = r.get('knife_number') or 0
            client_data[key]['knives'][knife] = client_data[key]['knives'].get(knife, 0) + r['amount']
            client_data[key]['total'] += r['amount']

        KNIFE_HEADER = [
            'CLIENT PHONE', 'FRONTDESK', 'MAINTENANCE', 'PLATFORM',
            '1刀', '2刀', '3刀', '4刀', '5刀', '6刀', '7刀', '8刀', 'TOTAL IN', 'STATUS',
        ]

        rows: list = [['💰 REVENUE TRACKER'], []]

        for maint_name in TEAM_STRUCTURE:
            rows.append([f'TEAM {maint_name}'])
            rows.append(KNIFE_HEADER)

            team_total = 0.0
            team_knives = {i: 0.0 for i in range(1, 9)}

            for (phone, mname, fname), cd in client_data.items():
                if mname != maint_name:
                    continue
                knife_vals = [cd['knives'].get(i, 0) for i in range(1, 9)]
                fmt_vals = [f'${v:,.0f}' if v else '' for v in knife_vals]
                rows.append([
                    phone, cd['frontdesk'], cd['maintenance'], cd['platform'],
                    *fmt_vals, f'${cd["total"]:,.0f}', cd['status'],
                ])
                team_total += cd['total']
                for i in range(1, 9):
                    team_knives[i] += cd['knives'].get(i, 0)

            team_knife_strs = [f'${team_knives[i]:,.0f}' if team_knives[i] else '' for i in range(1, 9)]
            rows.append(['TEAM TOTAL', '', '', '', *team_knife_strs, f'${team_total:,.0f}', ''])
            rows.append([])

        ws.clear()
        ws.update('A1', rows)

        try:
            ws.format('A1', {'textFormat': {'bold': True, 'fontSize': 11}})
        except Exception:
            pass

    # ─── Tab 4: Team Scoreboard ───────────────────────────────────────────────

    async def refresh_tab4_scoreboard(self):
        ws = self._get_or_create_ws('📈 Team Scoreboard', rows=200, cols=12)
        today_str = datetime.now().strftime('%Y-%m-%d')

        async with db.get_connection() as conn:
            cur = await conn.execute(
                'SELECT id, display_name FROM staff WHERE is_active=1')
            staff_by_name: Dict[str, int] = {r['display_name']: r['id'] for r in await cur.fetchall()}

            cur = await conn.execute(
                'SELECT * FROM daily_stats WHERE stat_date=?', (today_str,))
            today_stats: Dict[int, dict] = {r['staff_id']: dict(r) for r in await cur.fetchall()}

            cur = await conn.execute(
                """SELECT staff_id,
                          SUM(new_leads) AS total_new, SUM(contacted) AS total_contacted,
                          SUM(replied) AS total_replied, SUM(registered) AS total_registered,
                          SUM(training) AS total_training, SUM(withdrew) AS total_withdrew,
                          SUM(new_orders) AS total_orders
                   FROM daily_stats GROUP BY staff_id""")
            cum_stats: Dict[int, dict] = {r['staff_id']: dict(r) for r in await cur.fetchall()}

        COLS = ['TEAM', 'FRONTDESK', 'New', 'Reply', 'Reply%',
                'Register', 'Register%', 'Training', 'Withdraw', 'Orders', 'Conv%']

        def stat_row(maint: str, name: str, s: dict) -> list:
            new_c = s.get('new_leads') or s.get('total_new') or 0
            contacted = s.get('contacted') or s.get('total_contacted') or 0
            replied = s.get('replied') or s.get('total_replied') or 0
            registered = s.get('registered') or s.get('total_registered') or 0
            training = s.get('training') or s.get('total_training') or 0
            withdrew = s.get('withdrew') or s.get('total_withdrew') or 0
            orders = s.get('new_orders') or s.get('total_orders') or 0
            return [
                maint, name, new_c, replied,
                self._fmt_pct(replied, contacted),
                registered, self._fmt_pct(registered, replied),
                training, withdrew, orders,
                self._fmt_pct(orders, registered),
            ]

        rows: list = [
            [f'📈 TEAM SCOREBOARD — {today_str}'],
            [],
            ["TODAY'S PERFORMANCE"],
            COLS,
        ]

        for maint_name, fd_names in TEAM_STRUCTURE.items():
            team_today = dict.fromkeys(
                ['new_leads', 'contacted', 'replied', 'registered', 'training', 'withdrew', 'new_orders'], 0)

            for fd_name in fd_names:
                fid = staff_by_name.get(fd_name)
                if fid is None:
                    continue
                s = today_stats.get(fid, {})
                rows.append(stat_row(maint_name, fd_name, s))
                for k in team_today:
                    team_today[k] += s.get(k, 0) or 0

            rows.append(stat_row(maint_name, 'TOTAL', team_today))
            rows.append([])

        rows.append(['CUMULATIVE (ALL TIME)'])
        rows.append(COLS)

        for maint_name, fd_names in TEAM_STRUCTURE.items():
            team_cum = dict.fromkeys(
                ['total_new', 'total_contacted', 'total_replied', 'total_registered',
                 'total_training', 'total_withdrew', 'total_orders'], 0)

            for fd_name in fd_names:
                fid = staff_by_name.get(fd_name)
                if fid is None:
                    continue
                s = cum_stats.get(fid, {})
                rows.append(stat_row(maint_name, fd_name, s))
                for k in team_cum:
                    team_cum[k] += s.get(k, 0) or 0

            rows.append(stat_row(maint_name, 'TOTAL', team_cum))
            rows.append([])

        ws.clear()
        ws.update('A1', rows)

        try:
            ws.format('A1', {'textFormat': {'bold': True, 'fontSize': 11}})
        except Exception:
            pass

    # ─── Tab 5: Action Required ───────────────────────────────────────────────

    async def refresh_tab5_action_required(self):
        ws = self._get_or_create_ws('⚠️ Action Required', rows=200, cols=8)
        now = datetime.now()
        cutoff_72 = (now - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S')
        active_ph = ','.join(['?'] * len(ACTIVE_STATUSES))

        alerts: list = []

        async with db.get_connection() as conn:
            # Stale clients > 72h in active status
            cur = await conn.execute(
                f"""SELECT c.phone, c.status, c.updated_at,
                           s.display_name AS frontdesk_name,
                           m.display_name AS maintenance_name
                    FROM clients c
                    JOIN staff s ON c.frontdesk_id = s.id
                    LEFT JOIN staff m ON s.maintenance_id = m.id
                    WHERE c.status IN ({active_ph}) AND c.updated_at < ?
                    ORDER BY c.updated_at ASC LIMIT 50""",
                (*ACTIVE_STATUSES, cutoff_72))
            for r in await cur.fetchall():
                days = self._days_since(r['updated_at'])
                alerts.append({
                    'priority': '🔴 HIGH' if days > 3 else '🟡 MED',
                    'type': f'STALE >{days * 24}h',
                    'client': r['phone'],
                    'frontdesk': r['frontdesk_name'] or '',
                    'maintenance': r['maintenance_name'] or '',
                    'details': f"{r['status']} since {self._fmt_date(r['updated_at'])}",
                    'days_overdue': days,
                })

            # Registered but no training date
            cur = await conn.execute(
                """SELECT c.phone, c.registered_at,
                          s.display_name AS frontdesk_name,
                          m.display_name AS maintenance_name
                   FROM clients c
                   JOIN staff s ON c.frontdesk_id = s.id
                   LEFT JOIN staff m ON s.maintenance_id = m.id
                   WHERE c.status = 'registered' AND c.training_at IS NULL
                   ORDER BY c.registered_at ASC LIMIT 30""")
            for r in await cur.fetchall():
                days = self._days_since(r['registered_at'])
                alerts.append({
                    'priority': '🟡 MED',
                    'type': 'NO FOLLOWUP',
                    'client': r['phone'],
                    'frontdesk': r['frontdesk_name'] or '',
                    'maintenance': r['maintenance_name'] or '',
                    'details': 'registered but no training date',
                    'days_overdue': days,
                })

            # Ready for handoff (registered/training, no handoff_at)
            try:
                cur = await conn.execute(
                    """SELECT c.phone, c.status, c.registered_at,
                              s.display_name AS frontdesk_name,
                              m.display_name AS maintenance_name
                       FROM clients c
                       JOIN staff s ON c.frontdesk_id = s.id
                       LEFT JOIN staff m ON s.maintenance_id = m.id
                       WHERE c.status IN ('registered', 'training') AND c.handoff_at IS NULL
                       ORDER BY c.registered_at ASC LIMIT 30""")
                for r in await cur.fetchall():
                    days = self._days_since(r['registered_at'])
                    alerts.append({
                        'priority': '🟢 LOW',
                        'type': 'HANDOFF NEEDED',
                        'client': r['phone'],
                        'frontdesk': r['frontdesk_name'] or '',
                        'maintenance': r['maintenance_name'] or '',
                        'details': f"{r['status']}, ready for maintenance",
                        'days_overdue': days,
                    })
            except Exception:
                pass  # handoff_at may not exist yet on old DBs

        _priority_order = {'🔴 HIGH': 0, '🟡 MED': 1, '🟢 LOW': 2}
        alerts.sort(key=lambda a: _priority_order.get(a['priority'], 3))

        count = len(alerts)
        rows: list = [
            [f'⚠️ ACTION REQUIRED — {count} items need attention'],
            [],
            ['PRIORITY', 'TYPE', 'CLIENT', 'FRONTDESK', 'MAINTENANCE', 'DETAILS', 'DAYS OVERDUE'],
        ]
        for a in alerts[:50]:
            rows.append([
                a['priority'], a['type'], a['client'],
                a['frontdesk'], a['maintenance'], a['details'], a['days_overdue'],
            ])

        ws.clear()
        ws.update('A1', rows)

        try:
            ws.format('A1', {'textFormat': {'bold': True, 'fontSize': 11}})
        except Exception:
            pass

    # ─── Entry point ──────────────────────────────────────────────────────────

    async def refresh_all_tabs(self):
        """Refresh all 5 dashboard tabs. Call after each sync cycle."""
        if self.writer.spreadsheet is None:
            logger.warning('DashboardSheets: spreadsheet not connected, skipping')
            return

        tabs = [
            ('📊 Pipeline Dashboard', self.refresh_tab1_pipeline),
            ('🔥 Live Clients',       self.refresh_tab2_live_clients),
            ('💰 Revenue Tracker',    self.refresh_tab3_revenue),
            ('📈 Team Scoreboard',    self.refresh_tab4_scoreboard),
            ('⚠️ Action Required',    self.refresh_tab5_action_required),
        ]

        for name, fn in tabs:
            try:
                await fn()
                logger.info(f'DashboardSheets: refreshed {name}')
            except Exception as e:
                logger.error(f'DashboardSheets: failed to refresh {name}: {e}')
            await asyncio.sleep(1)  # rate-limit between sheet writes


# Module-level singleton — set by main.py after GSheetWriter is initialized
dashboard_sheets: Optional['DashboardSheets'] = None
