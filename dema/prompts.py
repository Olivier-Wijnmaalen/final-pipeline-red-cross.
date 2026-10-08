"""Load and verify the two authoritative prompts committed with the project."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import sha256_text


PROMPT_ROOT = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_MANIFEST = PROMPT_ROOT / "manifest.json"


class _NoopGeneration:
    def __enter__(self) -> "_NoopGeneration":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def update(self, **_: Any) -> None:
        return None


class NoopLangfuse:
    """Minimal tracing client used when approved local prompts run offline."""

    def start_as_current_observation(self, **_: Any) -> _NoopGeneration:
        return _NoopGeneration()

    def flush(self) -> None:
        return None


@dataclass(frozen=True)
class FrozenPrompt:
    """Small Langfuse-compatible prompt backed by a reviewed local snapshot."""

    name: str
    version: int
    prompt: str
    config: dict[str, Any]
    langfuse_prompt: None = None

    def compile(self, **variables: Any) -> str:
        compiled = self.prompt
        for key, value in variables.items():
            compiled = re.sub(
                r"{{\s*" + re.escape(key) + r"\s*}}",
                lambda _: str(value),
                compiled,
            )
        unresolved = sorted(set(re.findall(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", compiled)))
        if unresolved:
            raise ValueError(f"Unresolved prompt variables for {self.name}: {unresolved}")
        return compiled


def load_frozen_prompt(key: str) -> FrozenPrompt:
    """Load a committed prompt and verify its path, variables, and hash."""
    if not PROMPT_MANIFEST.exists():
        raise RuntimeError(f"Required prompt manifest is missing: {PROMPT_MANIFEST}")
    manifest = json.loads(PROMPT_MANIFEST.read_text(encoding="utf-8"))
    record = manifest.get("prompts", {}).get(key)
    if not isinstance(record, dict):
        raise RuntimeError(f"Frozen prompt manifest lacks {key!r}")
    prompt_path = (PROMPT_ROOT / str(record["file"])).resolve()
    if PROMPT_ROOT.resolve() not in prompt_path.parents:
        raise RuntimeError(f"Frozen prompt path escapes prompt directory: {prompt_path}")
    text = prompt_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_hash = sha256_text(text)
    if actual_hash != record.get("sha256"):
        raise RuntimeError(
            f"Frozen prompt hash mismatch for {record.get('name', key)}: {actual_hash}"
        )
    expected_variables = sorted(str(value) for value in record.get("expected_variables", []))
    actual_variables = sorted(
        set(re.findall(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", text))
    )
    if actual_variables != expected_variables:
        raise RuntimeError(
            f"Frozen prompt variables mismatch for {record.get('name', key)}: "
            f"expected {expected_variables}, found {actual_variables}"
        )
    return FrozenPrompt(
        name=str(record["name"]),
        version=int(record["version"]),
        prompt=text,
        config=dict(record.get("config", {})),
    )


def get_langfuse_client() -> Any:
    tracing_enabled = os.getenv("LANGFUSE_TRACING_ENABLED", "false").strip().lower()
    if tracing_enabled in {"0", "false", "no", "off"}:
        return NoopLangfuse()
    from langfuse import get_client

    client = get_client()
    if not client.auth_check():
        raise RuntimeError("Langfuse authentication failed")
    return client


def get_extraction_prompt(langfuse: Any) -> Any:
    del langfuse
    return load_frozen_prompt("stage1")


def get_scoring_prompt(langfuse: Any) -> Any:
    del langfuse
    return load_frozen_prompt("stage2")


def scoring_prompt_snapshot(prompt: Any) -> dict[str, Any]:
    """Return the reproducibility record stored beside every Stage 2 run."""
    return {
        "name": prompt.name,
        "version": prompt.version,
        "api_sha256": sha256_text(prompt.prompt),
        "crlf_sha256": sha256_text(
            prompt.prompt.replace("\r\n", "\n").replace("\n", "\r\n")
        ),
        "config": prompt.config,
        "prompt": prompt.prompt,
    }

