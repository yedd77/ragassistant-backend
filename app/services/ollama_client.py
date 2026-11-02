import logging
from typing import Any
from urllib.parse import urljoin

import requests

from app.config import get_settings


logger = logging.getLogger(__name__)
EMBED_REQUEST_SIZE = 100


class OllamaError(RuntimeError):
    """Raised when a local Ollama request cannot be completed or validated."""


def _api_url(path: str) -> str:
    base_url = get_settings().ollama_base_url.rstrip("/") + "/"
    return urljoin(base_url, path.lstrip("/"))


def _error_message(response: requests.Response) -> str:
    try:
        detail = response.json().get("error")
    except ValueError:
        detail = None
    return str(detail or response.text or "unknown Ollama error")[:1000]


def embed_texts(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """Generate embeddings locally with Ollama's nomic-embed-text model."""
    del task_type
    if not texts:
        return []

    settings = get_settings()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_REQUEST_SIZE):
        batch = texts[start:start + EMBED_REQUEST_SIZE]
        try:
            response = requests.post(
                _api_url("/api/embed"),
                json={"model": settings.ollama_embed_model, "input": batch},
                timeout=settings.ollama_timeout_seconds,
            )
            if not response.ok:
                raise OllamaError(
                    f"Ollama embeddings returned HTTP {response.status_code}: "
                    f"{_error_message(response)}"
                )
            payload: Any = response.json()
        except OllamaError:
            raise
        except requests.RequestException as exc:
            raise OllamaError(
                f"Ollama embedding request failed: {type(exc).__name__}: {exc}"
            ) from exc
        except ValueError as exc:
            raise OllamaError(
                "Ollama returned invalid JSON for the embedding request."
            ) from exc

        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != len(batch)
            or any(
                not isinstance(item, list)
                or not item
                or any(not isinstance(value, (int, float)) for value in item)
                for item in embeddings
            )
        ):
            raise OllamaError("Unexpected embedding response from Ollama.")
        vectors.extend(embeddings)

    logger.debug(
        "Generated %d embeddings with Ollama model %s.",
        len(vectors),
        settings.ollama_embed_model,
    )
    return vectors
