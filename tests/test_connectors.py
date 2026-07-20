"""M12: data connectors (mocked), git sync, and disabled placeholders."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from src.modules.com._retry import with_retry
from src.modules.com.barchart import BarchartConnector
from src.modules.com.barchart import DisabledConnectorError as BarchartDisabledError
from src.modules.com.claude import ClaudeClient, DisabledConnectorError
from src.modules.com.finviz import FinvizConnector
from src.modules.com.git import GitError, GitSync, deploy_strategies, sync_and_deploy
from src.modules.com.telegram import TelegramClient
from src.modules.com.tradingview import TradingViewConnector
from src.modules.com.zacks import DisabledConnectorError as ZacksDisabledError
from src.modules.com.zacks import ZacksConnector


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="https://provider.test", transport=httpx.MockTransport(handler))


_FINVIZ_HTML = """
<table id="screener-views-table">
  <tr><th>Ticker</th><th>Company</th></tr>
  <tr><td><a href="quote.ashx?t=AAPL&ty=c">AAPL</a></td><td>Apple</td></tr>
  <tr><td><a href="quote.ashx?t=MSFT&ty=c">MSFT</a></td><td>Microsoft</td></tr>
</table>
"""


async def test_finviz_scrapes_tickers_from_screener_pages() -> None:
    """No API key/base_url — direct scrape of Finviz's real public screener pages,
    extracting tickers via their stable ``quote.ashx?t=TICKER`` link pattern
    (mirrors the legacy dealer app's target screens, simplified to just tickers)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_FINVIZ_HTML)

    connector = FinvizConnector(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    screener = await connector.fetch_screener()
    tickers = {item["ticker"] for item in screener}
    assert tickers == {"AAPL", "MSFT"}
    assert all(item["metrics"]["recommendation"] == "buy" for item in screener)

    # Per-ticker convenience lookup reuses the same scrape.
    match = await connector.fetch_metrics("aapl")
    assert match["ticker"] == "AAPL"
    assert match["metrics"]["recommendation"] == "buy"

    no_match = await connector.fetch_metrics("ZZZZ")
    assert no_match == {"source": "finviz", "ticker": "ZZZZ", "metrics": {}, "raw": None}

    await connector.aclose()


async def test_finviz_one_screen_failing_does_not_block_others() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "ta_topgainers" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, text=_FINVIZ_HTML)

    connector = FinvizConnector(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    screener = await connector.fetch_screener()
    assert {item["ticker"] for item in screener} == {"AAPL", "MSFT"}
    await connector.aclose()


async def test_tradingview_scanner_parses_response() -> None:
    """No API key/base_url — POSTs directly to TradingView's real public scanner
    endpoint (mirrors the legacy dealer app's ``_fetch_scanner``)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://scanner.tradingview.com/america/scan"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"d": ["NASDAQ:AAPL", 150.0, 1.2, 900000, 0.5, 60.0]},
                    {"d": ["NYSE:GE", 100.0, 0.1, 600000, None, None]},
                ]
            },
        )

    connector = TradingViewConnector(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    results = await connector.fetch_all_technicals()
    by_ticker = {r["ticker"]: r for r in results}
    assert by_ticker["AAPL"]["recommendation"] == 0.5
    assert by_ticker["GE"]["recommendation"] is None

    match = await connector.fetch_technicals("aapl")
    assert match["recommendation"] == 0.5

    no_match = await connector.fetch_technicals("ZZZZ")
    assert no_match == {"source": "tradingview", "ticker": "ZZZZ", "recommendation": None, "raw": None}

    await connector.aclose()


async def test_zacks_and_barchart_are_disabled_placeholders() -> None:
    """Their real data needs a headless-browser anti-bot bypass this repo doesn't
    run — both are explicit DISABLED placeholders, same pattern as telegram/claude."""
    with pytest.raises(ZacksDisabledError):
        await ZacksConnector().fetch_rank("AAPL")
    with pytest.raises(ZacksDisabledError):
        await ZacksConnector().fetch_ranks()
    with pytest.raises(BarchartDisabledError):
        await BarchartConnector().fetch_opinion("AAPL")
    with pytest.raises(BarchartDisabledError):
        await BarchartConnector().fetch_all_opinions()



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


async def test_finviz_retries_transient_transport_errors_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, text=_FINVIZ_HTML)

    connector = FinvizConnector(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    screener = await connector.fetch_screener()
    assert {item["ticker"] for item in screener} == {"AAPL", "MSFT"}
    assert calls >= 2
    await connector.aclose()


async def test_tradingview_does_not_retry_on_persistent_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    connector = TradingViewConnector(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError):
        await connector.fetch_all_technicals()
    assert calls == 1  # a plain 500 (not a transport/timeout error) isn't retried
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
