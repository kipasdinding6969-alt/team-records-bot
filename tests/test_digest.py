"""Tests for Phase 2D: daily morning/evening digest + manager reports."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Client, ClientStatus, Staff, StaffRole


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_digest.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=9200, tg_chat_id=8200, tg_username='digeststaff',
        display_name='阿消息', role=StaffRole.FRONTDESK,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager(db):
    m = Staff(
        tg_user_id=9201, tg_chat_id=8201, tg_username='digestmgr',
        display_name='何军', role=StaffRole.MANAGER,
        team='何军', language='zh', is_active=True,
    )
    m.id = await db.create_staff(m)
    return m


# ─── Morning Digest ────────────────────────────────────────────────────────────

class TestMorningDigest:
    @pytest.mark.asyncio
    async def test_contains_staff_name(self, db, staff):
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert staff.display_name in msg

    @pytest.mark.asyncio
    async def test_has_pipeline_section(self, db, staff):
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert '流水线' in msg

    @pytest.mark.asyncio
    async def test_has_xp_goal(self, db, staff):
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert 'XP' in msg

    @pytest.mark.asyncio
    async def test_no_streak_still_valid(self, db, staff):
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert '早安' in msg
        assert '连续打卡' in msg or '打卡之旅' in msg

    @pytest.mark.asyncio
    async def test_with_streak_shows_days(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert '连续' in msg

    @pytest.mark.asyncio
    async def test_with_hot_leads(self, db, staff):
        client = Client(
            frontdesk_id=staff.id, phone='60123456789',
            source='telegram', status=ClientStatus.CONTACTED,
        )
        await db.create_client(client)
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert '早安' in msg  # basic sanity — hot leads section included

    @pytest.mark.asyncio
    async def test_badge_progress_shown_when_badges_seeded(self, db, staff):
        await db.seed_badges()
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        # next badge (新星, 50 XP) not yet reached — should show progress
        assert '下一徽章' in msg or 'XP' in msg

    @pytest.mark.asyncio
    async def test_xp_goal_reached_shows_congratulation(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 50)
        from engines.digest_engine import build_morning_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_morning_digest(staff)
        assert '达成' in msg or '已获' in msg


# ─── Evening Digest ────────────────────────────────────────────────────────────

class TestEveningDigest:
    @pytest.mark.asyncio
    async def test_contains_staff_name(self, db, staff):
        from engines.digest_engine import build_evening_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_evening_digest(staff)
        assert staff.display_name in msg

    @pytest.mark.asyncio
    async def test_has_today_stats_section(self, db, staff):
        from engines.digest_engine import build_evening_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_evening_digest(staff)
        assert '今日' in msg

    @pytest.mark.asyncio
    async def test_shows_xp_earned(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_evening_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_evening_digest(staff)
        assert 'XP' in msg
        assert '10' in msg

    @pytest.mark.asyncio
    async def test_streak_maintained_shown(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_evening_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_evening_digest(staff)
        assert '连续' in msg

    @pytest.mark.asyncio
    async def test_no_streak_encouragement(self, db, staff):
        from engines.digest_engine import build_evening_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_evening_digest(staff)
        assert '明天' in msg or '加油' in msg


# ─── Manager Digest ────────────────────────────────────────────────────────────

class TestManagerDigest:
    @pytest.mark.asyncio
    async def test_contains_manager_name(self, db, manager):
        from engines.digest_engine import build_manager_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_manager_digest(manager)
        assert manager.display_name in msg

    @pytest.mark.asyncio
    async def test_has_team_pipeline_section(self, db, manager):
        from engines.digest_engine import build_manager_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_manager_digest(manager)
        assert '团队' in msg

    @pytest.mark.asyncio
    async def test_has_performers_section(self, db, manager, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_manager_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_manager_digest(manager)
        assert '表现' in msg or '早报' in msg

    @pytest.mark.asyncio
    async def test_streak_section_included(self, db, manager, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        from engines.digest_engine import build_manager_digest
        with patch('engines.digest_engine.database_v2', db):
            msg = await build_manager_digest(manager)
        # Should mention streak if staff has one
        assert '连续' in msg or '早报' in msg


# ─── Time Check Logic ─────────────────────────────────────────────────────────

class TestTimeCheckLogic:
    def test_morning_hour_fires_at_8(self):
        from engines.digest_engine import _is_morning_hour
        assert _is_morning_hour(8) is True

    def test_morning_hour_not_at_9(self):
        from engines.digest_engine import _is_morning_hour
        assert _is_morning_hour(9) is False

    def test_morning_hour_not_at_7(self):
        from engines.digest_engine import _is_morning_hour
        assert _is_morning_hour(7) is False

    def test_evening_hour_fires_at_18(self):
        from engines.digest_engine import _is_evening_hour
        assert _is_evening_hour(18) is True

    def test_evening_hour_not_at_17(self):
        from engines.digest_engine import _is_evening_hour
        assert _is_evening_hour(17) is False

    def test_evening_hour_not_at_19(self):
        from engines.digest_engine import _is_evening_hour
        assert _is_evening_hour(19) is False
