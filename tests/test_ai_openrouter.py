"""OpenRouter provider: payload shape, response mapping and failure handling.

Every test injects a transport, so nothing here touches the network or spends credits.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Self

import pytest

from mymonee.config import Settings
from mymonee.services.ai import (
    AIProviderError,
    ExternalAIOptInRequired,
    MissingAPIKeyError,
    OpenRouterProvider,
    get_ai_provider,
)
from mymonee.services.ai import openrouter_provider as provider_module
from mymonee.services.ai.schemas import TransactionContext

TAXONOMY = [
    {
        "id": "food",
        "name": "Food",
        "subcategories": [
            {"id": "food-cafe", "name": "Cafes"},
            {"id": "food-grocery", "name": "Groceries"},
        ],
    },
    {
        "id": "utilities",
        "name": "Utilities",
        "subcategories": [{"id": "util-power", "name": "Power"}],
    },
]


def _settings(tmp_path: Path, **ai: object) -> Settings:
    return Settings(
        app={"data_dir": tmp_path, "name": "test-mymonee"},
        database={"filename": "test.db", "echo": False},
        privacy={"allow_external_ai": True},
        ai={
            "enabled": True,
            "provider": "openrouter",
            "model": "google/gemini-3.7-flash",
            **ai,
        },
    )


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _context(**overrides: object) -> TransactionContext:
    base: dict[str, object] = {
        "transaction_id": "tx-1",
        "amount": 480.0,
        "currency": "INR",
        "direction": "debit",
        "merchant_raw": "BLUE BOTTLE COFFEE",
        "merchant_normalized": "BLUE BOTTLE COFFEE",
        "description": "Cappuccino and croissant",
        "transaction_type": "purchase",
        "payment_method": "UPI",
        "account": "HDFC Savings",
        "card_last4": "4321",
    }
    base.update(overrides)
    return TransactionContext(**base)  # type: ignore[arg-type]


def _chat_response(content: dict[str, object], model: str = "google/gemini-3.7-flash") -> dict:
    return {"model": model, "choices": [{"message": {"content": json.dumps(content)}}]}


CLASSIFICATION = {
    "category_id": "food",
    "subcategory_id": "food-cafe",
    "confidence": 0.92,
    "signals": ["merchant is a coffee shop"],
}


class _Recorder:
    """Transport stub: returns queued responses (or raises queued exceptions)."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


# --------------------------------------------------------------------------- chat models


def test_chat_classification_parses_structured_output(tmp_path: Path) -> None:
    transport = _Recorder([_chat_response(CLASSIFICATION)])
    provider = OpenRouterProvider(_settings(tmp_path), transport=transport)

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert result.category_id == "food"
    assert result.subcategory_id == "food-cafe"
    assert result.confidence == 0.92
    assert result.model_used == "google/gemini-3.7-flash"

    path, payload = transport.calls[0]
    assert path == "/chat/completions"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["messages"][0]["role"] == "system"


def test_payload_carries_only_sanitized_fields(tmp_path: Path) -> None:
    transport = _Recorder([_chat_response(CLASSIFICATION)])
    provider = OpenRouterProvider(_settings(tmp_path), transport=transport)

    provider.classify_transaction(_context(), TAXONOMY)

    body = json.dumps(transport.calls[0][1])
    assert "4321" not in body  # card_last4 is deliberately not sent
    assert "test-key" not in body  # the key travels in headers only
    assert "BLUE BOTTLE COFFEE" in body


def test_chat_falls_back_to_the_next_model(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            AIProviderError("OpenRouter 503: upstream overloaded"),
            _chat_response(CLASSIFICATION, model="google/gemini-3.6-flash"),
        ]
    )
    provider = OpenRouterProvider(
        _settings(
            tmp_path,
            fallback_models=["google/gemini-3.7-flash", "google/gemini-3.6-flash"],
        ),
        transport=transport,
    )

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert result.model_used == "google/gemini-3.6-flash"
    assert [call[1]["model"] for call in transport.calls] == [
        "google/gemini-3.7-flash",
        "google/gemini-3.6-flash",
    ]


