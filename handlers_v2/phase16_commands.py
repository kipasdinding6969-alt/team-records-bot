"""Phase 16 handlers — /link, /unlink, /links, /override, /perms, /grant, /revoke."""
import json
import logging
from typing import Any, Dict

from database_v2 import database_v2
from models_v2 import Staff, StaffRole
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


# ─── Client Links ────────────────────────────────────────────────────────────

async def handle_link(task_data: Dict[str, Any]):
    """/link <client_id_1> <client_id_2> [type] [note]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    lang = staff.language
    parts = args.split(None, 3)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id,
            '用法 / Usage: /link <id1> <id2> [type] [note]\n'
            'Types: related, same_person, referral, family')
        return

    try:
        id_a, id_b = int(parts[0]), int(parts[1])
    except ValueError:
        await telegram_handler.send_message(chat_id, t('err_invalid_id', lang))
        return

    link_type = parts[2] if len(parts) > 2 else 'related'
    note = parts[3] if len(parts) > 3 else None

    valid_types = ('related', 'same_person', 'referral', 'family')
    if link_type not in valid_types:
        await telegram_handler.send_message(chat_id,
            f'Invalid type. Valid: {", ".join(valid_types)}')
        return

    # Verify both clients exist
    client_a = await database_v2.get_client_by_id(id_a)
    client_b = await database_v2.get_client_by_id(id_b)
    if not client_a or not client_b:
        await telegram_handler.send_message(chat_id, 'Client not found')
        return

    try:
        await database_v2.create_client_link(id_a, id_b, link_type, note, staff.id)
        await telegram_handler.send_message(chat_id,
            f'✅ Linked #{id_a} ↔ #{id_b} ({link_type})')
    except Exception as e:
        if 'UNIQUE' in str(e):
            await telegram_handler.send_message(chat_id, 'Already linked')
        else:
            await telegram_handler.send_message(chat_id, f'Error: {e}')


async def handle_unlink(task_data: Dict[str, Any]):
    """/unlink <client_id_1> <client_id_2>"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    parts = args.split()
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, 'Usage: /unlink <id1> <id2>')
        return

    try:
        id_a, id_b = int(parts[0]), int(parts[1])
    except ValueError:
        await telegram_handler.send_message(chat_id, 'Invalid IDs')
        return

    removed = await database_v2.remove_client_link(id_a, id_b)
    if removed:
        await telegram_handler.send_message(chat_id, f'✅ Unlinked #{id_a} ↔ #{id_b}')
    else:
        await telegram_handler.send_message(chat_id, 'Link not found')


async def handle_links(task_data: Dict[str, Any]):
    """/links <client_id>"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if not args:
        await telegram_handler.send_message(chat_id, 'Usage: /links <client_id>')
        return

    try:
        client_id = int(args.split()[0])
    except ValueError:
        await telegram_handler.send_message(chat_id, 'Invalid ID')
        return

    links = await database_v2.get_client_links(client_id)
    if not links:
        await telegram_handler.send_message(chat_id, f'No links for #{client_id}')
        return

    lines = [f'🔗 Links for #{client_id}:']
    for lnk in links:
        other_id = lnk['client_id_b'] if lnk['client_id_a'] == client_id else lnk['client_id_a']
        other_phone = lnk['phone_b'] if lnk['client_id_a'] == client_id else lnk['phone_a']
        lines.append(f'  ↔ #{other_id} ({other_phone}) [{lnk["link_type"]}]')
    await telegram_handler.send_message(chat_id, '\n'.join(lines))


# ─── Phone Registry Override ────────────────────────────────────────────────

async def handle_override(task_data: Dict[str, Any]):
    """/override <phone> — Admin/Leader override phone registry ownership."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if staff.role not in (StaffRole.ADMIN, StaffRole.LEADER, StaffRole.MANAGER):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    if not args:
        await telegram_handler.send_message(chat_id, 'Usage: /override <phone>')
        return

    phone = args.split()[0]
    entry = await database_v2.phone_registry_lookup(phone)
    if not entry:
        await telegram_handler.send_message(chat_id,
            f'Phone {phone} not in registry. Nothing to override.')
        return

    old_owner = entry['submitter_name']
    await database_v2.phone_registry_override(phone, staff.display_name, staff.id)
    await database_v2.phone_registry_log_action(
        phone, 'admin_override', staff.display_name, staff.id,
        json.dumps({'previous_owner': old_owner}, ensure_ascii=False))
    await telegram_handler.send_message(chat_id,
        f'✅ Override: {phone}\n'
        f'Previous: {old_owner}\n'
        f'New owner: {staff.display_name}')


