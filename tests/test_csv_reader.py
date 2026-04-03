"""Tests for engines/csv_reader.py — CSV parsing for Google Sheets data."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engines.csv_reader import (
    parse_client_csv,
    parse_financial_csv,
    parse_performance_csv,
    parse_daily_summary_csv,
    fetch_sheet_csv,
    sync_all_sheets,
)


# ── parse_client_csv ─────────────────────────────────────────────────────────

class TestParseClientCsv:

    def test_basic_parsing(self):
        csv_text = (
            "Row,Date,Phone,FD,Cat,Recruiter,FD#,FD@,Client#,AccID,Day1,Day2,Condition\n"
            "Row,日期,手机,前台,分类,推荐人,前台号,前台用户名,客户号,账户ID,首日,次日,情况\n"
            "1,3月15日,65 IPHONE,阿YIM,飞机筛选,小王,+86123,@test,+86999,ACC123,注册,注册,培训中\n"
        )
        records = parse_client_csv(csv_text)
        assert len(records) == 1
        r = records[0]
        assert r['date'] == '3月15日'
        assert r['frontdesk'] == '阿YIM'
        assert r['client_number'] == '+86999'

    def test_skip_header_rows(self):
        csv_text = "Header1\nHeader2\n"
        records = parse_client_csv(csv_text)
        assert records == []

    def test_skip_template_date(self):
        csv_text = (
            "Row,Date,Phone,FD,Cat,Recruiter,FD#,FD@,Client#,AccID,Day1,Day2,Condition\n"
            "Chinese header row here\n"
            "1,X月X日,phone,fd,cat,rec,num,user,cnum,aid,d1,d2,cond\n"
        )
        records = parse_client_csv(csv_text)
        assert len(records) == 0

    def test_skip_short_rows(self):
        csv_text = (
            "Header\nHeader2\n"
            "too,short\n"
        )
        records = parse_client_csv(csv_text)
        assert records == []

    def test_skip_empty_date(self):
        csv_text = (
            "h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13\n"
            "h1,h2,h3,h4,h5,h6,h7,h8,h9,h10,h11,h12,h13\n"
            "1,,phone,fd,cat,rec,num,user,cnum,aid,d1,d2,cond\n"
        )
        records = parse_client_csv(csv_text)
        assert records == []

    def test_dual_block_parsing(self):
        """Test parsing of block 2 (columns O-AA)."""
        header = ','.join(['h'] * 27)
        header2 = ','.join(['h'] * 27)
        # Block 1 (cols 0-12) + col 13 separator + Block 2 (cols 14-26)
        data = '1,3月1日,p,fd,c,r,n,u,cn,ai,d1,d2,co,sep,2,4月1日,p2,fd2,c2,r2,n2,u2,cn2,ai2,d12,d22,co2'
        csv_text = f"{header}\n{header2}\n{data}\n"
        records = parse_client_csv(csv_text)
        # Should get records from both blocks
        assert len(records) >= 1
        dates = [r['date'] for r in records]
        assert '3月1日' in dates

    def test_multiple_rows(self):
        header = ','.join(['h'] * 13)
        csv_text = (
            f"{header}\n{header}\n"
            "1,3月10日,p1,fd1,c1,r1,n1,u1,cn1,a1,d1,d2,co\n"
            "2,3月11日,p2,fd2,c2,r2,n2,u2,cn2,a2,d1,d2,co\n"
            "3,3月12日,p3,fd3,c3,r3,n3,u3,cn3,a3,d1,d2,co\n"
        )
        records = parse_client_csv(csv_text)
        assert len(records) == 3


# ── parse_financial_csv ──────────────────────────────────────────────────────

class TestParseFinancialCsv:

    def test_basic_parsing(self):
        header = ','.join(['h'] * 19)
        csv_text = (
            f"{header}\n"
            "3月15日,ACC123,GRP456,阿YIM,维护员,+86123,Iconnect,$1000,$500,note,$100,$200,$300,$400,$500,$600,$700,$800,$4600\n"
        )
        records = parse_financial_csv(csv_text)
        assert len(records) == 1
        r = records[0]
        assert r['date'] == '3月15日'
        assert r['new_order_amount'] == 1000.0
        assert r['pressure_amount'] == 500.0

    def test_skip_header_date(self):
        header = ','.join(['h'] * 19)
        csv_text = f"{header}\n日期," + ','.join(['x'] * 18) + "\n"
        records = parse_financial_csv(csv_text)
        assert records == []

    def test_money_parsing_edge_cases(self):
        header = ','.join(['h'] * 19)
        # Dash means zero, currency symbols stripped
        csv_text = (
            f"{header}\n"
            "3月1日,A,G,F,M,N,P,-,$500,note,-,-,-,-,-,-,-,-,$500\n"
        )
        records = parse_financial_csv(csv_text)
        assert len(records) == 1
        assert records[0]['new_order_amount'] == 0.0
        assert records[0]['pressure_amount'] == 500.0

    def test_empty_csv(self):
        records = parse_financial_csv("header\n")
        assert records == []

    def test_short_rows_skipped(self):
        csv_text = "header\ntoo,short\n"
        records = parse_financial_csv(csv_text)
        assert records == []

    def test_large_amount_rejected(self):
        """Amounts > 10M should be rejected (return 0.0)."""
        header = ','.join(['h'] * 19)
        csv_text = (
            f"{header}\n"
            "3月1日,A,G,F,M,N,P,$99999999,0,note,0,0,0,0,0,0,0,0,0\n"
        )
        records = parse_financial_csv(csv_text)
        assert records[0]['new_order_amount'] == 0.0


# ── parse_performance_csv ────────────────────────────────────────────────────

class TestParsePerformanceCsv:

    def test_basic_parsing(self):
        # 3 header rows + data rows
        csv_text = (
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "x,阿YIM,飞机筛选,100,20,80%,5,10,2,15,60,90%,50,45,40,30,75%,25,5\n"
        )
        records = parse_performance_csv(csv_text)
        assert len(records) == 1
        r = records[0]
        assert r['name'] == '阿YIM'
        assert r['category'] == '飞机筛选'
        assert r['powder_count'] == 100
        assert r['reply_rate'] == 80.0

    def test_too_few_header_rows(self):
        csv_text = "h\nh\n"
        records = parse_performance_csv(csv_text)
        assert records == []

    def test_name_carries_forward(self):
        """When name is empty, use the previous name."""
        csv_text = (
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "x,阿YIM,飞机筛选,10,2,80%,1,1,0,3,6,90%,5,4,4,3,75%,2,0\n"
            "x,,RCS筛选,20,4,80%,2,2,1,5,10,85%,8,7,6,5,80%,3,1\n"
        )
        records = parse_performance_csv(csv_text)
        assert len(records) == 2
        assert records[0]['name'] == '阿YIM'
        assert records[1]['name'] == '阿YIM'
        assert records[1]['category'] == 'RCS筛选'

    def test_skip_sum_row(self):
        csv_text = (
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "x,SUM,飞机筛选,100,20,80%,5,10,2,15,60,90%,50,45,40,30,75%,25,5\n"
        )
        records = parse_performance_csv(csv_text)
        assert records == []

    def test_safe_int_large_value_rejected(self):
        """Values > 100K should be rejected."""
        csv_text = (
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h,h\n"
            "x,Test,Cat,999999,0,0%,0,0,0,0,0,0%,0,0,0,0,0%,0,0\n"
        )
        records = parse_performance_csv(csv_text)
        assert records[0]['powder_count'] == 0


# ── parse_daily_summary_csv ──────────────────────────────────────────────────

class TestParseDailySummaryCsv:

    def test_basic_parsing(self):
        csv_text = (
            "Daily Summary\n"
            "2024-03-15\n"
            "header row\n"
            "header row\n"
            "header row\n"
            "阿YIM,10,8,80%,6,75%,4,66%,3,50%,2,33%\n"
        )
        records = parse_daily_summary_csv(csv_text)
        assert len(records) == 1
        r = records[0]
        assert r['frontdesk'] == '阿YIM'
        assert r['new_powder'] == 10
        assert r['today_reply'] == 8
        assert r['today_reply_rate'] == 80.0
        assert r['report_date'] == '2024-03-15'

    def test_too_few_rows(self):
        csv_text = "h\nh\nh\n"
        records = parse_daily_summary_csv(csv_text)
        assert records == []

    def test_skip_header_names(self):
        csv_text = (
            "Daily\n2024-01-01\nh\nh\nh\n"
            "前台,1,1,1%,1,1%,1,1%,1,1%,1,1%\n"
        )
        records = parse_daily_summary_csv(csv_text)
        assert records == []

    def test_skip_short_rows(self):
        csv_text = "h\n2024-01-01\nh\nh\nh\ntoo,short\n"
        records = parse_daily_summary_csv(csv_text)
        assert records == []


# ── fetch_sheet_csv ──────────────────────────────────────────────────────────

class TestFetchSheetCsv:

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value='col1,col2\nval1,val2')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('engines.csv_reader.aiohttp.ClientSession', return_value=mock_session):
            result = await fetch_sheet_csv(12345)
            assert result == 'col1,col2\nval1,val2'

    @pytest.mark.asyncio
    async def test_fetch_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('engines.csv_reader.aiohttp.ClientSession', return_value=mock_session):
            result = await fetch_sheet_csv(12345)
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_network_error(self):
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=Exception('connection timeout'))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch('engines.csv_reader.aiohttp.ClientSession', return_value=mock_session):
            result = await fetch_sheet_csv(12345)
            assert result is None


# ── sync_all_sheets ──────────────────────────────────────────────────────────

class TestSyncAllSheets:

    @pytest.mark.asyncio
    async def test_sync_returns_structure(self):
        with patch('engines.csv_reader.fetch_sheet_csv', new_callable=AsyncMock, return_value=None), \
             patch('engines.csv_reader.asyncio.sleep', new_callable=AsyncMock):
            result = await sync_all_sheets()
            assert 'client_records' in result
            assert 'financial_records' in result
            assert 'performance_records' in result
            assert 'daily_summary' in result
            assert 'errors' in result
            assert 'timestamp' in result

    @pytest.mark.asyncio
    async def test_sync_all_fail_collects_errors(self):
        with patch('engines.csv_reader.fetch_sheet_csv', new_callable=AsyncMock, return_value=None), \
             patch('engines.csv_reader.asyncio.sleep', new_callable=AsyncMock):
            result = await sync_all_sheets()
            assert len(result['errors']) > 0
