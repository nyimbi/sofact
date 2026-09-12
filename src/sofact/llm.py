"""Advisory access to a local-interface LLM.

The model is an *advisor*. It sharpens questions, proposes what an answer might be
missing, and never decides anything: gates are deterministic
(:mod:`sofact.elicitation`) and verdicts are the verifier's. This module is therefore
allowed to fail, and is required to say so out loud rather than returning a
plausible shrug.

It talks to any OpenAI-compatible ``/chat/completions`` endpoint. Default is a local
Ollama daemon fronting ``deepseek-v4.1-flash:cloud`` — note ``:cloud`` means the
weights are *not* on this machine (ADR-0002).
"""

from __future__ import annotations

import os
from typing import Any, Self

import httpx
from pydantic import Field

from sofact.views import NonEmptyStr, View

__all__ = ["DEFAULT_BASE_URL", "DEFAULT_MODEL", "LlmClient", "LlmConfig", "LlmUnavailable"]

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash:cloud"


class LlmUnavailable(RuntimeError):
	"""The model could not be reached, or returned nothing usable."""


class LlmConfig(View):
	"""Where the model lives and how hard to lean on it."""

	base_url: NonEmptyStr = DEFAULT_BASE_URL
	model: NonEmptyStr = DEFAULT_MODEL
	api_key: NonEmptyStr = "ollama"
	timeout_seconds: float = Field(default=120.0, gt=0)
	max_tokens: int = Field(default=1024, gt=0)
	temperature: float = Field(default=0.3, ge=0.0, le=2.0)

	@classmethod
	def from_env(cls) -> Self:
		"""Read overrides from the environment, falling back to the defaults."""
		return cls(
			base_url=os.environ.get("SOFACT_BASE_URL", DEFAULT_BASE_URL),
			model=os.environ.get("SOFACT_MODEL", DEFAULT_MODEL),
			api_key=os.environ.get("SOFACT_API_KEY", "ollama"),
			timeout_seconds=float(os.environ.get("SOFACT_LLM_TIMEOUT", "120")),
			max_tokens=int(os.environ.get("SOFACT_LLM_MAX_TOKENS", "1024")),
			temperature=float(os.environ.get("SOFACT_LLM_TEMPERATURE", "0.3")),
		)


class LlmClient:
	"""Thin async client over an OpenAI-compatible chat endpoint."""

	def __init__(self, config: LlmConfig | None = None) -> None:
		self.config = config or LlmConfig.from_env()

	def __repr__(self) -> str:
		return f"LlmClient({self.config.model} @ {self.config.base_url})"

	@property
	def _headers(self) -> dict[str, str]:
		return {
			"Authorization": f"Bearer {self.config.api_key}",
			"Content-Type": "application/json",
		}

	async def available(self) -> bool:
		"""Whether the endpoint answers at all. Never raises; absence is an answer."""
		try:
			async with httpx.AsyncClient(timeout=5.0) as client:
				response = await client.get(f"{self.config.base_url}/models", headers=self._headers)
			return response.status_code == 200 and "data" in response.json()
		except (httpx.HTTPError, ValueError):
			return False

	async def complete(self, *, system: str, user: str) -> str:
		"""One non-streaming completion, or :class:`LlmUnavailable`.

		Empty content is treated as failure, not as an empty opinion. Reasoning
		models sometimes exhaust the token budget inside a hidden reasoning channel
		and return ``""`` with ``finish_reason: stop``; that looks like success at the
		HTTP layer and is useless at this one, so it is raised rather than passed on.
		"""
		assert system.strip(), "system prompt must not be blank"
		assert user.strip(), "user prompt must not be blank"
		body: dict[str, Any] = {
			"model": self.config.model,
			"messages": [
				{"role": "system", "content": system},
				{"role": "user", "content": user},
			],
			"max_tokens": self.config.max_tokens,
			"temperature": self.config.temperature,
			"stream": False,
		}
		try:
			async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
				response = await client.post(
					f"{self.config.base_url}/chat/completions",
					headers=self._headers,
					json=body,
				)
		except httpx.HTTPError as exc:
			raise LlmUnavailable(f"{self.config.base_url} unreachable: {exc}") from exc

		if response.status_code != 200:
			raise LlmUnavailable(
				f"{self.config.model} returned HTTP {response.status_code}: {response.text[:200]}"
			)

		try:
			message = response.json()["choices"][0]["message"]
		except (KeyError, IndexError, ValueError) as exc:
			raise LlmUnavailable(f"{self.config.model} returned an unusable body: {exc}") from exc

		content = (message.get("content") or "").strip()
		if not content:
			reasoning = (message.get("reasoning") or "").strip()
			detail = "only a reasoning channel, no content" if reasoning else "no content at all"
			raise LlmUnavailable(f"{self.config.model} produced {detail}")
		return content
