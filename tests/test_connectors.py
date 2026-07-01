"""M12: data connectors (mocked), git sync, and disabled placeholders."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from src.modules.com.barchart import BarchartConnector
from src.modules.com.claude import ClaudeClient, DisabledConnectorError
from src.modules.com.finviz import FinvizConnector
from src.modules.com.git import GitSync
from src.modules.com.telegram import TelegramClient
from src.modules.com.tradingview import TradingViewConnector
from src.modules.com.zacks import ZacksConnector


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(handler))


async def test_zacks_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rank": 1, "name": "Strong Buy"})

    connector = ZacksConnector("https://provider.test", client=_client(handler))
    result = await connector.fetch_rank("AAPL")
    assert result == {"source": "zacks", "ticker": "AAPL", "rank": 1, "raw": {"rank": 1, "name": "Strong Buy"}}
    await connector.aclose()


async def test_other_connectors_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"metrics": {}, "opinion": "buy", "recommendation": "strong_buy"})

    finviz = FinvizConnector("https://provider.test", client=_client(handler))
    barchart = BarchartConnector("https://provider.test", client=_client(handler))
    tv = TradingViewConnector("https://provider.test", client=_client(handler))

    assert (await finviz.fetch_metrics("AAPL"))["source"] == "finviz"
    assert (await barchart.fetch_opinion("AAPL"))["opinion"] == "buy"
    assert (await tv.fetch_technicals("AAPL"))["recommendation"] == "strong_buy"

    for c in (finviz, barchart, tv):
        await c.aclose()


async def test_disabled_placeholders() -> None:
    with pytest.raises(DisabledConnectorError):
        await ClaudeClient("key").complete("hi")
    assert await TelegramClient("t", "c").notify("hello") is False


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
async def test_git_sync(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=origin, check=True)
    (origin / "buy").mkdir()
    (origin / "buy" / "x.py").write_text("STRATEGY_NAME='x'\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=origin, check=True)

    dest = tmp_path / "dest"
    sync = GitSync(str(origin), str(dest), branch="main")
    commit = await sync.sync()
    assert len(commit) == 40
    assert (dest / "buy" / "x.py").exists()
