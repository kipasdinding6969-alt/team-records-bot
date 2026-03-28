"""V2 quick action handlers — /add, /u, /note, /remind, inline status buttons."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database_v2 import database_v2
from models_v2 import Client, ClientNote, ClientStatus, NoteType, Reminder, Staff
from i18n import t
from telegram_handler import telegram_handler

logger = logging.getLogger(__name__)

# Standalone emoji map — avoids creating dummy Client objects.
_STATUS_EMOJIS = {
    ClientStatus.NEW: '🆕',
    ClientStatus.CONTACTED: '📱',
    ClientStatus.REPLIED: '💬',
    ClientStatus.REGISTERED: '✅',
    ClientStatus.TRAINING: '📚',
    ClientStatus.WITHDREW: '💰',
    ClientStatus.ORDERED: '🎯',
    ClientStatus.GHOSTED: '👻',
    ClientStatus.BLOCKED: '🚫',
    ClientStatus.SCAMMED: '⚠️',
    ClientStatus.SCHEDULED: '📅',
    ClientStatus.DEAD: '💀',
}


def status_emoji(status: ClientStatus) -> str:
    return _STATUS_EMOJIS.get(status, '❓')


def _parse_time_delta(time_str: str) -> Optional[timedelta]:
    """Parse '2h', '30m', '1d' into timedelta. Returns None on failure."""
    time_str = time_str.strip().lower()
    if time_str.endswith('h'):
        try:
            return timedelta(hours=float(time_str[:-1]))
        except ValueError:
            return None
    if time_str.endswith('m'):
        try:
            return timedelta(minutes=float(time_str[:-1]))
        except ValueError:
            return None
    if time_str.endswith('d'):
        try:
            return timedelta(days=float(time_str[:-1]))
        except ValueError:
            return None
    return None


async def _get_staff(user_id: int) -> Optional[Staff]:
    return await database_v2.get_staff_by_tg_id(user_id)


def _build_status_buttons(client_id: int, current_status: ClientStatus) -> List[Dict]:
    """Return a list of button-spec dicts for valid next statuses."""
    return [
        {'text': f'{status_emoji(s)} {s.value}', 'callback_data': f'v2_status_{client_id}_{s.value}'}
        for s in ClientStatus.valid_transitions(current_status)
        if s not in ClientStatus.terminal_statuses()  # keep buttons tidy; terminal via /u
    ]


async def handle_add_client(task_data: Dict[str, Any]):
    """
    /add <phone> <source>
    Quickly add a new client. Requires frontdesk registration.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Role permission check
    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'add'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        msg = t('add_usage', lang)
        await telegram_handler.send_message(chat_id, msg)
        return

    phone, source = parts[0], parts[1]

    # Policy: daily client limit
    from engines.policy_engine import check_can_add_client
    allowed, reason = await check_can_add_client(staff.id)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_add_limit', lang, reason=reason))
        return

    # Check duplicate
    existing = await database_v2.get_client_by_phone(phone, staff.id)
    if existing:
        msg = t('add_duplicate', lang, phone=phone, status=existing.status.value)
        await telegram_handler.send_message(chat_id, msg)
        return

    client = Client(frontdesk_id=staff.id, phone=phone, source=source)
    client_id = await database_v2.create_client(client)

    msg = t('add_success', lang, phone=phone, source=source, id=client_id)
    await telegram_handler.send_message(chat_id, msg)
    logger.info(f'Staff {staff.display_name} added client {phone} (source: {source})')

    # Push new client to Google Sheets (non-blocking)
    try:
        from engines.sheet_sync_v2 import sheet_sync_v2
        await sheet_sync_v2.export_client_to_sheet(client_id)
    except Exception as _e:
        logger.debug(f'Sheet export skipped after /add: {_e}')


