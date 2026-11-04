import json
import unittest

from Parser.config import GeminiConfig
from Parser.errors import ProviderSchemaError
from Parser.extraction_schema import ExtractionEnvelope, provider_schema
from Parser.gemini_client import GeminiClient


class FakeResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeSdk:
    def __init__(self, response):
        self.models = FakeModels(response)


class GeminiClientTests(unittest.TestCase):
    def client(self, response):
        sdk = FakeSdk(response)
        client = GeminiClient(GeminiConfig(api_key="offline", retries=0), sdk_client=sdk)
        return client, sdk

    def test_provider_schema_removes_only_additional_properties(self):
        schema = provider_schema()
        serialized = json.dumps(schema)
        self.assertNotIn("additionalProperties", serialized)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["properties"]), {"tasks"})
        self.assertIn("$defs", schema)
        self.assertIn("ExtractedTask", schema["$defs"])
        self.assertIn("title", schema["$defs"]["ExtractedTask"]["properties"])

    def test_submits_provider_schema_and_parses_mapping(self):
        client, sdk = self.client(FakeResponse(parsed={"tasks": [{"title": "Lab", "type": "assignment"}]}))
        result = client.extract("extract")
        submitted = sdk.models.calls[0]["config"]["response_schema"]
        self.assertIsInstance(result, ExtractionEnvelope)
        self.assertEqual(result.tasks[0].title, "Lab")
        self.assertNotIn("additionalProperties", json.dumps(submitted))
        self.assertEqual(submitted["properties"]["tasks"]["type"], "array")

    def test_malformed_output_raises_provider_schema_error(self):
        client, sdk = self.client(FakeResponse(text='{"tasks": [{"unexpected": true}]}'))
        with self.assertRaises(ProviderSchemaError):
            client.extract("extract")
        self.assertEqual(len(sdk.models.calls), 1)

    def test_offline_fake_does_not_make_network_call(self):
        client, sdk = self.client(FakeResponse(text='{"tasks": []}'))
        result = client.extract("extract")
        self.assertEqual(result.tasks, [])
        self.assertEqual(len(sdk.models.calls), 1)


if __name__ == "__main__":
    unittest.main()