# ─── Permission Management ──────────────────────────────────────────────────

async def handle_perms(task_data: Dict[str, Any]):
    """/perms [staff_name] — Show current permissions."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    # If no args, show own permissions
    if not args:
        target = staff
    else:
        # Admin+ can view others
        if staff.role not in (StaffRole.ADMIN, StaffRole.LEADER, StaffRole.MANAGER):
            await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
            return
        # Find staff by name
        all_staff = await database_v2.get_all_staff()
        target = next((s for s in all_staff if s.display_name == args), None)
        if not target:
            await telegram_handler.send_message(chat_id, f'Staff "{args}" not found')
            return

    overrides = await database_v2.get_all_permission_overrides(target.id)
    lines = [f'🔐 Permissions for {target.display_name} ({target.role.value}):']
    lines.append(f'Role defaults: all commands allowed' if target.role in (
        StaffRole.ADMIN, StaffRole.LEADER, StaffRole.MANAGER, StaffRole.FRONTDESK, StaffRole.MAINTENANCE
    ) else f'Role defaults: restricted')

    if overrides:
        lines.append('\nOverrides:')
        for o in overrides:
            status = '✅ GRANT' if o['allowed'] else '❌ DENY'
            lines.append(f'  /{o["command"]}: {status}')
            if o.get('reason'):
                lines.append(f'    Reason: {o["reason"]}')
    else:
        lines.append('\nNo overrides set.')

    await telegram_handler.send_message(chat_id, '\n'.join(lines))


async def handle_grant(task_data: Dict[str, Any]):
    """/grant <staff_name> <command> [reason]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if staff.role not in (StaffRole.ADMIN, StaffRole.LEADER, StaffRole.MANAGER):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    parts = args.split(None, 2)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, 'Usage: /grant <staff_name> <command> [reason]')
        return

    target_name = parts[0]
    command = parts[1].lstrip('/')
    reason = parts[2] if len(parts) > 2 else None

    all_staff = await database_v2.get_all_staff()
    target = next((s for s in all_staff if s.display_name == target_name), None)
    if not target:
        await telegram_handler.send_message(chat_id, f'Staff "{target_name}" not found')
        return

    await database_v2.set_permission_override(target.id, command, True, staff.id, reason)
    await telegram_handler.send_message(chat_id,
        f'✅ Granted /{command} to {target.display_name}')


async def handle_revoke(task_data: Dict[str, Any]):
    """/revoke <staff_name> <command> [reason]"""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    if staff.role not in (StaffRole.ADMIN, StaffRole.LEADER, StaffRole.MANAGER):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    parts = args.split(None, 2)
    if len(parts) < 2:
        await telegram_handler.send_message(chat_id, 'Usage: /revoke <staff_name> <command> [reason]')
        return

    target_name = parts[0]
    command = parts[1].lstrip('/')
    reason = parts[2] if len(parts) > 2 else None

    all_staff = await database_v2.get_all_staff()
    target = next((s for s in all_staff if s.display_name == target_name), None)
    if not target:
        await telegram_handler.send_message(chat_id, f'Staff "{target_name}" not found')
        return

    await database_v2.set_permission_override(target.id, command, False, staff.id, reason)
    await telegram_handler.send_message(chat_id,
        f'❌ Revoked /{command} from {target.display_name}')


# ─── Exports ─────────────────────────────────────────────────────────────────

PHASE16_COMMANDS = {
    'link': handle_link,
    'unlink': handle_unlink,
    'links': handle_links,
    'override': handle_override,
    'perms': handle_perms,
    'grant': handle_grant,
    'revoke': handle_revoke,
}

PHASE16_CALLBACKS = {}

PHASE16_CONVERSATIONS = {}
