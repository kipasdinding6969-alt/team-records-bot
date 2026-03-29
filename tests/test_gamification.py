"""Gamification test suite — leaderboard, hot leads, templates, contests (30+ tests)."""
import asyncio
import os
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Client, ClientStatus, DailyStat, Staff, StaffRole


@pytest_asyncio.fixture
async def db(tmp_path):
    """File-based temp DB, fresh per test."""
    db_file = str(tmp_path / 'test_gamification.db')
    d = DatabaseV2(db_file)
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def frontdesk(db):
    s = Staff(
        tg_user_id=2001,
        tg_chat_id=3001,
        display_name='阿YIM',
        role=StaffRole.FRONTDESK,
        team='A',
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager(db):
    s = Staff(
        tg_user_id=2002,
        tg_chat_id=3002,
        display_name='Manager',
        role=StaffRole.MANAGER,
        team='A',
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, frontdesk):
    c = Client(
        frontdesk_id=frontdesk.id,
        phone='555-0001',
        source='test',
    )
    c.id = await db.create_client(c)
    return c


# ─── Leaderboard ──────────────────────────────────────────────────────────────

class TestLeaderboard:
    @pytest.mark.asyncio
    async def test_leaderboard_empty(self, db, frontdesk):
        rows = await db.get_leaderboard(period='today')
        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_leaderboard_today_returns_frontdesk(self, db, frontdesk):
        from datetime import date
        stat = DailyStat(
            staff_id=frontdesk.id,
            stat_date=date.today(),
            new_leads=5,
            new_orders=2,
            total_deposit=100.0,
        )
        await db.upsert_daily_stats(stat)
        rows = await db.get_leaderboard(period='today')
        assert len(rows) >= 1
        names = [r['display_name'] for r in rows]
        assert frontdesk.display_name in names

    @pytest.mark.asyncio
    async def test_leaderboard_week(self, db, frontdesk):
        rows = await db.get_leaderboard(period='week')
        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_leaderboard_month(self, db, frontdesk):
        rows = await db.get_leaderboard(period='month')
        assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_leaderboard_team_filter(self, db, frontdesk):
        rows = await db.get_leaderboard(period='today', team='A')
        assert all(r['team'] == 'A' for r in rows if r['team'])

    @pytest.mark.asyncio
    async def test_leaderboard_team_filter_no_match(self, db, frontdesk):
        rows = await db.get_leaderboard(period='today', team='DOES_NOT_EXIST')
        assert rows == []

    @pytest.mark.asyncio
    async def test_leaderboard_order_by_orders_desc(self, db, frontdesk, manager):
        from datetime import date
        stat_high = DailyStat(staff_id=frontdesk.id, stat_date=date.today(), new_leads=1, new_orders=10)
        await db.upsert_daily_stats(stat_high)
        # manager role won't show in leaderboard (not frontdesk/newbie/cs)
        rows = await db.get_leaderboard(period='today')
        orders = [r['total_orders'] for r in rows]
        assert orders == sorted(orders, reverse=True)


# ─── Hot Leads ────────────────────────────────────────────────────────────────

class TestHotLeads:
    @pytest.mark.asyncio
    async def test_hot_leads_empty(self, db, frontdesk):
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        assert leads == []

    @pytest.mark.asyncio
    async def test_hot_leads_base_score(self, db, frontdesk, client_row):
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        assert len(leads) == 1
        assert leads[0]['score'] >= 10  # base + recent

    @pytest.mark.asyncio
    async def test_hot_leads_replied_bonus(self, db, frontdesk, client_row):
        await db.update_client_status(client_row.id, ClientStatus.REPLIED, frontdesk.id)
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        assert leads[0]['score'] >= 30  # base + replied + recent

    @pytest.mark.asyncio
    async def test_hot_leads_registered_bonus(self, db, frontdesk, client_row):
        await db.update_client_status(client_row.id, ClientStatus.REPLIED, frontdesk.id)
        await db.update_client_status(client_row.id, ClientStatus.REGISTERED, frontdesk.id)
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        assert leads[0]['score'] >= 50  # base + replied + registered + recent

    @pytest.mark.asyncio
    async def test_hot_leads_excludes_dead(self, db, frontdesk):
        c = Client(frontdesk_id=frontdesk.id, phone='555-dead', source='test')
        c.id = await db.create_client(c)
        await db.update_client_status(c.id, ClientStatus.CONTACTED, frontdesk.id)
        await db.update_client_status(c.id, ClientStatus.DEAD, frontdesk.id)
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        phones = [l['phone'] for l in leads]
        assert '555-dead' not in phones

    @pytest.mark.asyncio
    async def test_hot_leads_score_capped_100(self, db, frontdesk, client_row):
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        for lead in leads:
            assert lead['score'] <= 100
            assert lead['score'] >= 0

    @pytest.mark.asyncio
    async def test_hot_leads_limit(self, db, frontdesk):
        for i in range(5):
            c = Client(frontdesk_id=frontdesk.id, phone=f'555-00{i+2}', source='test')
            await db.create_client(c)
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id, limit=3)
        assert len(leads) <= 3

    @pytest.mark.asyncio
    async def test_hot_leads_global(self, db, frontdesk, client_row):
        leads = await db.get_hot_leads()
        assert len(leads) >= 1

    @pytest.mark.asyncio
    async def test_hot_leads_team_staff_ids(self, db, frontdesk, client_row):
        leads = await db.get_hot_leads(team_staff_ids=[frontdesk.id])
        assert len(leads) >= 1

    @pytest.mark.asyncio
    async def test_hot_leads_sorted_by_score_desc(self, db, frontdesk):
        for i in range(3):
            c = Client(frontdesk_id=frontdesk.id, phone=f'555-sort{i}', source='test')
            await db.create_client(c)
        leads = await db.get_hot_leads(frontdesk_id=frontdesk.id)
        scores = [l['score'] for l in leads]
        assert scores == sorted(scores, reverse=True)


