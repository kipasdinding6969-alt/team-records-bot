"""NocoDB webhook sync — aiohttp web server that receives NocoDB change events
and upserts records into the local SQLite database.

Environment variables:
  NOCODB_WEBHOOK_PORT   — port to listen on (default 8765)
  NOCODB_WEBHOOK_SECRET — HMAC-SHA256 secret for signature validation
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

WEBHOOK_PORT = int(os.getenv('NOCODB_WEBHOOK_PORT', '8765'))
WEBHOOK_SECRET = os.getenv('NOCODB_WEBHOOK_SECRET', '')

# Module-level reference to allow mocking in tests
from database_v2 import database_v2

# aiohttp is imported lazily so tests can mock without the server running
_server_task: Optional[asyncio.Task] = None


def _verify_hmac(body: bytes, signature: str) -> bool:
    """Validate HMAC-SHA256 signature from NocoDB webhook header."""
    if not WEBHOOK_SECRET:
        return True  # no secret configured → skip validation
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lstrip('sha256='))


def _parse_event(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract table name, operation, and row data from NocoDB webhook payload.

    NocoDB v2 webhook shape (simplified):
    {
      "type": "records.update" | "records.insert" | "records.delete",
      "data": {
        "table_name": "clients",
        "rows": [{ ...row fields... }]
      }
    }
    """
    event_type = payload.get('type', '')
    data = payload.get('data', {})
    table_name = data.get('table_name', data.get('tableName', ''))
    rows = data.get('rows', data.get('record', []))

    if isinstance(rows, dict):
        rows = [rows]

    if event_type.endswith('.delete'):
        op = 'delete'
    elif event_type.endswith('.insert') or event_type.endswith('.create'):
        op = 'insert'
    else:
        op = 'update'

    return {
        'table': table_name.lower(),
        'op': op,
        'rows': rows,
    }


async def _upsert_client(row: Dict[str, Any]):
    """Upsert a client row from NocoDB into local SQLite."""
    from models_v2 import Client, ClientStatus

    phone = row.get('phone') or row.get('Phone')
    if not phone:
        logger.warning('nocodb_webhook: client row missing phone, skipping')
        return

    # Compare timestamps — only update if NocoDB record is newer
    nocodb_updated = row.get('updated_at') or row.get('UpdatedAt')
    existing = await database_v2.get_client_by_phone(phone)
    if existing and nocodb_updated and existing.updated_at:
        try:
            nc_dt = datetime.fromisoformat(nocodb_updated.replace('Z', '+00:00'))
            if existing.updated_at.timestamp() >= nc_dt.timestamp():
                logger.debug(f'nocodb_webhook: client {phone} local is newer, skipping')
                return
        except (ValueError, AttributeError):
            pass

    status_str = row.get('status') or row.get('Status') or 'new'
    try:
        status = ClientStatus(status_str.lower())
    except ValueError:
        status = ClientStatus.NEW

    frontdesk_id = row.get('frontdesk_id') or row.get('FrontdeskId')
    if not frontdesk_id:
        logger.warning(f'nocodb_webhook: client {phone} missing frontdesk_id, skipping')
        return

    if existing:
        existing.status = status
        existing.status_note = row.get('status_note') or row.get('StatusNote') or existing.status_note
        existing.nickname = row.get('nickname') or row.get('Nickname') or existing.nickname
        await database_v2.update_client_status(existing.id, status, frontdesk_id)
        logger.info(f'nocodb_webhook: updated client {phone} → {status.value}')
    else:
        source = row.get('source') or row.get('Source') or 'nocodb'
        client = Client(
            frontdesk_id=int(frontdesk_id),
            phone=phone,
            source=source,
            status=status,
            nickname=row.get('nickname') or row.get('Nickname'),
        )
        await database_v2.create_client(client)
        logger.info(f'nocodb_webhook: inserted client {phone}')


async def _upsert_staff(row: Dict[str, Any]):
    """Upsert a staff row from NocoDB into local SQLite."""
    from models_v2 import Staff, StaffRole

    tg_user_id = row.get('tg_user_id') or row.get('TgUserId')
    if not tg_user_id:
        return

    role_str = row.get('role') or row.get('Role') or 'frontdesk'
    try:
        role = StaffRole(role_str.lower())
    except ValueError:
        role = StaffRole.FRONTDESK

    existing = await database_v2.get_staff_by_tg_id(int(tg_user_id))
    if existing:
        existing.role = role
        existing.display_name = row.get('display_name') or row.get('DisplayName') or existing.display_name
        existing.team = row.get('team') or row.get('Team') or existing.team
        await database_v2.update_staff(existing)
        logger.info(f'nocodb_webhook: updated staff tg_id={tg_user_id}')
    else:
        staff = Staff(
            tg_user_id=int(tg_user_id),
            tg_chat_id=int(tg_user_id),
            display_name=row.get('display_name') or row.get('DisplayName') or str(tg_user_id),
            role=role,
        )
        await database_v2.create_staff(staff)
        logger.info(f'nocodb_webhook: inserted staff tg_id={tg_user_id}')


async def process_webhook_event(event: Dict[str, Any]):
    """Dispatch parsed event to the correct upsert handler."""
    table = event.get('table', '')
    op = event.get('op', 'update')
    rows = event.get('rows', [])

    for row in rows:
        try:
            if 'client' in table:
                if op != 'delete':
                    await _upsert_client(row)
            elif 'staff' in table:
                if op != 'delete':
                    await _upsert_staff(row)
            else:
                logger.debug(f'nocodb_webhook: unhandled table {table}')
        except Exception as exc:
            logger.error(f'nocodb_webhook: error processing row in {table}: {exc}')


async def _handle_webhook(request):
    """aiohttp request handler for POST /webhook/nocodb."""
    import aiohttp.web as web

    body = await request.read()
    sig = request.headers.get('x-nocodb-signature', '')

    if not _verify_hmac(body, sig):
        logger.warning('nocodb_webhook: invalid HMAC signature')
        return web.Response(status=401, text='Invalid signature')

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error(f'nocodb_webhook: bad JSON: {exc}')
        return web.Response(status=400, text='Bad JSON')

    logger.info(f'nocodb_webhook: received event type={payload.get("type", "?")}')
    event = _parse_event(payload)
    if event:
        asyncio.create_task(process_webhook_event(event))

    return web.Response(status=200, text='ok')


async def start_webhook_server():
    """Start the aiohttp webhook server in the background."""
    import aiohttp.web as web

    app = web.Application()
    app.router.add_post('/webhook/nocodb', _handle_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', WEBHOOK_PORT)
    await site.start()
    logger.info(f'NocoDB webhook server started on port {WEBHOOK_PORT}')
    return runner
