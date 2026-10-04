"""A model can live on another endpoint, with its own key and its own request budget."""

from __future__ import annotations

from pathlib import Path

from conftest import MINI_SPEC

from genstudy.cli import endpoint
from genstudy.config import load_study

OTHER = """
[models.b]
served_id = "vendor/model-b"
base_url = "https://router.example.org/api/v1/"
api_key_env = "ROUTER_KEY"
extra = { reasoning = { effort = "low" }, provider = { order = ["vendor"], allow_fallbacks = false } }
"""


def test_per_model_endpoint_key_and_counter(tmp_path: Path) -> None:
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "P1.md").write_text("Trains are delayed.", encoding="utf-8")
    path = tmp_path / "study.toml"
    path.write_text(MINI_SPEC + OTHER, encoding="utf-8")
    spec = load_study(path)
    assert spec.models["a"].base_url is None
    assert endpoint(spec, "a") == (
        "https://example.invalid/v1",
        "SCADS_API_KEY",
        "requests_per_day.json",
    )
    assert endpoint(spec, None) == endpoint(spec, "a")
    b = spec.models["b"]
    assert b.base_url == "https://router.example.org/api/v1"
    assert b.extra["provider"] == {"order": ["vendor"], "allow_fallbacks": False}
    url, key_env, counter = endpoint(spec, "b")
    assert (url, key_env) == ("https://router.example.org/api/v1", "ROUTER_KEY")
    assert counter == "requests_per_day.router.example.org.json"