async def handle_update_status(task_data: Dict[str, Any]):
    """
    /u <phone> <status>
    Quick status update for a client. Validates state machine transitions.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Role permission check
    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'u'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, t('update_usage', lang))
        return

    phone, status_str = parts[0], parts[1].lower()

    # Validate status value
    try:
        new_status = ClientStatus(status_str)
    except ValueError:
        valid = ', '.join(s.value for s in ClientStatus)
        await telegram_handler.send_message(
            chat_id, t('invalid_status', lang, valid=valid))
        return

    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        await telegram_handler.send_message(chat_id, t('client_not_found', lang, phone=phone))
        return

    # Validate state machine transition
    valid_transitions = ClientStatus.valid_transitions(client.status)
    if new_status not in valid_transitions:
        valid_str = ', '.join(s.value for s in valid_transitions)
        await telegram_handler.send_message(
            chat_id, t('invalid_transition', lang,
                        from_status=client.status.value,
                        to_status=new_status.value,
                        valid=valid_str))
        return

    # Policy enforcement
    from engines.policy_engine import enforce_on_status_change
    allowed, reason = await enforce_on_status_change(client, new_status, staff)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_status_blocked', lang, reason=reason))
        return

    ok = await database_v2.update_client_status(client.id, new_status, staff.id)
    if ok:
        emoji = status_emoji(new_status)
        msg = t('status_updated', lang, phone=phone, status=status_str, emoji=emoji)
        await telegram_handler.send_message(chat_id, msg)

        # Index into RAG
        try:
            from engines.rag_engine import index_client_notes
            await index_client_notes(client.id)
        except Exception:
            pass

        # Push updated status to Google Sheets (non-blocking)
        try:
            from engines.sheet_sync_v2 import sheet_sync_v2
            await sheet_sync_v2.export_client_to_sheet(client.id)
        except Exception as _e:
            logger.debug(f'Sheet export skipped after /u: {_e}')
    else:
        await telegram_handler.send_message(chat_id, t('err_something_wrong', lang))


async def handle_add_note(task_data: Dict[str, Any]):
    """
    /note <phone> <text>
    Add a note to a client.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Role permission check
    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'note'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, t('note_usage', lang))
        return

    phone, content = parts[0], parts[1]
    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        await telegram_handler.send_message(chat_id, t('client_not_found', lang, phone=phone))
        return

    note = ClientNote(
        client_id=client.id,
        staff_id=staff.id,
        note_type=NoteType.NOTE,
        content=content,
    )
    await database_v2.add_client_note(note)

    msg = t('note_saved', lang, phone=phone)
    await telegram_handler.send_message(chat_id, msg)

    # Re-index RAG
    try:
        from engines.rag_engine import index_client_notes
        await index_client_notes(client.id)
    except Exception:
        pass

    # Log to Obsidian (non-blocking)
    try:
        from engines.obsidian_brain import obsidian_brain
        await obsidian_brain.log_client_interaction(phone, staff.display_name, content)
    except Exception:
        pass