def test_structured_output_rejection_retries_prompt_only(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            AIProviderError("OpenRouter rejected the request (400): response_format unsupported"),
            _chat_response(CLASSIFICATION),
        ]
    )
    provider = OpenRouterProvider(_settings(tmp_path, fallback_models=[]), transport=transport)

    provider.classify_transaction(_context(), TAXONOMY)

    assert "response_format" in transport.calls[0][1]
    assert "response_format" not in transport.calls[1][1]


def test_taxonomy_is_compacted_and_ids_are_remapped(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            _chat_response(
                {
                    "category_id": "c01",
                    "subcategory_id": "s01",
                    "confidence": 0.9,
                    "signals": [],
                }
            )
        ]
    )
    provider = OpenRouterProvider(_settings(tmp_path, fallback_models=[]), transport=transport)

    result = provider.classify_transaction(_context(), TAXONOMY)

    prompt = transport.calls[0][1]["messages"][1]["content"]
    assert '"c01"' in prompt and '"s01"' in prompt
    assert "food-cafe" not in prompt  # real ids are never sent
    assert result.category_id == "food"
    assert result.subcategory_id == "food-cafe"


def test_reasoning_is_disabled_by_default(tmp_path: Path) -> None:
    transport = _Recorder([_chat_response(CLASSIFICATION)])
    provider = OpenRouterProvider(_settings(tmp_path), transport=transport)

    provider.classify_transaction(_context(), TAXONOMY)

    assert transport.calls[0][1]["reasoning"] == {"enabled": False}


def test_reasoning_can_be_left_to_the_provider(tmp_path: Path) -> None:
    transport = _Recorder([_chat_response(CLASSIFICATION)])
    provider = OpenRouterProvider(_settings(tmp_path, disable_reasoning=False), transport=transport)

    provider.classify_transaction(_context(), TAXONOMY)

    assert "reasoning" not in transport.calls[0][1]


def test_reasoning_flag_is_dropped_when_the_endpoint_mandates_it(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            AIProviderError(
                "OpenRouter rejected the request (400): Reasoning is mandatory for this "
                "endpoint and cannot be disabled."
            ),
            _chat_response(CLASSIFICATION),
        ]
    )
    provider = OpenRouterProvider(
        _settings(tmp_path, fallback_models=[], disable_reasoning=True),
        transport=transport,
    )

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert transport.calls[0][1]["reasoning"] == {"enabled": False}
    assert "reasoning" not in transport.calls[1][1]
    assert result.category_id == "food"


def test_malformed_model_output_is_a_provider_error(tmp_path: Path) -> None:
    transport = _Recorder([{"choices": [{"message": {"content": "not json at all"}}]}])
    provider = OpenRouterProvider(_settings(tmp_path, fallback_models=[]), transport=transport)

    with pytest.raises(AIProviderError, match="malformed structured output"):
        provider.classify_transaction(_context(), TAXONOMY)


# --------------------------------------------------------------------------- Jev / System One


def _system_one(answer: dict, model: str = "typesafe/jev-1.13-20260917") -> dict:
    return {"model": model, "answers": {"classification": answer}}


def test_jev_single_choice_maps_subcategory_to_its_category(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            _system_one(
                {
                    "type": "choice",
                    "choice": "s0101",
                    "confidence": 0.96,
                    "probabilities": {"s0101": 0.96, "s0102": 0.02, "c01": 0.01},
                }
            )
        ]
    )
    provider = OpenRouterProvider(
        _settings(tmp_path, model="typesafe/jev-1.13", fallback_models=[]),
        transport=transport,
    )

    result = provider.classify_transaction(_context(), TAXONOMY)

    path, payload = transport.calls[0]
    assert path == "/systemone"
    assert list(payload["questions"]) == ["classification"]  # one question, not two
    criteria = payload["questions"]["classification"]["criteria"]
    assert set(criteria) == {"c01", "c02", "s0101", "s0102", "s0201"}
    assert criteria["s0101"] == "Food › Cafes"
    assert result.category_id == "food"
    assert result.subcategory_id == "food-cafe"
    assert result.confidence == pytest.approx(0.96)
    assert any(signal.startswith("margin=") for signal in result.signals)


