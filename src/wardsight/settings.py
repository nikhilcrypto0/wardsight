"""OpenAI settings for every LLM command, read ONLY from this project's .env.

python-dotenv's default search walks up through parent folders, so a missing project .env
would silently pick up one from a parent (another project's key, another bill). Here the
path is fixed: the .env next to pyproject.toml, and nothing else.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def openai_model(env_file: Path = ENV_FILE) -> str:
    """Load the key and model from the project .env and return the model name, or stop."""
    if not env_file.is_file():
        raise SystemExit(f"Missing {env_file}\nCopy .env.example to that exact path and fill in OPENAI_API_KEY "
                         "and WARDSIGHT_OPENAI_MODEL. A .env in a parent folder is ignored on purpose.")
    values = dotenv_values(env_file)
    key, model = values.get("OPENAI_API_KEY"), values.get("WARDSIGHT_OPENAI_MODEL")
    if not key or not model:
        raise SystemExit(f"{env_file} needs both OPENAI_API_KEY and WARDSIGHT_OPENAI_MODEL filled in.")
    os.environ["OPENAI_API_KEY"] = key  # the project key wins over any key already in the shell
    return model


def check_model(model: str, retrieve: Callable[[str], object] | None = None) -> None:
    """One free lookup before a paid run: stop if the key cannot see this model (typo, retired)."""
    import openai

    if retrieve is None:
        retrieve = openai.OpenAI().models.retrieve
    try:
        retrieve(model)
    except openai.NotFoundError as exc:
        raise SystemExit(f"Model '{model}' is not available to this API key (misspelled or retired). "
                         "Check https://platform.openai.com/docs/deprecations and set WARDSIGHT_OPENAI_MODEL.") from exc
    print(f"model check: '{model}' is available. (The API does not report retirement dates; "
          "see the OpenAI deprecations page.)")
