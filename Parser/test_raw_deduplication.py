import unittest

from Parser import (
    InMemoryRawFingerprintStore,
    RawCrawlerInput,
    RawDedupAction,
    RawDedupReason,
    RawDeduplicationError,
    RawDuplicateChecker,
    RawFingerprint,
    canonicalize_url,
    fingerprint_raw_input,
)


def raw(payload, url=None):
    return RawCrawlerInput(payload=payload, source_url=url)


class RawDeduplicationTests(unittest.TestCase):
    def test_url_canonicalization(self):
        self.assertEqual(canonicalize_url(" HTTPS://EXAMPLE.COM:443/Path/#fragment "), "https://example.com/Path")
        self.assertEqual(canonicalize_url("http://Example.com:8080/a/"), "http://example.com:8080/a")
        self.assertEqual(canonicalize_url("https://example.com"), "https://example.com/")

    def test_tracking_query_sorting_and_meaningful_parameters(self):
        self.assertEqual(
            canonicalize_url("https://EXAMPLE.com/p?utm_source=x&id=2&REF=z&id=1&blank=&gclid=x"),
            "https://example.com/p?blank=&id=1&id=2",
        )

    def test_url_rejection_and_path_case(self):
        self.assertEqual(canonicalize_url("https://example.com/CaSe?Name=VaLuE"), "https://example.com/CaSe?Name=VaLuE")
        for value in ("", "example.com/path", "https:///path", "https://", "https://bad host/x", "https://example.com:bad"):
            with self.subTest(value=value):
                with self.assertRaises(RawDeduplicationError):
                    canonicalize_url(value)

    def test_json_is_stable_and_ignores_source_metadata(self):
        first = raw('{"source":{"alias":"Portal"},"record":{"Link":"https://one","Title":"  Nộp   bài ","id":2}}', "https://one")
        second = raw('{"record":{"id":2,"source_url":"https://two","Title":"NỘP bài"},"source":{"alias":"Other"}}', "https://two")
        self.assertEqual(fingerprint_raw_input(first).content_hash, fingerprint_raw_input(second).content_hash)

    def test_vietnamese_bytes_and_invalid_payloads(self):
        value = fingerprint_raw_input(raw("Nộp bài   cuối kỳ")).content_hash
        self.assertEqual(value, fingerprint_raw_input(raw("NỘP bài cuối kỳ".encode())).content_hash)
        with self.assertRaises(RawDeduplicationError):
            fingerprint_raw_input(raw(b"\xff"))
        with self.assertRaises(RawDeduplicationError):
            fingerprint_raw_input(raw(123))

    def test_decisions_and_explicit_remember(self):
        checker = RawDuplicateChecker(InMemoryRawFingerprintStore())
        item = raw("alpha", "https://example.com/a")
        first = checker.check(item)
        self.assertEqual((first.action, first.reason), (RawDedupAction.PROCESS, RawDedupReason.NEW_RECORD))
        self.assertEqual(checker.check(item).reason, RawDedupReason.NEW_RECORD)
        checker.remember(first.fingerprint)
        self.assertEqual(checker.check(item).reason, RawDedupReason.UNCHANGED_URL)
        changed = checker.check(raw("beta", "https://example.com/a"))
        self.assertEqual((changed.action, changed.reason), (RawDedupAction.PROCESS, RawDedupReason.CHANGED_URL_CONTENT))

    def test_content_dedup_and_urlless_records(self):
        checker = RawDuplicateChecker(InMemoryRawFingerprintStore())
        first = checker.check(raw("same", "https://example.com/a"))
        checker.remember(first.fingerprint)
        duplicate = checker.check(raw("same", "https://example.com/b"))
        self.assertEqual(duplicate.reason, RawDedupReason.DUPLICATE_CONTENT)
        url_less = checker.check(raw("portal post"))
        checker.remember(url_less.fingerprint)
        self.assertEqual(checker.check(raw("portal post")).reason, RawDedupReason.DUPLICATE_CONTENT)

    def test_second_url_keeps_both_url_lookups_and_original_content(self):
        store = InMemoryRawFingerprintStore()
        first = RawFingerprint("https://example.com/a", "hash")
        second = RawFingerprint("https://example.com/b", "hash")
        store.remember(first)
        store.remember(second)
        self.assertEqual(store.find_by_url(first.canonical_url), first)
        self.assertEqual(store.find_by_url(second.canonical_url), second)
        self.assertEqual(store.find_by_content_hash("hash"), first)


if __name__ == "__main__":
    unittest.main()
