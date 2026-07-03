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
from src.modules.com.git import GitError, GitSync, deploy_strategies, sync_and_deploy
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
async def test_git_sync_requires_existing_checkout(tmp_path: Path) -> None:
    """``GitSync`` never clones — ``local_path`` must already be a git checkout (set up
    out-of-band on the host), matching how ``EXT_STRATEGIES`` is provisioned."""
    with pytest.raises(GitError):
        await GitSync(str(tmp_path / "not-a-repo")).sync()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
async def test_git_sync_pulls_existing_checkout(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=origin, check=True)
    (origin / "buy").mkdir()
    (origin / "buy" / "x.py").write_text("STRATEGY_NAME='x'\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=origin, check=True)

    # Pre-clone, exactly as EXT_STRATEGIES is provisioned out-of-band on the host.
    dest = tmp_path / "dest"
    subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True)

    (origin / "buy" / "y.py").write_text("STRATEGY_NAME='y'\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=origin, check=True)

    commit = await GitSync(str(dest)).sync()
    assert len(commit) == 40
    assert (dest / "buy" / "y.py").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
async def test_git_sync_and_deploy_never_runs_from_staging(tmp_path: Path) -> None:
    """The app must load strategies from ``target_root``, never straight from the
    ``EXT_STRATEGIES`` staging clone."""
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=origin, check=True)
    (origin / "sell").mkdir()
    (origin / "sell" / "y.py").write_text("STRATEGY_NAME='y'\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=origin, check=True)

    staging = tmp_path / "algorithms"
    subprocess.run(["git", "clone", "-q", str(origin), str(staging)], check=True)
    target = tmp_path / "strategies"

    commit, copied = await sync_and_deploy(staging_root=staging, target_root=target)
    assert len(commit) == 40
    assert copied == ["sell/y.py"]
    assert (target / "sell" / "y.py").exists()
    # Not executed from the staging clone directly, but it is present there too.
    assert (staging / "sell" / "y.py").exists()


def test_deploy_strategies_skips_underscore_files_and_never_deletes(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    target = tmp_path / "target"
    (staging / "buy").mkdir(parents=True)
    (staging / "buy" / "new_strat.py").write_text("STRATEGY_NAME='new'\n")
    (staging / "buy" / "_helper.py").write_text("# not a strategy\n")
    (target / "buy").mkdir(parents=True)
    (target / "buy" / "existing_builtin.py").write_text("STRATEGY_NAME='builtin'\n")

    copied = deploy_strategies(staging, target)

    assert copied == ["buy/new_strat.py"]
    assert (target / "buy" / "new_strat.py").exists()
    assert (target / "buy" / "existing_builtin.py").exists()  # untouched
    assert not (target / "buy" / "_helper.py").exists()
