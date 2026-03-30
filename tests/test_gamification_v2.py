"""Tests for Phase 2B: Duolingo-style XP, streaks, badges, leaderboard."""
import asyncio
from datetime import date, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    """Fresh isolated DB for each test."""
    d = DatabaseV2(str(tmp_path / 'test_gamv2.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    """A single active frontdesk staff member."""
    s = Staff(
        tg_user_id=9100,
        tg_chat_id=8100,
        tg_username='teststaff',
        display_name='阿测试',
        role=StaffRole.FRONTDESK,
        team='阿俊',
        language='zh',
        is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def staff2(db):
    """A second staff member for leaderboard tests."""
    s = Staff(
        tg_user_id=9101,
        tg_chat_id=8101,
        tg_username='teststaff2',
        display_name='阿测试2',
        role=StaffRole.FRONTDESK,
        team='阿俊',
        language='zh',
        is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


# ─── XP Awarding ──────────────────────────────────────────────────────────────

class TestXPAwarding:
    @pytest.mark.asyncio
    async def test_award_xp_inserts_event(self, db, staff):
        awarded = await db.award_xp(staff.id, 'add_client', 10)
        assert awarded == 10

    @pytest.mark.asyncio
    async def test_get_staff_xp_today(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        await db.award_xp(staff.id, 'update_status', 5)
        xp = await db.get_staff_xp(staff.id, 'today')
        assert xp == 15

    @pytest.mark.asyncio
    async def test_get_staff_xp_all(self, db, staff):
        await db.award_xp(staff.id, 'voice_update', 15)
        await db.award_xp(staff.id, 'reply_within_1h', 10)
        xp = await db.get_staff_xp(staff.id, 'all')
        assert xp == 25

    @pytest.mark.asyncio
    async def test_get_staff_xp_zero_when_none(self, db, staff):
        xp = await db.get_staff_xp(staff.id, 'today')
        assert xp == 0

    @pytest.mark.asyncio
    async def test_award_xp_week_period(self, db, staff):
        await db.award_xp(staff.id, 'update_status', 5)
        xp = await db.get_staff_xp(staff.id, 'week')
        assert xp == 5


# ─── Streak Tracking ──────────────────────────────────────────────────────────

class TestStreakTracking:
    @pytest.mark.asyncio
    async def test_first_award_creates_streak(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        streak = await db.get_streak(staff.id)
        assert streak['current_streak'] == 1
        assert streak['longest_streak'] == 1

    @pytest.mark.asyncio
    async def test_same_day_double_award_no_double_streak(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        await db.award_xp(staff.id, 'update_status', 5)
        streak = await db.get_streak(staff.id)
        assert streak['current_streak'] == 1

    @pytest.mark.asyncio
    async def test_consecutive_days_increments_streak(self, db, staff):
        today = date.today()
        yesterday = today - timedelta(days=1)
        # Manually set last_action_date to yesterday
        async with db.get_connection() as conn:
            await conn.execute(
                'INSERT INTO streaks (staff_id, current_streak, longest_streak, last_action_date, freeze_available) VALUES (?,5,5,?,1)',
                (staff.id, yesterday.isoformat())
            )
            await conn.commit()
        await db.update_streak(staff.id)
        streak = await db.get_streak(staff.id)
        assert streak['current_streak'] == 6
        assert streak['longest_streak'] == 6

    @pytest.mark.asyncio
    async def test_missed_day_resets_streak(self, db, staff):
        two_days_ago = date.today() - timedelta(days=2)
        async with db.get_connection() as conn:
            await conn.execute(
                'INSERT INTO streaks (staff_id, current_streak, longest_streak, last_action_date, freeze_available) VALUES (?,10,10,?,1)',
                (staff.id, two_days_ago.isoformat())
            )
            await conn.commit()
        await db.update_streak(staff.id)
        streak = await db.get_streak(staff.id)
        assert streak['current_streak'] == 1
        assert streak['longest_streak'] == 10  # longest preserved

    @pytest.mark.asyncio
    async def test_get_streak_returns_defaults_when_missing(self, db, staff):
        streak = await db.get_streak(staff.id)
        assert streak['current_streak'] == 0
        assert streak['freeze_available'] == 1


# ─── Streak Freeze ────────────────────────────────────────────────────────────

class TestStreakFreeze:
    @pytest.mark.asyncio
    async def test_use_streak_freeze_decrements(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)  # creates streak row
        result = await db.use_streak_freeze(staff.id)
        assert result is True
        streak = await db.get_streak(staff.id)
        assert streak['freeze_available'] == 0

    @pytest.mark.asyncio
    async def test_use_streak_freeze_returns_false_when_empty(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        await db.use_streak_freeze(staff.id)  # use the 1 available
        result = await db.use_streak_freeze(staff.id)  # try again
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_weekly_streak_freezes(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        await db.use_streak_freeze(staff.id)
        await db.reset_weekly_streak_freezes()
        streak = await db.get_streak(staff.id)
        assert streak['freeze_available'] == 1


# ─── Badge Seeding ────────────────────────────────────────────────────────────

class TestBadgeSeeding:
    @pytest.mark.asyncio
    async def test_seed_badges_creates_10_badges(self, db):
        await db.seed_badges()
        badges = await db.get_all_badges()
        assert len(badges) == 10

    @pytest.mark.asyncio
    async def test_seed_badges_idempotent(self, db):
        await db.seed_badges()
        await db.seed_badges()
        badges = await db.get_all_badges()
        assert len(badges) == 10

    @pytest.mark.asyncio
    async def test_seed_badges_correct_names(self, db):
        await db.seed_badges()
        badges = await db.get_all_badges()
        names = [b['name'] for b in badges]
        assert '新星' in names
        assert 'MVP' in names
        assert '传奇' in names

    @pytest.mark.asyncio
    async def test_seed_badges_emojis_present(self, db):
        await db.seed_badges()
        badges = await db.get_all_badges()
        for badge in badges:
            assert badge['emoji'], f"Badge {badge['name']} missing emoji"


# ─── Badge Auto-Award ─────────────────────────────────────────────────────────

class TestBadgeAutoAward:
    @pytest.mark.asyncio
    async def test_xp_threshold_badge_awarded(self, db, staff):
        await db.seed_badges()
        # Award 50+ XP to trigger 新星 (50 XP threshold)
        await db.award_xp(staff.id, 'voice_update', 50)
        new_badges = await db.check_and_award_badges(staff.id)
        names = [b['name'] for b in new_badges]
        assert '新星' in names

    @pytest.mark.asyncio
    async def test_streak_badge_awarded_at_3_days(self, db, staff):
        await db.seed_badges()
        # Simulate 3-day streak
        async with db.get_connection() as conn:
            await conn.execute(
                'INSERT INTO streaks (staff_id, current_streak, longest_streak, last_action_date, freeze_available) VALUES (?,3,3,?,1)',
                (staff.id, date.today().isoformat())
            )
            await conn.commit()
        new_badges = await db.check_and_award_badges(staff.id)
        names = [b['name'] for b in new_badges]
        assert '首次连续' in names

    @pytest.mark.asyncio
    async def test_badge_not_re_awarded(self, db, staff):
        await db.seed_badges()
        await db.award_xp(staff.id, 'voice_update', 50)
        first = await db.check_and_award_badges(staff.id)
        second = await db.check_and_award_badges(staff.id)
        first_names = {b['name'] for b in first}
        second_names = {b['name'] for b in second}
        # Already-earned badges should not appear in second check
        assert not first_names.intersection(second_names)

    @pytest.mark.asyncio
    async def test_get_staff_badges_returns_earned(self, db, staff):
        await db.seed_badges()
        await db.award_xp(staff.id, 'voice_update', 50)
        await db.check_and_award_badges(staff.id)
        earned = await db.get_staff_badges(staff.id)
        assert len(earned) >= 1
        assert all('name' in b and 'emoji' in b for b in earned)


# ─── XP Leaderboard ──────────────────────────────────────────────────────────

class TestXPLeaderboard:
    @pytest.mark.asyncio
    async def test_leaderboard_ordered_by_xp(self, db, staff, staff2):
        await db.award_xp(staff.id, 'voice_update', 15)
        await db.award_xp(staff2.id, 'add_client', 10)
        rows = await db.get_xp_leaderboard(period='today')
        assert rows[0]['total_xp'] >= rows[1]['total_xp']

    @pytest.mark.asyncio
    async def test_leaderboard_filters_by_team(self, db, staff, staff2):
        await db.award_xp(staff.id, 'voice_update', 15)
        await db.award_xp(staff2.id, 'add_client', 10)
        rows = await db.get_xp_leaderboard(period='today', team_id='阿俊')
        names = [r['display_name'] for r in rows]
        assert '阿测试' in names
        assert '阿测试2' in names

    @pytest.mark.asyncio
    async def test_leaderboard_includes_streak(self, db, staff):
        await db.award_xp(staff.id, 'add_client', 10)
        rows = await db.get_xp_leaderboard(period='today')
        assert rows[0]['current_streak'] >= 0


# ─── Gamification Engine ─────────────────────────────────────────────────────

class TestGamificationEngine:
    @pytest.mark.asyncio
    async def test_award_action_xp_returns_amount(self, db, staff):
        from engines.gamification_v2 import award_action_xp
        # Patch the global database_v2 singleton used by the engine
        with patch('engines.gamification_v2.database_v2', db):
            result = await award_action_xp(staff.id, 'add_client')
        assert result['xp_awarded'] == 10

    @pytest.mark.asyncio
    async def test_award_action_xp_unknown_action_returns_zero(self, db, staff):
        from engines.gamification_v2 import award_action_xp
        with patch('engines.gamification_v2.database_v2', db):
            result = await award_action_xp(staff.id, 'unknown_action')
        assert result['xp_awarded'] == 0

    @pytest.mark.asyncio
    async def test_morning_motivation_message(self, db, staff):
        from engines.gamification_v2 import get_morning_motivation
        with patch('engines.gamification_v2.database_v2', db):
            msg = await get_morning_motivation(staff.id, staff.display_name)
        assert staff.display_name in msg
        assert 'XP' in msg

    @pytest.mark.asyncio
    async def test_build_xp_status_message(self, db, staff):
        from engines.gamification_v2 import build_xp_status_message
        await db.award_xp(staff.id, 'add_client', 10)
        with patch('engines.gamification_v2.database_v2', db):
            msg = await build_xp_status_message(staff.id, staff.display_name, 'zh')
        assert '10' in msg
        assert 'XP' in msg

    @pytest.mark.asyncio
    async def test_build_badges_message_empty(self, db, staff):
        from engines.gamification_v2 import build_badges_message
        await db.seed_badges()
        with patch('engines.gamification_v2.database_v2', db):
            msg = await build_badges_message(staff.id, 'zh')
        assert '徽章' in msg
