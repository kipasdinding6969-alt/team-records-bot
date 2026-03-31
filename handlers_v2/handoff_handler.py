"""Phase 10C: Shift handoff handler — commands + callbacks."""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from database_v2 import database_v2
from i18n import t
from models_v2 import ShiftHandoff
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff, require_permission, resolve_team_scope

logger = logging.getLogger(__name__)


@require_permission('handoff')
async def handle_handoff(task_data: Dict[str, Any]):
    """Handle /handoff command with subcommands."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()
    staff = await _get_staff(user_id)
    if not staff:
        return

    parts = args.split() if args else []
    subcmd = parts[0] if parts else ''

    if subcmd == 'accept' and len(parts) >= 2:
        try:
            handoff_id = int(parts[1])
        except ValueError:
            await telegram_handler.send_message(chat_id, "Invalid handoff ID.")
            return
        await _accept_handoff(chat_id, staff, handoff_id)
    elif subcmd == 'list':
        await _list_handoffs(chat_id, staff)
    else:
        # Target staff can be @username or display name
        target = subcmd.lstrip('@') if subcmd else None
        await _create_handoff(chat_id, staff, target)


async def _create_handoff(chat_id: int, staff, target_name: str = None):
    """Create a shift handoff with active client summary."""
    active_clients = await database_v2.get_active_clients_for_staff(staff.id)

    if not active_clients:
        await telegram_handler.send_message(chat_id, "No active clients to hand off.")
        return

    # Resolve target staff if provided
    to_staff_id = None
    to_display = 'any available'
    if target_name:
        all_staff = await database_v2.get_all_staff()
        for s in all_staff:
            if s.display_name == target_name or s.tg_username == target_name:
                to_staff_id = s.id
                to_display = s.display_name
                break
        else:
            await telegram_handler.send_message(
                chat_id, f"⚠️ Staff '{target_name}' not found. Handoff will be sent to any available staff.")

    client_ids = [c.id for c in active_clients]

    handoff = ShiftHandoff(
        from_staff_id=staff.id,
        to_staff_id=to_staff_id,
        team=staff.team,
        status='pending',
        notes=None,
        client_ids=json.dumps(client_ids),
    )
    handoff_id = await database_v2.create_handoff(handoff)

    # Build summary text
    text = f"🔄 Shift Handoff from {staff.display_name} → {to_display}\n"
    text += "━" * 27 + "\n"
    text += f"Active Clients ({len(active_clients)}):\n\n"

    for i, c in enumerate(active_clients[:10], 1):
        status_note = (c.status_note or '').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        last_update = ''
        if c.updated_at:
            delta = datetime.utcnow() - c.updated_at.replace(tzinfo=None)
            hours = int(delta.total_seconds() / 3600)
            last_update = f"{hours}h ago" if hours < 48 else f"{hours // 24}d ago"
        text += f"{i}. {c.nickname or c.phone} ({c.phone}) — {c.status.value}\n"
        if status_note:
            text += f"   📝 \"{status_note}\"\n"
        if last_update:
            text += f"   ⏰ Last contact: {last_update}\n"
        text += "\n"

    if len(active_clients) > 10:
        text += f"... and {len(active_clients) - 10} more\n"

    buttons = [
        [
            {'text': '✅ Accept Handoff', 'callback_data': f'handoff:accept:{handoff_id}'},
            {'text': '❌ Decline', 'callback_data': f'handoff:decline:{handoff_id}'},
        ]
    ]

    # Send accept/decline buttons to the TARGET staff, not the creator
    if to_staff_id:
        to_staff_obj = await database_v2.get_staff_by_id(to_staff_id)
        if to_staff_obj and to_staff_obj.tg_chat_id:
            await telegram_handler.send_message(to_staff_obj.tg_chat_id, text, reply_markup={'inline_keyboard': buttons})
        else:
            logger.warning(f"Could not send handoff buttons to staff {to_staff_id}: no chat_id")

    # Send confirmation (no buttons) to the creator
    await telegram_handler.send_message(chat_id, text)

    # Log timeline events for each client
    for cid in client_ids:
        try:
            await database_v2.log_event(
                cid, 'handoff_created',
                json.dumps({'from': staff.display_name, 'to': to_display, 'handoff_id': handoff_id}),
                staff.id)
        except Exception as e:
            logger.warning(f"Failed to log handoff event for client {cid}: {e}")


async def _accept_handoff(chat_id: int, staff, handoff_id: int):
    """Accept an incoming handoff."""
    handoff = await database_v2.get_handoff_by_id(handoff_id)
    if not handoff:
        await telegram_handler.send_message(chat_id, "Handoff not found.")
        return

    if handoff.status != 'pending':
        await telegram_handler.send_message(chat_id, f"Handoff already {handoff.status}.")
        return

    success = await database_v2.accept_handoff(handoff_id, staff.id)
    if success:
        from_staff = await database_v2.get_staff_by_id(handoff.from_staff_id)
        from_name = from_staff.display_name if from_staff else 'Unknown'

        # Count clients
        client_ids = json.loads(handoff.client_ids) if handoff.client_ids else []

        text = f"✅ Handoff accepted!\n"
        text += f"From: {from_name}\n"
        text += f"Clients transferred: {len(client_ids)}\n"

        await telegram_handler.send_message(chat_id, text)

        # Log timeline events
        for cid in client_ids:
            try:
                await database_v2.log_event(
                    cid, 'handoff_accepted',
                    json.dumps({'from': from_name, 'to': staff.display_name, 'handoff_id': handoff_id}),
                    staff.id)
            except Exception as e:
                logger.warning(f"Failed to log handoff accept event for client {cid}: {e}")
    else:
        await telegram_handler.send_message(chat_id, "Failed to accept handoff.")


async def _list_handoffs(chat_id: int, staff):
    """List pending handoffs for the staff's team."""
    team = staff.team
    # Get handoffs targeted to this staff OR open to any available (to_staff_id IS NULL) in the same team
    targeted = await database_v2.get_pending_handoffs(team=team, to_staff_id=staff.id)
    open_handoffs = await database_v2.get_pending_handoffs(team=team)
    # Merge: open_handoffs without to_staff_id + targeted (deduplicate by id)
    seen_ids = {h.id for h in targeted}
    handoffs = list(targeted)
    for h in open_handoffs:
        if h.to_staff_id is None and h.id not in seen_ids:
            handoffs.append(h)
            seen_ids.add(h.id)

    if not handoffs:
        await telegram_handler.send_message(chat_id, "No pending handoffs.")
        return

    text = "📋 Pending Handoffs\n" + "━" * 25 + "\n\n"
    all_buttons: list = []
    for h in handoffs:
        from_staff = await database_v2.get_staff_by_id(h.from_staff_id)
        from_name = from_staff.display_name if from_staff else 'Unknown'
        client_ids = json.loads(h.client_ids) if h.client_ids else []
        age = ''
        if h.created_at:
            delta = datetime.utcnow() - h.created_at.replace(tzinfo=None)
            hours = int(delta.total_seconds() / 3600)
            age = f" ({hours}h ago)" if hours < 48 else f" ({hours // 24}d ago)"

        to_name = 'any'
        if h.to_staff_id:
            to_staff = await database_v2.get_staff_by_id(h.to_staff_id)
            to_name = to_staff.display_name if to_staff else 'any'

        text += f"#{h.id}: {from_name} → {to_name}{age}\n"
        text += f"  Clients: {len(client_ids)}\n"

        all_buttons.append([
            {'text': f'✅ Accept #{h.id}', 'callback_data': f'handoff:accept:{h.id}'},
            {'text': f'❌ Decline #{h.id}', 'callback_data': f'handoff:decline:{h.id}'},
        ])

    await telegram_handler.send_message(chat_id, text, reply_markup={'inline_keyboard': all_buttons})


