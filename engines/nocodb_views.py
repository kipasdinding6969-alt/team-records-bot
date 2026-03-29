"""NocoDB shared views engine — creates and retrieves shared public view links.

Uses the NocoDB v2 REST API to:
  1. Create views (gallery/grid) on specified tables
  2. Enable shared access and return public URLs

Usage:
    urls = await create_shared_views(base_url, api_token, table_ids)
    # Returns {'pipeline_dashboard': 'https://...', 'deposits_tracker': '...', 'team_scoreboard': '...'}
"""
import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


# View definitions — (view_key, title, table_key, view_type, sort_field, sort_dir, group_field)
VIEW_SPECS = [
    {
        'key': 'pipeline_dashboard',
        'title': 'Pipeline Dashboard',
        'table_key': 'clients',
        'type': 'grid',
        'group_by': 'status',
    },
    {
        'key': 'deposits_tracker',
        'title': 'Deposits Tracker',
        'table_key': 'deposits',
        'type': 'grid',
        'sort_by': 'deposit_date',
        'sort_dir': 'desc',
    },
    {
        'key': 'team_scoreboard',
        'title': 'Team Scoreboard',
        'table_key': 'daily_stats',
        'type': 'grid',
        'group_by': 'frontdesk_name',
    },
]


async def _create_view(
    session: aiohttp.ClientSession,
    base_url: str,
    api_token: str,
    table_id: str,
    title: str,
    view_type: str = 'grid',
) -> Optional[str]:
    """Create a view on a table. Returns the new view ID or None on failure."""
    headers = {'xc-auth': api_token, 'Content-Type': 'application/json'}
    payload = {'title': title, 'type': view_type.upper()}
    url = f'{base_url}/api/v1/db/meta/projects/tables/{table_id}/views'
    try:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                return data.get('id')
            body = await resp.text()
            logger.warning(f'nocodb_views: create view failed {resp.status}: {body[:200]}')
            return None
    except Exception as exc:
        logger.error(f'nocodb_views: create_view error: {exc}')
        return None


async def _enable_shared_view(
    session: aiohttp.ClientSession,
    base_url: str,
    api_token: str,
    view_id: str,
) -> Optional[str]:
    """Enable shared access for a view. Returns the public UUID or None."""
    headers = {'xc-auth': api_token, 'Content-Type': 'application/json'}
    url = f'{base_url}/api/v1/db/meta/views/{view_id}/share'
    try:
        async with session.post(url, headers=headers) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                return data.get('uuid') or data.get('id')
            body = await resp.text()
            logger.warning(f'nocodb_views: share view failed {resp.status}: {body[:200]}')
            return None
    except Exception as exc:
        logger.error(f'nocodb_views: share_view error: {exc}')
        return None


async def create_shared_views(
    base_url: str,
    api_token: str,
    table_ids: Dict[str, str],
) -> Dict[str, str]:
    """Create shared views for pipeline dashboard, deposits, and team scoreboard.

    Args:
        base_url:  NocoDB base URL, e.g. 'https://app.nocodb.com'
        api_token: NocoDB API token
        table_ids: mapping of table_key → NocoDB table ID
                   e.g. {'clients': 'md_xxx', 'deposits': 'md_yyy', 'daily_stats': 'md_zzz'}

    Returns:
        dict of view_key → public share URL
    """
    base_url = base_url.rstrip('/')
    result: Dict[str, str] = {}

    async with aiohttp.ClientSession() as session:
        for spec in VIEW_SPECS:
            table_key = spec['table_key']
            table_id = table_ids.get(table_key)
            if not table_id:
                logger.warning(f'nocodb_views: no table_id for {table_key}, skipping')
                continue

            view_id = await _create_view(
                session, base_url, api_token, table_id,
                spec['title'], spec.get('type', 'grid'))

            if not view_id:
                continue

            share_uuid = await _enable_shared_view(session, base_url, api_token, view_id)
            if share_uuid:
                share_url = f'{base_url}/nc/v/{share_uuid}'
                result[spec['key']] = share_url
                logger.info(f'nocodb_views: {spec["key"]} → {share_url}')

    return result


async def get_existing_shared_views(
    base_url: str,
    api_token: str,
    table_ids: Dict[str, str],
) -> Dict[str, Any]:
    """List existing views for the given tables, keyed by table_key."""
    base_url = base_url.rstrip('/')
    result: Dict[str, Any] = {}
    headers = {'xc-auth': api_token}

    async with aiohttp.ClientSession() as session:
        for table_key, table_id in table_ids.items():
            url = f'{base_url}/api/v1/db/meta/projects/tables/{table_id}/views'
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result[table_key] = data.get('list', [])
            except Exception as exc:
                logger.error(f'nocodb_views: list views for {table_key}: {exc}')

    return result
