"""Auto-follow-up drip campaign engine."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from database_v2 import database_v2, _status_change_hooks

logger = logging.getLogger(__name__)

# ─── Default sequences ─────────────────────────────────────────────────────────

_DEFAULT_SEQUENCES = [
    {
        'name': 'new_lead',
        'stage': 'new',
        'delays': [1, 3, 7, 14],
        'templates': [
            '你好！我是你的专属客服，很高兴认识您！有任何问题随时联系我哦 😊',
            '您好，我来跟进一下，不知道您对我们的服务有什么疑问吗？',
            '您好！我们有一些非常适合您的投资机会，现在加入还有特别优惠哦！',
            '您好，这是我们最后一次跟进，如果您有兴趣欢迎随时联系我！',
        ],
    },
    {
        'name': 'contacted',
        'stage': 'contacted',
        'delays': [2, 5],
        'templates': [
            '您好！我之前联系过您，想跟进一下您的情况，有任何问题欢迎告诉我！',
            '您好，好久不见！我们最近有新的优惠活动，不知道您有没有兴趣？',
        ],
    },
    {
        'name': 'registered',
        'stage': 'registered',
        'delays': [1, 3],
        'templates': [
            '恭喜您成功注册！欢迎加入我们的大家庭！有任何问题随时找我 🎉',
            '您好！提醒您记得完成培训，培训后即可开始享受我们的服务！',
        ],
    },
]


async def seed_default_sequences():
    """Create default follow-up sequences if they don't exist (idempotent)."""
    for seq in _DEFAULT_SEQUENCES:
        try:
            await database_v2.create_sequence(
                name=seq['name'],
                stage=seq['stage'],
                delays=seq['delays'],
                templates=seq['templates'],
            )
        except Exception as e:
            logger.warning(f'seed_default_sequences: skipped {seq["name"]}: {e}')
    logger.info('Follow-up sequences seeded (idempotent)')


async def enqueue_client(client_id: int, stage: str):
    """Find a matching enabled sequence for the stage and enqueue the client."""
    try:
        # Cancel any existing pending followups for this client first
        await database_v2.cancel_followup(client_id)

        sequences = await database_v2.get_sequences(enabled_only=True)
        matching = [s for s in sequences if s['stage'] == stage]
        if not matching:
            logger.debug(f'enqueue_client: no sequence for stage={stage}')
            return

        seq = matching[0]
        delays = seq['delays']
        if not delays:
            return

        first_delay_days = delays[0]
        first_send_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=first_delay_days)

        await database_v2.enqueue_followup(
            client_id=client_id,
            sequence_id=seq['id'],
            next_send_at=first_send_at,
        )
        logger.info(f'enqueue_client: client={client_id} seq={seq["name"]} first_send={first_send_at.date()}')
    except Exception as e:
        logger.error(f'enqueue_client error (client={client_id}): {e}')


async def process_due_followups():
    """Process all due follow-up queue items. Called by the Ralph Loop every 30 min."""
    try:
        from telegram_handler import telegram_handler

        due_items = await database_v2.get_due_followups()
        if not due_items:
            return

        logger.info(f'process_due_followups: {len(due_items)} item(s) due')

        for item in due_items:
            queue_id = item['id']
            client_id = item['client_id']
            step = item['step']
            delays = item['delays']
            templates = item['templates']

            try:
                client = await database_v2.get_client_by_id(client_id)
                if not client:
                    await database_v2.complete_followup(queue_id, 'cancelled')
                    continue

                # Get frontdesk staff to send reminder to
                staff = await database_v2.get_staff_by_id(client.frontdesk_id)
                if not staff or not staff.tg_chat_id:
                    await database_v2.complete_followup(queue_id, 'cancelled')
                    continue

                # Build and send the followup reminder
                template_text = templates[step] if step < len(templates) else templates[-1]
                message = (
                    f'🔔 **跟进提醒** (第{step + 1}次)\n'
                    f'客户: {client.phone}'
                    + (f' ({client.nickname})' if client.nickname else '')
                    + f'\n状态: {client.status.value}\n\n'
                    f'📝 建议话术:\n{template_text}'
                )
                await telegram_handler.send_message(staff.tg_chat_id, message)

                # Determine next step or completion
                next_step = step + 1
                if next_step < len(delays):
                    # Advance to next step
                    next_delay_days = delays[next_step]
                    next_send_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=next_delay_days)
                    await database_v2.advance_followup_step(queue_id, next_step, next_send_at)
                    logger.info(f'followup: client={client_id} advanced to step={next_step}')
                else:
                    # Final step reached — mark completed
                    await database_v2.complete_followup(queue_id, 'completed')
                    logger.info(f'followup: client={client_id} sequence completed')

                # Ghosting check: after 3 sends with no reply/progress, mark client as ghosted
                if next_step >= 3:
                    initial_stage = item['stage']
                    if client.status.value == initial_stage:
                        from models_v2 import ClientStatus
                        try:
                            # Use a system staff id of 0 — no actual staff acted on this
                            await database_v2.update_client_status(
                                client_id, ClientStatus.GHOSTED,
                                staff_id=client.frontdesk_id,
                                note='跟进3次无回复，自动标记为已流失'
                            )
                            await database_v2.complete_followup(queue_id, 'ghosted')
                            logger.info(f'followup: client={client_id} marked ghosted after 3 no-replies')
                        except Exception as ge:
                            logger.warning(f'followup ghosting failed client={client_id}: {ge}')

            except Exception as item_err:
                logger.error(f'process_due_followups item error (queue={queue_id}): {item_err}')

    except Exception as e:
        logger.error(f'process_due_followups error: {e}')


async def _on_status_change(client_id: int, new_status: str):
    """Hook registered in _status_change_hooks — auto-enqueue when status changes."""
    try:
        await enqueue_client(client_id, new_status)
    except Exception as e:
        logger.warning(f'_on_status_change hook error: {e}')


def register_hooks():
    """Register status-change hooks. Called once at startup."""
    if _on_status_change not in _status_change_hooks:
        _status_change_hooks.append(_on_status_change)
        logger.info('followup_engine: status-change hook registered')
