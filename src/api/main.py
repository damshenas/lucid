"""FastAPI application factory.

``create_app()`` builds the app, wires the composition root (``AppContext``) via lifespan,
mounts the ``/api/v1`` routers and health probes, and serves the built React bundle at ``/``
when present.

Run: ``uvicorn src.api.main:create_app --factory --no-access-log``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.modules.db.models import Base
from src.modules.health import router as health_router
from src.modules.logger import configure_logging, get_logger

from .context import AppContext
from .runtime import TradingRuntime
from .v1 import (
    admin,
    auth,
    backtesting,
    orders,
    positions,
    prices,
    settings,
    signals,
    strategies,
)

_logger = get_logger("api")
_UI_DIST = Path("src/ui/dist")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    ctx: AppContext = getattr(app.state, "context", None) or AppContext.build()
    app.state.context = ctx
    configure_logging(level=ctx.settings.logger.level, file_path=None)

    if ctx.is_sqlite:
        async with ctx.db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with ctx.db.session() as session:
        await ctx.strategy_service(session).scan()
        await session.commit()

    runtime = TradingRuntime(ctx)
    runtime.wire()
    app.state.runtime = runtime
    # Background jobs run only against a real database, not the in-memory test DB.
    if not ctx.is_sqlite:
        runtime.start()

    _logger.info("Lucid %s ready", __version__)
    yield

    if not ctx.is_sqlite:
        runtime.shutdown()
    await ctx.db.dispose()


def create_app(context: AppContext | None = None) -> FastAPI:
    app = FastAPI(
        title="Lucid",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.state.context = context

    app.include_router(health_router)
    for module in (
        auth,
        positions,
        orders,
        signals,
        settings,
        strategies,
        prices,
        backtesting,
        admin,
    ):
        app.include_router(module.router)

    _mount_ui(app)
    return app


def _mount_ui(app: FastAPI) -> None:
    if not _UI_DIST.exists():
        return
    assets = _UI_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = _UI_DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        # API/health are matched by their routers first; everything else is the SPA.
        return FileResponse(index)
