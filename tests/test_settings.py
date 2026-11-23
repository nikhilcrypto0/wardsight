"""LLM settings come only from this project's .env, and a bad model stops before any paid call."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import openai
import pytest

from wardsight.settings import ENV_FILE, check_model, openai_model

SRC = Path(__file__).resolve().parents[1] / "src"


def test_env_file_is_the_one_next_to_pyproject():
    assert ENV_FILE.parent == SRC.parent and (ENV_FILE.parent / "pyproject.toml").is_file()


def test_a_parent_folder_env_is_never_used(tmp_path: Path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=parent-key\nWARDSIGHT_OPENAI_MODEL=parent-model\n")
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(SystemExit, match="Missing"):
        openai_model(project / ".env")


def test_project_env_key_wins_over_the_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "shell-key-from-another-project")
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=project-key\nWARDSIGHT_OPENAI_MODEL=some-model\n")
    assert openai_model(env) == "some-model"
    assert os.environ["OPENAI_API_KEY"] == "project-key"


def test_both_values_are_required(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=project-key\n")
    with pytest.raises(SystemExit, match="WARDSIGHT_OPENAI_MODEL"):
        openai_model(env)


def test_no_module_searches_parent_folders_for_env():
    offenders = [p for p in SRC.rglob("*.py") if "load_dotenv" in p.read_text() or "find_dotenv" in p.read_text()]
    assert offenders == []


def test_missing_model_stops_the_run():
    def retrieve(model: str):
        response = httpx.Response(404, request=httpx.Request("GET", f"https://api.openai.com/v1/models/{model}"))
        raise openai.NotFoundError("model not found", response=response, body=None)

    with pytest.raises(SystemExit, match="not available"):
        check_model("gpt-retired", retrieve)


def test_available_model_passes(capsys: pytest.CaptureFixture[str]):
    check_model("gpt-ok", lambda model: {"id": model})
    assert "is available" in capsys.readouterr().out