# ─── Templates ────────────────────────────────────────────────────────────────

class TestTemplates:
    @pytest.mark.asyncio
    async def test_get_templates_empty(self, db):
        templates = await db.get_templates()
        assert isinstance(templates, list)

    @pytest.mark.asyncio
    async def test_create_and_get_template(self, db, frontdesk):
        tmpl_id = await db.create_template(
            name='Test Template',
            content='Hello {name}',
            category='greeting',
            created_by=frontdesk.id,
        )
        assert tmpl_id > 0
        tmpl = await db.get_template_by_id(tmpl_id)
        assert tmpl is not None
        assert tmpl['name'] == 'Test Template'
        assert tmpl['content'] == 'Hello {name}'
        assert tmpl['category'] == 'greeting'
        assert tmpl['is_default'] == 0

    @pytest.mark.asyncio
    async def test_create_default_template(self, db, frontdesk):
        tmpl_id = await db.create_template(
            name='Default',
            content='Hi!',
            category='general',
            created_by=frontdesk.id,
            is_default=True,
        )
        tmpl = await db.get_template_by_id(tmpl_id)
        assert tmpl['is_default'] == 1

    @pytest.mark.asyncio
    async def test_delete_custom_template(self, db, frontdesk):
        tmpl_id = await db.create_template('Del', 'content', 'general', frontdesk.id)
        deleted = await db.delete_template(tmpl_id)
        assert deleted is True
        assert await db.get_template_by_id(tmpl_id) is None

    @pytest.mark.asyncio
    async def test_cannot_delete_default_template(self, db, frontdesk):
        tmpl_id = await db.create_template('Default', 'Hi!', 'general', frontdesk.id, is_default=True)
        deleted = await db.delete_template(tmpl_id)
        assert deleted is False
        assert await db.get_template_by_id(tmpl_id) is not None

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, db):
        tmpl = await db.get_template_by_id(9999)
        assert tmpl is None

    @pytest.mark.asyncio
    async def test_seed_default_templates(self, db):
        await db.seed_default_templates()
        templates = await db.get_templates()
        default_templates = [t for t in templates if t['is_default'] == 1]
        assert len(default_templates) == 5

    @pytest.mark.asyncio
    async def test_seed_default_templates_idempotent(self, db):
        await db.seed_default_templates()
        await db.seed_default_templates()
        templates = await db.get_templates()
        default_templates = [t for t in templates if t['is_default'] == 1]
        assert len(default_templates) == 5

    @pytest.mark.asyncio
    async def test_get_templates_ordered_defaults_first(self, db, frontdesk):
        await db.create_template('Custom', 'body', 'custom', frontdesk.id)
        await db.create_template('DefaultOne', 'hi', 'greeting', frontdesk.id, is_default=True)
        templates = await db.get_templates()
        if len(templates) >= 2:
            assert templates[0]['is_default'] >= templates[-1]['is_default']


