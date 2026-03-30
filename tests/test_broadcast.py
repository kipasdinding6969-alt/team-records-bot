"""Tests for Phase 8A: Broadcast Engine."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_broadcast.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def manager(db):
    s = Staff(
        tg_user_id=9001, tg_chat_id=9001,
        display_name='广播经理', role=StaffRole.MANAGER,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def frontdesk(db):
    s = Staff(
        tg_user_id=9002, tg_chat_id=9002,
        display_name='前台员工', role=StaffRole.FRONTDESK,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def clients_data(db, frontdesk):
    """Insert 5 clients with different statuses and sources."""
    async with db.get_connection() as conn:
        await conn.executemany(
            """INSERT INTO clients (frontdesk_id, phone, nickname, status, source)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (frontdesk.id, '+60111000001', '客户一', 'replied', 'telegram'),
                (frontdesk.id, '+60111000002', '客户二', 'replied', 'facebook'),
                (frontdesk.id, '+60111000003', '客户三', 'new', 'telegram'),
                (frontdesk.id, '+60111000004', '客户四', 'registered', 'tiktok'),
                (frontdesk.id, '+60111000005', '客户五', 'replied', 'instagram'),
            ],
        )
        await conn.commit()


# ─── Template rendering ────────────────────────────────────────────────────────

def test_render_template_name():
    from engines.broadcast_engine import _render_template
    row = {'nickname': '张三', 'status': 'replied', 'contacted_at': None}
    result = _render_template('你好 {name}', row)
    assert result == '你好 张三'


def test_render_template_status():
    from engines.broadcast_engine import _render_template
    row = {'nickname': '李四', 'status': 'registered', 'contacted_at': None}
    result = _render_template('状态：{status}', row)
    assert '状态：registered' in result


def test_render_template_days_no_contact():
    from engines.broadcast_engine import _render_template
    row = {'nickname': '王五', 'status': 'new', 'contacted_at': None}
    result = _render_template('{days_since_contact}天未联系', row)
    assert '0天未联系' in result


def test_render_template_days_with_contact():
    from engines.broadcast_engine import _render_template
    contacted = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    row = {'nickname': '赵六', 'status': 'contacted', 'contacted_at': contacted}
    result = _render_template('{days_since_contact}天', row)
    assert result.startswith('5天') or result.startswith('4天')  # allow 1 day drift


def test_render_template_fallback_phone():
    from engines.broadcast_engine import _render_template
    row = {'nickname': '', 'phone': '+60111234567', 'status': 'new', 'contacted_at': None}
    result = _render_template('联系 {name}', row)
    assert '+60111234567' in result


def test_render_template_all_vars():
    from engines.broadcast_engine import _render_template
    row = {'nickname': '测试', 'status': 'training', 'contacted_at': None}
    tmpl = 'Hi {name}, status={status}, days={days_since_contact}'
    result = _render_template(tmpl, row)
    assert 'Hi 测试' in result
    assert 'status=training' in result
    assert 'days=0' in result


# ─── Segment filtering ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_segment_by_status(db, clients_data):
    from engines.broadcast_engine import get_segment_targets
    with patch('engines.broadcast_engine.database_v2', db):
        targets = await get_segment_targets('status', 'replied')
    assert len(targets) == 3
    assert all(t['status'] == 'replied' for t in targets)


@pytest.mark.asyncio
async def test_segment_by_team(db, clients_data, frontdesk):
    from engines.broadcast_engine import get_segment_targets
    with patch('engines.broadcast_engine.database_v2', db):
        targets = await get_segment_targets('team', '阿俊')
    assert len(targets) == 5


@pytest.mark.asyncio
async def test_segment_by_source(db, clients_data):
    from engines.broadcast_engine import get_segment_targets
    with patch('engines.broadcast_engine.database_v2', db):
        targets = await get_segment_targets('source', 'telegram')
    assert len(targets) == 2
    assert all(t['source'] == 'telegram' for t in targets)


@pytest.mark.asyncio
async def test_segment_unknown_type_returns_empty(db, clients_data):
    from engines.broadcast_engine import get_segment_targets
    with patch('engines.broadcast_engine.database_v2', db):
        targets = await get_segment_targets('unknown', 'anything')
    assert targets == []


