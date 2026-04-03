"""Tests for handlers_v2/export_handler.py — /export, /export_template, /import."""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from models_v2 import Staff, StaffRole


# ── Helpers ──────────────────────────────────────────────────────────────────

def _staff(role=StaffRole.FRONTDESK, lang='zh', staff_id=1, name='FD', tg_user_id=100):
    return Staff(
        id=staff_id, tg_user_id=tg_user_id, tg_chat_id=tg_user_id,
        display_name=name, role=role, language=lang,
    )


def _td(user_id=100, chat_id=100, args='', **extra):
    d = {'user_id': user_id, 'chat_id': chat_id, 'args': args}
    d.update(extra)
    return d


_P_STAFF = 'handlers_v2.export_handler._get_staff'
_P_TH = 'handlers_v2.export_handler.telegram_handler'
_P_DB = 'handlers_v2.export_handler.database_v2'
_P_T = 'handlers_v2.export_handler.t'


# ── /export ──────────────────────────────────────────────────────────────────

class TestHandleExport:

    @pytest.mark.asyncio
    async def test_export_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='err'):
            th.send_message = AsyncMock()
            from handlers_v2.export_handler import handle_export
            await handle_export(_td())
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_export_permission_denied(self):
        staff = _staff(role=StaffRole.NEWBIE)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='denied'), \
             patch('engines.policy_engine.check_permission', return_value=False):
            th.send_message = AsyncMock()
            from handlers_v2.export_handler import handle_export
            await handle_export(_td())
            th.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_export_empty_result(self):
        staff = _staff(role=StaffRole.MANAGER)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='empty'), \
             patch('engines.policy_engine.check_permission', return_value=True):
            th.send_message = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    build_export_rows=AsyncMock(return_value=[]),
                    export_to_excel=Mock(return_value=b''),
                ),
            }):
                from handlers_v2.export_handler import handle_export
                await handle_export(_td())
                # Should show empty message
                calls = th.send_message.call_args_list
                assert len(calls) >= 1

    @pytest.mark.asyncio
    async def test_export_success(self):
        staff = _staff(role=StaffRole.MANAGER)
        rows = [{'phone': '+123', 'status': 'new'}]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='success'):
            th.send_message = AsyncMock()
            th.send_document = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    build_export_rows=AsyncMock(return_value=rows),
                    export_to_excel=Mock(return_value=b'xlsx-bytes'),
                ),
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_export
                await handle_export(_td())
                th.send_document.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_export_send_document_fails(self):
        staff = _staff(role=StaffRole.MANAGER)
        rows = [{'phone': '+123'}]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='exported 1'):
            th.send_message = AsyncMock()
            th.send_document = AsyncMock(side_effect=Exception('upload failed'))
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    build_export_rows=AsyncMock(return_value=rows),
                    export_to_excel=Mock(return_value=b'data'),
                ),
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_export
                await handle_export(_td())
                # Should fallback to text message
                assert th.send_message.await_count >= 2

    @pytest.mark.asyncio
    async def test_export_with_status_filter(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        rows = [{'phone': '+1', 'status': 'training'}]
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='ok'):
            th.send_message = AsyncMock()
            th.send_document = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    build_export_rows=AsyncMock(return_value=rows),
                    export_to_excel=Mock(return_value=b'data'),
                ),
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_export
                await handle_export(_td(args='training'))
                th.send_document.assert_awaited_once()


# ── /export_template ─────────────────────────────────────────────────────────

