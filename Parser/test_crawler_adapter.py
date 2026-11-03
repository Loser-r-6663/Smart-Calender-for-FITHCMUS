import json
from datetime import datetime, timezone
import unittest

from Parser import CrawlerAdapterError, SourcePlatform, adapt_crawl_results
from Parser.llm_parser import LLMParser


class RawTask:
    Title = "Nộp bài"
    Type = "assignment"
    Description = "Mô tả tiếng Việt"
    CreateDate = "2026-11-03"
    Duration = "2h"
    Deadline = "2026-11-10"
    Course = "CT101"
    Content = "Nội dung"
    Link = "https://example.test/task"


class DumpedRecord:
    def model_dump(self):
        return {"Title": "Dumped", "Link": "N/A", "Content": "x"}


class FakeGateway:
    def __init__(self):
        self.prompts = []

    def extract(self, prompt):
        self.prompts.append(prompt)
        return {"tasks": [{"title": "Nộp bài", "type": "assignment"}]}


class CrawlerAdapterTests(unittest.TestCase):
    def test_raw_task_mapping_sources_and_shared_timestamp(self):
        captured = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
        result = adapt_crawl_results(
            {"Portal": [RawTask()], "Moodle": [{"Title": "Moodle", "link": "https://example.test/moodle"}], "FB": [{"Time": "10:00", "Content": "Tin"}], "FIT": [], "New": [{"Title": "Custom"}]},
            captured_at=captured,
        )
        self.assertEqual([item.source_platform for item in result], [SourcePlatform.PORTAL, SourcePlatform.MOODLE, SourcePlatform.FACEBOOK, SourcePlatform.CUSTOM])
        self.assertEqual({item.captured_at for item in result}, {captured})
        self.assertEqual(result[0].source_alias, "Portal")
        self.assertEqual(result[0].source_url, "https://example.test/task")
        self.assertEqual(result[1].source_url, "https://example.test/moodle")
        self.assertIn("Nộp bài", result[0].payload)
        self.assertEqual(json.loads(result[2].payload)["record"]["Time"], "10:00")

    def test_model_dump_and_deterministic_serialization(self):
        first = adapt_crawl_results({"Portal": [DumpedRecord()]}, captured_at=datetime(2026, 1, 1))
        second = adapt_crawl_results({"Portal": [DumpedRecord()]}, captured_at=datetime(2026, 1, 1))
        self.assertEqual(first[0].payload, second[0].payload)
        self.assertIn('"Link":null', first[0].payload)
        self.assertIsNone(first[0].source_url)

    def test_adapter_to_llm_parser_fake_gateway(self):
        raw = adapt_crawl_results({"FB": [{"Content": "Lịch học"}]}, captured_at=datetime(2026, 1, 1))[0]
        gateway = FakeGateway()
        tasks = LLMParser(gateway).parse(raw)
        self.assertEqual(tasks[0].title, "Nộp bài")
        self.assertIn("platform=facebook", gateway.prompts[0])

    def test_invalid_inputs(self):
        for value in (None, [], "text"):
            with self.subTest(value=value):
                with self.assertRaises(CrawlerAdapterError):
                    adapt_crawl_results(value)
        with self.assertRaises(CrawlerAdapterError):
            adapt_crawl_results({"Portal": "not records"})
        with self.assertRaises(CrawlerAdapterError):
            adapt_crawl_results({"Portal": [object()]})


if __name__ == "__main__":
    unittest.main()
