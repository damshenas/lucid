"""M12: data connectors (mocked), git sync, and disabled placeholders."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from src.modules.com._retry import with_retry
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


async def test_connectors_discovery_methods_return_one_item_per_ticker() -> None:
    """Each connector's bulk 'discover every currently-rated ticker' method (used by
    a buy strategy with USES_WATCHLIST = False, e.g. strategies/buy/signal_follow.py)
    returns items shaped exactly like its single-ticker fetch method's result."""

    def zacks_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ranks"
        return httpx.Response(200, json={"items": [{"ticker": "AAPL", "rank": 1}]})

    def finviz_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/screener"
        return httpx.Response(200, json={"items": [{"ticker": "MSFT", "metrics": {"recommendation": "buy"}}]})

    def tv_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/technicals"
        return httpx.Response(200, json={"items": [{"ticker": "NVDA", "recommendation": "strong_buy"}]})

    def barchart_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/opinions"
        return httpx.Response(200, json={"items": [{"ticker": "TSLA", "opinion": "sell"}]})

    zacks = ZacksConnector("https://provider.test", client=_client(zacks_handler))
    finviz = FinvizConnector("https://provider.test", client=_client(finviz_handler))
    tv = TradingViewConnector("https://provider.test", client=_client(tv_handler))
    barchart = BarchartConnector("https://provider.test", client=_client(barchart_handler))

    assert await zacks.fetch_ranks() == [{"source": "zacks", "ticker": "AAPL", "rank": 1, "raw": {"ticker": "AAPL", "rank": 1}}]
    assert (await finviz.fetch_screener())[0]["ticker"] == "MSFT"
    assert (await tv.fetch_all_technicals())[0]["recommendation"] == "strong_buy"
    assert (await barchart.fetch_all_opinions())[0]["opinion"] == "sell"

    for c in (zacks, finviz, tv, barchart):
        await c.aclose()



async def test_with_retry_succeeds_after_transient_failures() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ValueError("transient")
        return "ok"

    result = await with_retry(
        flaky, retry_attempts=3, backoff_base=0.001, retryable_exceptions=(ValueError,)
    )
    assert result == "ok"
    assert calls == 3


async def test_with_retry_raises_after_exhausting_attempts() -> None:
    async def always_fails() -> str:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await with_retry(
            always_fails, retry_attempts=2, backoff_base=0.001, retryable_exceptions=(ValueError,)
        )


async def test_with_retry_does_not_retry_non_retryable_exceptions() -> None:
    calls = 0

    async def raises_type_error() -> str:
        nonlocal calls
        calls += 1
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        await with_retry(
            raises_type_error, retry_attempts=3, backoff_base=0.001, retryable_exceptions=(ValueError,)
        )
    assert calls == 1


async def test_zacks_retries_on_429_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={})
        return httpx.Response(200, json={"rank": 2, "name": "Buy"})

    connector = ZacksConnector(
        "https://provider.test",
        client=httpx.AsyncClient(
            base_url="https://provider.test",
            transport=httpx.MockTransport(handler),
        ),
    )
    connector._provider._backoff_base = 0.001  # keep the test fast
    result = await connector.fetch_rank("AAPL")
    assert result["rank"] == 2
    assert calls == 2
    await connector.aclose()


async def test_zacks_does_not_retry_on_404() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={})

    connector = ZacksConnector("https://provider.test", client=_client(handler))
    connector._provider._backoff_base = 0.001
    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch_rank("AAPL")
    assert calls == 1
    await connector.aclose()


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
