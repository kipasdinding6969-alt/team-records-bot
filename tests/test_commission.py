"""Phase 10A: Commission tracking tests — DB operations, auto-calculation, rules, approval."""
import asyncio
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import (
    Client, ClientNote, ClientStatus, Commission, CommissionRule,
    Deposit, NoteType, Staff, StaffRole,
)


@pytest_asyncio.fixture
async def db(tmp_path):
    db_file = str(tmp_path / 'test_commission.db')
    d = DatabaseV2(db_file)
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff_row(db):
    s = Staff(tg_user_id=3001, tg_chat_id=4001, display_name='CommStaff',
              role=StaffRole.FRONTDESK, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def admin_row(db):
    s = Staff(tg_user_id=3002, tg_chat_id=4002, display_name='Admin',
              role=StaffRole.ADMIN, language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager_row(db):
    s = Staff(tg_user_id=3003, tg_chat_id=4003, display_name='Manager',
              role=StaffRole.MANAGER, team='阿俊', language='zh')
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, staff_row):
    c = Client(frontdesk_id=staff_row.id, phone='09001', source='telegram')
    c.id = await db.create_client(c)
    return c


@pytest_asyncio.fixture
async def seeded_db(db):
    """DB with default commission rules seeded."""
    await db.seed_commission_rules()
    return db


class TestCommissionRules:
    @pytest.mark.asyncio
    async def test_seed_commission_rules(self, db):
        """Default rules are seeded on first run."""
        await db.seed_commission_rules()
        rules = await db.get_active_commission_rules()
        assert len(rules) == 3
        triggers = {r.status_trigger for r in rules}
        assert triggers == {'deposit', 'first_deposit', 'registration'}

    @pytest.mark.asyncio
    async def test_seed_idempotent(self, db):
        """Seeding twice does not duplicate rules."""
        await db.seed_commission_rules()
        await db.seed_commission_rules()
        rules = await db.get_active_commission_rules()
        assert len(rules) == 3

    @pytest.mark.asyncio
    async def test_get_rules_by_trigger(self, seeded_db):
        rules = await seeded_db.get_active_commission_rules(trigger='deposit')
        assert len(rules) == 1
        assert rules[0].status_trigger == 'deposit'

    @pytest.mark.asyncio
    async def test_set_rule_deactivates_old(self, seeded_db):
        """Setting a new rule deactivates the old one for same trigger."""
        await seeded_db.set_commission_rule('deposit', 'percentage', 0.10)
        rules = await seeded_db.get_active_commission_rules(trigger='deposit')
        assert len(rules) == 1
        assert rules[0].rate_value == 0.10

    @pytest.mark.asyncio
    async def test_set_rule_with_team(self, seeded_db):
        """Team-specific rule is separate from global."""
        await seeded_db.set_commission_rule('deposit', 'fixed', 20.0, team='阿俊')
        global_rules = await seeded_db.get_active_commission_rules(trigger='deposit')
        team_rules = await seeded_db.get_active_commission_rules(trigger='deposit', team='阿俊')
        # Global rule still active
        assert len(global_rules) == 1
        # Team rule returned (includes global fallback)
        assert any(r.team == '阿俊' for r in team_rules)

    @pytest.mark.asyncio
    async def test_rule_model_fields(self, seeded_db):
        rules = await seeded_db.get_active_commission_rules(trigger='deposit')
        rule = rules[0]
        assert isinstance(rule, CommissionRule)
        assert rule.rate_type == 'percentage'
        assert rule.rate_value == 0.05
        assert rule.is_active is True


class TestCommissionCalculation:
    @pytest.mark.asyncio
    async def test_percentage_commission(self, seeded_db, staff_row, client_row):
        """5% deposit commission is calculated correctly."""
        cid = await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=1000)
        assert cid is not None
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert len(comms) == 1
        assert comms[0].amount == 50.0  # 5% of 1000

    @pytest.mark.asyncio
    async def test_fixed_commission(self, seeded_db, staff_row, client_row):
        """Fixed first_deposit bonus is $10."""
        cid = await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='first_deposit', amount=500)
        assert cid is not None
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert comms[0].amount == 10.0

    @pytest.mark.asyncio
    async def test_registration_bonus(self, seeded_db, staff_row, client_row):
        """Registration bonus is $2 fixed."""
        cid = await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='registration', amount=0)
        assert cid is not None
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert comms[0].amount == 2.0

    @pytest.mark.asyncio
    async def test_no_rule_returns_none(self, db, staff_row, client_row):
        """No commission if no rules exist."""
        cid = await db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=100)
        assert cid is None

    @pytest.mark.asyncio
    async def test_min_amount_filter(self, seeded_db, staff_row, client_row):
        """Min amount rule prevents commission for small deposits."""
        await seeded_db.set_commission_rule('deposit', 'percentage', 0.05, min_amount=500)
        cid = await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=100)
        assert cid is None

    @pytest.mark.asyncio
    async def test_max_commission_cap(self, seeded_db, staff_row, client_row):
        """Max commission caps the payout."""
        await seeded_db.set_commission_rule('deposit', 'percentage', 0.05, max_commission=25.0)
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=1000)
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert comms[0].amount == 25.0  # capped from 50 to 25

    @pytest.mark.asyncio
    async def test_commission_has_period(self, seeded_db, staff_row, client_row):
        """Commission records include a period string."""
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=100)
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert comms[0].period is not None
        assert '-W' in comms[0].period  # ISO week format

    @pytest.mark.asyncio
    async def test_commission_model_fields(self, seeded_db, staff_row, client_row):
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=200)
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        c = comms[0]
        assert isinstance(c, Commission)
        assert c.status == 'pending'
        assert c.staff_id == staff_row.id
        assert c.client_id == client_row.id
        assert c.trigger_type == 'deposit'


