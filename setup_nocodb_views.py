#!/usr/bin/env python3
"""CLI: Create NocoDB shared views for pipeline dashboard, deposits tracker, team scoreboard.

Usage:
    python setup_nocodb_views.py

Environment variables required:
    NOCODB_URL         — NocoDB base URL, e.g. https://app.nocodb.com
    NOCODB_API_TOKEN   — API token with project write access
    NOCODB_TABLE_CLIENTS   — table ID for clients table
    NOCODB_TABLE_DEPOSITS  — table ID for deposits table
    NOCODB_TABLE_STATS     — table ID for daily_stats table
"""
import asyncio
import json
import os
import sys


async def main():
    base_url = os.getenv('NOCODB_URL', '').rstrip('/')
    api_token = os.getenv('NOCODB_API_TOKEN') or os.getenv('NOCODB_TOKEN', '')

    if not base_url or not api_token:
        print('ERROR: NOCODB_URL and NOCODB_API_TOKEN must be set', file=sys.stderr)
        sys.exit(1)

    table_ids = {
        'clients':    os.getenv('NOCODB_TABLE_CLIENTS', ''),
        'deposits':   os.getenv('NOCODB_TABLE_DEPOSITS', ''),
        'daily_stats': os.getenv('NOCODB_TABLE_STATS', ''),
    }

    missing = [k for k, v in table_ids.items() if not v]
    if missing:
        print(f'WARNING: table IDs missing for: {missing}', file=sys.stderr)
        table_ids = {k: v for k, v in table_ids.items() if v}

    if not table_ids:
        print('ERROR: no table IDs configured', file=sys.stderr)
        sys.exit(1)

    from engines.nocodb_views import create_shared_views
    print(f'Creating shared views on {base_url} ...')
    urls = await create_shared_views(base_url, api_token, table_ids)

    if not urls:
        print('No views were created. Check logs for errors.')
        sys.exit(1)

    print('\nShared view URLs:')
    for key, url in urls.items():
        print(f'  {key}: {url}')

    out_file = 'nocodb_views.json'
    with open(out_file, 'w') as f:
        json.dump(urls, f, indent=2)
    print(f'\nSaved to {out_file}')


if __name__ == '__main__':
    asyncio.run(main())