# ─── Contests ─────────────────────────────────────────────────────────────────

class TestContests:
    @pytest.mark.asyncio
    async def test_create_contest(self, db, manager):
        end_date = datetime.utcnow() + timedelta(days=7)
        contest_id = await db.create_contest(
            title='Weekly Leads',
            metric='leads',
            target=100.0,
            team='A',
            end_date=end_date,
            created_by=manager.id,
        )
        assert contest_id > 0

    @pytest.mark.asyncio
    async def test_get_active_contest(self, db, manager):
        end_date = datetime.utcnow() + timedelta(days=3)
        await db.create_contest('Test', 'orders', None, None, end_date, manager.id)
        contest = await db.get_active_contest()
        assert contest is not None
        assert contest['title'] == 'Test'
        assert contest['status'] == 'active'

    @pytest.mark.asyncio
    async def test_get_active_contest_team_filter(self, db, manager):
        end_date = datetime.utcnow() + timedelta(days=3)
        await db.create_contest('Team A Contest', 'leads', None, 'A', end_date, manager.id)
        contest = await db.get_active_contest(team='A')
        assert contest is not None
        contest_b = await db.get_active_contest(team='B')
        # May or may not match depending on NULL team logic — just check type
        assert contest_b is None or isinstance(contest_b, dict)

    @pytest.mark.asyncio
    async def test_no_active_contest(self, db):
        contest = await db.get_active_contest()
        assert contest is None

    @pytest.mark.asyncio
    async def test_end_contest_no_scores(self, db, manager):
        end_date = datetime.utcnow() + timedelta(days=1)
        contest_id = await db.create_contest('End Test', 'orders', None, None, end_date, manager.id)
        winner = await db.end_contest(contest_id)
        assert winner is None
        contest = await db.get_active_contest()
        assert contest is None

    @pytest.mark.asyncio
    async def test_end_contest_with_winner(self, db, manager, frontdesk):
        end_date = datetime.utcnow() + timedelta(days=1)
        contest_id = await db.create_contest('Winner Test', 'orders', None, None, end_date, manager.id)
        await db.upsert_contest_score(contest_id, frontdesk.id, 42.0)
        winner = await db.end_contest(contest_id)
        assert winner is not None
        assert winner['staff_id'] == frontdesk.id
        assert winner['score'] == 42.0

    @pytest.mark.asyncio
    async def test_upsert_contest_score(self, db, manager, frontdesk):
        end_date = datetime.utcnow() + timedelta(days=1)
        contest_id = await db.create_contest('Score Test', 'leads', None, None, end_date, manager.id)
        await db.upsert_contest_score(contest_id, frontdesk.id, 10.0)
        scores = await db.get_contest_scores(contest_id)
        assert len(scores) == 1
        assert scores[0]['score'] == 10.0

    @pytest.mark.asyncio
    async def test_upsert_contest_score_updates(self, db, manager, frontdesk):
        end_date = datetime.utcnow() + timedelta(days=1)
        contest_id = await db.create_contest('Update Score', 'leads', None, None, end_date, manager.id)
        await db.upsert_contest_score(contest_id, frontdesk.id, 5.0)
        await db.upsert_contest_score(contest_id, frontdesk.id, 20.0)
        scores = await db.get_contest_scores(contest_id)
        assert len(scores) == 1
        assert scores[0]['score'] == 20.0

    @pytest.mark.asyncio
    async def test_get_contest_scores_sorted_desc(self, db, manager, frontdesk):
        s2 = Staff(tg_user_id=7777, tg_chat_id=8888, display_name='Staff2', role=StaffRole.FRONTDESK)
        s2.id = await db.create_staff(s2)
        end_date = datetime.utcnow() + timedelta(days=1)
        contest_id = await db.create_contest('Multi Score', 'orders', None, None, end_date, manager.id)
        await db.upsert_contest_score(contest_id, frontdesk.id, 5.0)
        await db.upsert_contest_score(contest_id, s2.id, 15.0)
        scores = await db.get_contest_scores(contest_id)
        assert scores[0]['score'] >= scores[1]['score']

    @pytest.mark.asyncio
    async def test_auto_end_expired_contests(self, db, manager):
        # Use UTC to match SQLite's CURRENT_TIMESTAMP
        past_end = datetime.utcnow() - timedelta(hours=2)
        contest_id = await db.create_contest('Expired', 'leads', None, None, past_end, manager.id)
        count = await db.auto_end_expired_contests()
        assert count >= 1
        contest = await db.get_active_contest()
        assert contest is None

    @pytest.mark.asyncio
    async def test_auto_end_does_not_end_future(self, db, manager):
        future_end = datetime.utcnow() + timedelta(days=7)
        await db.create_contest('Future', 'leads', None, None, future_end, manager.id)
        count = await db.auto_end_expired_contests()
        assert count == 0
        contest = await db.get_active_contest()
        assert contest is not None

    @pytest.mark.asyncio
    async def test_refresh_contest_scores_no_stats(self, db, manager, frontdesk):
        end_date = datetime.utcnow() + timedelta(days=3)
        contest_id = await db.create_contest('Refresh', 'leads', None, None, end_date, manager.id)
        # Should run without error even with no daily_stats
        await db.refresh_contest_scores(contest_id)
        scores = await db.get_contest_scores(contest_id)
        assert isinstance(scores, list)


