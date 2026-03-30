"""Natural Language Understanding Engine for CRM operations.

Parses free-text Chinese or English messages into structured CRM intents.
Primary: Ollama (josiefied-qwen2.5-7b) for intent classification + entity extraction.
Fallback: regex-based parser when Ollama is unavailable or low confidence.
"""
import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'josiefied-qwen2.5-7b-abliterated-v2'
CONFIDENCE_THRESHOLD = 0.7

# Intent constants
QUERY_CLIENT = 'QUERY_CLIENT'
UPDATE_STATUS = 'UPDATE_STATUS'
ADD_NOTE = 'ADD_NOTE'
LIST_PIPELINE = 'LIST_PIPELINE'
SEARCH = 'SEARCH'
HELP = 'HELP'
UNKNOWN = 'UNKNOWN'

VALID_INTENTS = {QUERY_CLIENT, UPDATE_STATUS, ADD_NOTE, LIST_PIPELINE, SEARCH, HELP}

PIPELINE_STATUSES = [
    'new', 'contacted', 'replied', 'registered',
    'training', 'withdrew', 'ordered', 'ghosted', 'blocked', 'dead',
]

# Chinese status keywords → canonical status
_STATUS_MAP = {
    '新': 'new',
    '新客户': 'new',
    '联系': 'contacted',
    '联系了': 'contacted',
    '联系到': 'contacted',
    '已联系': 'contacted',
    '回复': 'replied',
    '回复了': 'replied',
    '已回复': 'replied',
    '注册': 'registered',
    '注册了': 'registered',
    '已注册': 'registered',
    '培训': 'training',
    '培训中': 'training',
    '在培训': 'training',
    '退出': 'withdrew',
    '退了': 'withdrew',
    '放弃': 'withdrew',
    '下单': 'ordered',
    '已下单': 'ordered',
    '订单': 'ordered',
    '跑路': 'ghosted',
    '失联': 'ghosted',
    '拉黑': 'blocked',
    '封号': 'blocked',
    '死客': 'dead',
    '死了': 'dead',
    # English keywords
    'contacted': 'contacted',
    'replied': 'replied',
    'registered': 'registered',
    'training': 'training',
    'withdrew': 'withdrew',
    'ordered': 'ordered',
    'ghosted': 'ghosted',
    'blocked': 'blocked',
    'dead': 'dead',
}

_NL_SYSTEM = (
    "You are a JSON-only intent classifier for a frontdesk sales CRM bot.\n\n"
    "CRM Pipeline statuses: new → contacted → replied → registered → training → withdrew → ordered\n"
    "Terminal statuses: ghosted, blocked, dead\n\n"
    "Given Chinese or English text from a frontdesk worker, classify the intent and extract entities.\n\n"
    "Intent types:\n"
    "- QUERY_CLIENT: looking up a specific client (e.g. '阿明什么情况', '查一下阿明')\n"
    "- UPDATE_STATUS: updating a client status (e.g. '阿明已经注册了', '阿明下单了')\n"
    "- ADD_NOTE: adding a note to a client (e.g. '给阿明备注今天有兴趣', '备注阿明：明天跟进')\n"
    "- LIST_PIPELINE: querying pipeline stats (e.g. '我今天有多少新客户', '今天多少人注册')\n"
    "- SEARCH: searching clients by criteria (e.g. '找所有培训中的客户', '查看所有新客户')\n"
    "- HELP: asking for help or doesn't know how to use (e.g. '我不知道怎么用', '帮我')\n\n"
    "Extract these entities when present:\n"
    "- client_name: person's name (e.g. 阿明, 小红, 阿Jun)\n"
    "- phone: phone number (digits only)\n"
    "- status: one of the pipeline statuses above\n"
    "- note: note content to record\n\n"
    "Few-shot examples:\n"
    "Input: '阿明什么情况' → "
    '{\"intent\": \"QUERY_CLIENT\", \"confidence\": 0.95, \"entities\": {\"client_name\": \"阿明\", \"phone\": null, \"status\": null, \"note\": null}}\n'
    "Input: '阿明已经注册了' → "
    '{\"intent\": \"UPDATE_STATUS\", \"confidence\": 0.92, \"entities\": {\"client_name\": \"阿明\", \"phone\": null, \"status\": \"registered\", \"note\": null}}\n'
    "Input: '给阿明备注：今天有兴趣' → "
    '{\"intent\": \"ADD_NOTE\", \"confidence\": 0.90, \"entities\": {\"client_name\": \"阿明\", \"phone\": null, \"status\": null, \"note\": \"今天有兴趣\"}}\n'
    "Input: '我今天有多少新客户' → "
    '{\"intent\": \"LIST_PIPELINE\", \"confidence\": 0.88, \"entities\": {\"client_name\": null, \"phone\": null, \"status\": \"new\", \"note\": null}}\n'
    "Input: '找一下所有培训中的客户' → "
    '{\"intent\": \"SEARCH\", \"confidence\": 0.91, \"entities\": {\"client_name\": null, \"phone\": null, \"status\": \"training\", \"note\": null}}\n'
    "Input: '我不知道怎么用' → "
    '{\"intent\": \"HELP\", \"confidence\": 0.97, \"entities\": {\"client_name\": null, \"phone\": null, \"status\": null, \"note\": null}}\n'
    "Input: '0123456789 下单了' → "
    '{\"intent\": \"UPDATE_STATUS\", \"confidence\": 0.93, \"entities\": {\"client_name\": null, \"phone\": \"0123456789\", \"status\": \"ordered\", \"note\": null}}\n\n'
    "Respond ONLY with valid JSON matching this schema exactly:\n"
    '{\"intent\": \"INTENT_TYPE\", \"confidence\": 0.0, \"entities\": {\"client_name\": null, \"phone\": null, \"status\": null, \"note\": null}}\n'
    "If confidence < 0.5 use intent UNKNOWN. Never add explanation text."
)