class TestHandleExportTemplate:

    @pytest.mark.asyncio
    async def test_template_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='err'):
            th.send_message = AsyncMock()
            from handlers_v2.export_handler import handle_export_template
            await handle_export_template(_td())
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_template_success(self):
        staff = _staff(role=StaffRole.MANAGER)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.send_document = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    generate_template=Mock(return_value=b'template-bytes'),
                ),
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_export_template
                await handle_export_template(_td())
                th.send_document.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_template_send_fails(self):
        staff = _staff(role=StaffRole.MANAGER)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th:
            th.send_message = AsyncMock()
            th.send_document = AsyncMock(side_effect=Exception('fail'))
            with patch.dict('sys.modules', {
                'engines.excel_engine': MagicMock(
                    generate_template=Mock(return_value=b'data'),
                ),
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_export_template
                await handle_export_template(_td())
                # Should send error message
                last_msg = th.send_message.call_args[0][1]
                assert '失败' in last_msg or '重试' in last_msg


# ── /import ──────────────────────────────────────────────────────────────────

class TestHandleImport:

    @pytest.mark.asyncio
    async def test_import_not_registered(self):
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=None), \
             patch(_P_TH) as th, patch(_P_T, return_value='err'):
            th.send_message = AsyncMock()
            from handlers_v2.export_handler import handle_import
            await handle_import(_td())
            th.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_import_not_manager(self):
        staff = _staff(role=StaffRole.FRONTDESK)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_T, return_value='denied'):
            th.send_message = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_import
                await handle_import(_td())
                th.send_message.assert_awaited()

    @pytest.mark.asyncio
    async def test_import_sets_conversation_state(self):
        staff = _staff(role=StaffRole.MANAGER)
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.send_message = AsyncMock()
            db.set_conversation_state = AsyncMock()
            with patch.dict('sys.modules', {
                'engines.policy_engine': MagicMock(check_permission=Mock(return_value=True)),
            }):
                from handlers_v2.export_handler import handle_import
                await handle_import(_td())
                db.set_conversation_state.assert_awaited_once()
                state = db.set_conversation_state.call_args[0][1]
                assert state['handler'] == 'import_excel'


# ── Import conversation ──────────────────────────────────────────────────────

class TestImportConversation:

    @pytest.mark.asyncio
    async def test_conversation_wrong_handler(self):
        with patch(_P_DB) as db:
            db.get_conversation_state = AsyncMock(return_value={'handler': 'something_else'})
            from handlers_v2.export_handler import handle_import_conversation
            result = await handle_import_conversation(_td())
            assert result is False

    @pytest.mark.asyncio
    async def test_conversation_no_file(self):
        with patch(_P_DB) as db, patch(_P_TH) as th:
            th.send_message = AsyncMock()
            db.get_conversation_state = AsyncMock(return_value={
                'handler': 'import_excel', 'step': 'await_file'
            })
            from handlers_v2.export_handler import handle_import_conversation
            result = await handle_import_conversation(_td())
            assert result is True
            msg = th.send_message.call_args[0][1]
            assert '.xlsx' in msg


# ── xl callback ──────────────────────────────────────────────────────────────

class TestXlCallback:

    @pytest.mark.asyncio
    async def test_xl_cancel(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.edit_message = AsyncMock()
            db.get_conversation_state = AsyncMock(return_value={
                'handler': 'import_excel', 'step': 'await_confirm'
            })
            db.clear_conversation_state = AsyncMock()
            from handlers_v2.export_handler import handle_xl_callback
            await handle_xl_callback({
                'chat_id': 1, 'user_id': 100,
                'data': 'xl:cancel', 'message_id': 5
            })
            db.clear_conversation_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_xl_confirm_no_data(self):
        staff = _staff()
        with patch(_P_STAFF, new_callable=AsyncMock, return_value=staff), \
             patch(_P_TH) as th, \
             patch(_P_DB) as db:
            th.edit_message = AsyncMock()
            db.get_conversation_state = AsyncMock(return_value={
                'handler': 'import_excel', 'step': 'await_confirm',
                'parsed_rows': [],
            })
            db.clear_conversation_state = AsyncMock()
            from handlers_v2.export_handler import handle_xl_callback
            await handle_xl_callback({
                'chat_id': 1, 'user_id': 100,
                'data': 'xl:confirm', 'message_id': 5
            })
            msg = th.edit_message.call_args[0][2]
            assert '无有效数据' in msg or '重新上传' in msg


# ── Registry ─────────────────────────────────────────────────────────────────

class TestExportRegistry:

    def test_export_commands(self):
        from handlers_v2.export_handler import EXPORT_HANDLER_COMMANDS
        assert 'export' in EXPORT_HANDLER_COMMANDS
        assert 'export_template' in EXPORT_HANDLER_COMMANDS
        assert 'import' in EXPORT_HANDLER_COMMANDS

    def test_export_callbacks(self):
        from handlers_v2.export_handler import EXPORT_HANDLER_CALLBACKS
        assert 'xl' in EXPORT_HANDLER_CALLBACKS

    def test_export_conversations(self):
        from handlers_v2.export_handler import EXPORT_HANDLER_CONVERSATIONS
        assert 'import_excel' in EXPORT_HANDLER_CONVERSATIONS
