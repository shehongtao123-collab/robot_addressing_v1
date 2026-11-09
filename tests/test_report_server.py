"""Report-viewer checks with local files and local HTTP only; no model calls."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from evaluate import DATASET_PATH, validate
from reporting.intent_reports import write_json
from reporting.server import ReportHTTPServer, ReportRequestHandler


def write_reports(directory, metadata, descriptions, results):
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "details.json", {"metadata": {**metadata, "models": descriptions}, "results": results})


class ViewerRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="robot-viewer-refresh-")
        self.root = Path(self.temp.name)
        self.results = self.root / "results"
        _, gold = validate()
        metadata = {"schema_version": 1, "status": "complete", "label_key": "intent", "rounds": 1,
                    "model_count": 1, "human_utterances_per_round": 2, "full_dataset_human_utterances": 150,
                    "conversation_id": "hotel_day_001", "conversation_utterances": 200,
                    "planned_evaluations": 2, "completed_evaluations": 2, "elapsed_seconds": 0,
                    "dataset_sha256": hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
                    "prompt_sha256": "fixture", "started_at": "2026-01-01T00:00:00+00:00"}
        config = {"profile": "fixture", "model": "fixture-model", "base_url": "http://unused.invalid"}
        rows = [{"id": row["id"], "conversation_id": row["conversation_id"], "text": row["text"],
                 "speaker_id": row["speaker_id"], "tag": row["tag"], "expected": row["intent"],
                 "intent": row["intent"], "correct": True, "error": None, "round": 1,
                 "profile": "fixture", "model": "fixture-model", "input_tokens": 10,
                 "output_tokens": 1, "total_tokens": 11, "known_input_tokens": 10,
                 "known_output_tokens": 1, "known_total_tokens": 11, "missing_usage_count": 0,
                 "request_link": "details.html#" + row["id"], "request_anchor": row["id"],
                 "attempts": [{"request": None, "response": None, "usage": None}]}
                for row in gold[:2]]
        write_reports(self.results / "one", metadata, [config], rows)
        second = json.loads(json.dumps(rows))
        second[0].update(intent="ignore", correct=False)
        write_reports(self.results / "two", {**metadata, "started_at": "2026-01-02T00:00:00+00:00"}, [config], second)
        self.silence = patch.object(ReportRequestHandler, "log_message")
        self.silence.start()
        self.server = ReportHTTPServer(("127.0.0.1", 0), self.root)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.silence.stop()
        self.temp.cleanup()

    def read(self, filename):
        # Conditional headers must not turn a new report into a cached 304.
        request = Request(self.base + "/results/" + filename,
                          headers={"If-Modified-Since": "Wed, 01 Jan 2099 00:00:00 GMT"})
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
            return json.load(response)

    def test_refresh_after_deleting_one_run_then_all_runs(self):
        first = self.read("summary.json")
        self.assertEqual(first["models"][0]["rows"][0]["rounds"], 2)
        self.assertEqual(first["models"][0]["rows"][0]["accuracy"], .5)
        original = (self.results / "two/details.json").read_bytes()
        shutil.rmtree(self.results / "one")
        second = self.read("summary.json")
        self.assertEqual(second["models"][0]["rows"][0]["rounds"], 1)
        self.assertEqual(second["models"][0]["rows"][0]["accuracy"], 0)
        detail = self.read("details.json")
        self.assertEqual(len(detail["results"]), 2)
        self.assertTrue(all(row["source_run_id"] == "two" for row in detail["results"]))
        self.assertEqual((self.results / "two/details.json").read_bytes(), original)
        shutil.rmtree(self.results / "two")
        empty = self.read("summary.json")
        self.assertEqual(empty["metadata"]["rounds"], 0)
        self.assertEqual(empty["metadata"]["completed_evaluations"], 0)
        self.assertEqual(empty["models"], [])
        self.assertEqual(self.read("details.json")["results"], [])

    def test_deleting_entire_results_directory_does_not_restore_old_runs(self):
        self.read("summary.json")
        shutil.rmtree(self.results)
        empty = self.read("summary.json")
        self.assertEqual(empty["metadata"]["rounds"], 0)
        self.assertFalse(self.results.exists())

    def test_refresh_does_not_create_or_modify_any_report_file(self):
        original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}
        self.read("summary.json")
        self.read("details.json")
        self.read("summary.json")
        current = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(current, original)
        self.assertFalse((self.results / "summary.json").exists())
        self.assertFalse((self.results / "details.json").exists())

    def test_round_order_uses_time_not_directory_name_and_normalizes_timezone(self):
        (self.results / "one").rename(self.results / "z-earliest")
        (self.results / "two").rename(self.results / "a-latest")
        for name, started in (("z-earliest", "2026-01-01T09:00:00+08:00"),
                              ("a-latest", "2026-01-01T02:00:00+00:00")):
            path = self.results / name / "details.json"
            data = json.loads(path.read_text())
            data["metadata"]["started_at"] = started
            path.write_text(json.dumps(data))
        details = self.read("details.json")
        order = [(row["round"], row["source_run_id"]) for row in details["results"]]
        self.assertEqual(order, [(1, "z-earliest"), (1, "z-earliest"), (2, "a-latest"), (2, "a-latest")])

    def test_round_times_interleave_separate_commands_chronologically(self):
        path = self.results / "one/details.json"
        data = json.loads(path.read_text())
        data["metadata"]["rounds"] = 2
        data["metadata"]["round_started_at"] = {"fixture": {"1": "2026-01-01T00:00:00Z", "2": "2026-01-03T00:00:00Z"}}
        later = json.loads(json.dumps(data["results"]))
        for row in later:
            row["round"] = 2
        data["results"].extend(later)
        path.write_text(json.dumps(data))
        summary = self.read("summary.json")
        rounds = summary["models"][0]["rounds"]
        self.assertEqual([(row["round"], row["source_run_id"], row["source_round"]) for row in rounds],
                         [(1, "one", 1), (2, "two", 1), (3, "one", 2)])

    def test_raw_run_reports_are_served_without_rewriting(self):
        original = (self.results / "one/details.json").read_bytes()
        with urlopen(self.base + "/results/one/details.json") as response:
            self.assertEqual(response.read(), original)
        self.assertEqual((self.results / "one/details.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