def test_jev_category_only_choice_leaves_subcategory_empty(tmp_path: Path) -> None:
    transport = _Recorder([_system_one({"type": "choice", "choice": "c02", "confidence": 0.8})])
    provider = OpenRouterProvider(
        _settings(tmp_path, model="typesafe/jev-1.13", fallback_models=[]),
        transport=transport,
    )

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert result.category_id == "utilities"
    assert result.subcategory_id is None


def test_jev_unknown_label_is_a_provider_error(tmp_path: Path) -> None:
    transport = _Recorder([_system_one({"type": "choice", "choice": "does-not-exist"})])
    provider = OpenRouterProvider(
        _settings(tmp_path, model="typesafe/jev-1.13", fallback_models=[]),
        transport=transport,
    )

    with pytest.raises(AIProviderError, match="unknown label"):
        provider.classify_transaction(_context(), TAXONOMY)


def test_jev_falls_back_to_a_chat_model_when_it_fails(tmp_path: Path) -> None:
    transport = _Recorder(
        [
            AIProviderError("OpenRouter 503: unavailable"),
            _chat_response(CLASSIFICATION, model="google/gemini-3.7-flash"),
        ]
    )
    provider = OpenRouterProvider(
        _settings(
            tmp_path,
            model="typesafe/jev-1.13",
            fallback_models=["google/gemini-3.7-flash"],
        ),
        transport=transport,
    )

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert transport.calls[0][0] == "/systemone"
    assert transport.calls[1][0] == "/chat/completions"
    assert result.model_used == "google/gemini-3.7-flash"


# --------------------------------------------------------------------------- configuration


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(MissingAPIKeyError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(_settings(tmp_path), transport=_Recorder([]))


def test_external_ai_gate_is_enforced(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.privacy.allow_external_ai = False

    with pytest.raises(ExternalAIOptInRequired):
        OpenRouterProvider(settings, transport=_Recorder([]))


def test_factory_selects_openrouter(tmp_path: Path) -> None:
    assert isinstance(get_ai_provider(_settings(tmp_path)), OpenRouterProvider)


# --------------------------------------------------------------------------- HTTP behaviour


def _http_error(
    status: int, body: bytes, headers: dict[str, str] | None = None
) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://openrouter.ai/api/v1/chat/completions",
        status,
        "error",
        headers or {},  # type: ignore[arg-type]
        io.BytesIO(body),
    )


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_http_401_is_permanent_and_not_retried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[object] = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        raise _http_error(401, b'{"error": {"message": "invalid api key"}}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = OpenRouterProvider(_settings(tmp_path, max_attempts=3))

    with pytest.raises(AIProviderError, match="401"):
        provider.classify_transaction(_context(), TAXONOMY)

    assert len(calls) == 1


def test_http_429_retries_and_honours_retry_after(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sleeps: list[float] = []
    responses = [
        _http_error(429, b'{"error": {"message": "rate limited"}}', {"Retry-After": "2"}),
        _Response(_chat_response(CLASSIFICATION)),
    ]

    def fake_urlopen(request, timeout=None):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(provider_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    provider = OpenRouterProvider(_settings(tmp_path, max_attempts=2))

    result = provider.classify_transaction(_context(), TAXONOMY)

    assert result.category_id == "food"
    assert sleeps == [2.0]


def test_error_envelope_in_a_200_response_is_surfaced(tmp_path: Path) -> None:
    transport = _Recorder([{"error": {"message": "no credits remaining", "code": 402}}])
    provider = OpenRouterProvider(_settings(tmp_path, fallback_models=[]), transport=transport)

    with pytest.raises(AIProviderError, match="no credits remaining"):
        provider.classify_transaction(_context(), TAXONOMY)
