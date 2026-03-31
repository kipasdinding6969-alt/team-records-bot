"""V2 quick action handlers — /add, /u, /note, /remind, inline status buttons."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from database_v2 import database_v2
from models_v2 import Client, ClientNote, ClientStatus, NoteType, Reminder, Staff
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

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


def _build_status_buttons(client_id: int, current_status: ClientStatus) -> List[Dict]:
    """Return a list of button-spec dicts for valid next statuses."""
    return [
        {'text': f'{status_emoji(s)} {s.value}', 'callback_data': f'v2_status_{client_id}_{s.value}'}
        for s in ClientStatus.valid_transitions(current_status)
        if s not in ClientStatus.terminal_statuses()  # keep buttons tidy; terminal via /u
    ]


async def handle_add_client(task_data: Dict[str, Any]):
    """
    /add <phone> <source> [account_id]
    Quickly add a new client. Requires frontdesk registration.
    account_id (编号) is optional at add time — set later with /num.
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

    parts = args.split(None, 2)
    if len(parts) < 2:
        msg = t('add_usage', lang)
        await telegram_handler.send_message(chat_id, msg)
        return

    phone, source = parts[0], parts[1]
    account_id = parts[2] if len(parts) > 2 else None

    # Policy: daily client limit
    from engines.policy_engine import check_can_add_client
    allowed, reason = await check_can_add_client(staff.id)
    if not allowed:
        await telegram_handler.send_message(chat_id, t('policy_add_limit', lang, reason=reason))
        return

    # Check duplicate (same frontdesk)
    existing = await database_v2.get_client_by_phone(phone, staff.id)
    if existing:
        msg = t('add_duplicate', lang, phone=phone, status=existing.status.value)
        await telegram_handler.send_message(chat_id, msg)
        return

    # Phase 16: Phone Registry duplicate guard (cross-frontdesk)
    registry_entry = await database_v2.phone_registry_lookup(phone)
    if registry_entry:
        owner_name = registry_entry['submitter_name']
        owner_staff_id = registry_entry['submitter_staff_id']
        submitted_at = registry_entry['submitted_at']
        if owner_staff_id != staff.id:
            # Different frontdesk owns this number — block
            import json
            await database_v2.phone_registry_log_action(
                phone, 'duplicate_blocked', staff.display_name, staff.id,
                json.dumps({'original_submitter': owner_name}, ensure_ascii=False))
            msg = (
                f"⚠️ 号码重复 / Duplicate Number\n"
                f"该号码已由 {owner_name} 于 {submitted_at} 提交\n"
                f"This number was submitted by {owner_name} on {submitted_at}\n"
                f"如需覆盖请联系管理员 / Contact admin to override"
            )
            await telegram_handler.send_message(chat_id, msg)
            return
        # Same frontdesk — allow edit (fall through)

    client = Client(frontdesk_id=staff.id, phone=phone, source=source, account_id=account_id)
    client_id = await database_v2.create_client(client)

    # Phase 16: Register phone in registry if not already there
    if not registry_entry:
        try:
            from datetime import datetime as _dt
            await database_v2.phone_registry_insert(
                phone, staff.display_name, _dt.utcnow().isoformat(),
                source='bot', submitter_staff_id=staff.id)
            await database_v2.phone_registry_log_action(
                phone, 'submit', staff.display_name, staff.id)
        except Exception as _e:
            logger.debug(f'Phone registry insert skipped: {_e}')

    acct_str = f'\n🆔 编号: {account_id}' if account_id else '\n💡 /num {phone} {编号} 设置编号'
    msg = t('add_success', lang, phone=phone, source=source, id=client_id) + acct_str
    await telegram_handler.send_message(chat_id, msg)
    logger.info(f'Staff {staff.display_name} added client {phone} (source: {source}, acct: {account_id})')

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