@pytest.mark.asyncio
async def test_segment_by_status_no_match(db, clients_data):
    from engines.broadcast_engine import get_segment_targets
    with patch('engines.broadcast_engine.database_v2', db):
        targets = await get_segment_targets('status', 'ordered')
    assert targets == []


# ─── Delivery tracking ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_broadcast_log(db, manager):
    log_id = await db.create_broadcast_log(
        staff_id=manager.id,
        template='Hello {name}',
        segment_filter='status:replied',
        total_targets=10,
    )
    assert log_id > 0


@pytest.mark.asyncio
async def test_update_broadcast_log(db, manager):
    log_id = await db.create_broadcast_log(
        staff_id=manager.id,
        template='Test',
        segment_filter='status:new',
        total_targets=5,
    )
    await db.update_broadcast_log(log_id, sent_count=4, failed_count=1, completed=True)

    logs = await db.get_broadcast_logs(staff_id=manager.id)
    assert len(logs) == 1
    assert logs[0]['sent_count'] == 4
    assert logs[0]['failed_count'] == 1
    assert logs[0]['completed_at'] is not None


@pytest.mark.asyncio
async def test_get_broadcast_logs_empty(db, manager):
    logs = await db.get_broadcast_logs(staff_id=manager.id)
    assert logs == []


@pytest.mark.asyncio
async def test_get_broadcast_logs_limit(db, manager):
    for i in range(5):
        await db.create_broadcast_log(manager.id, f'tmpl{i}', 'status:new', i)
    logs = await db.get_broadcast_logs(limit=3)
    assert len(logs) == 3


# ─── Rate limiting ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_broadcast_rate_limited(db, manager, clients_data):
    """send_broadcast sleeps between sends at rate ≤ 25/s."""
    import engines.broadcast_engine as bce

    mock_client = MagicMock()
    mock_client.send_message = AsyncMock()

    mock_tg = MagicMock()
    mock_tg.client = mock_client

    sleep_calls = []

    async def fake_sleep(t):
        sleep_calls.append(t)

    with patch('engines.broadcast_engine.database_v2', db), \
         patch('engines.broadcast_engine.asyncio.sleep', fake_sleep), \
         patch('handlers_v2.broadcast_handler.telegram_handler', mock_tg), \
         patch('engines.broadcast_engine.telegram_handler', mock_tg):
        result = await bce.send_broadcast(
            staff_id=manager.id,
            template='Hi {name}',
            segment_type='status',
            segment_value='replied',
        )

    # 3 clients with status=replied → 3 sleep calls
    assert len(sleep_calls) == 3
    # Each sleep is 0.04s (1/25)
    for s in sleep_calls:
        assert abs(s - bce._SEND_INTERVAL) < 1e-6


@pytest.mark.asyncio
async def test_send_broadcast_counts_blocked(db, manager, clients_data):
    from engines.broadcast_engine import send_broadcast

    mock_client = MagicMock()
    call_count = 0

    async def send_msg(phone, text):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception('User is blocked by privacy settings')

    mock_client.send_message = send_msg
    mock_tg = MagicMock()
    mock_tg.client = mock_client

    async def fake_sleep(_):
        pass

    with patch('engines.broadcast_engine.database_v2', db), \
         patch('engines.broadcast_engine.asyncio.sleep', fake_sleep), \
         patch('engines.broadcast_engine.telegram_handler', mock_tg):
        result = await send_broadcast(
            staff_id=manager.id,
            template='Hi',
            segment_type='status',
            segment_value='replied',
        )

    assert result['total'] == 3
    assert result['sent'] == 2
    assert result['blocked'] == 1
    assert result['failed'] == 0


# ─── Permission: only manager+ can broadcast ──────────────────────────────────

def test_broadcast_permission_manager():
    from engines.policy_engine import check_permission
    assert check_permission('manager', 'broadcast') is True


def test_broadcast_permission_admin():
    from engines.policy_engine import check_permission
    assert check_permission('admin', 'broadcast') is True


def test_broadcast_permission_frontdesk_denied():
    from engines.policy_engine import check_permission
    assert check_permission('frontdesk', 'broadcast') is False


def test_broadcast_permission_newbie_denied():
    from engines.policy_engine import check_permission
    assert check_permission('newbie', 'broadcast') is False
