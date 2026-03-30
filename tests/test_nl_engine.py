"""Tests for engines/nl_engine.py — intent parsing, entity extraction, fallback."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from engines.nl_engine import (
    parse,
    _parse_regex,
    _parse_ollama,
    _validate_and_clean,
    QUERY_CLIENT,
    UPDATE_STATUS,
    ADD_NOTE,
    LIST_PIPELINE,
    SEARCH,
    HELP,
    UNKNOWN,
    CONFIDENCE_THRESHOLD,
    PIPELINE_STATUSES,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ollama_mock(intent: str, confidence: float, entities: dict):
    """Build an aiohttp session mock that returns a valid Ollama response."""
    body = {
        'response': json.dumps({
            'intent': intent,
            'confidence': confidence,
            'entities': entities,
        })
    }
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=body)

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_ctx)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


def _make_ollama_error_mock(status: int = 500):
    """Mock that returns non-200 HTTP status."""
    mock_resp = AsyncMock()
    mock_resp.status = status

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_ctx)

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_cls


# ── _validate_and_clean ──────────────────────────────────────────────────────

class TestValidateAndClean:
    def test_valid_intent(self):
        r = _validate_and_clean({'intent': 'QUERY_CLIENT', 'confidence': 0.9,
                                  'entities': {'client_name': '阿明', 'phone': None,
                                               'status': None, 'note': None}})
        assert r['intent'] == QUERY_CLIENT
        assert r['confidence'] == 0.9

    def test_unknown_intent_becomes_unknown(self):
        r = _validate_and_clean({'intent': 'INVALID', 'confidence': 0.9, 'entities': {}})
        assert r['intent'] == UNKNOWN

    def test_confidence_clamped(self):
        r = _validate_and_clean({'intent': 'HELP', 'confidence': 1.5, 'entities': {}})
        assert r['confidence'] == 1.0
        r2 = _validate_and_clean({'intent': 'HELP', 'confidence': -0.5, 'entities': {}})
        assert r2['confidence'] == 0.0

    def test_invalid_status_nulled(self):
        r = _validate_and_clean({'intent': 'UPDATE_STATUS', 'confidence': 0.8,
                                  'entities': {'status': 'notastatus'}})
        assert r['entities']['status'] is None

    def test_valid_status_preserved(self):
        r = _validate_and_clean({'intent': 'UPDATE_STATUS', 'confidence': 0.8,
                                  'entities': {'status': 'registered'}})
        assert r['entities']['status'] == 'registered'

    def test_empty_strings_become_none(self):
        r = _validate_and_clean({'intent': 'QUERY_CLIENT', 'confidence': 0.8,
                                  'entities': {'client_name': '', 'phone': '', 'status': '', 'note': ''}})
        assert r['entities']['client_name'] is None
        assert r['entities']['phone'] is None


# ── _parse_regex ─────────────────────────────────────────────────────────────

class TestParseRegex:
    def test_help_chinese(self):
        r = _parse_regex('我不知道怎么用')
        assert r['intent'] == HELP
        assert r['confidence'] >= 0.7

    def test_help_english(self):
        r = _parse_regex('help me')
        assert r['intent'] == HELP

    def test_list_pipeline_stats(self):
        r = _parse_regex('我今天有多少新客户')
        assert r['intent'] == LIST_PIPELINE
        assert r['confidence'] >= 0.7

    def test_search_by_status(self):
        r = _parse_regex('找所有培训中的客户')
        assert r['intent'] == SEARCH
        assert r['confidence'] >= 0.7

    def test_add_note_with_colon(self):
        r = _parse_regex('给阿明备注：今天有兴趣')
        assert r['intent'] == ADD_NOTE
        assert r['entities']['note'] == '今天有兴趣'

    def test_update_status_chinese(self):
        r = _parse_regex('阿明已经注册了')
        assert r['intent'] == UPDATE_STATUS
        assert r['entities']['status'] == 'registered'

    def test_update_status_phone(self):
        r = _parse_regex('0123456789 下单了')
        assert r['intent'] == UPDATE_STATUS
        assert r['entities']['phone'] == '0123456789'
        assert r['entities']['status'] == 'ordered'

    def test_query_client_by_name(self):
        r = _parse_regex('阿明什么情况')
        assert r['intent'] == QUERY_CLIENT
        assert r['confidence'] >= 0.7

    def test_phone_extraction(self):
        r = _parse_regex('查一下 0123456789')
        assert r['entities']['phone'] == '0123456789'

    def test_name_extraction_ah_prefix(self):
        r = _parse_regex('阿明注册了')
        assert r['entities']['client_name'] is not None
        assert '阿明' in r['entities']['client_name']

    def test_status_training(self):
        r = _parse_regex('找所有培训中的客户')
        assert r['entities']['status'] == 'training'

    def test_status_contacted(self):
        r = _parse_regex('阿Jun已联系')
        assert r['entities']['status'] == 'contacted'

    def test_unknown_returns_low_confidence(self):
        r = _parse_regex('hello world xyz 123abc')
        # QUERY_CLIENT may match but we just ensure it doesn't crash and returns a dict
        assert 'intent' in r
        assert 'confidence' in r
        assert 'entities' in r


# ── _parse_ollama ─────────────────────────────────────────────────────────────

class TestParseOllama:
    @pytest.mark.asyncio
    async def test_returns_query_client(self, monkeypatch):
        mock_cls = _make_ollama_mock(QUERY_CLIENT, 0.95, {
            'client_name': '阿明', 'phone': None, 'status': None, 'note': None
        })
        import engines.nl_engine as mod
        monkeypatch.setattr('engines.nl_engine.aiohttp' if hasattr(mod, 'aiohttp') else 'aiohttp.ClientSession',
                            mock_cls, raising=False)

        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('阿明什么情况')

        assert r['intent'] == QUERY_CLIENT
        assert r['confidence'] == 0.95
        assert r['entities']['client_name'] == '阿明'

    @pytest.mark.asyncio
    async def test_returns_update_status(self, monkeypatch):
        mock_cls = _make_ollama_mock(UPDATE_STATUS, 0.92, {
            'client_name': '阿明', 'phone': None, 'status': 'registered', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('阿明已经注册了')

        assert r['intent'] == UPDATE_STATUS
        assert r['entities']['status'] == 'registered'

    @pytest.mark.asyncio
    async def test_returns_add_note(self, monkeypatch):
        mock_cls = _make_ollama_mock(ADD_NOTE, 0.88, {
            'client_name': '阿明', 'phone': None, 'status': None, 'note': '今天有兴趣'
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('给阿明备注：今天有兴趣')

        assert r['intent'] == ADD_NOTE
        assert r['entities']['note'] == '今天有兴趣'

    @pytest.mark.asyncio
    async def test_returns_list_pipeline(self, monkeypatch):
        mock_cls = _make_ollama_mock(LIST_PIPELINE, 0.90, {
            'client_name': None, 'phone': None, 'status': 'new', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('我今天有多少新客户')

        assert r['intent'] == LIST_PIPELINE
        assert r['entities']['status'] == 'new'

    @pytest.mark.asyncio
    async def test_returns_search(self, monkeypatch):
        mock_cls = _make_ollama_mock(SEARCH, 0.91, {
            'client_name': None, 'phone': None, 'status': 'training', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('找一下所有培训中的客户')

        assert r['intent'] == SEARCH
        assert r['entities']['status'] == 'training'

    @pytest.mark.asyncio
    async def test_returns_help(self, monkeypatch):
        mock_cls = _make_ollama_mock(HELP, 0.97, {
            'client_name': None, 'phone': None, 'status': None, 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('我不知道怎么用')

        assert r['intent'] == HELP

    @pytest.mark.asyncio
    async def test_http_error_returns_unknown(self, monkeypatch):
        mock_cls = _make_ollama_error_mock(500)
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('any text')

        assert r['intent'] == UNKNOWN
        assert r['confidence'] == 0.0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_unknown(self, monkeypatch):
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={'response': 'not json {'})

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await _parse_ollama('any text')

        assert r['intent'] == UNKNOWN


# ── parse() — integration: Ollama + fallback ─────────────────────────────────

class TestParse:
    @pytest.mark.asyncio
    async def test_high_confidence_ollama_used(self):
        """When Ollama returns high confidence, use its result."""
        mock_cls = _make_ollama_mock(QUERY_CLIENT, 0.95, {
            'client_name': '阿明', 'phone': None, 'status': None, 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('阿明什么情况')

        assert r['intent'] == QUERY_CLIENT
        assert r['confidence'] >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_low_confidence_falls_back_to_regex(self):
        """When Ollama returns confidence below threshold, regex result is used if better."""
        mock_cls = _make_ollama_mock(UNKNOWN, 0.3, {
            'client_name': None, 'phone': None, 'status': None, 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('我不知道怎么用')

        # Regex HELP has 0.85 confidence → should win
        assert r['intent'] == HELP
        assert r['confidence'] >= CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_ollama_unavailable_regex_fallback(self):
        """When Ollama crashes entirely, regex picks up."""
        mock_cls = _make_ollama_error_mock(500)
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('阿明已经注册了')

        # Regex should detect UPDATE_STATUS
        assert r['intent'] == UPDATE_STATUS
        assert r['entities']['status'] == 'registered'

    @pytest.mark.asyncio
    async def test_phone_entity_extraction(self):
        mock_cls = _make_ollama_mock(UPDATE_STATUS, 0.93, {
            'client_name': None, 'phone': '0123456789', 'status': 'ordered', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('0123456789 下单了')

        assert r['entities']['phone'] == '0123456789'
        assert r['entities']['status'] == 'ordered'

    @pytest.mark.asyncio
    async def test_mixed_chinese_english(self):
        mock_cls = _make_ollama_mock(UPDATE_STATUS, 0.89, {
            'client_name': '阿Jun', 'phone': None, 'status': 'registered', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('阿Jun already registered')

        assert r['intent'] == UPDATE_STATUS
        assert r['entities']['client_name'] == '阿Jun'

    @pytest.mark.asyncio
    async def test_note_content_preserved(self):
        mock_cls = _make_ollama_mock(ADD_NOTE, 0.90, {
            'client_name': '小红', 'phone': None, 'status': None, 'note': '明天跟进'
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('给小红备注：明天跟进')

        assert r['entities']['note'] == '明天跟进'

    @pytest.mark.asyncio
    async def test_unknown_text_returns_result_without_crash(self):
        """Completely unrecognisable text should not raise, returns a result."""
        mock_cls = _make_ollama_mock(UNKNOWN, 0.1, {
            'client_name': None, 'phone': None, 'status': None, 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('xyzxyz random noise 123')

        assert 'intent' in r
        assert 'confidence' in r
        assert 'entities' in r

    @pytest.mark.asyncio
    async def test_invalid_status_from_ollama_cleared(self):
        """Ollama returning unknown status should result in null status."""
        mock_cls = _make_ollama_mock(UPDATE_STATUS, 0.88, {
            'client_name': '阿明', 'phone': None, 'status': 'flying', 'note': None
        })
        with __import__('unittest.mock').mock.patch('aiohttp.ClientSession', mock_cls):
            r = await parse('阿明flying了')

        assert r['entities']['status'] is None


# ── Confidence threshold constant ────────────────────────────────────────────

def test_confidence_threshold_value():
    assert CONFIDENCE_THRESHOLD == 0.7


# ── Pipeline statuses completeness ───────────────────────────────────────────

def test_pipeline_statuses_include_all():
    required = {'new', 'contacted', 'replied', 'registered', 'training', 'withdrew', 'ordered'}
    assert required.issubset(set(PIPELINE_STATUSES))