async def handle_remind(task_data: Dict[str, Any]):
    """
    /remind <phone> <time> <message>
    Set a personal reminder for a client. Time: 2h, 30m, 1d, etc.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Role permission check
    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'remind'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 2)
    if len(parts) < 3:
        await telegram_handler.send_message(chat_id, t('remind_usage', lang))
        return

    phone, time_str, message = parts[0], parts[1], parts[2]

    delta = _parse_time_delta(time_str)
    if not delta:
        await telegram_handler.send_message(chat_id, t('remind_bad_time', lang, time=time_str))
        return

    # Policy: remind limits
    from engines.policy_engine import check_remind_limits
    allowed, reason = check_remind_limits(delta)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_remind_blocked', lang, reason=reason))
        return

    client = await database_v2.get_client_by_phone(phone, staff.id)
    client_id = client.id if client else None

    remind_at = datetime.now() + delta
    reminder = Reminder(
        staff_id=staff.id,
        client_id=client_id,
        remind_at=remind_at,
        message=message,
        source='manual',
    )
    await database_v2.create_reminder(reminder)

    # Also set next_followup on the client
    if client:
        await database_v2.set_next_followup(client.id, remind_at)

    time_fmt = remind_at.strftime('%m-%d %H:%M')
    msg = t('remind_set', lang, phone=phone, time=time_fmt, message=message)
    await telegram_handler.send_message(chat_id, msg)


async def handle_handoff(task_data: Dict[str, Any]):
    """
    /handoff <phone> [note]
    Frontdesk marks client as ready for maintenance.
    Sets handoff_at, copies maintenance_id from frontdesk's team, notifies maintenance.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    # Role permission check
    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'handoff'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 1)
    if not parts:
        await telegram_handler.send_message(chat_id, t('handoff_usage', lang))
        return

    phone = parts[0]
    note = parts[1] if len(parts) > 1 else ''

    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        await telegram_handler.send_message(chat_id, t('client_not_found', lang, phone=phone))
        return

    # Policy: client must be registered before handoff
    from engines.policy_engine import check_can_handoff
    allowed, reason = await check_can_handoff(client)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_handoff_blocked', lang, reason=reason))
        return

    # Get maintenance person for this frontdesk
    maintenance = await database_v2.get_maintenance_for_staff(staff.id)
    if not maintenance:
        await telegram_handler.send_message(chat_id, t('handoff_no_maintenance', lang))
        return

    await database_v2.set_client_handoff(client.id, maintenance.id, note or None)

    # Confirm to frontdesk
    await telegram_handler.send_message(
        chat_id,
        t('handoff_success', lang, phone=phone, maintenance=maintenance.display_name,
          note=note or '-'))

    # Notify maintenance person (if they have a real chat_id)
    if maintenance.tg_chat_id and maintenance.tg_chat_id > 0:
        notify_msg = t('handoff_notification', lang,
                       frontdesk=staff.display_name, phone=phone,
                       status=client.status.value, note=note or '-')
        try:
            await telegram_handler.send_message(maintenance.tg_chat_id, notify_msg)
        except Exception as e:
            logger.debug(f'Handoff notification to maintenance failed: {e}')

    logger.info(
        f'{staff.display_name} handed off {phone} to {maintenance.display_name}'
        + (f' — {note}' if note else ''))

    # Log handoff to Obsidian (non-blocking)
    try:
        from datetime import date
        from engines.obsidian_brain import obsidian_brain
        await obsidian_brain.log_handoff(
            date_str=date.today().isoformat(),
            frontdesk=staff.display_name,
            maintenance=maintenance.display_name,
            phone=phone,
            status=client.status.value,
            note=note,
        )
    except Exception:
        pass


async def handle_inline_status_callback(task_data: Dict[str, Any]):
    """
    Callback: v2_status_<client_id>_<status>
    Inline button status update with transition validation.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    # Parse: v2_status_<client_id>_<status>
    parts = callback_data.split('_', 3)
    if len(parts) < 4:
        return

    try:
        client_id = int(parts[2])
        status_str = parts[3]
        new_status = ClientStatus(status_str)
    except (ValueError, IndexError):
        return

    client = await database_v2.get_client_by_id(client_id)
    if not client or client.frontdesk_id != staff.id:
        return

    # Validate transition
    if new_status not in ClientStatus.valid_transitions(client.status):
        await telegram_handler.send_message(
            chat_id, t('invalid_transition', lang,
                        from_status=client.status.value,
                        to_status=new_status.value,
                        valid=', '.join(s.value for s in ClientStatus.valid_transitions(client.status))))
        return

    # Policy enforcement
    from engines.policy_engine import enforce_on_status_change
    allowed, reason = await enforce_on_status_change(client, new_status, staff)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_status_blocked', lang, reason=reason))
        return

    ok = await database_v2.update_client_status(client_id, new_status, staff.id)
    if ok:
        emoji = status_emoji(new_status)
        msg = t('status_updated', lang, phone=client.phone, status=status_str, emoji=emoji)
        await telegram_handler.send_message(chat_id, msg)


# Handler registries
QUICK_ACTIONS_COMMANDS = {
    'add': handle_add_client,
    'u': handle_update_status,
    'note': handle_add_note,
    'remind': handle_remind,
    'handoff': handle_handoff,
}

QUICK_ACTIONS_CALLBACKS = {
    'v2_status_*': handle_inline_status_callback,
}

QUICK_ACTIONS_CONVERSATIONS = {}
