"""Follow-up sequence management handlers — /sequences."""
import logging
from typing import Any, Dict

from database_v2 import database_v2
from i18n import t
from telegram_handler import telegram_handler
from handlers_v2 import get_staff as _get_staff

logger = logging.getLogger(__name__)


async def handle_sequences(task_data: Dict[str, Any]):
    """/sequences [enable <id> | disable <id>] — list or toggle follow-up sequences."""
    chat_id = task_data.get('chat_id')
    user_id = task_data.get('user_id')
    args = task_data.get('args', '').strip()

    staff = await _get_staff(user_id)
    if not staff:
        await telegram_handler.send_message(chat_id, t('err_not_registered', 'zh'))
        return

    from engines.policy_engine import check_permission
    if not check_permission(staff.role.value, 'sequences'):
        await telegram_handler.send_message(chat_id, t('err_permission_denied', staff.language))
        return

    lang = staff.language
    parts = args.split()

    # Toggle: /sequences enable <id> | disable <id>
    if len(parts) == 2 and parts[0] in ('enable', 'disable'):
        action = parts[0]
        try:
            seq_id = int(parts[1])
        except ValueError:
            await telegram_handler.send_message(chat_id, t('followup_invalid_id', lang))
            return

        enabled = action == 'enable'
        ok = await database_v2.toggle_sequence(seq_id, enabled)
        if ok:
            state = t('followup_enabled', lang) if enabled else t('followup_disabled', lang)
            await telegram_handler.send_message(
                chat_id, t('followup_toggle_ok', lang, seq_id=seq_id, state=state))
        else:
            await telegram_handler.send_message(chat_id, t('followup_seq_not_found', lang))
        return

    # List all sequences
    sequences = await database_v2.get_sequences()
    if not sequences:
        await telegram_handler.send_message(chat_id, t('followup_no_sequences', lang))
        return

    lines = [t('followup_sequences_title', lang), '']
    for seq in sequences:
        status_icon = '✅' if seq['enabled'] else '❌'
        delays_str = ', '.join(f'D{d}' for d in seq['delays'])
        steps = len(seq['templates'])
        lines.append(
            f'{status_icon} **#{seq["id"]}** `{seq["name"]}`\n'
            f'   阶段: {seq["stage"]} | 步骤: {steps} | 延迟: {delays_str}'
        )

    lines.append('')
    lines.append(t('followup_toggle_hint', lang))
    await telegram_handler.send_message(chat_id, '\n'.join(lines))


# ─── Handler registries ────────────────────────────────────────────────────────

FOLLOWUP_HANDLER_COMMANDS: Dict[str, Any] = {
    'sequences': handle_sequences,
}

FOLLOWUP_HANDLER_CALLBACKS: Dict[str, Any] = {}

FOLLOWUP_HANDLER_CONVERSATIONS: Dict[str, Any] = {}
