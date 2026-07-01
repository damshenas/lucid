"""M0 smoke tests: the app boots and config loads."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import FastAPI

from src.api.main import create_app
from src.conf.schema import LucidConfig


def test_create_app_returns_fastapi() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Lucid"


def test_default_yml_matches_schema() -> None:
    default_yml = Path("src/conf/default.yml")
    data = yaml.safe_load(default_yml.read_text())
    config = LucidConfig.model_validate(data)
    assert config.risk.enabled is False
    assert config.broker.paper_mode is True
    assert config.execution.quantity_mode.value == "fixed_usd"
