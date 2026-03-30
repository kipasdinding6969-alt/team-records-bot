"""Voice note handler — transcribe OGG → parse intent → inline confirm."""
import logging
import os
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import ClientNote, ClientStatus, NoteType
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


async def handle_voice_message(task_data: Dict[str, Any]):
    """Staff sends voice note in DM → transcribe → parse → confirmation buttons."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    voice_path = task_data.get('voice_path')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    if not voice_path or not os.path.exists(voice_path):
        await telegram_handler.send_message(chat_id, t('voice_no_file', lang))
        return

    await telegram_handler.send_message(chat_id, t('voice_transcribing', lang))

    from engines.voice_engine import transcribe, parse_intent
    text = await transcribe(voice_path)

    # Cleanup temp file immediately after transcription
    try:
        os.unlink(voice_path)
    except Exception:
        pass

    if not text:
        await telegram_handler.send_message(chat_id, t('voice_transcribe_failed', lang))
        return

    intent = await parse_intent(text)
    client_phone = intent.get('client_phone')
    new_status = intent.get('new_status')
    note = intent.get('note')

    # Persist pending data in conversation state
    await telegram_handler.set_conversation_state(user_id, {
        'step': 'voice_confirm',
        'pending': {
            'phone': client_phone,
            'status': new_status,
            'note': note,
            'transcript': text,
        },
    })

    preview = t('voice_confirm_preview', lang,
                transcript=text[:200],
                phone=client_phone or '?',
                status=new_status or '?',
                note=note or '-')

    keyboard = telegram_handler.create_inline_keyboard([[
        {'text': t('btn_voice_confirm', lang), 'callback_data': 'voice_confirm'},
        {'text': t('btn_voice_edit', lang), 'callback_data': 'voice_edit'},
        {'text': t('btn_voice_cancel', lang), 'callback_data': 'voice_cancel'},
    ]])
    await telegram_handler.send_message(chat_id, preview,
                                        reply_markup=keyboard, parse_mode='markdown')


async def handle_voice_confirm_callback(task_data: Dict[str, Any]):
    """voice_confirm — apply the parsed update to the DB."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language
    state = await telegram_handler.get_conversation_state(user_id)
    pending = (state or {}).get('pending', {})

    phone = pending.get('phone')
    new_status_str = pending.get('status')
    note = pending.get('note')

    await telegram_handler.clear_conversation_state(user_id)

    if not phone or not new_status_str:
        await telegram_handler.send_message(chat_id, t('voice_confirm_missing', lang))
        return

    try:
        new_status = ClientStatus(new_status_str)
    except ValueError:
        await telegram_handler.send_message(
            chat_id, t('voice_confirm_bad_status', lang, status=new_status_str))
        return

    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        await telegram_handler.send_message(
            chat_id, t('voice_client_not_found', lang, phone=phone))
        return

    await database_v2.update_client_status(client.id, new_status, staff.id)

    if note:
        client_note = ClientNote(
            client_id=client.id,
            staff_id=staff.id,
            note_type=NoteType.NOTE,
            content=note,
        )
        await database_v2.add_client_note(client_note)

    await telegram_handler.send_message(
        chat_id, t('voice_updated', lang, phone=phone, status=new_status_str))
    logger.info(f"Voice update: staff {staff.display_name} → {phone} → {new_status_str}")


async def handle_voice_cancel_callback(task_data: Dict[str, Any]):
    """voice_cancel — discard pending voice update."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    staff = await _get_staff(user_id)
    lang = staff.language if staff else 'zh'
    await telegram_handler.clear_conversation_state(user_id)
    await telegram_handler.send_message(chat_id, t('voice_cancelled', lang))


async def handle_voice_edit_callback(task_data: Dict[str, Any]):
    """voice_edit — clear state and prompt user to use /u command instead."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    staff = await _get_staff(user_id)
    lang = staff.language if staff else 'zh'
    await telegram_handler.clear_conversation_state(user_id)
    await telegram_handler.send_message(chat_id, t('voice_edit_hint', lang))


# ── Handler registries ──────────────────────────────────────────────────────

VOICE_COMMANDS: dict = {}

VOICE_CALLBACKS = {
    'voice_confirm': handle_voice_confirm_callback,
    'voice_cancel':  handle_voice_cancel_callback,
    'voice_edit':    handle_voice_edit_callback,
}

VOICE_CONVERSATIONS = {
    'voice_confirm': handle_voice_confirm_callback,
}
