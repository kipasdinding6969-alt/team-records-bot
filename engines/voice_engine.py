"""Voice transcription + intent parsing engine.

Transcription: faster-whisper (CPU, tiny model) — graceful fallback to None.
Intent parsing: Ollama LLM (josiefied-qwen2.5-7b-abliterated-v2) → JSON.
"""
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OLLAMA_URL = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'josiefied-qwen2.5-7b-abliterated-v2'

_PIPELINE_STATUSES = [
    'new', 'contacted', 'replied', 'registered',
    'training', 'withdrew', 'ordered', 'ghosted', 'blocked', 'dead',
]

_INTENT_SYSTEM = (
    "You are a data extraction assistant for a frontdesk sales CRM.\n\n"
    "Pipeline statuses: new → contacted → replied → registered → training → withdrew → ordered\n"
    "Terminal statuses: ghosted, blocked, dead\n\n"
    "Given Chinese or English text describing a client update, extract:\n"
    "- client_phone: phone number string (digits, may have country code prefix)\n"
    "- new_status: one of the statuses above, or null if not mentioned\n"
    "- note: short summary note about the client, or null\n\n"
    "Respond ONLY with valid JSON, no explanation:\n"
    '{"client_phone": "1234567890", "new_status": "contacted", "note": "Called, interested"}\n'
    "If a field cannot be determined use null."
)


async def transcribe(audio_path: str) -> Optional[str]:
    """Transcribe OGG voice file to text using faster-whisper.

    Returns transcribed string, or None if unavailable/failed.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel('tiny', device='cpu', compute_type='int8')
        segments, _ = model.transcribe(audio_path, language='zh')
        text = ''.join(seg.text for seg in segments).strip()
        logger.info(f"Transcribed {audio_path}: {text[:80]!r}")
        return text or None
    except ImportError:
        logger.warning("faster-whisper not installed — transcription unavailable")
        return None
    except Exception as e:
        logger.error(f"Transcription failed for {audio_path}: {e}")
        return None


async def parse_intent(text: str) -> Dict[str, Any]:
    """Parse natural-language client update into structured intent via Ollama.

    Returns dict with keys: client_phone, new_status, note (all may be None).
    """
    empty: Dict[str, Any] = {'client_phone': None, 'new_status': None, 'note': None}
    try:
        import aiohttp  # type: ignore
        payload = {
            'model': OLLAMA_MODEL,
            'system': _INTENT_SYSTEM,
            'prompt': f"Extract client update info from this text:\n\n{text}",
            'stream': False,
            'format': 'json',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OLLAMA_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Ollama returned HTTP {resp.status}")
                    return empty
                data = await resp.json()
        raw = data.get('response', '{}')
        parsed = json.loads(raw)
        result: Dict[str, Any] = {
            'client_phone': parsed.get('client_phone') or None,
            'new_status': parsed.get('new_status') or None,
            'note': parsed.get('note') or None,
        }
        # Validate status value
        if result['new_status'] and result['new_status'] not in _PIPELINE_STATUSES:
            logger.warning(f"Unknown status from LLM: {result['new_status']!r}")
            result['new_status'] = None
        logger.info(f"Parsed intent: {result}")
        return result
    except ImportError:
        logger.error("aiohttp not installed — cannot call Ollama")
        return empty
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Intent parse JSON error: {e}")
        return empty
    except Exception as e:
        logger.error(f"Intent parse failed: {e}")
        return empty
