"""Obsidian REST API client — second brain integration for the team records bot."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = 'http://localhost:27123'
API_KEY = '7f7fd125d3f3ab9b8741cdc98f1c33287e2362d24edff98447631d4ad101d10d'
_HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
}


class ObsidianBrain:
    """Async Obsidian REST API client. All failures are non-fatal (logged as warnings)."""

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        try:
            async with aiohttp.ClientSession(headers=_HEADERS) as session:
                async with session.get(
                    f'{BASE_URL}{path}',
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        ct = resp.headers.get('content-type', '')
                        if 'json' in ct:
                            return await resp.json()
                        return await resp.text()
                    logger.warning(f'Obsidian GET {path} → {resp.status}')
                    return None
        except Exception as e:
            logger.warning(f'Obsidian GET {path} failed: {e}')
            return None

    async def _put(self, path: str, content: str) -> bool:
        try:
            async with aiohttp.ClientSession(headers={**_HEADERS, 'Content-Type': 'text/markdown'}) as session:
                async with session.put(
                    f'{BASE_URL}{path}',
                    data=content.encode('utf-8'),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        return True
                    logger.warning(f'Obsidian PUT {path} → {resp.status}')
                    return False
        except Exception as e:
            logger.warning(f'Obsidian PUT {path} failed: {e}')
            return False

    async def _post(self, path: str, content: str) -> bool:
        try:
            async with aiohttp.ClientSession(headers={**_HEADERS, 'Content-Type': 'text/markdown'}) as session:
                async with session.post(
                    f'{BASE_URL}{path}',
                    data=content.encode('utf-8'),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        return True
                    logger.warning(f'Obsidian POST {path} → {resp.status}')
                    return False
        except Exception as e:
            logger.warning(f'Obsidian POST {path} failed: {e}')
            return False

    async def list_files(self, path: str = '/') -> List[str]:
        """List files in vault directory. Returns list of file paths."""
        norm = path.rstrip('/')
        result = await self._get(f'/vault/{norm}/', {'list': 'true'})
        if result is None:
            return []
        if isinstance(result, dict):
            return result.get('files', [])
        return []

    async def read_note(self, path: str) -> str:
        """Read note content as markdown string."""
        result = await self._get(f'/vault/{path}', None)
        if result is None:
            return ''
        return str(result)

    async def write_note(self, path: str, content: str) -> bool:
        """Write/overwrite note at path."""
        return await self._put(f'/vault/{path}', content)

    async def append_note(self, path: str, content: str) -> bool:
        """Append content to existing note."""
        return await self._post(f'/vault/{path}', content)

    async def search(self, query: str) -> List[Dict]:
        """Simple text search in vault."""
        try:
            async with aiohttp.ClientSession(headers=_HEADERS) as session:
                async with session.get(
                    f'{BASE_URL}/search/simple/',
                    params={'query': query},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data if isinstance(data, list) else []
                    return []
        except Exception as e:
            logger.warning(f'Obsidian search failed: {e}')
            return []

    # ── High-level operations ─────────────────────────────────────────────────

    async def log_client_interaction(self, client_phone: str, frontdesk: str, interaction: str):
        """Append interaction log to workspace/clients/<phone>.md"""
        from datetime import datetime
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        line = f'\n## {ts} — {frontdesk}\n{interaction}\n'
        path = f'workspace/clients/{client_phone}.md'
        ok = await self.append_note(path, line)
        if not ok:
            # Create file if append fails
            header = f'# Client: {client_phone}\n'
            await self.write_note(path, header + line)

    async def get_sop(self, topic: str) -> str:
        """Search docs/ and workspace/ for SOP content matching topic."""
        results = await self.search(topic)
        if not results:
            return ''
        texts = []
        for r in results[:3]:
            file_path = r.get('filename', '')
            if file_path:
                content = await self.read_note(file_path)
                if content:
                    texts.append(f'**{file_path}**\n{content[:500]}')
        return '\n\n---\n\n'.join(texts)

    async def save_daily_report(self, date_str: str, report_text: str) -> bool:
        """Save daily team report to memory/reports/YYYY-MM-DD.md"""
        path = f'memory/reports/{date_str}.md'
        content = f'# Daily Report — {date_str}\n\n{report_text}\n'
        return await self.write_note(path, content)

    async def get_training_material(self, keyword: str) -> str:
        """Search docs/ for training content."""
        results = await self.search(keyword)
        if not results:
            return ''
        texts = []
        for r in results[:2]:
            file_path = r.get('filename', '')
            if file_path and ('docs/' in file_path or 'workspace/' in file_path):
                content = await self.read_note(file_path)
                if content:
                    texts.append(f'**{file_path}**\n{content[:800]}')
        return '\n\n---\n\n'.join(texts)

    async def log_handoff(self, date_str: str, frontdesk: str, maintenance: str,
                           phone: str, status: str, note: str):
        """Append handoff record to workspace/handoffs/YYYY-MM-DD.md"""
        from datetime import datetime
        ts = datetime.now().strftime('%H:%M')
        line = f'\n- [{ts}] {frontdesk} → {maintenance}: {phone} ({status}) — {note or "no note"}\n'
        path = f'workspace/handoffs/{date_str}.md'
        ok = await self.append_note(path, line)
        if not ok:
            header = f'# Handoffs — {date_str}\n'
            await self.write_note(path, header + line)


# Global singleton
obsidian_brain = ObsidianBrain()