class TestCommissionSummaryAndApproval:
    @pytest.mark.asyncio
    async def test_commission_summary(self, seeded_db, staff_row, client_row):
        """Summary aggregates correctly."""
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=1000)
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='first_deposit', amount=1000)
        summary = await seeded_db.get_commission_summary(staff_id=staff_row.id)
        assert summary['total_count'] == 2
        assert summary['total_amount'] == 60.0  # 50 + 10
        assert summary['pending_amount'] == 60.0

    @pytest.mark.asyncio
    async def test_approve_commissions(self, seeded_db, staff_row, client_row, manager_row):
        """Approving pending commissions updates status."""
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=500)
        count = await seeded_db.approve_commissions(manager_row.id, staff_id=staff_row.id)
        assert count == 1
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert comms[0].status == 'approved'
        assert comms[0].approved_by == manager_row.id

    @pytest.mark.asyncio
    async def test_approve_only_pending(self, seeded_db, staff_row, client_row, manager_row):
        """Already approved commissions are not re-approved."""
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=500)
        await seeded_db.approve_commissions(manager_row.id, staff_id=staff_row.id)
        # Second approve should affect 0
        count = await seeded_db.approve_commissions(manager_row.id, staff_id=staff_row.id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_summary_after_approval(self, seeded_db, staff_row, client_row, manager_row):
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=1000)
        await seeded_db.approve_commissions(manager_row.id, staff_id=staff_row.id)
        summary = await seeded_db.get_commission_summary(staff_id=staff_row.id)
        assert summary['pending_amount'] == 0
        assert summary['approved_amount'] == 50.0

    @pytest.mark.asyncio
    async def test_filter_by_period(self, seeded_db, staff_row, client_row):
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=100)
        period = seeded_db._current_week_period()
        comms = await seeded_db.get_commissions(staff_id=staff_row.id, period=period)
        assert len(comms) == 1
        # Wrong period returns empty
        comms_empty = await seeded_db.get_commissions(staff_id=staff_row.id, period='2020-W01')
        assert len(comms_empty) == 0

    @pytest.mark.asyncio
    async def test_filter_by_status(self, seeded_db, staff_row, client_row, manager_row):
        await seeded_db.calculate_commission(
            staff_id=staff_row.id, client_id=client_row.id,
            deposit_id=None, trigger_type='deposit', amount=100)
        pending = await seeded_db.get_commissions(staff_id=staff_row.id, status='pending')
        assert len(pending) == 1
        approved = await seeded_db.get_commissions(staff_id=staff_row.id, status='approved')
        assert len(approved) == 0


class TestFirstDepositAndRegistration:
    @pytest.mark.asyncio
    async def test_is_first_deposit_true(self, db, staff_row, client_row):
        """Client with no deposits returns True."""
        assert await db.is_first_deposit(client_row.id) is True

    @pytest.mark.asyncio
    async def test_is_first_deposit_false(self, db, staff_row, client_row):
        """Client with existing deposit returns False."""
        d = Deposit(client_id=client_row.id, frontdesk_id=staff_row.id,
                    amount=100, deposit_date=date.today())
        await db.create_deposit(d)
        assert await db.is_first_deposit(client_row.id) is False

    @pytest.mark.asyncio
    async def test_is_first_registration_true(self, db, client_row):
        """No prior registration notes means first registration."""
        assert await db.is_first_registration(client_row.id) is True

    @pytest.mark.asyncio
    async def test_is_first_registration_false_after_status_change(self, db, staff_row, client_row):
        """After two registration status changes, is_first_registration is False."""
        # Simulate two registration status changes
        note = ClientNote(client_id=client_row.id, staff_id=staff_row.id,
                          note_type=NoteType.STATUS_CHANGE,
                          old_status='new', new_status='registered')
        await db.add_client_note(note)
        await db.add_client_note(note)
        assert await db.is_first_registration(client_row.id) is False


class TestAutoCalculateHooks:
    @pytest.mark.asyncio
    async def test_auto_deposit_commission(self, seeded_db, staff_row, client_row):
        """auto_calculate_deposit_commission creates deposit + first_deposit commissions."""
        from handlers_v2.commission_handler import auto_calculate_deposit_commission
        # Patch the module-level database_v2 in commission_handler
        with patch('handlers_v2.commission_handler.database_v2', seeded_db):
            await auto_calculate_deposit_commission(
                staff_id=staff_row.id, client_id=client_row.id,
                deposit_id=None, amount=1000, team='阿俊')
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        # Should have both deposit (50) and first_deposit (10)
        triggers = {c.trigger_type for c in comms}
        assert 'deposit' in triggers
        assert 'first_deposit' in triggers

    @pytest.mark.asyncio
    async def test_auto_registration_commission(self, seeded_db, staff_row, client_row):
        """auto_calculate_registration_commission creates registration bonus."""
        from handlers_v2.commission_handler import auto_calculate_registration_commission
        with patch('handlers_v2.commission_handler.database_v2', seeded_db):
            await auto_calculate_registration_commission(client_row.id, 'registered')
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert len(comms) == 1
        assert comms[0].trigger_type == 'registration'
        assert comms[0].amount == 2.0

    @pytest.mark.asyncio
    async def test_auto_registration_skips_non_registered(self, seeded_db, staff_row, client_row):
        """Hook does nothing for non-registered status changes."""
        from handlers_v2.commission_handler import auto_calculate_registration_commission
        with patch('handlers_v2.commission_handler.database_v2', seeded_db):
            await auto_calculate_registration_commission(client_row.id, 'contacted')
        comms = await seeded_db.get_commissions(staff_id=staff_row.id)
        assert len(comms) == 0
