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
from typing import Any, Final, Self

import httpx
from pydantic import Field

from sofact.views import NonEmptyStr, View

__all__ = [
	"DEFAULT_BASE_URL",
	"DEFAULT_MAX_TOKENS",
	"DEFAULT_MODEL",
	"LlmClient",
	"LlmConfig",
	"LlmUnavailable",
]

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash:cloud"

DEFAULT_MAX_TOKENS: Final[int] = 4096
"""Enough for the deepest prompt this product writes, measured rather than guessed.

The default was 1024, and on the default model two of P0's six dimension prompts —
``boundary`` and ``failure`` — spent all 1024 inside the reasoning channel and
returned ``content: ""`` with ``finish_reason: length``. So the shipped default
could not complete the interrogation the front door exists to run, and the failure
arrived as a refusal about a reasoning channel rather than as a budget problem. At
4096 all six answer, with the longest at 2915 characters, so the floor is measured
against the worst prompt in the product rather than chosen for tidiness.

Raising a token cap is a spend decision, not a correctness one: this is a local
model by default (ADR-0002) and the cap only bounds a runaway, so the honest
default is the one that lets the product work.
"""

DEFAULT_MAX_TOKENS_ENV: Final[str] = "SOFACT_LLM_MAX_TOKENS"


class LlmUnavailable(RuntimeError):
	"""The model could not be reached, or returned nothing usable."""


def _why_no_content(message: dict[str, Any], choice: dict[str, Any], config: LlmConfig) -> str:
	"""Why an empty ``content`` happened, read off the reply rather than assumed.

	The first version of this said "only a reasoning channel, no content" whenever the
	reply carried a non-empty ``reasoning`` field, and that attribution is wrong for
	every provider that streams the chain of thought *beside* the answer instead of
	inside the budget — DeepSeek-R1, Qwen3 and friends return ``reasoning_content`` on
	perfectly good replies. The string asserted a cause the client had not checked, and
	a reader of a run that stopped at P0 was sent looking at the wrong thing.

	The cause is in the response. ``finish_reason == "length"`` means the budget was
	spent, and if a reasoning channel is also present then the budget was spent
	*inside* it — which is the case this refusal exists for, and the only one an
	operator can act on, since it is fixed by raising ``SOFACT_LLM_MAX_TOKENS``.
	Otherwise the model simply returned nothing, and saying so is the whole truth.
	"""
	channel = (message.get("reasoning") or message.get("reasoning_content") or "").strip()
	if choice.get("finish_reason") == "length":
		if channel:
			return (
				f"no content: the {config.max_tokens}-token budget went into a "
				f"{len(channel)}-character reasoning channel (finish_reason: length). "
				f"Raise {DEFAULT_MAX_TOKENS_ENV} above {config.max_tokens}."
			)
		return (
			f"no content: the {config.max_tokens}-token budget was spent before any was "
			f"written (finish_reason: length). Raise {DEFAULT_MAX_TOKENS_ENV}."
		)
	if channel:
		return "no content, only a reasoning channel"
	return "no content at all"


class LlmConfig(View):
	"""Where the model lives and how hard to lean on it."""

	base_url: NonEmptyStr = DEFAULT_BASE_URL
	model: NonEmptyStr = DEFAULT_MODEL
	api_key: NonEmptyStr = "ollama"
	timeout_seconds: float = Field(default=120.0, gt=0)
	max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, gt=0)
	temperature: float = Field(default=0.3, ge=0.0, le=2.0)

	@classmethod
	def from_env(cls) -> Self:
		"""Read overrides from the environment, falling back to the defaults."""
		return cls(
			base_url=os.environ.get("SOFACT_BASE_URL", DEFAULT_BASE_URL),
			model=os.environ.get("SOFACT_MODEL", DEFAULT_MODEL),
			api_key=os.environ.get("SOFACT_API_KEY", "ollama"),
			timeout_seconds=float(os.environ.get("SOFACT_LLM_TIMEOUT", "120")),
			max_tokens=int(os.environ.get(DEFAULT_MAX_TOKENS_ENV, str(DEFAULT_MAX_TOKENS))),
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
			# ``str(exc)`` is empty for every httpx transport error — ConnectError,
			# ConnectTimeout, ReadTimeout all stringify to "" — so the shipped message
			# read "http://localhost:11434/v1 unreachable: ." with the reason missing and
			# the sentence ending on a bare colon. The class name is the reason: a
			# timeout and a refused connection are different problems with different
			# fixes, and only the type distinguishes them.
			raise LlmUnavailable(
				f"{self.config.base_url} unreachable after {self.config.timeout_seconds:g}s: "
				f"{type(exc).__name__}"
			) from exc

		if response.status_code != 200:
			raise LlmUnavailable(
				f"{self.config.model} returned HTTP {response.status_code}: {response.text[:200]}"
			)

		try:
			choice = response.json()["choices"][0]
			message = choice["message"]
		except (KeyError, IndexError, ValueError) as exc:
			raise LlmUnavailable(f"{self.config.model} returned an unusable body: {exc}") from exc

		content = (message.get("content") or "").strip()
		if not content:
			raise LlmUnavailable(
				f"{self.config.model} produced {_why_no_content(message, choice, self.config)}"
			)
		return content
