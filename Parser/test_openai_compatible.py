import json
import os
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from Parser.config import OpenAICompatibleConfig
from Parser.errors import (
    ConfigurationError,
    ProviderAuthenticationError,
    ProviderEmptyResponseError,
    ProviderPermissionError,
    ProviderRequestError,
    ProviderSchemaError,
)
from Parser.factory import create_llm_gateway
from Parser.openai_compatible_client import OpenAICompatibleClient, chat_completions_url


class FakeResponse:
    def __init__(self, value):
        self.value = value
        self.closed = False

    def read(self):
        return json.dumps(self.value).encode()

    def close(self):
        self.closed = True


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []
        self.timeouts = []
        self.responses = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        response = FakeResponse(self.response)
        self.responses.append(response)
        return response


def response(content):
    return {"choices": [{"message": {"content": content}}]}


class OpenAICompatibleTests(unittest.TestCase):
    def config(self, **kwargs):
        return OpenAICompatibleConfig(api_key="secret", retries=0, **kwargs)

    def test_config_defaults_and_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            config = OpenAICompatibleConfig.from_env(require_key=False)
        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.model, "gpt-4o-mini")
        self.assertEqual(config.response_format, "json_object")
        with self.assertRaises(ConfigurationError):
            OpenAICompatibleConfig(response_format="xml")
        for field, value in (
            ("base_url", None), ("model", 1), ("response_format", None),
            ("max_input_chars", "30000"), ("max_output_tokens", 1.5),
            ("timeout_seconds", "30"), ("retries", 1.5), ("temperature", "0"),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ConfigurationError):
                    OpenAICompatibleConfig(**{field: value})

    def test_endpoint_construction(self):
        self.assertEqual(chat_completions_url("https://host/v1/"), "https://host/v1/chat/completions")
        self.assertEqual(chat_completions_url("https://host/custom/chat/completions"), "https://host/custom/chat/completions")

    def test_request_body_and_headers_for_each_format(self):
        for mode in ("json_schema", "json_object", "none"):
            opener = FakeOpener(response('{"tasks": []}'))
            OpenAICompatibleClient(self.config(response_format=mode), opener=opener).extract("hello")
            self.assertTrue(opener.responses[0].closed)
            request = opener.requests[0]
            body = json.loads(request.data)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(request.get_header("Authorization"), "Bearer secret")
            self.assertEqual(body["messages"], [{"role": "user", "content": "hello"}])
            if mode == "none":
                self.assertNotIn("response_format", body)
            elif mode == "json_object":
                self.assertEqual(body["response_format"], {"type": "json_object"})
            else:
                self.assertEqual(body["response_format"]["type"], "json_schema")

    def test_content_variants_and_validation(self):
        for content in ('{"tasks": []}', '```json\n{"tasks": []}\n```', [{"type": "text", "text": '{"tasks": []}'}]):
            opener = FakeOpener(response(content))
            self.assertEqual(OpenAICompatibleClient(self.config(), opener=opener).extract("x").tasks, [])
        with self.assertRaises(ProviderSchemaError):
            OpenAICompatibleClient(self.config(), opener=FakeOpener(response('{"tasks":[{"unexpected":true}]}'))).extract("x")
        with self.assertRaises(ProviderEmptyResponseError):
            OpenAICompatibleClient(self.config(), opener=FakeOpener({"choices": []})).extract("x")

    def test_http_mapping_and_retry_counts(self):
        for status, error_type, retries in ((401, ProviderAuthenticationError, 0), (403, ProviderPermissionError, 0), (400, ProviderRequestError, 0), (429, ProviderRequestError, 2), (500, ProviderRequestError, 2)):
            opener = FakeOpener(error=HTTPError("http://host", status, "bad", {}, None))
            sleeps = []
            client = OpenAICompatibleClient(OpenAICompatibleConfig(api_key="secret", retries=retries), opener=opener, sleep=sleeps.append, random_value=lambda: 0)
            with self.assertRaises(error_type):
                client.extract("x")
            self.assertEqual(len(opener.requests), retries + 1)
            self.assertEqual(len(sleeps), retries)
        opener = FakeOpener(error=socket.timeout())
        sleeps = []
        with self.assertRaises(ProviderRequestError):
            OpenAICompatibleClient(OpenAICompatibleConfig(api_key="secret", retries=1), opener=opener, sleep=sleeps.append).extract("x")
        self.assertEqual(len(opener.requests), 2)

    def test_factory_selection_is_lazy_and_aliases_work(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "secret"}, clear=False):
            with patch("Parser.openai_compatible_client.OpenAICompatibleClient") as constructor:
                create_llm_gateway()
                constructor.assert_called_once()
        with self.assertRaises(ConfigurationError):
            create_llm_gateway("not-a-provider")


if __name__ == "__main__":
    unittest.main()
