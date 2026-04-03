"""Tests for engines/followup_engine.py — drip campaign scheduling, processing, ghosting."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from engines.followup_engine import (
    enqueue_client, process_due_followups, seed_default_sequences,
    register_hooks, _on_status_change, _DEFAULT_SEQUENCES,
)
from models_v2 import Client, ClientStatus, Staff, StaffRole


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _staff(sid=1, chat_id=2001, name='阿YIM'):
    return Staff(tg_user_id=1001, tg_chat_id=chat_id, display_name=name,
                 id=sid, role=StaffRole.FRONTDESK, language='zh')


def _client(cid=1, phone='1234567890', status=ClientStatus.NEW, frontdesk_id=1, nickname=None):
    return Client(frontdesk_id=frontdesk_id, phone=phone, source='test',
                  id=cid, status=status, nickname=nickname)


# ─── Tests ─────────────────────────────────────────────────────────────────────

class TestDefaultSequences:
    def test_default_sequences_defined(self):
        assert len(_DEFAULT_SEQUENCES) >= 3
        stages = {s['stage'] for s in _DEFAULT_SEQUENCES}
        assert 'new' in stages
        assert 'contacted' in stages
        assert 'registered' in stages

    def test_sequences_have_delays_and_templates(self):
        for seq in _DEFAULT_SEQUENCES:
            assert len(seq['delays']) > 0
            assert len(seq['templates']) > 0
            assert len(seq['delays']) == len(seq['templates'])


class TestSeedDefaultSequences:
    @pytest.mark.asyncio
    async def test_seed_creates_sequences(self):
        mock_db = MagicMock()
        mock_db.create_sequence = AsyncMock()
        with patch('engines.followup_engine.database_v2', mock_db):
            await seed_default_sequences()
        assert mock_db.create_sequence.call_count == len(_DEFAULT_SEQUENCES)

    @pytest.mark.asyncio
    async def test_seed_handles_duplicate_errors(self):
        mock_db = MagicMock()
        mock_db.create_sequence = AsyncMock(side_effect=Exception('UNIQUE constraint'))
        with patch('engines.followup_engine.database_v2', mock_db):
            # Should not raise
            await seed_default_sequences()


class TestEnqueueClient:
    @pytest.mark.asyncio
    async def test_enqueue_with_matching_sequence(self):
        mock_db = MagicMock()
        mock_db.cancel_followup = AsyncMock()
        mock_db.get_sequences = AsyncMock(return_value=[
            {'id': 1, 'name': 'new_lead', 'stage': 'new', 'delays': [1, 3], 'templates': ['t1', 't2']}
        ])
        mock_db.enqueue_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await enqueue_client(client_id=10, stage='new')

        mock_db.cancel_followup.assert_awaited_once_with(10)
        mock_db.enqueue_followup.assert_awaited_once()
        call_kwargs = mock_db.enqueue_followup.call_args[1]
        assert call_kwargs['client_id'] == 10
        assert call_kwargs['sequence_id'] == 1

    @pytest.mark.asyncio
    async def test_enqueue_no_matching_sequence(self):
        mock_db = MagicMock()
        mock_db.cancel_followup = AsyncMock()
        mock_db.get_sequences = AsyncMock(return_value=[])
        mock_db.enqueue_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await enqueue_client(client_id=10, stage='nonexistent')

        mock_db.enqueue_followup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_cancels_existing_first(self):
        mock_db = MagicMock()
        mock_db.cancel_followup = AsyncMock()
        mock_db.get_sequences = AsyncMock(return_value=[
            {'id': 2, 'name': 'contacted', 'stage': 'contacted', 'delays': [2], 'templates': ['t1']}
        ])
        mock_db.enqueue_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await enqueue_client(client_id=5, stage='contacted')

        mock_db.cancel_followup.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_enqueue_empty_delays_skips(self):
        mock_db = MagicMock()
        mock_db.cancel_followup = AsyncMock()
        mock_db.get_sequences = AsyncMock(return_value=[
            {'id': 3, 'name': 'empty', 'stage': 'new', 'delays': [], 'templates': []}
        ])
        mock_db.enqueue_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await enqueue_client(client_id=10, stage='new')

        mock_db.enqueue_followup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enqueue_handles_error(self):
        mock_db = MagicMock()
        mock_db.cancel_followup = AsyncMock(side_effect=Exception('DB error'))

        with patch('engines.followup_engine.database_v2', mock_db):
            # Should not raise
            await enqueue_client(client_id=10, stage='new')


class TestProcessDueFollowups:
    @pytest.mark.asyncio
    async def test_no_due_items(self):
        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[])

        with patch('engines.followup_engine.database_v2', mock_db):
            await process_due_followups()

    @pytest.mark.asyncio
    async def test_sends_message_and_advances(self):
        client = _client(cid=1, status=ClientStatus.NEW)
        staff = _staff(sid=1, chat_id=2001)

        due_item = {
            'id': 100, 'client_id': 1, 'step': 0, 'stage': 'new',
            'delays': [1, 3, 7], 'templates': ['Hello!', 'Follow up', 'Last chance']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=staff)
        mock_db.advance_followup_step = AsyncMock()
        mock_db.complete_followup = AsyncMock()

        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db), \
             patch('telegram_handler.telegram_handler', mock_tg):
            await process_due_followups()

        mock_tg.send_message.assert_awaited_once()
        msg = mock_tg.send_message.call_args[0][1]
        assert '跟进提醒' in msg
        assert 'Hello!' in msg
        mock_db.advance_followup_step.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completes_on_final_step(self):
        client = _client(cid=1, status=ClientStatus.CONTACTED)
        staff = _staff()

        due_item = {
            'id': 101, 'client_id': 1, 'step': 1, 'stage': 'contacted',
            'delays': [2, 5], 'templates': ['t1', 't2']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=staff)
        mock_db.complete_followup = AsyncMock()
        mock_db.advance_followup_step = AsyncMock()

        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db), \
             patch('telegram_handler.telegram_handler', mock_tg):
            await process_due_followups()

        mock_db.complete_followup.assert_awaited_once_with(101, 'completed')
        mock_db.advance_followup_step.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancels_for_missing_client(self):
        due_item = {
            'id': 102, 'client_id': 999, 'step': 0, 'stage': 'new',
            'delays': [1], 'templates': ['t1']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=None)
        mock_db.complete_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await process_due_followups()

        mock_db.complete_followup.assert_awaited_once_with(102, 'cancelled')

    @pytest.mark.asyncio
    async def test_cancels_for_missing_staff(self):
        client = _client()
        due_item = {
            'id': 103, 'client_id': 1, 'step': 0, 'stage': 'new',
            'delays': [1], 'templates': ['t1']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=None)
        mock_db.complete_followup = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db):
            await process_due_followups()

        mock_db.complete_followup.assert_awaited_once_with(103, 'cancelled')

    @pytest.mark.asyncio
    async def test_ghosting_after_3_sends(self):
        """After step >= 3 with no status change, client gets ghosted."""
        client = _client(cid=1, status=ClientStatus.NEW)
        staff = _staff()

        due_item = {
            'id': 104, 'client_id': 1, 'step': 2, 'stage': 'new',
            'delays': [1, 3, 7, 14], 'templates': ['t1', 't2', 't3', 't4']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=staff)
        mock_db.advance_followup_step = AsyncMock()
        mock_db.update_client_status = AsyncMock(return_value=True)
        mock_db.complete_followup = AsyncMock()

        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db), \
             patch('telegram_handler.telegram_handler', mock_tg):
            await process_due_followups()

        # Should be marked ghosted
        mock_db.update_client_status.assert_awaited()
        args = mock_db.update_client_status.call_args
        assert args[0][1] == ClientStatus.GHOSTED

    @pytest.mark.asyncio
    async def test_includes_nickname_in_message(self):
        client = _client(cid=1, status=ClientStatus.NEW, nickname='小明')
        staff = _staff()

        due_item = {
            'id': 105, 'client_id': 1, 'step': 0, 'stage': 'new',
            'delays': [1], 'templates': ['hi']
        }

        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(return_value=[due_item])
        mock_db.get_client_by_id = AsyncMock(return_value=client)
        mock_db.get_staff_by_id = AsyncMock(return_value=staff)
        mock_db.complete_followup = AsyncMock()

        mock_tg = MagicMock()
        mock_tg.send_message = AsyncMock()

        with patch('engines.followup_engine.database_v2', mock_db), \
             patch('telegram_handler.telegram_handler', mock_tg):
            await process_due_followups()

        msg = mock_tg.send_message.call_args[0][1]
        assert '小明' in msg

    @pytest.mark.asyncio
    async def test_outer_exception_does_not_crash(self):
        mock_db = MagicMock()
        mock_db.get_due_followups = AsyncMock(side_effect=Exception('DB gone'))

        with patch('engines.followup_engine.database_v2', mock_db):
            # Should not raise
            await process_due_followups()


class TestOnStatusChangeHook:
    @pytest.mark.asyncio
    async def test_hook_enqueues_client(self):
        with patch('engines.followup_engine.enqueue_client', new_callable=AsyncMock) as mock_enqueue:
            await _on_status_change(client_id=42, new_status='contacted')
        mock_enqueue.assert_awaited_once_with(42, 'contacted')

    @pytest.mark.asyncio
    async def test_hook_handles_error(self):
        with patch('engines.followup_engine.enqueue_client',
                   new_callable=AsyncMock, side_effect=Exception('fail')):
            # Should not raise
            await _on_status_change(client_id=1, new_status='new')


class TestRegisterHooks:
    def test_register_hooks_adds_callback(self):
        from database_v2 import _status_change_hooks
        original_len = len(_status_change_hooks)
        # Remove if already registered to test idempotency
        if _on_status_change in _status_change_hooks:
            _status_change_hooks.remove(_on_status_change)

        register_hooks()
        assert _on_status_change in _status_change_hooks

        # Second call is idempotent
        register_hooks()
        count = sum(1 for h in _status_change_hooks if h is _on_status_change)
        assert count == 1

        # Restore
        if len(_status_change_hooks) > original_len:
            _status_change_hooks.remove(_on_status_change)