def _empty_result(intent: str = UNKNOWN, confidence: float = 0.0) -> Dict[str, Any]:
    return {
        'intent': intent,
        'confidence': confidence,
        'entities': {
            'client_name': None,
            'phone': None,
            'status': None,
            'note': None,
        },
    }


def _validate_and_clean(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalise parsed result."""
    intent = parsed.get('intent', UNKNOWN)
    if intent not in VALID_INTENTS:
        intent = UNKNOWN

    try:
        confidence = float(parsed.get('confidence', 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    raw_entities = parsed.get('entities', {}) or {}
    status = raw_entities.get('status') or None
    if status and status not in PIPELINE_STATUSES:
        status = None

    return {
        'intent': intent,
        'confidence': confidence,
        'entities': {
            'client_name': raw_entities.get('client_name') or None,
            'phone': raw_entities.get('phone') or None,
            'status': status,
            'note': raw_entities.get('note') or None,
        },
    }


async def parse(text: str) -> Dict[str, Any]:
    """Parse natural-language CRM message into structured intent.

    Returns:
        {intent, confidence, entities: {client_name, phone, status, note}}

    If Ollama unavailable or confidence < threshold, falls back to regex parser.
    """
    result = await _parse_ollama(text)

    # Use regex fallback if Ollama failed or confidence is too low
    if result['intent'] == UNKNOWN or result['confidence'] < CONFIDENCE_THRESHOLD:
        regex_result = _parse_regex(text)
        # Take whichever has higher confidence
        if regex_result['confidence'] > result['confidence']:
            result = regex_result

    return result


async def _parse_ollama(text: str) -> Dict[str, Any]:
    """Call Ollama to classify intent + extract entities."""
    try:
        import aiohttp
        payload = {
            'model': OLLAMA_MODEL,
            'system': _NL_SYSTEM,
            'prompt': f"Classify this CRM message:\n\n{text}",
            'stream': False,
            'format': 'json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OLLAMA_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Ollama NL returned HTTP {resp.status}")
                    return _empty_result()
                data = await resp.json()

        raw = data.get('response', '{}')
        parsed = json.loads(raw)
        result = _validate_and_clean(parsed)
        logger.info(f"Ollama NL parse: {text[:60]!r} → {result['intent']} ({result['confidence']:.2f})")
        return result

    except ImportError:
        logger.error("aiohttp not installed — cannot call Ollama")
        return _empty_result()
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"NL parse JSON error: {e}")
        return _empty_result()
    except Exception as e:
        logger.error(f"NL Ollama parse failed: {e}")
        return _empty_result()


def _parse_regex(text: str) -> Dict[str, Any]:
    """Regex-based fallback parser for common CRM patterns."""
    t = text.strip()
    result = _empty_result()

    # Detect phone number
    phone_match = re.search(r'\b(\d{7,15})\b', t)
    phone = phone_match.group(1) if phone_match else None

    # Detect Chinese/English name: 阿X, 小X patterns first, then 2-4 char CJK names, then capitalised word
    _status_kws = set(_STATUS_MAP.keys())
    name_match = re.search(r'(阿\S{1,3}|小\S{1,3}|[\u4e00-\u9fff]{2,4}|[A-Z][a-z]{1,9})', t)
    name = name_match.group(1) if name_match else None
    # Discard if matched a known status keyword (avoid false positives)
    if name and name in _status_kws:
        name = None

    # Detect status
    detected_status: Optional[str] = None
    for kw, status in _STATUS_MAP.items():
        if kw in t:
            detected_status = status
            break

    # HELP
    if re.search(r'不知道|怎么用|帮我|help|how to|帮助', t, re.IGNORECASE):
        result['intent'] = HELP
        result['confidence'] = 0.85
        return result

    # LIST_PIPELINE — pipeline stats query
    if re.search(r'多少|几个|统计|今天.*客户|客户.*今天|pipeline|漏斗', t, re.IGNORECASE):
        result['intent'] = LIST_PIPELINE
        result['confidence'] = 0.75
        result['entities']['status'] = detected_status
        return result

    # SEARCH — search by criteria
    if re.search(r'找|搜索|查看所有|所有.*客户|search|find all', t, re.IGNORECASE):
        result['intent'] = SEARCH
        result['confidence'] = 0.78
        result['entities']['status'] = detected_status
        result['entities']['client_name'] = name
        result['entities']['phone'] = phone
        return result

    # ADD_NOTE
    if re.search(r'备注|note|记录|记一下|笔记', t, re.IGNORECASE):
        note_match = re.search(r'[：:](.*)', t)
        note_text = note_match.group(1).strip() if note_match else None
        result['intent'] = ADD_NOTE
        result['confidence'] = 0.80
        result['entities']['client_name'] = name
        result['entities']['phone'] = phone
        result['entities']['note'] = note_text
        return result

    # UPDATE_STATUS — explicit status keyword present + client identifier
    if detected_status and (name or phone):
        result['intent'] = UPDATE_STATUS
        result['confidence'] = 0.82
        result['entities']['client_name'] = name
        result['entities']['phone'] = phone
        result['entities']['status'] = detected_status
        return result

    # QUERY_CLIENT — client name/phone lookup
    if re.search(r'什么情况|怎么了|查一下|查询|看看|情况如何|status|lookup|check', t, re.IGNORECASE) \
            or (name or phone):
        result['intent'] = QUERY_CLIENT
        result['confidence'] = 0.72
        result['entities']['client_name'] = name
        result['entities']['phone'] = phone
        return result

    return result
