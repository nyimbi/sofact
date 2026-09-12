"""The advisor's wire protocol, over a real HTTP server.

The model is the one boundary the project allows to be faked, and even here the fake
is a real server: ``pytest-httpserver`` listens on a real socket, so the request the
client builds is the request under test. Nothing is stubbed, and the client is the
real :class:`~sofact.llm.LlmClient`.

What matters is the *failure* behaviour. This module may fail — it is an advisor, not
a gate — but it is required to say so out loud rather than returning a plausible
shrug. A blank completion, a reasoning-only completion, an HTML error page, and a
closed port all have to arrive at the caller as the same honest
:class:`~sofact.llm.LlmUnavailable`.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError
from pytest_httpserver import HTTPServer

from sofact.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, LlmClient, LlmConfig, LlmUnavailable

CLOSED_PORT = "http://127.0.0.1:9/v1"
CHAT_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"


def client_for(
	httpserver: HTTPServer,
	*,
	model: str = "test-model",
	api_key: str = "test-key",
	max_tokens: int = 64,
	temperature: float = 0.0,
) -> LlmClient:
	"""A real client aimed at the live test server."""
	return LlmClient(
		LlmConfig(
			base_url=httpserver.url_for("/v1"),
			model=model,
			api_key=api_key,
			max_tokens=max_tokens,
			temperature=temperature,
			timeout_seconds=5.0,
		),
	)


def reply(content: str, **extra: object) -> dict[str, object]:
	"""A chat-completions body carrying ``content``."""
	message: dict[str, object] = {"role": "assistant", "content": content, **extra}
	return {"choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #


def test_the_defaults_point_at_a_local_openai_compatible_endpoint() -> None:
	config = LlmConfig()

	assert config.base_url == DEFAULT_BASE_URL == "http://localhost:11434/v1"
	assert config.model == DEFAULT_MODEL
	assert config.max_tokens > 0
	assert 0.0 <= config.temperature <= 2.0


def test_the_default_model_is_cloud_hosted_which_is_why_it_is_not_hermetic() -> None:
	"""ADR-0002's trigger, pinned: ``:cloud`` means the weights are not on this machine."""
	assert DEFAULT_MODEL.endswith(":cloud")


def test_config_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("SOFACT_BASE_URL", "http://example.test/v1")
	monkeypatch.setenv("SOFACT_MODEL", "some-model")
	monkeypatch.setenv("SOFACT_API_KEY", "sekrit")
	monkeypatch.setenv("SOFACT_LLM_TIMEOUT", "7.5")
	monkeypatch.setenv("SOFACT_LLM_MAX_TOKENS", "256")
	monkeypatch.setenv("SOFACT_LLM_TEMPERATURE", "0.9")

	config = LlmConfig.from_env()

	assert config.base_url == "http://example.test/v1"
	assert config.model == "some-model"
	assert config.api_key == "sekrit"
	assert config.timeout_seconds == 7.5
	assert config.max_tokens == 256
	assert config.temperature == 0.9


