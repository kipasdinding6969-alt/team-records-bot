"""Voice engine + handler tests — mock Ollama/Whisper, test intent parsing + callbacks."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Client, ClientStatus, Staff, StaffRole


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_voice.db'))
    await d.initialize()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=9001,
        tg_chat_id=8001,
        display_name='TestStaff',
        role=StaffRole.FRONTDESK,
        team='A',
        language='zh',
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client_row(db, staff):
    c = Client(frontdesk_id=staff.id, phone='0123456789', source='fb')
    c.id = await db.create_client(c)
    return c


@pytest_asyncio.fixture
async def named_client(db, staff):
    """Client with nickname 阿明 but no phone."""
    c = Client(frontdesk_id=staff.id, phone='0987654321', source='wechat', nickname='阿明')
    c.id = await db.create_client(c)
    return c


def _make_mock_tg():
    """Build a mock TelegramHandler with async-safe methods."""
    m = MagicMock()
    m.send_message = AsyncMock()
    m.get_conversation_state = AsyncMock(return_value=None)
    m.set_conversation_state = AsyncMock()
    m.clear_conversation_state = AsyncMock()
    m.create_inline_keyboard = MagicMock(return_value=[[]])
    return m


# ── Voice Engine: parse_intent ───────────────────────────────────────────────

class TestParseIntent:
    def _mock_session(self, status: int, body: dict):
        """Build aiohttp session mock returning given status + JSON body."""
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=body)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_session_cls = MagicMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        return mock_session_cls

    @pytest.mark.asyncio
    async def test_parse_full_intent(self):
        """Mocked Ollama returns full JSON — all fields extracted."""
        payload = {'response': json.dumps({
            'client_name': None,
            'client_phone': '0123456789',
            'new_status': 'contacted',
            'note': 'Called, interested',
        })}
        with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent('打了电话 0123456789 有兴趣')

        assert result['client_phone'] == '0123456789'
        assert result['new_status'] == 'contacted'
        assert result['note'] == 'Called, interested'
        assert result['client_name'] is None

    @pytest.mark.asyncio
    async def test_parse_chinese_name_extracted(self):
        """Chinese-name utterance: client_name extracted, no phone."""
        payload = {'response': json.dumps({
            'client_name': '阿明',
            'client_phone': None,
            'new_status': 'registered',
            'note': '账号123456',
        })}
        with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent('阿明今天注册了，账号123456')

        assert result['client_name'] == '阿明'
        assert result['client_phone'] is None
        assert result['new_status'] == 'registered'
        assert result['note'] == '账号123456'

    @pytest.mark.asyncio
    async def test_parse_partial_intent(self):
        """Partial JSON — missing fields become None."""
        payload = {'response': json.dumps({'client_phone': '9876543210'})}
        with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent('phone only')

        assert result['client_phone'] == '9876543210'
        assert result['new_status'] is None
        assert result['note'] is None
        assert result['client_name'] is None

    @pytest.mark.asyncio
    async def test_parse_invalid_status_cleared(self):
        """Unknown status from LLM is cleared to None."""
        payload = {'response': json.dumps({
            'client_name': None,
            'client_phone': '111',
            'new_status': 'invalid_xyz',
            'note': None,
        })}
        with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent('some text')

        assert result['new_status'] is None

    @pytest.mark.asyncio
    async def test_parse_ollama_http_error_returns_empty(self):
        """Ollama HTTP 500 → all None."""
        with patch('aiohttp.ClientSession', self._mock_session(500, {})):
            from engines.voice_engine import parse_intent
            result = await parse_intent('some text')

        assert result == {'client_name': None, 'client_phone': None, 'new_status': None, 'note': None}

    @pytest.mark.asyncio
    async def test_parse_network_exception_returns_empty(self):
        """Network exception → all None, no crash."""
        with patch('aiohttp.ClientSession', side_effect=Exception("connection refused")):
            from engines.voice_engine import parse_intent
            result = await parse_intent('some text')

        assert result == {'client_name': None, 'client_phone': None, 'new_status': None, 'note': None}

    @pytest.mark.asyncio
    async def test_all_valid_statuses_accepted(self):
        """Each pipeline status is accepted as-is from Ollama."""
        valid = ['new', 'contacted', 'replied', 'registered',
                 'training', 'withdrew', 'ordered', 'ghosted', 'blocked', 'dead']
        for status in valid:
            payload = {'response': json.dumps({
                'client_name': None, 'client_phone': '111', 'new_status': status, 'note': None,
            })}
            with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
                from engines.voice_engine import parse_intent
                result = await parse_intent('text')
            assert result['new_status'] == status, f"Status {status!r} was rejected"

    @pytest.mark.asyncio
    async def test_parse_result_always_has_client_name_key(self):
        """client_name key is always present in parse_intent result."""
        payload = {'response': json.dumps({'client_phone': '111', 'new_status': 'new'})}
        with patch('aiohttp.ClientSession', self._mock_session(200, payload)):
            from engines.voice_engine import parse_intent
            result = await parse_intent('text')
        assert 'client_name' in result


# ── Voice Engine: transcribe ─────────────────────────────────────────────────

class TestTranscribe:
    @pytest.mark.asyncio
    async def test_transcribe_bad_path_returns_none(self):
        """Non-existent file path → None, no crash."""
        from engines.voice_engine import transcribe
        result = await transcribe('/tmp/definitely_does_not_exist_voice_abc.ogg')
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_import_error_returns_none(self):
        """faster-whisper ImportError → None gracefully."""
        with patch.dict('sys.modules', {'faster_whisper': None}):
            from engines.voice_engine import transcribe
            result = await transcribe('/tmp/fake.ogg')
        assert result is None

    @pytest.mark.asyncio
    async def test_transcribe_mocked_model_returns_text(self, tmp_path):
        """Mocked WhisperModel returns expected transcription."""
        fake_ogg = tmp_path / 'voice.ogg'
        fake_ogg.write_bytes(b'fake audio data')

        mock_segment = MagicMock()
        mock_segment.text = '阿明今天注册了'

        mock_model = MagicMock()
        mock_model.transcribe = MagicMock(return_value=([mock_segment], None))

        mock_whisper_cls = MagicMock(return_value=mock_model)

        with patch.dict('sys.modules', {'faster_whisper': MagicMock(WhisperModel=mock_whisper_cls)}):
            import importlib
            import engines.voice_engine as ve
            importlib.reload(ve)
            result = await ve.transcribe(str(fake_ogg))

        assert result == '阿明今天注册了'

    @pytest.mark.asyncio
    async def test_transcribe_uses_config_model_size(self, tmp_path):
        """transcribe() reads model size from _get_whisper_model_size."""
        fake_ogg = tmp_path / 'voice.ogg'
        fake_ogg.write_bytes(b'data')

        mock_segment = MagicMock()
        mock_segment.text = 'hello'

        mock_model = MagicMock()
        mock_model.transcribe = MagicMock(return_value=([mock_segment], None))

        captured = {}

        def fake_whisper_cls(size, **kwargs):
            captured['size'] = size
            return mock_model

        mock_fw = MagicMock()
        mock_fw.WhisperModel = fake_whisper_cls

        with (
            patch.dict('sys.modules', {'faster_whisper': mock_fw}),
            patch('engines.voice_engine._get_whisper_model_size', return_value='base'),
        ):
            from engines import voice_engine as ve
            result = await ve.transcribe(str(fake_ogg))

        assert result == 'hello'
        assert captured.get('size') == 'base'


# ── Voice Handler: handle_voice_confirm_callback ─────────────────────────────

class TestVoiceConfirmCallback:
    @pytest.mark.asyncio
    async def test_confirm_updates_status(self, db, staff, client_row):
        """Confirming valid voice intent updates client status in DB."""
        pending = {
            'name': None,
            'phone': client_row.phone,
            'status': 'contacted',
            'note': 'Spoke on phone',
            'transcript': '联系了客户',
        }
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'step': 'voice_confirm', 'pending': pending})

        with (
            patch('handlers_v2.voice.database_v2', db),
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        updated = await db.get_client_by_id(client_row.id)
        assert updated.status == ClientStatus.CONTACTED
        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_missing_phone_sends_error(self, db, staff):
        """Pending with no phone and no name → error message, no DB update."""
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'pending': {'phone': None, 'name': None, 'status': 'contacted', 'note': None}})

        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        mock_tg.send_message.assert_called_once()
        sent = mock_tg.send_message.call_args[0][1]
        assert '缺少' in sent or 'Missing' in sent

    @pytest.mark.asyncio
    async def test_confirm_bad_status_sends_error(self, db, staff, client_row):
        """Invalid status string → error message."""
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'pending': {
                'phone': client_row.phone, 'name': None, 'status': 'NOT_A_STATUS', 'note': None,
            }})

        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_confirm_client_not_found_sends_error(self, db, staff):
        """Phone not in DB → error message."""
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'pending': {
                'phone': '0000000000', 'name': None, 'status': 'contacted', 'note': None,
            }})

        with (
            patch('handlers_v2.voice.database_v2', db),
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        mock_tg.send_message.assert_called_once()
        sent = mock_tg.send_message.call_args[0][1]
        assert '找不到' in sent or 'not found' in sent

    @pytest.mark.asyncio
    async def test_confirm_name_lookup_fallback(self, db, staff, named_client):
        """No phone but name extracted → search_clients fallback updates correct client."""
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'pending': {
                'phone': None,
                'name': '阿明',
                'status': 'registered',
                'note': '账号123456',
            }})

        with (
            patch('handlers_v2.voice.database_v2', db),
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        updated = await db.get_client_by_id(named_client.id)
        assert updated.status == ClientStatus.REGISTERED
        # Two messages: "found by name" + "updated"
        assert mock_tg.send_message.call_count == 2
        name_msg = mock_tg.send_message.call_args_list[0][0][1]
        assert '阿明' in name_msg

    @pytest.mark.asyncio
    async def test_confirm_name_not_found_sends_error(self, db, staff):
        """Name-only lookup with no DB match → not-found error."""
        mock_tg = _make_mock_tg()
        mock_tg.get_conversation_state = AsyncMock(
            return_value={'pending': {
                'phone': None,
                'name': '不存在的人',
                'status': 'contacted',
                'note': None,
            }})

        with (
            patch('handlers_v2.voice.database_v2', db),
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_confirm_callback
            await handle_voice_confirm_callback({
                'chat_id': staff.tg_chat_id,
                'user_id': staff.tg_user_id,
            })

        mock_tg.send_message.assert_called_once()
        sent = mock_tg.send_message.call_args[0][1]
        assert '找不到' in sent or 'not found' in sent


# ── Voice Handler: cancel + edit ─────────────────────────────────────────────

class TestVoiceCancelEdit:
    @pytest.mark.asyncio
    async def test_cancel_clears_state_and_sends_message(self, staff):
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_cancel_callback
            await handle_voice_cancel_callback({'chat_id': 8001, 'user_id': 9001})

        mock_tg.clear_conversation_state.assert_called_once_with(9001)
        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_clears_state_and_shows_hint(self, staff):
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_edit_callback
            await handle_voice_edit_callback({'chat_id': 8001, 'user_id': 9001})

        mock_tg.clear_conversation_state.assert_called_once_with(9001)
        mock_tg.send_message.assert_called_once()


# ── handle_voice_message integration ─────────────────────────────────────────

class TestHandleVoiceMessage:
    @pytest.mark.asyncio
    async def test_voice_message_no_file_sends_error(self, staff):
        mock_tg = _make_mock_tg()
        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
        ):
            from handlers_v2.voice import handle_voice_message
            await handle_voice_message({
                'chat_id': 8001, 'user_id': 9001, 'voice_path': None,
            })

        mock_tg.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_voice_message_transcribe_failed_sends_error(self, staff, tmp_path):
        """Voice file exists but transcription fails → error message."""
        fake_ogg = tmp_path / 'fake.ogg'
        fake_ogg.write_bytes(b'fake audio data')
        mock_tg = _make_mock_tg()

        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
            patch('engines.voice_engine.transcribe', AsyncMock(return_value=None)),
        ):
            from handlers_v2.voice import handle_voice_message
            await handle_voice_message({
                'chat_id': 8001, 'user_id': 9001,
                'voice_path': str(fake_ogg),
            })

        # First call: "transcribing...", second: "failed"
        assert mock_tg.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_voice_message_success_flow(self, staff, tmp_path):
        """Full success: transcribe + parse → conversation state set + preview sent."""
        fake_ogg = tmp_path / 'voice.ogg'
        fake_ogg.write_bytes(b'fake audio data')
        mock_tg = _make_mock_tg()

        mock_intent = {
            'client_name': '阿明',
            'client_phone': None,
            'new_status': 'registered',
            'note': '账号123456',
        }

        with (
            patch('handlers_v2.voice._get_staff', AsyncMock(return_value=staff)),
            patch('handlers_v2.voice.telegram_handler', mock_tg),
            patch('engines.voice_engine.transcribe', AsyncMock(return_value='阿明今天注册了，账号123456')),
            patch('engines.voice_engine.parse_intent', AsyncMock(return_value=mock_intent)),
        ):
            from handlers_v2.voice import handle_voice_message
            await handle_voice_message({
                'chat_id': 8001, 'user_id': 9001,
                'voice_path': str(fake_ogg),
            })

        # Messages: "transcribing...", then preview with keyboard
        assert mock_tg.send_message.call_count == 2
        mock_tg.set_conversation_state.assert_called_once()
        state_arg = mock_tg.set_conversation_state.call_args[0][1]
        assert state_arg['pending']['name'] == '阿明'
        assert state_arg['pending']['status'] == 'registered'


# ── Registry exports ─────────────────────────────────────────────────────────

class TestVoiceRegistry:
    def test_callbacks_registered(self):
        from handlers_v2.voice import VOICE_CALLBACKS
        assert 'voice_confirm' in VOICE_CALLBACKS
        assert 'voice_cancel' in VOICE_CALLBACKS
        assert 'voice_edit' in VOICE_CALLBACKS

    def test_conversations_registered(self):
        from handlers_v2.voice import VOICE_CONVERSATIONS
        assert 'voice_confirm' in VOICE_CONVERSATIONS

    def test_commands_empty(self):
        from handlers_v2.voice import VOICE_COMMANDS
        assert isinstance(VOICE_COMMANDS, dict)