async def handle_handoff_callback(task_data: Dict[str, Any]):
    """Handle handoff inline keyboard callbacks."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    callback_data = task_data.get('callback_data', '')
    staff = await _get_staff(user_id)
    if not staff:
        return

    parts = callback_data.split(':')
    if len(parts) < 3:
        return

    action = parts[1]
    try:
        handoff_id = int(parts[2])
    except ValueError:
        return

    if action == 'accept':
        await _accept_handoff(chat_id, staff, handoff_id)
    elif action == 'decline':
        handoff = await database_v2.get_handoff_by_id(handoff_id)
        if not handoff:
            await telegram_handler.send_message(chat_id, "Handoff not found or already processed.")
            return
        # Authorization: only from_staff, to_staff, or a manager can decline
        is_authorized = (
            staff.id == handoff.from_staff_id
            or staff.id == handoff.to_staff_id
            or staff.is_manager_or_above()
        )
        if not is_authorized:
            await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
            return
        success = await database_v2.decline_handoff(handoff_id)
        if success:
            await telegram_handler.send_message(chat_id, "❌ Handoff declined.")
        else:
            await telegram_handler.send_message(chat_id, "Handoff not found or already processed.")


# ─── Handler registry ─────────────────────────────────────────────────────

HANDOFF_COMMANDS: Dict[str, Any] = {
    'handoff': handle_handoff,
}

HANDOFF_CALLBACKS: Dict[str, Any] = {
    'handoff_*': handle_handoff_callback,
}

HANDOFF_CONVERSATIONS: Dict = {}
