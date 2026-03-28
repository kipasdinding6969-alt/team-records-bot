"""NocoDB REST API writer engine — async aiohttp, v2 internal API.

NocoDB v2 API uses field *titles* (display names), not column_names.
All translation is handled automatically via field_map in nocodb_config.json.
"""
import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'nocodb_config.json')
CHUNK_SIZE = 100


def _load_config() -> Dict[str, Any]:
    path = os.getenv('NOCODB_CONFIG', _CONFIG_PATH)
    with open(os.path.normpath(path)) as f:
        cfg = json.load(f)
    url = os.getenv('NOCODB_URL')
    token = os.getenv('NOCODB_TOKEN')
    if url:
        cfg['url'] = url.rstrip('/')
    if token:
        cfg['api_token'] = token
    cfg['url'] = cfg['url'].rstrip('/')
    return cfg


def _fmt(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return v
    return v


def _clean(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _fmt(v) for k, v in record.items() if v is not None}


class NocoDBWriter:
    """Async NocoDB v2 REST writer with automatic field name translation."""

    def __init__(self):
        cfg = _load_config()
        self._base = cfg['url']
        self._token = cfg['api_token']
        self._tables = cfg['tables']
        # field_map: {table_key: {column_name: title}}
        self._field_map: Dict[str, Dict[str, str]] = cfg.get('field_map', {})
        # reverse map: {table_key: {title: column_name}}
        self._reverse_map: Dict[str, Dict[str, str]] = {}
        for tbl, fmap in self._field_map.items():
            self._reverse_map[tbl] = {v: k for k, v in fmap.items()}
        self._session: Optional[aiohttp.ClientSession] = None

    def _to_titles(self, table_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Translate column_names → NocoDB titles for API calls."""
        fmap = self._field_map.get(table_key, {})
        out = {}
        for k, v in data.items():
            title = fmap.get(k, k)  # fallback to raw key
            out[title] = v
        return out

    def _from_titles(self, table_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Translate NocoDB titles → column_names for internal use."""
        rmap = self._reverse_map.get(table_key, {})
        out = {}
        for k, v in data.items():
            col = rmap.get(k, k)
            out[col] = v
        return out

    def _title(self, table_key: str, col: str) -> str:
        """Get the NocoDB title for a column_name."""
        return self._field_map.get(table_key, {}).get(col, col)

    # ── session ──

    async def __aenter__(self):
        await self._open()
        return self

    async def __aexit__(self, *_):
        await self._close()

    async def _open(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={'xc-token': self._token, 'Content-Type': 'application/json'},
            )

    async def _close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def _s(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError('Not opened — use async with')
        return self._session

    def _url(self, table_key: str) -> str:
        return f"{self._base}/api/v2/tables/{self._tables[table_key]}/records"

    # ── low-level CRUD ──

    async def _list(self, table_key: str, where: str = '',
                    limit: int = 100) -> List[Dict[str, Any]]:
        s = self._s()
        url = self._url(table_key)
        results = []
        offset = 0
        while True:
            params: Dict[str, Any] = {'limit': limit, 'offset': offset}
            if where:
                params['where'] = where
            async with s.get(url, params=params) as r:
                if r.status == 422:
                    body = await r.text()
                    logger.error('List %s failed: %s where=%s', table_key, body, where)
                    return []
                r.raise_for_status()
                body = await r.json()
            rows = body.get('list', [])
            results.extend(rows)
            if body.get('pageInfo', {}).get('isLastPage', True) or len(rows) < limit:
                break
            offset += limit
        return results

    async def _create(self, table_key: str, records: List[Dict[str, Any]]) -> List[Dict]:
        s = self._s()
        url = self._url(table_key)
        created = []
        for i in range(0, len(records), CHUNK_SIZE):
            chunk = [_clean(self._to_titles(table_key, r)) for r in records[i:i + CHUNK_SIZE]]
            payload = chunk if len(chunk) > 1 else chunk[0]
            async with s.post(url, json=payload) as r:
                if r.status >= 400:
                    err = await r.text()
                    logger.error('Create %s failed: %s payload=%s', table_key, err, str(payload)[:200])
                    continue
                body = await r.json()
            created.extend(body if isinstance(body, list) else [body])
        return created

    async def _update(self, table_key: str, records: List[Dict[str, Any]]) -> None:
        s = self._s()
        url = self._url(table_key)
        for i in range(0, len(records), CHUNK_SIZE):
            chunk = []
            for r in records[i:i + CHUNK_SIZE]:
                translated = _clean(self._to_titles(table_key, r))
                # Ensure Id is always present for updates
                if 'Id' not in translated and 'id' in r:
                    translated['Id'] = r['id']
                chunk.append(translated)
            payload = chunk if len(chunk) > 1 else chunk[0]
            async with s.patch(url, json=payload) as r:
                if r.status >= 400:
                    err = await r.text()
                    logger.error('Update %s failed: %s', table_key, err)

    async def _upsert(self, table_key: str, where: str,
                      data: Dict[str, Any]) -> Dict:
        existing = await self._list(table_key, where)
        if existing:
            row = existing[0]
            titled = _clean(self._to_titles(table_key, data))
            titled['Id'] = row['Id']
            await self._update(table_key, [data | {'id': row['Id']}])
            logger.debug('updated %s Id=%s', table_key, row['Id'])
            return {**row, **titled}
        created = await self._create(table_key, [data])
        logger.debug('created %s', table_key)
        return created[0] if created else {}

    # ── public API ──

    async def upsert_staff(self, data: Dict[str, Any]) -> Dict:
        tg_id = data.get('tg_user_id', data.get('Telegram ID'))
        title = self._title('staff', 'tg_user_id')
        return await self._upsert('staff', f'({title},eq,{tg_id})', data)

    async def upsert_client(self, data: Dict[str, Any]) -> Dict:
        phone = data.get('phone', data.get('Phone'))
        title = self._title('clients', 'phone')
        return await self._upsert('clients', f'({title},eq,{phone})', data)

    async def add_note(self, data: Dict[str, Any]) -> Dict:
        created = await self._create('client_notes', [data])
        return created[0] if created else {}

    async def upsert_daily_stat(self, data: Dict[str, Any]) -> Dict:
        dt = data.get('date', data.get('Date', ''))
        tg_id = data.get('frontdesk_tg_id', data.get('Frontdesk TG ID', 0))
        t_date = self._title('daily_stats', 'date')
        t_tgid = self._title('daily_stats', 'frontdesk_tg_id')
        where = f'({t_date},eq,{dt})~and({t_tgid},eq,{tg_id})'
        return await self._upsert('daily_stats', where, data)

    async def add_deposit(self, data: Dict[str, Any]) -> Dict:
        created = await self._create('deposits', [data])
        return created[0] if created else {}

    async def upsert_reminder(self, data: Dict[str, Any]) -> Dict:
        if 'sqlite_id' in data:
            sid = data.pop('sqlite_id')
            # Try match by staff + client + time
            staff_tg = data.get('staff_tg_id', 0)
            t_staff = self._title('reminders', 'staff_tg_id')
            where = f'({t_staff},eq,{staff_tg})'
            return await self._upsert('reminders', where, data)
        created = await self._create('reminders', [data])
        return created[0] if created else {}

    async def set_team_target(self, data: Dict[str, Any]) -> Dict:
        month = data.get('month', data.get('Month', ''))
        team = data.get('team', data.get('Team', ''))
        t_month = self._title('team_targets', 'month')
        t_team = self._title('team_targets', 'team')
        where = f'({t_month},eq,{month})~and({t_team},eq,{team})'
        return await self._upsert('team_targets', where, data)

    async def get_clients(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        if not filters:
            rows = await self._list('clients')
        else:
            parts = []
            for k, v in filters.items():
                title = self._title('clients', k)
                parts.append(f'({title},eq,{v})')
            where = '~and'.join(parts)
            rows = await self._list('clients', where)
        return [self._from_titles('clients', r) for r in rows]

    async def get_pipeline_stats(self) -> Dict[str, int]:
        all_clients = await self._list('clients')
        title = self._title('clients', 'status')
        counts: Dict[str, int] = {}
        for row in all_clients:
            status = row.get(title, 'unknown')
            counts[status] = counts.get(status, 0) + 1
        return counts

    # ── SQLite migration ──

    async def full_sync_from_sqlite(self, db_path: str) -> Dict[str, int]:
        """Bulk migrate all V2 SQLite data → NocoDB."""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        counts: Dict[str, int] = {}

        # Staff
        rows = conn.execute('SELECT * FROM staff').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            await self.upsert_staff(d)
        counts['staff'] = len(rows)

        # Clients
        rows = conn.execute('SELECT * FROM clients').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            d.pop('sheet_row', None)
            d.pop('embedding_id', None)
            await self.upsert_client(d)
        counts['clients'] = len(rows)

        # Client Notes
        rows = conn.execute('SELECT * FROM client_notes').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            await self.add_note(d)
        counts['client_notes'] = len(rows)

        # Daily Stats
        rows = conn.execute('SELECT * FROM daily_stats').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            await self.upsert_daily_stat(d)
        counts['daily_stats'] = len(rows)

        # Deposits
        rows = conn.execute('SELECT * FROM deposits').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            await self.add_deposit(d)
        counts['deposits'] = len(rows)

        # Reminders
        rows = conn.execute('SELECT * FROM reminders').fetchall()
        for row in rows:
            d = dict(row)
            sid = d.pop('id', None)
            d['sqlite_id'] = sid
            await self.upsert_reminder(d)
        counts['reminders'] = len(rows)

        # Team Targets
        rows = conn.execute('SELECT * FROM team_targets').fetchall()
        for row in rows:
            d = dict(row)
            d.pop('id', None)
            await self.set_team_target(d)
        counts['team_targets'] = len(rows)

        conn.close()
        logger.info('SQLite sync complete: %s', counts)
        return counts


# ── CLI ──

async def _main():
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

    parser = argparse.ArgumentParser(description='NocoDB writer CLI')
    parser.add_argument('--sync', metavar='DB_PATH', nargs='?',
                        const='team_records_v2.db',
                        help='Full SQLite → NocoDB migration')
    parser.add_argument('--stats', action='store_true', help='Print pipeline stats')
    args = parser.parse_args()

    async with NocoDBWriter() as writer:
        if args.sync:
            print(f'Syncing {args.sync} → NocoDB…')
            counts = await writer.full_sync_from_sqlite(args.sync)
            for table, n in counts.items():
                print(f'  {table}: {n}')
            print('✅ Done.')
        elif args.stats:
            stats = await writer.get_pipeline_stats()
            for status, count in stats.items():
                print(f'  {status}: {count}')
        else:
            parser.print_help()


if __name__ == '__main__':
    asyncio.run(_main())