async def handle_bulkupdate(task_data: Dict[str, Any]):
    """
    /bulkupdate <status> <phone1> <phone2> ...
    Batch status update with preview + inline confirm/cancel.
    Not available to VIEWER or NEWBIE roles.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from models_v2 import StaffRole
    if staff.role in (StaffRole.VIEWER, StaffRole.NEWBIE):
        await telegram_handler.send_message(chat_id, t('bulkupdate_no_permission', lang))
        return

    parts = args.split()
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, t('bulkupdate_usage', lang))
        return

    status_str = parts[0].lower()
    phones = parts[1:]

    try:
        new_status = ClientStatus(status_str)
    except ValueError:
        valid = ', '.join(s.value for s in ClientStatus)
        await telegram_handler.send_message(
            chat_id, t('bulkupdate_invalid_status', lang, status=status_str, valid=valid))
        return

    # Validate each phone — build list of (phone, client_or_None)
    is_manager = staff.is_manager_or_above()
    valid_clients = []
    warnings = []
    for phone in phones:
        client = await database_v2.get_client_by_phone(phone, None if is_manager else staff.id)
        if not client:
            warnings.append(t('bulkupdate_phone_not_found', lang, phone=phone))
            continue
        if not is_manager and client.frontdesk_id != staff.id:
            warnings.append(t('bulkupdate_phone_not_owned', lang, phone=phone))
            continue
        valid_clients.append(client)

    if not valid_clients:
        msg_parts = [t('bulkupdate_usage', lang)] + warnings
        await telegram_handler.send_message(chat_id, '\n'.join(msg_parts))
        return

    phone_list = '\n'.join(f'• {c.phone} ({c.status.value} → {status_str})' for c in valid_clients)
    if warnings:
        phone_list += '\n' + '\n'.join(warnings)

    preview = t('bulkupdate_preview', lang,
                status=status_str, count=len(valid_clients), phones=phone_list)

    # Encode client ids in callback_data
    ids_str = ','.join(str(c.id) for c in valid_clients)
    buttons = [
        [
            {'text': t('bulkupdate_confirm', lang),
             'callback_data': f'v2_bulk_confirm_{status_str}_{ids_str}'},
            {'text': t('bulkupdate_cancel', lang),
             'callback_data': 'v2_bulk_cancel'},
        ]
    ]
    await telegram_handler.send_message(chat_id, preview, reply_markup={'inline_keyboard': buttons})


async def handle_bulkupdate_callback(task_data: Dict[str, Any]):
    """Callback: v2_bulk_confirm_<status>_<id1,id2,...> or v2_bulk_cancel."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')

    staff = await _get_staff(user_id)
    if not staff:
        return

    lang = staff.language

    if callback_data == 'v2_bulk_cancel':
        await telegram_handler.send_message(chat_id, t('bulkupdate_cancelled', lang))
        return

    # v2_bulk_confirm_<status>_<ids>
    parts = callback_data.split('_', 4)
    if len(parts) < 5:
        return

    status_str = parts[3]
    ids_str = parts[4]

    try:
        new_status = ClientStatus(status_str)
        client_ids = [int(i) for i in ids_str.split(',') if i]
    except (ValueError, IndexError):
        return

    ok = 0
    fail = 0
    for cid in client_ids:
        try:
            success = await database_v2.update_client_status(cid, new_status, staff.id)
            if success:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    await telegram_handler.send_message(
        chat_id, t('bulkupdate_success', lang, ok=ok, fail=fail))


