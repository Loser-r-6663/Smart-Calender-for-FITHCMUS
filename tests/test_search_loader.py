"""Offline session checks using real repositories with mocked HTTP reads."""

import unittest
from unittest.mock import Mock, patch

import requests

from academic_search import SearchAuthenticationError, SearchLoadError, load_snapshot
from test_search_records import SHARED_ID, task

USER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
URL = "https://search.example.invalid"
PUBLIC_KEY = "fictional-public-client-key"


def row(title):
    return task(title=title).model_dump(mode="json")


def response(rows=None, status=200):
    result = Mock()
    result.ok = status < 400
    result.status_code = status
    result.reason = "Rejected" if status >= 400 else "OK"
    result.json.return_value = [] if rows is None else rows
    return result


class SearchLoaderTests(unittest.TestCase):
    def setUp(self):
        self.get_patch = patch("requests.get")
        self.get = self.get_patch.start()
        self.addCleanup(self.get_patch.stop)
        self.write_patch = patch("requests.post", side_effect=AssertionError("Unexpected write"))
        self.write_patch.start()
        self.addCleanup(self.write_patch.stop)

    def load(self, **session):
        return load_snapshot(supabase_url=URL, public_key=PUBLIC_KEY, limit=23, **session)

    def test_guest_loads_only_public_with_explicit_key(self):
        self.get.return_value = response([row("Public notice")])
        with patch("Database.Repository.user_task_repository.UserTaskRepository") as personal:
            snapshot = self.load()
            personal.assert_not_called()
        self.get.assert_called_once()
        args = self.get.call_args
        self.assertEqual(args.args, (URL + "/rest/v1/tasks",))
        self.assertEqual(args.kwargs["params"], {"select": "*", "limit": 23, "offset": 0, "order": "id.asc"})
        self.assertEqual(args.kwargs["headers"]["apikey"], PUBLIC_KEY)
        self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer " + PUBLIC_KEY)
        self.assertEqual(snapshot.loaded_scopes, ("public",))
        self.assertEqual(dict(snapshot.row_limits), {"public": 23})
        self.assertEqual([(r.key, r.title) for r in snapshot.records],
                         [(("public", SHARED_ID), "Public notice")])

    def test_accounts_load_their_own_records_and_details_from_full_keys(self):
        snapshots = []
        for owner, token, title in ((USER_A, "fictional-token-a", "Personal A"),
                                    (USER_B, "fictional-token-b", "Personal B")):
            with self.subTest(owner=owner):
                self.get.reset_mock()
                self.get.side_effect = [response([row("Public notice")]), response([row(title)])]
                snapshot = self.load(access_token=token, user_id=owner)
                snapshots.append(snapshot)
                self.assertEqual(self.get.call_count, 2)
                public_call, personal_call = self.get.call_args_list
                self.assertEqual(public_call.kwargs["headers"]["Authorization"], "Bearer " + PUBLIC_KEY)
                self.assertEqual(personal_call.args, (URL + "/rest/v1/user_task",))
                self.assertEqual(personal_call.kwargs["params"],
                                 {"select": "*", "limit": 23, "offset": 0, "order": "id.asc", "user_id": "eq." + owner})
                self.assertEqual(personal_call.kwargs["headers"]["apikey"], PUBLIC_KEY)
                self.assertEqual(personal_call.kwargs["headers"]["Authorization"], "Bearer " + token)
                self.assertEqual(snapshot.loaded_scopes, ("public", "personal"))
                self.assertEqual(dict(snapshot.row_limits), {"public": 23, "personal": 23})
                self.assertEqual(snapshot.get_task(("public", SHARED_ID)).title, "Public notice")
                self.assertEqual(snapshot.get_task(("personal", SHARED_ID)).title, title)
                self.assertIsNone(snapshot.get_task(("personal", USER_B)))
                self.assertIsNone(snapshot.get_task(("unknown", SHARED_ID)))
                self.assertEqual(self.get.call_count, 2)
        self.assertEqual(snapshots[0].get_task(("personal", SHARED_ID)).title, "Personal A")

    def test_incomplete_or_invalid_session_cannot_issue_any_request(self):
        for session in (
            {"access_token": "token"}, {"user_id": USER_A},
            {"access_token": "", "user_id": USER_A},
            {"access_token": "token", "user_id": ""},
            {"access_token": "  ", "user_id": USER_A},
            {"access_token": "token", "user_id": "not-a-uuid"},
        ):
            with self.subTest(session=session), self.assertRaises(SearchAuthenticationError):
                self.load(**session)
        self.get.assert_not_called()

    def test_empty_reads_still_report_loaded_scopes_and_limits(self):
        self.get.return_value = response()
        guest = self.load()
        self.assertEqual(guest.records, ())
        self.assertEqual(guest.loaded_scopes, ("public",))
        self.assertIsNone(guest.get_task(("personal", SHARED_ID)))
        self.get.reset_mock()
        signed_in = self.load(access_token="token", user_id=USER_A)
        self.assertEqual(signed_in.records, ())
        self.assertEqual(dict(signed_in.row_limits), {"public": 23, "personal": 23})
        self.assertEqual(self.get.call_count, 2)

    def test_rejected_personal_token_is_an_authentication_error(self):
        for status in (401, 403):
            with self.subTest(status=status):
                self.get.side_effect = [response([row("Public notice")]), response(status=status)]
                with self.assertRaises(SearchAuthenticationError) as caught:
                    self.load(access_token="rejected-token", user_id=USER_A)
                self.assertIsInstance(caught.exception.__cause__, requests.HTTPError)

    def test_failed_public_read_is_a_load_error(self):
        self.get.return_value = response(status=503)
        with self.assertRaises(SearchLoadError) as caught:
            self.load(access_token="token", user_id=USER_A)
        self.assertNotIsInstance(caught.exception, SearchAuthenticationError)
        self.get.assert_called_once()

    def test_failed_personal_read_never_returns_partial_success(self):
        self.get.side_effect = [response([row("Public notice")]), requests.Timeout("offline timeout")]
        with self.assertRaises(SearchLoadError) as caught:
            self.load(access_token="token", user_id=USER_A)
        self.assertIsInstance(caught.exception.__cause__, requests.Timeout)

    def test_invalid_limit_and_missing_public_key_fail_before_reads(self):
        for limit in (0, -1, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                load_snapshot(supabase_url=URL, public_key=PUBLIC_KEY, limit=limit)
        with self.assertRaises(ValueError):
            load_snapshot(supabase_url=URL, public_key="")
        self.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