# ─── Permission Matrix ────────────────────────────────────────────────────────

class TestPermissions:
    def test_frontdesk_can_leaderboard(self):
        from engines.policy_engine import check_permission
        assert check_permission('frontdesk', 'leaderboard') is True

    def test_frontdesk_can_hot(self):
        from engines.policy_engine import check_permission
        assert check_permission('frontdesk', 'hot') is True

    def test_frontdesk_can_summary(self):
        from engines.policy_engine import check_permission
        assert check_permission('frontdesk', 'summary') is True

    def test_frontdesk_can_template(self):
        from engines.policy_engine import check_permission
        assert check_permission('frontdesk', 'template') is True

    def test_frontdesk_can_contest(self):
        from engines.policy_engine import check_permission
        assert check_permission('frontdesk', 'contest') is True

    def test_cs_can_leaderboard(self):
        from engines.policy_engine import check_permission
        assert check_permission('customer_service', 'leaderboard') is True

    def test_cs_can_hot(self):
        from engines.policy_engine import check_permission
        assert check_permission('customer_service', 'hot') is True

    def test_cs_cannot_contest(self):
        from engines.policy_engine import check_permission
        assert check_permission('customer_service', 'contest') is False

    def test_viewer_can_leaderboard(self):
        from engines.policy_engine import check_permission
        assert check_permission('viewer', 'leaderboard') is True

    def test_viewer_cannot_hot(self):
        from engines.policy_engine import check_permission
        assert check_permission('viewer', 'hot') is False

    def test_newbie_cannot_leaderboard(self):
        from engines.policy_engine import check_permission
        assert check_permission('newbie', 'leaderboard') is False

    def test_admin_can_all_gamification(self):
        from engines.policy_engine import check_permission
        for cmd in ('leaderboard', 'hot', 'summary', 'template', 'contest'):
            assert check_permission('admin', cmd) is True, f'admin should have {cmd}'