async def handle_num(task_data: Dict[str, Any]):
    """
    /num <phone> <account_id>
    Set or update the account number (编号) for a client.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'u'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', lang))
        return

    parts = args.split(None, 1)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id,
            '用法: /num <手机号> <编号>\n'
            'Usage: /num <phone> <account_id>\n\n'
            '例: /num 46123456789 763')
        return

    phone, account_id = parts[0], parts[1]
    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        await telegram_handler.send_message(chat_id, t('client_not_found', lang, phone=phone))
        return

    # Update account_id
    client.account_id = account_id
    await database_v2.update_client(client)

    await telegram_handler.send_message(chat_id,
        f'✅ 编号已更新 / Account ID updated\n'
        f'📱 {phone}\n'
        f'🆔 {account_id}')
    logger.info(f'{staff.display_name} set account_id={account_id} for {phone}')


async def handle_info(task_data: Dict[str, Any]):
    """
    /info <phone>
    Show full client details: phone, account_id, status, source, timestamps, notes.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    if not args:
        await telegram_handler.send_message(chat_id,
            '用法: /info <手机号>\nUsage: /info <phone>')
        return

    phone = args.split()[0]

    # Search across own clients first, then team if in group
    client = await database_v2.get_client_by_phone(phone, staff.id)
    if not client:
        # Try searching all clients (for leaders/managers)
        from handlers_v2 import resolve_team_scope, get_team_staff_ids
        team = resolve_team_scope(task_data, staff)
        if team and staff.role.value in ('leader', 'maintenance', 'manager', 'admin'):
            team_ids = await get_team_staff_ids(team)
            for sid in team_ids:
                client = await database_v2.get_client_by_phone(phone, sid)
                if client:
                    break

    if not client:
        await telegram_handler.send_message(chat_id, t('client_not_found', lang, phone=phone))
        return

    # Get staff name who owns this client
    owner = await database_v2.get_staff_by_id(client.frontdesk_id)
    owner_name = owner.display_name if owner else '?'

    # Get notes
    notes = await database_v2.get_client_notes(client.id, limit=3)
    notes_text = ''
    if notes:
        notes_text = '\n\n📝 最近备注 / Recent Notes:'
        for n in notes:
            notes_text += f'\n  • {n.note} ({n.created_at[:10] if n.created_at else ""})'

    # Build info card
    from models_v2 import status_emoji
    se = status_emoji(client.status)
    text = (
        f'📋 <b>客户详情 / Client Info</b>\n\n'
        f'📱 手机: {client.phone}\n'
        f'🆔 编号: {client.account_id or "未设置 /num"}\n'
        f'{se} 状态: {client.status.value}\n'
        f'📡 来源: {client.source}\n'
        f'👤 前台: {owner_name}\n'
        f'📅 添加: {(client.created_at or "")[:10]}\n'
    )

    if client.contacted_at:
        text += f'📱 联系: {client.contacted_at[:10]}\n'
    if client.registered_at:
        text += f'✅ 注册: {client.registered_at[:10]}\n'
    if client.total_deposited:
        text += f'💰 入金: {client.total_deposited}\n'
    if client.platform:
        text += f'🌐 平台: {client.platform}\n'

    text += notes_text
    text += f'\n\n/u {phone} <状态>  /note {phone} <备注>  /num {phone} <编号>'

    await telegram_handler.send_message(chat_id, text, parse_mode='html')


async def handle_req(task_data: Dict[str, Any]):
    """
    /req <message>
    Send a support request to the 客服中心 group and management 紧急 topic.
    Any staff can request help — message goes to support team.
    """
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language

    if not args:
        await telegram_handler.send_message(chat_id,
            '用法: /req <你的问题或请求>\n'
            'Usage: /req <your question or request>\n\n'
            '例: /req 客户46123456789注册有问题，需要客服帮助')
        return

    # Build support request message
    request_msg = (
        f'🛎️ <b>支持请求 / Support Request</b>\n\n'
        f'👤 来自: {staff.display_name} ({staff.role.value})\n'
        f'👥 团队: {staff.team or "未分组"}\n'
        f'📝 内容: {args}\n'
        f'🕐 时间: {datetime.now().strftime("%H:%M")}'
    )

    sent = False

    # 1. Send to 客服中心
    try:
        from team_config import team_config
        kefu_id = team_config.get_kefu_id()
        if kefu_id:
            await telegram_handler.send_message(kefu_id, request_msg, parse_mode='html')
            sent = True
    except Exception as e:
        logger.error(f'Failed to send req to kefu: {e}')

    # 2. Send to management 紧急 topic
    try:
        await telegram_handler.send_to_management(request_msg, topic='紧急', parse_mode='html')
        sent = True
    except Exception as e:
        logger.error(f'Failed to send req to management: {e}')

    if sent:
        await telegram_handler.send_message(chat_id,
            '✅ 请求已发送给客服和管理层\nRequest sent to support team & management')
    else:
        await telegram_handler.send_message(chat_id,
            '❌ 发送失败，请直接联系客服\nFailed to send, contact support directly')

    logger.info(f'Support request from {staff.display_name}: {args[:50]}')


# Handler registries
QUICK_ACTIONS_COMMANDS = {
    'add': handle_add_client,
    'u': handle_update_status,
    'num': handle_num,
    'info': handle_info,
    'req': handle_req,
    'note': handle_add_note,
    'remind': handle_remind,
    'handoff': handle_handoff,
    'bulkupdate': handle_bulkupdate,
}

QUICK_ACTIONS_CALLBACKS = {
    'v2_status_*': handle_inline_status_callback,
    'v2_bulk_confirm_*': handle_bulkupdate_callback,
    'v2_bulk_cancel': handle_bulkupdate_callback,
}

QUICK_ACTIONS_CONVERSATIONS = {}
