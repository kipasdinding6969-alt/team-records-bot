"""Tests for Phase 9A: Smart Tags & Filters."""
import pytest
import pytest_asyncio

from database_v2 import DatabaseV2
from models_v2 import Staff, StaffRole, Client, ClientStatus


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(tmp_path):
    d = DatabaseV2(str(tmp_path / 'test_tags.db'))
    await d.initialize()
    await d.connect()
    return d


@pytest_asyncio.fixture
async def staff(db):
    s = Staff(
        tg_user_id=7001, tg_chat_id=6001, tg_username='tagstaff',
        display_name='标签员工', role=StaffRole.FRONTDESK,
        team='阿俊', language='zh', is_active=True,
    )
    s.id = await db.create_staff(s)
    return s


@pytest_asyncio.fixture
async def client(db, staff):
    c = Client(
        frontdesk_id=staff.id, phone='0100000001', source='facebook',
        status=ClientStatus.NEW, nickname='测试客户',
    )
    c.id = await db.create_client(c)
    return c


@pytest_asyncio.fixture
async def client2(db, staff):
    c = Client(
        frontdesk_id=staff.id, phone='0100000002', source='instagram',
        status=ClientStatus.REPLIED, nickname='第二客户',
    )
    c.id = await db.create_client(c)
    return c


# ─── add_tag ──────────────────────────────────────────────────────────────────

class TestAddTag:
    @pytest.mark.asyncio
    async def test_add_tag_returns_true(self, db, client, staff):
        result = await db.add_tag(client.id, 'vip', staff.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_add_duplicate_tag_returns_false(self, db, client, staff):
        await db.add_tag(client.id, 'vip', staff.id)
        result = await db.add_tag(client.id, 'vip', staff.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_add_multiple_tags(self, db, client, staff):
        await db.add_tag(client.id, 'vip', staff.id)
        await db.add_tag(client.id, 'whale', staff.id)
        await db.add_tag(client.id, 'hot', staff.id)
        tags = await db.get_client_tags(client.id)
        assert set(tags) == {'vip', 'whale', 'hot'}

    @pytest.mark.asyncio
    async def test_tag_is_lowercased(self, db, client, staff):
        await db.add_tag(client.id, 'VIP', staff.id)
        tags = await db.get_client_tags(client.id)
        assert 'vip' in tags


# ─── remove_tag ───────────────────────────────────────────────────────────────

class TestRemoveTag:
    @pytest.mark.asyncio
    async def test_remove_existing_tag(self, db, client, staff):
        await db.add_tag(client.id, 'whale', staff.id)
        result = await db.remove_tag(client.id, 'whale')
        assert result is True
        tags = await db.get_client_tags(client.id)
        assert 'whale' not in tags

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tag_returns_false(self, db, client, staff):
        result = await db.remove_tag(client.id, 'ghost')
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_only_one_tag(self, db, client, staff):
        await db.add_tag(client.id, 'vip', staff.id)
        await db.add_tag(client.id, 'hot', staff.id)
        await db.remove_tag(client.id, 'vip')
        tags = await db.get_client_tags(client.id)
        assert tags == ['hot']


# ─── get_client_tags ──────────────────────────────────────────────────────────

class TestGetClientTags:
    @pytest.mark.asyncio
    async def test_no_tags_returns_empty_list(self, db, client):
        tags = await db.get_client_tags(client.id)
        assert tags == []

    @pytest.mark.asyncio
    async def test_returns_tags_in_insertion_order(self, db, client, staff):
        for tag in ['referral', 'vip', 'hot']:
            await db.add_tag(client.id, tag, staff.id)
        tags = await db.get_client_tags(client.id)
        assert tags == ['referral', 'vip', 'hot']


# ─── get_all_tags_with_counts ──────────────────────────────────────────────────

class TestGetAllTagsWithCounts:
    @pytest.mark.asyncio
    async def test_counts_across_clients(self, db, client, client2, staff):
        await db.add_tag(client.id, 'vip', staff.id)
        await db.add_tag(client2.id, 'vip', staff.id)
        await db.add_tag(client.id, 'whale', staff.id)
        results = await db.get_all_tags_with_counts()
        tag_map = {r['tag']: r['count'] for r in results}
        assert tag_map['vip'] == 2
        assert tag_map['whale'] == 1

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self, db):
        results = await db.get_all_tags_with_counts()
        assert results == []


# ─── filter_clients_by_criteria ───────────────────────────────────────────────

class TestFilterClientsByCriteria:
    @pytest.mark.asyncio
    async def test_filter_by_tag(self, db, client, client2, staff):
        await db.add_tag(client.id, 'vip', staff.id)
        results = await db.filter_clients_by_criteria(staff.id, None, {'tag': 'vip'})
        assert len(results) == 1
        assert results[0]['phone'] == client.phone

    @pytest.mark.asyncio
    async def test_filter_by_status(self, db, client, client2, staff):
        results = await db.filter_clients_by_criteria(staff.id, None, {'status': 'replied'})
        phones = [r['phone'] for r in results]
        assert client2.phone in phones
        assert client.phone not in phones

    @pytest.mark.asyncio
    async def test_filter_by_source(self, db, client, client2, staff):
        results = await db.filter_clients_by_criteria(staff.id, None, {'source': 'facebook'})
        assert any(r['phone'] == client.phone for r in results)

    @pytest.mark.asyncio
    async def test_filter_no_criteria_returns_all(self, db, client, client2, staff):
        results = await db.filter_clients_by_criteria(staff.id, None, {})
        assert len(results) >= 2
