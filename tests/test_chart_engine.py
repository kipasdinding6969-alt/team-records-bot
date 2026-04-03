"""Tests for engines/chart_engine.py — chart generation.

Matplotlib is mocked at the module-import level where needed; pure-logic
helpers are tested directly.
"""
import os
import tempfile
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_database():
    """Return a mock database singleton with standard helpers."""
    db = MagicMock()
    # get_connection returns an async context manager
    conn = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[("阿YIM",), ("阿俊",)])
    conn.execute = AsyncMock(return_value=cursor)

    class _FakeCtx:
        async def __aenter__(self_inner):
            return conn
        async def __aexit__(self_inner, *a):
            pass

    db.get_connection = MagicMock(return_value=_FakeCtx())
    db.get_client_records_by_frontdesk = AsyncMock(return_value=[])
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChartEngineInit:
    def test_setup_complete_when_matplotlib_available(self):
        """ChartEngine.setup_complete is True when matplotlib is importable."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()
            assert engine.setup_complete is True

    def test_setup_complete_false_when_matplotlib_missing(self):
        """ChartEngine.setup_complete is False when matplotlib unavailable."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", False):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()
            assert engine.setup_complete is False


class TestSaveChart:
    def test_save_chart_creates_png(self):
        """_save_chart writes a file to temp dir and returns the path."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            mock_fig = MagicMock()
            path = engine._save_chart(mock_fig, "test_chart")
            assert path.endswith(".png")
            assert "test_chart" in path
            mock_fig.savefig.assert_called_once()

    def test_save_chart_closes_figure(self):
        """_save_chart calls plt.close to free memory."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"), \
             patch("engines.chart_engine.plt") as mock_plt:
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            mock_fig = MagicMock()
            engine._save_chart(mock_fig, "test")
            mock_plt.close.assert_called_once_with(mock_fig)


class TestAddWatermark:
    def test_watermark_adds_text_to_axes(self):
        """_add_watermark adds text element to the axes."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            mock_ax = MagicMock()
            engine._add_watermark(mock_ax, "2024-03-15")
            mock_ax.text.assert_called_once()
            call_kwargs = mock_ax.text.call_args
            # Watermark text should contain the date
            assert "2024-03-15" in str(call_kwargs)


class TestDailyFunnelChart:
    @pytest.mark.asyncio
    async def test_funnel_raises_when_not_initialized(self):
        """daily_funnel_chart raises RuntimeError if setup_complete is False."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", False):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()
            with pytest.raises(RuntimeError, match="not properly initialized"):
                await engine.daily_funnel_chart(date(2024, 3, 15))

    @pytest.mark.asyncio
    async def test_funnel_returns_png_path(self):
        """daily_funnel_chart returns a .png path on success."""
        mock_db = _mock_database()
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"), \
             patch("engines.chart_engine.database", mock_db), \
             patch("engines.chart_engine.plt") as mock_plt:
            # Mock subplots to return (fig, ax)
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)
            mock_plt.cm.viridis.return_value = [(0, 0, 0, 1)] * 6
            # barh returns mock bars
            mock_bar = MagicMock()
            mock_bar.get_width.return_value = 0.5
            mock_bar.get_y.return_value = 0
            mock_bar.get_height.return_value = 0.5
            mock_ax.barh.return_value = [mock_bar] * 6

            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            path = await engine.daily_funnel_chart(date(2024, 3, 15))
            assert path.endswith(".png")
            assert "daily_funnel" in path


class TestConversionGauge:
    @pytest.mark.asyncio
    async def test_gauge_zero_records(self):
        """conversion_gauge handles zero records (0% rate) without error."""
        mock_db = _mock_database()
        mock_db.get_client_records_by_frontdesk = AsyncMock(return_value=[])

        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"), \
             patch("engines.chart_engine.database", mock_db), \
             patch("engines.chart_engine.plt") as mock_plt, \
             patch("engines.chart_engine.np") as mock_np:
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt.subplots.return_value = (mock_fig, mock_ax)
            mock_np.pi = 3.14159
            mock_np.linspace.return_value = [0, 1, 2, 3]

            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            path = await engine.conversion_gauge("阿YIM")
            assert path.endswith(".png")


class TestTeamPieChart:
    @pytest.mark.asyncio
    async def test_pie_unknown_team_raises(self):
        """team_pie_chart raises ValueError for unknown team."""
        with patch("engines.chart_engine.MATPLOTLIB_AVAILABLE", True), \
             patch("engines.chart_engine.setup_chinese_font", return_value=True), \
             patch("engines.chart_engine.setup_chart_style"):
            from engines.chart_engine import ChartEngine
            engine = ChartEngine()

            with pytest.raises(ValueError, match="not found"):
                await engine.team_pie_chart("不存在的队")
