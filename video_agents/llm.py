"""Обёртка над Claude API: структурированные ответы и ресёрч с веб-поиском."""

from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# При отказе модели запрос автоматически повторяется на подходящей модели-замене.
# Серверная замена есть не у всех моделей: у Haiku её нет, и параметр вызвал бы ошибку.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
MAX_PAUSE_CONTINUATIONS = 5

# Цены Claude API, $ за 1 млн токенов (вход, выход); веб-поиск - $10 за 1000 запросов.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.0, 50.0),
}
WEB_SEARCH_PRICE = 0.01


class CostLedger:
    """Журнал расходов: сколько стоил каждый вызов и на каком этапе (идеи, сценарий, ...)."""

    def __init__(self):
        self.entries: list[tuple[str, float]] = []

    def add(self, stage: str, cost: float) -> None:
        self.entries.append((stage, cost))

    def mark(self) -> int:
        return len(self.entries)

    def since(self, mark: int) -> dict[str, float]:
        totals: dict[str, float] = {}
        for stage, cost in self.entries[mark:]:
            totals[stage] = totals.get(stage, 0.0) + cost
        return totals


def estimate_cost(model: str, usage) -> float:
    """Примерная стоимость ответа по счётчику токенов; для неизвестной модели - 0."""
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    cost = tokens_in * price_in / 1e6 + (usage.output_tokens or 0) * price_out / 1e6
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    return cost + searches * WEB_SEARCH_PRICE


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, model: str = "claude-opus-5-5", client: anthropic.Anthropic | None = None,
                 ledger: CostLedger | None = None, stage: str = "other"):
        self.model = model
        self.client = client or anthropic.Anthropic()
        self.ledger = ledger
        self.stage = stage

    def _fallback(self) -> dict:
        if self.model in FALLBACK_MODELS:
            return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return {}

    def _record(self, response) -> None:
        if self.ledger is not None:
            # При отказе ответ мог прийти от модели-замены - считаем по её ценам.
            model = response.model if response.model in PRICES else self.model
            self.ledger.add(self.stage, estimate_cost(model, response.usage))

    def structured(
        self,
        *,
        system: str,
        prompt: str | list[dict],
        output_model: type[T],
        effort: str = "high",
        max_tokens: int = 16000,
    ) -> T:
        """Один запрос, ответ валидируется по pydantic-модели. prompt - текст или блоки (текст + картинки)."""
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_model,
            output_config={"effort": effort},
            **self._fallback(),
        )
        self._record(response)
        self._check_stop(response)
        if response.parsed_output is None:
            raise LLMError(f"Модель не вернула {output_model.__name__} (request {response._request_id})")
        return response.parsed_output

    def research(self, *, system: str, prompt: str, effort: str = "medium", max_searches: int = 5) -> str:
        """Свободный текст с веб-поиском (поиск выполняется на стороне Anthropic)."""
        messages: list = [{"role": "user", "content": prompt}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}]
        for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=messages,
                tools=tools,
                output_config={"effort": effort},
                **self._fallback(),
            )
            self._record(response)
            if response.stop_reason != "pause_turn":
                break
            # Длинный серверный поиск: отдаём ответ обратно, чтобы модель продолжила.
            messages.append({"role": "assistant", "content": response.content})
        self._check_stop(response)
        return "\n".join(block.text for block in response.content if block.type == "text").strip()

    @staticmethod
    def _check_stop(response) -> None:
        if response.stop_reason == "refusal":
            details = response.stop_details
            reason = f"{details.category}: {details.explanation}" if details else "без пояснений"
            raise LLMError(f"Модель отказалась отвечать ({reason})")
        if response.stop_reason == "max_tokens":
            raise LLMError("Ответ обрезан по max_tokens")
