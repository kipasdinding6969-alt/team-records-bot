"""Tests for Phase 9D: Performance Coaching."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole, Client, ClientStatus


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_coaching.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=9300, tg_chat_id=8300, tg_username='coachstaff',
        display_name='教练员工', role=StaffRole.FRONTDESK,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def manager(db):
    s = Staff(
        tg_user_id=9301, tg_chat_id=8301, tg_username='coachmanager',
        display_name='教练经理', role=StaffRole.MANAGER,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client(db, staff):
    c = Client(
        frontdesk_id=staff.id, phone='0400000001', source='facebook',
        status=ClientStatus.NEW,
    )
    c.id = await db.create_client(c)
    return c


# ─── Metrics gathering ────────────────────────────────────────────────────────

class TestMetricsGathering:
    @pytest.mark.asyncio
    async def test_gather_metrics_returns_required_keys(self, db, staff):
        from handlers_v2.coaching import _gather_staff_metrics
        with patch('handlers_v2.coaching.database_v2', db):
            metrics = await _gather_staff_metrics(staff.id)
        required_keys = ['sla_pct', 'team_avg_sla', 'reply_rate', 'conv_rate',
                         'avg_response_min', 'xp_week', 'streak']
        for key in required_keys:
            assert key in metrics, f'Missing key: {key}'

    @pytest.mark.asyncio
    async def test_metrics_defaults_with_no_data(self, db, staff):
        from handlers_v2.coaching import _gather_staff_metrics
        with patch('handlers_v2.coaching.database_v2', db):
            metrics = await _gather_staff_metrics(staff.id)
        assert metrics['sla_pct'] == 0.0
        assert metrics['reply_rate'] == 0.0
        assert metrics['conv_rate'] == 0.0
        assert metrics['xp_week'] == 0

    @pytest.mark.asyncio
    async def test_sla_pct_calculated_from_events(self, db, staff, client):
        from datetime import timedelta, datetime
        from handlers_v2.coaching import _gather_staff_metrics
        # One met SLA event
        started = datetime.utcnow() - timedelta(minutes=15)
        sla_id = await db.start_sla_event(client.id, staff.id, 'first_response', 30, started)
        await db.complete_sla_event(sla_id)
        with patch('handlers_v2.coaching.database_v2', db):
            metrics = await _gather_staff_metrics(staff.id)
        assert metrics['sla_pct'] == 100.0

    @pytest.mark.asyncio
    async def test_xp_week_from_awards(self, db, staff):
        from handlers_v2.coaching import _gather_staff_metrics
        await db.award_xp(staff.id, 'add_client', 10)
        await db.award_xp(staff.id, 'update_status', 5)
        with patch('handlers_v2.coaching.database_v2', db):
            metrics = await _gather_staff_metrics(staff.id)
        assert metrics['xp_week'] >= 15

    @pytest.mark.asyncio
    async def test_streak_reflects_current_streak(self, db, staff):
        from handlers_v2.coaching import _gather_staff_metrics
        await db.award_xp(staff.id, 'add_client', 10)
        with patch('handlers_v2.coaching.database_v2', db):
            metrics = await _gather_staff_metrics(staff.id)
        assert metrics['streak'] >= 1


# ─── Report building ──────────────────────────────────────────────────────────

class TestBuildCoachingReport:
    @pytest.mark.asyncio
    async def test_report_contains_staff_name(self):
        from handlers_v2.coaching import _build_coaching_report
        metrics = {
            'sla_pct': 80.0, 'team_avg_sla': 75.0,
            'reply_rate': 70.0, 'conv_rate': 30.0,
            'avg_response_min': 25.0, 'xp_week': 100, 'streak': 5,
        }
        report = await _build_coaching_report('小测', metrics, '1. 继续保持。\n2. 提高转化率。')
        assert '小测' in report

    @pytest.mark.asyncio
    async def test_report_contains_metrics(self):
        from handlers_v2.coaching import _build_coaching_report
        metrics = {
            'sla_pct': 85.5, 'team_avg_sla': 75.0,
            'reply_rate': 72.0, 'conv_rate': 28.0,
            'avg_response_min': 22.0, 'xp_week': 150, 'streak': 3,
        }
        report = await _build_coaching_report('小明', metrics, '1. 好的建议。')
        assert '85.5' in report
        assert '72.0' in report

    @pytest.mark.asyncio
    async def test_report_contains_ai_tips(self):
        from handlers_v2.coaching import _build_coaching_report
        metrics = {
            'sla_pct': 60.0, 'team_avg_sla': 75.0,
            'reply_rate': 50.0, 'conv_rate': 20.0,
            'avg_response_min': 40.0, 'xp_week': 50, 'streak': 0,
        }
        ai_tips = '1. 加油努力。\n2. 多联系客户。'
        report = await _build_coaching_report('小红', metrics, ai_tips)
        assert '加油努力' in report

    @pytest.mark.asyncio
    async def test_report_has_header(self):
        from handlers_v2.coaching import _build_coaching_report
        metrics = {
            'sla_pct': 90.0, 'team_avg_sla': 80.0,
            'reply_rate': 75.0, 'conv_rate': 35.0,
            'avg_response_min': 18.0, 'xp_week': 200, 'streak': 7,
        }
        report = await _build_coaching_report('阿强', metrics, '1. 非常好。')
        assert '教练报告' in report
        assert '━' in report


# ─── Ollama integration (mocked) ─────────────────────────────────────────────

class TestOllamaIntegration:
    @pytest.mark.asyncio
    async def test_ollama_failure_returns_fallback(self):
        from handlers_v2.coaching import _call_ollama
        import aiohttp
        with patch.object(aiohttp, 'ClientSession', side_effect=Exception('connection refused')):
            result = await _call_ollama('test prompt')
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_ollama_success_returns_response(self):
        from handlers_v2.coaching import _call_ollama
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={'response': '1. 很好的建议。'})
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session.post.return_value = mock_ctx
        with patch('handlers_v2.coaching.aiohttp') as mock_aiohttp:
            mock_aiohttp.ClientSession.return_value = mock_session
            mock_aiohttp.ClientTimeout = MagicMock()
            result = await _call_ollama('test prompt')
        assert isinstance(result, str)


# ─── handle_coaching command (mocked Telegram) ───────────────────────────────

class TestHandleCoachingCommand:
    def _task(self, user_id: int, args: str):
        return {'chat_id': 9000, 'user_id': user_id, 'args': args}

    @pytest.mark.asyncio
    async def test_unregistered_user(self, db):
        from handlers_v2.coaching import handle_coaching
        sent = []
        with patch('handlers_v2.coaching.database_v2', db), \
             patch('handlers_v2.coaching.telegram_handler') as tgh, \
             patch('handlers_v2.coaching._get_staff', return_value=None):
            tgh.send_message = AsyncMock(side_effect=lambda cid, msg: sent.append(msg))
            await handle_coaching(self._task(999, ''))
        assert len(sent) == 1

    @pytest.mark.asyncio
    async def test_team_command_denied_for_frontdesk(self, db, staff):
        from handlers_v2.coaching import handle_coaching
        sent = []
        with patch('handlers_v2.coaching.database_v2', db), \
             patch('handlers_v2.coaching.telegram_handler') as tgh, \
             patch('handlers_v2.coaching._get_staff', return_value=staff), \
             patch('handlers_v2.coaching._call_ollama', return_value='tips'):
            tgh.send_message = AsyncMock(side_effect=lambda cid, msg: sent.append(msg))
            await handle_coaching(self._task(staff.tg_user_id, 'team'))
        # frontdesk can't run /coaching team
        assert any('permission' in m.lower() or '权限' in m for m in sent)