def test_config_falls_back_to_the_defaults_when_the_environment_is_silent(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	for name in (
		"SOFACT_BASE_URL",
		"SOFACT_MODEL",
		"SOFACT_API_KEY",
		"SOFACT_LLM_TIMEOUT",
		"SOFACT_LLM_MAX_TOKENS",
		"SOFACT_LLM_TEMPERATURE",
	):
		monkeypatch.delenv(name, raising=False)

	config = LlmConfig.from_env()

	assert config.base_url == DEFAULT_BASE_URL
	assert config.model == DEFAULT_MODEL
	assert config.timeout_seconds == 120.0
	assert config.max_tokens == 1024


@pytest.mark.parametrize(
	"build",
	[
		pytest.param(lambda: LlmConfig(timeout_seconds=0.0), id="zero-timeout"),
		pytest.param(lambda: LlmConfig(timeout_seconds=-1.0), id="negative-timeout"),
		pytest.param(lambda: LlmConfig(max_tokens=0), id="zero-max-tokens"),
		pytest.param(lambda: LlmConfig(max_tokens=-5), id="negative-max-tokens"),
		pytest.param(lambda: LlmConfig(temperature=-0.1), id="negative-temperature"),
		pytest.param(lambda: LlmConfig(temperature=2.5), id="temperature-above-range"),
		pytest.param(lambda: LlmConfig(base_url=""), id="blank-base-url"),
		pytest.param(lambda: LlmConfig(model=""), id="blank-model"),
		pytest.param(lambda: LlmConfig(api_key=""), id="blank-api-key"),
	],
)
def test_config_refuses_an_impossible_setting(build: Callable[[], LlmConfig]) -> None:
	with pytest.raises(ValidationError):
		build()


def test_the_repr_names_the_model_and_the_endpoint(httpserver: HTTPServer) -> None:
	client = client_for(httpserver)
	rendered = repr(client)

	assert "test-model" in rendered
	assert client.config.base_url in rendered


# --------------------------------------------------------------------------- #
# availability: absence is an answer, never an exception
# --------------------------------------------------------------------------- #


async def test_available_is_true_when_the_endpoint_lists_models(httpserver: HTTPServer) -> None:
	httpserver.expect_request(MODELS_PATH, method="GET").respond_with_json({"data": [{"id": "m"}]})

	assert await client_for(httpserver).available() is True


async def test_available_is_false_when_the_endpoint_errors(httpserver: HTTPServer) -> None:
	httpserver.expect_request(MODELS_PATH, method="GET").respond_with_json({}, status=500)

	assert await client_for(httpserver).available() is False


async def test_available_is_false_when_the_body_is_not_json(httpserver: HTTPServer) -> None:
	httpserver.expect_request(MODELS_PATH, method="GET").respond_with_data(
		"<html>gateway</html>", content_type="application/json"
	)

	assert await client_for(httpserver).available() is False


async def test_available_is_false_when_nothing_is_listening_not_an_exception() -> None:
	client = LlmClient(LlmConfig(base_url=CLOSED_PORT, timeout_seconds=2.0))

	assert await client.available() is False


# --------------------------------------------------------------------------- #
# completion
# --------------------------------------------------------------------------- #


async def test_complete_sends_exactly_the_request_the_endpoint_expects(
	httpserver: HTTPServer,
) -> None:
	"""The body is matched field for field, so a drifted request cannot pass."""
	httpserver.expect_request(
		CHAT_PATH,
		method="POST",
		json={
			"model": "test-model",
			"messages": [
				{"role": "system", "content": "be terse"},
				{"role": "user", "content": "what is missing?"},
			],
			"max_tokens": 64,
			"temperature": 0.0,
			"stream": False,
		},
		headers={"Authorization": "Bearer test-key", "Content-Type": "application/json"},
	).respond_with_json(reply("  add an oracle  "))

	content = await client_for(httpserver).complete(system="be terse", user="what is missing?")

	assert content == "add an oracle"


async def test_the_authorization_header_carries_the_configured_key(httpserver: HTTPServer) -> None:
	"""The key is read from config, not hardcoded — a different key must be sent."""
	httpserver.expect_request(
		CHAT_PATH, method="POST", headers={"Authorization": "Bearer another-key"}
	).respond_with_json(reply("ok"))

	client = client_for(httpserver, api_key="another-key")
	assert await client.complete(system="s", user="u") == "ok"


async def test_empty_content_is_failure_not_an_empty_opinion(httpserver: HTTPServer) -> None:
	"""A reasoning model can exhaust its budget inside the hidden channel and return
	"", which looks like success at the HTTP layer and is useless at this one."""
	httpserver.expect_request(CHAT_PATH, method="POST").respond_with_json(reply(""))

	with pytest.raises(LlmUnavailable) as caught:
		await client_for(httpserver).complete(system="s", user="u")

	assert "no content at all" in str(caught.value)


async def test_a_reasoning_only_reply_says_so(httpserver: HTTPServer) -> None:
	httpserver.expect_request(CHAT_PATH, method="POST").respond_with_json(
		reply("", reasoning="thinking about it")
	)

	with pytest.raises(LlmUnavailable) as caught:
		await client_for(httpserver).complete(system="s", user="u")

	assert "only a reasoning channel" in str(caught.value)


async def test_an_http_error_names_the_status_and_a_snippet_of_the_body(
	httpserver: HTTPServer,
) -> None:
	httpserver.expect_request(CHAT_PATH, method="POST").respond_with_json(
		{"error": {"message": "model not found"}}, status=503
	)

	with pytest.raises(LlmUnavailable) as caught:
		await client_for(httpserver).complete(system="s", user="u")

	message = str(caught.value)
	assert "503" in message
	assert "model not found" in message


@pytest.mark.parametrize("body", ["no choices", "an empty choice list", "not json at all"])
async def test_an_unusable_body_is_reported_not_ignored(httpserver: HTTPServer, body: str) -> None:
	handler = httpserver.expect_request(CHAT_PATH, method="POST")
	if body == "no choices":
		handler.respond_with_json({"id": "x"})
	elif body == "an empty choice list":
		handler.respond_with_json({"choices": []})
	else:
		handler.respond_with_data("<html>nope</html>", content_type="application/json")

	with pytest.raises(LlmUnavailable) as caught:
		await client_for(httpserver).complete(system="s", user="u")

	assert "unusable body" in str(caught.value)


async def test_an_unreachable_endpoint_becomes_llm_unavailable() -> None:
	"""A closed socket must not leak httpx's exception type into the caller."""
	client = LlmClient(LlmConfig(base_url=CLOSED_PORT, timeout_seconds=2.0))

	with pytest.raises(LlmUnavailable) as caught:
		await client.complete(system="s", user="u")

	assert "unreachable" in str(caught.value)


@pytest.mark.parametrize(("system", "user"), [("   ", "u"), ("s", "\t\n"), ("", "u")])
async def test_a_blank_prompt_is_refused_before_any_request_is_made(
	httpserver: HTTPServer, system: str, user: str
) -> None:
	with pytest.raises(AssertionError):
		await client_for(httpserver).complete(system=system, user=user)

	assert (
		httpserver.get_matching_requests_count(httpserver.create_matcher(CHAT_PATH, method="POST"))
		== 0
	)
