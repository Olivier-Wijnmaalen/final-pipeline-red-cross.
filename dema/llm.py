"""Shared OpenAI client and structured JSON model-call handling."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .storage import atomic_write_json, atomic_write_text, sha256_text


class IncompleteResponseError(RuntimeError):
    def __init__(self, response: Any, reason: str):
        super().__init__(f"Incomplete model response ({reason})")
        self.response = response


def build_model_client() -> Any:
    from openai import OpenAI

    provider = os.getenv("AI_PROVIDER", "azure").strip().lower()
    if provider == "azure":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        if not endpoint or not api_key:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required")
        return OpenAI(base_url=endpoint, api_key=api_key, timeout=900, max_retries=3)
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        return OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key=api_key,
            timeout=900,
            max_retries=3,
        )
    raise RuntimeError("AI_PROVIDER must be azure or openai")


def model_name() -> str:
    if os.getenv("AI_PROVIDER", "azure").strip().lower() == "azure":
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        if not deployment:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT is required")
        return deployment
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not model:
        raise RuntimeError("OPENAI_MODEL is required")
    return model


def model_runtime_identity(model: str) -> dict[str, str]:
    """Return a secret-free identity for cache and provenance decisions."""
    provider = os.getenv("AI_PROVIDER", "azure").strip().lower()
    if provider == "azure":
        base_url = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    else:
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return {
        "provider": provider,
        "model": model,
        # Keep internal endpoint names out of artifacts while distinguishing
        # otherwise identical deployment names hosted by different providers.
        "base_url_sha256": sha256_text(base_url),
    }


def parse_json_response(raw: str) -> dict[str, Any]:
    candidate = raw.strip().lstrip("\ufeff")
    if candidate.startswith("```json") and candidate.endswith("```"):
        candidate = candidate[7:-3].strip()
    elif candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate[3:-3].strip()
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("The model response is not a JSON object")
    return data


def response_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    result: dict[str, int] = {}
    for source, target in (
        ("input_tokens", "input"),
        ("output_tokens", "output"),
        ("total_tokens", "total"),
    ):
        value = getattr(usage, source, None)
        if isinstance(value, int):
            result[target] = value
    return result


def create_json_response(
    *,
    client: Any,
    model: str,
    input_text: str,
    temperature: float,
    max_output_tokens: int,
    json_mode: bool = False,
    response_schema: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Make one OpenAI Responses call and return its parsed JSON object."""
    call_parameters: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if response_schema is not None:
        call_parameters["text"] = {
            "format": {
                "type": "json_schema",
                "name": "dema_structured_output",
                "strict": True,
                "schema": response_schema,
            }
        }
    elif json_mode:
        call_parameters["text"] = {"format": {"type": "json_object"}}
    response = client.responses.create(**call_parameters)
    if response.status != "completed":
        reason = getattr(
            getattr(response, "incomplete_details", None), "reason", "unknown"
        )
        raise IncompleteResponseError(response, reason)
    return response, parse_json_response(response.output_text or "")


def call_model_json(
    *,
    client: Any,
    langfuse: Any,
    prompt_object: Any,
    compiled_prompt: str,
    stage_name: str,
    model: str,
    temperature: float,
    max_output_tokens: int,
    metadata: dict[str, Any],
    artifact_prefix: Path,
    json_mode: bool = False,
    response_schema: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request = {
        "stage": stage_name,
        "model": model,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "prompt_name": prompt_object.name,
        "prompt_version": prompt_object.version,
        "compiled_prompt_sha256": sha256_text(compiled_prompt),
        "metadata": metadata,
    }
    atomic_write_json(artifact_prefix.with_suffix(".request.json"), request)
    started = time.monotonic()
    observation_parameters = {
        "as_type": "generation",
        "name": stage_name,
        "model": model,
        "model_parameters": {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        },
        "input": {**metadata, "compiled_prompt_sha256": request["compiled_prompt_sha256"]},
        "metadata": {**metadata, "pipeline": "frozen-dema-two-stage"},
    }
    linked_prompt = getattr(prompt_object, "langfuse_prompt", prompt_object)
    if linked_prompt is not None:
        observation_parameters["prompt"] = linked_prompt
    with langfuse.start_as_current_observation(**observation_parameters) as generation:
        try:
            response, data = create_json_response(
                client=client,
                model=model,
                input_text=compiled_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                json_mode=json_mode,
                response_schema=response_schema,
            )
        except IncompleteResponseError as exc:
            response = exc.response
            atomic_write_text(
                artifact_prefix.with_suffix(".raw.txt"), response.output_text or ""
            )
            atomic_write_json(
                artifact_prefix.with_suffix(".response.json"),
                response.model_dump(mode="json"),
            )
            generation.update(level="ERROR", status_message=str(exc))
            raise
        raw = response.output_text or ""
        atomic_write_text(artifact_prefix.with_suffix(".raw.txt"), raw)
        atomic_write_json(
            artifact_prefix.with_suffix(".response.json"),
            response.model_dump(mode="json"),
        )
        atomic_write_json(artifact_prefix.with_suffix(".json"), data)
        usage = response_usage(response)
        generation.update(output=data, usage_details=usage)
    return data, {
        "response_id": response.id,
        "usage": usage,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
