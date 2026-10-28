"""Обёртка над Claude API: структурированные ответы и ресёрч с веб-поиском."""

from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# При отказе модели запрос автоматически повторяется на подходящей модели-замене.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_PAUSE_CONTINUATIONS = 5


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, model: str = "claude-opus-5-5", client: anthropic.Anthropic | None = None):
        self.model = model
        self.client = client or anthropic.Anthropic()

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
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
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
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
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
