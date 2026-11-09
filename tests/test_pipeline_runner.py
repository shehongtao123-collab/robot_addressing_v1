"""Offline integration tests using the real SDK against a local HTTP fixture."""

from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import cast
import unittest

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming
from openai.types.completion_usage import CompletionUsage

from evaluate import DATASET_PATH, ROOT, iter_inputs, score, validate
from evaluation.pipeline_runner import build_messages, load_models, parse_intent, parse_intents, render_prompt, unclassified_utterances
from reporting.page_generator import page
from reporting.intent_reports import audit_saved_reports, import_legacy, refresh_history, aggregate_utterances, write_json, build_reports


def write_reports(directory, metadata, descriptions, results):
    """Test fixture: persist only the raw results used by the viewer."""
    directory.mkdir(parents=True, exist_ok=True)
    metadata = {**metadata, "models": descriptions}
    write_json(directory / "details.json", {"metadata": metadata, "results": results})
    return build_reports(metadata, descriptions, results)


class InputConstructionTests(unittest.TestCase):
    """Pure input checks: no server, SDK client, or model requests."""

    def test_only_current_target_is_unclassified_for_every_sample(self):
        conversation, _ = validate()
        for label_key in ("intent", "policy_intent"):
            for sample in iter_inputs(label_key):
                messages = build_messages(sample, "test instructions")
                pending = [m for m in messages if m["role"] == "user" and "（unclassified）" in m["content"]]
                self.assertEqual(len(pending), 1)
                self.assertIs(pending[0], messages[-1])
                self.assertIn("utterance_index: 0", messages[-1]["content"])
                self.assertNotRegex(messages[-1]["content"].split("（unclassified）", 1)[0], r"^(林晨|周宁|许悦)说：")
                self.assertNotIn("intent", sample["target"])
                self.assertNotIn("expected", sample["target"])
                self.assertEqual([r["id"] for r in unclassified_utterances(sample)], [sample["id"]])
                prior = conversation[:int(sample["id"][1:]) - 1]
                self.assertEqual(len(messages), len(prior) + 2)
                for original, message in zip(prior, messages[1:-1]):
                    if original["role"] == "human":
                        self.assertTrue(message["content"].endswith("（" + original[label_key] + "）"))
                        self.assertNotIn("unclassified", message["content"])
                        self.assertNotIn("utterance_index", message["content"])
                    else:
                        self.assertEqual(message["role"], "assistant")
                        self.assertEqual(message["content"], original["text"])

    def test_tenth_human_utterance_has_nine_labeled_human_predecessors(self):
        sample = list(iter_inputs())[9]
        messages = build_messages(sample, "test instructions")
        history = [m for m in messages[1:-1] if m["role"] == "user"]
        self.assertEqual(len(history), 9)
        self.assertTrue(all(m["content"].endswith(("（addressing）", "（ignore）")) for m in history))
        self.assertIn("（unclassified）", messages[-1]["content"])
        self.assertEqual(len(unclassified_utterances(sample)), 1)


class SummaryAggregationTests(unittest.TestCase):
    """Pure report checks. No HTTP server or model clients are constructed."""

    def record(self, *, correct=True, failed=False, number=1):
        _, gold = validate()
        row = gold[0]
        return {"id": row["id"], "conversation_id": row["conversation_id"], "text": row["text"],
                "speaker_id": row["speaker_id"], "tag": row["tag"], "expected": row["intent"],
                "profile": "fixture", "model": "fixture-model", "round": 1,
                "intent": row["intent"] if correct else None if failed else "ignore",
                "correct": correct, "error": "fixture failure" if failed else None,
                "input_tokens": 10 * number, "output_tokens": number, "total_tokens": 11 * number,
                "known_input_tokens": 10 * number, "known_output_tokens": number,
                "known_total_tokens": 11 * number, "missing_usage_count": 0,
                "request_link": "details.html#fixture", "request_anchor": "fixture",
                "attempts": [{"request": None, "response": None, "usage": None}]}

    def test_two_results_are_one_row_with_correct_count_over_test_count(self):
        first, second = self.record(), self.record(correct=False, number=2)
        second["source_evaluation_valid"] = False
        result = aggregate_utterances([first, second])
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual((row["rounds"], row["correct_count"], row["accuracy"]), (2, 1, .5))
        self.assertEqual((row["input_tokens"], row["output_tokens"], row["total_tokens"]), (30, 3, 33))
        self.assertEqual(len(row["evaluations"]), 2)

    def test_failed_output_stays_in_denominator_and_missing_tokens_stay_unknown(self):
        first, second = self.record(), self.record(correct=False, failed=True)
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            second[field] = None
        second.update(known_input_tokens=0, known_output_tokens=0, known_total_tokens=0, missing_usage_count=1)
        row = aggregate_utterances([first, second])[0]
        self.assertEqual((row["rounds"], row["correct_count"], row["failed_count"], row["accuracy"]), (2, 1, 1, .5))
        self.assertIsNone(row["input_tokens"])
        self.assertEqual(row["known_input_tokens"], 10)
        self.assertEqual(row["missing_usage_count"], 1)

    def test_six_tests_are_one_row_instead_of_six_rows(self):
        rows = [self.record(correct=index < 4, number=index + 1) for index in range(6)]
        result = aggregate_utterances(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]["rounds"], result[0]["correct_count"]), (6, 4))
        self.assertAlmostEqual(result[0]["accuracy"], 4 / 6)

    def test_history_includes_both_saved_reports_and_preserves_source_files(self):
        digest = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
        metadata = {"schema_version": 1, "label_key": "intent", "status": "complete", "rounds": 1,
                    "model_count": 1, "human_utterances_per_round": 1, "full_dataset_human_utterances": 150,
                    "conversation_id": "hotel_day_001", "conversation_utterances": 200,
                    "planned_evaluations": 1, "completed_evaluations": 1, "dataset_sha256": digest,
                    "prompt_sha256": "fixture", "started_at": "2026-01-01T00:00:00+00:00", "elapsed_seconds": 0}
        config = {"profile": "fixture", "model": "fixture-model", "base_url": "http://localhost/unused"}
        with tempfile.TemporaryDirectory(prefix="robot-summary-only-") as temp:
            root = Path(temp)
            write_reports(root / "one", {**metadata, "evaluation_valid": False, "invalidated_reason": "old input bug"}, [config], [self.record()])
            write_reports(root / "two", {**metadata, "evaluation_valid": True}, [config], [self.record(correct=False, number=2)])
            original = {path: path.read_bytes() for path in root.glob("*/*.json")}
            summary, merged_details = refresh_history(root, "intent")
            group = summary["models"][0]
            self.assertEqual(group["round_count"], 2)
            self.assertEqual(len(group["rows"]), 1)
            self.assertEqual(group["rows"][0]["accuracy"], .5)
            self.assertEqual(group["rows"][0]["rounds"], 2)
            self.assertEqual(len(summary["metadata"]["flagged_runs"]), 1)
            self.assertEqual(len(merged_details["results"]), 2)
            self.assertTrue(all(path.read_bytes() == content for path, content in original.items()))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, gold = validate()
        cls.truth = {row["text"]: row["intent"] for row in gold}
        if len(cls.truth) != 150:
            raise AssertionError("Fixture requires distinct target utterances")
        cls.received = []
        cls.counts = Counter()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body: CompletionCreateParamsNonStreaming = cast(CompletionCreateParamsNonStreaming,
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                cls.received.append(body)
                model = body["model"]
                target = body["messages"][-1]["content"].split("（unclassified）", 1)[0]
                cls.counts[(model, target)] += 1
                if model == "failure" or (model == "retry" and cls.counts[(model, target)] == 1):
                    raw = b'{"error":{"message":"fixture server failure","type":"server_error"}}'
                    status = 503
                else:
                    intent = "ignore" if model == "ignore" else cls.truth[target]
                    humans = [message["content"].split("（unclassified）", 1)[0]
                              for message in body["messages"] if message["role"] == "user" and "（unclassified）" in message["content"]]
                    content = "\n".join(f"{index}:" + ("ignore" if model == "ignore" else cls.truth[text])
                                        for index, text in enumerate(humans))
                    if model == "invalid" and cls.counts[(model, target)] == 1:
                        content = "invalid answer"
                    usage: CompletionUsage | None = None if model == "no-usage" else CompletionUsage(
                        prompt_tokens=len(body["messages"]) * 7 + 13, completion_tokens=4,
                        total_tokens=len(body["messages"]) * 7 + 17)
                    response: ChatCompletion = ChatCompletion(id="fixture-completion", object="chat.completion",
                        created=1, model=model, choices=[Choice(index=0, finish_reason="stop",
                        message=ChatCompletionMessage(role="assistant", content=content))], usage=usage)
                    raw, status = response.model_dump_json().encode(), 200
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="robot-addressing-test-")
        self.directory = Path(self.temporary.name)
        self.copy = self.directory / "standalone"
        self.copy.mkdir()
        (self.copy / "datasets").mkdir()
        (self.copy / "templates").mkdir()
        shutil.copyfile(ROOT / "evaluate.py", self.copy / "evaluate.py")
        for name in ("evaluation", "reporting", "prompts"):
            shutil.copytree(ROOT / name, self.copy / name)
        shutil.copyfile(DATASET_PATH, self.copy / "datasets" / "conversation.jsonl")
        for name in ("summary.html", "runs.html", "details.html", "result_summary.html", "result_runs.html", "result_details.html"):
            shutil.copyfile(ROOT / "templates" / name, self.copy / "templates" / name)
        self.start = len(self.received)

    def tearDown(self):
        self.temporary.cleanup()

    def run_config(self, models, rounds=1, limit=None):
        prior = set((self.directory / "results").iterdir()) if (self.directory / "results").exists() else set()
        profiles = [{"name": name, "model": name, "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
                     "api_key_env": "ROBOT_ADDRESSING_FIXTURE_KEY", "api_key": "test-secret-must-not-appear",
                     "timeout_seconds": 3,
                     "request_options": {"max_completion_tokens": 128}, "extra_body": {"fixture_extension": True}}
                    for name in models]
        config = self.directory / "models.json"
        config.write_text(json.dumps({"models": profiles}))
        command = [sys.executable, str(self.copy / "evaluate.py"), "run", "--config", str(config),
                   "--task", "intent", "--rounds", str(rounds),
                   "--results-directory", str(self.directory / "results")]
        if limit:
            command.extend(["--limit", str(limit)])
        environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "ROBOT_ADDRESSING_FIXTURE_KEY")}
        result = subprocess.run(command, cwd=self.directory, env=environment, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-2000:])
        output = next(path for path in (self.directory / "results").iterdir() if path.is_dir() and path not in prior and path.name != "history")
        self.assertEqual({path.name for path in output.iterdir()}, {"details.json"})
        raw = json.loads((output / "details.json").read_text())
        from reporting.intent_reports import build_reports, source_models
        summary, details = build_reports(raw["metadata"], source_models(raw["metadata"], raw["results"]), raw["results"])
        return output, summary, raw

    def test_two_models_two_full_rounds_without_application(self):
        self.assertIsNone(importlib.util.find_spec("aura_brain"))
        output, summary, details = self.run_config(["perfect", "ignore"], rounds=2)
        self.assertEqual(len(details["results"]), 600)
        self.assertEqual(summary["metadata"]["status"], "complete")
        self.assertEqual(summary["models"][0]["statistics"]["accuracy"], 1)
        self.assertEqual(summary["models"][1]["statistics"]["accuracy"], .5)
        for model in summary["models"]:
            self.assertEqual(model["statistics"]["total"], 300)
            self.assertEqual([r["statistics"]["total"] for r in model["rounds"]], [150, 150])
        wire = self.received[self.start:]
        self.assertEqual(len(wire), 600)
        expected_messages = [build_messages(sample, render_prompt(self.copy / "prompts" / "intent_classification.md")) for sample in iter_inputs()]
        for index, result in enumerate(details["results"]):
            body = result["attempts"][0]["request"]["body"]
            self.assertEqual(body, wire[index])
            self.assertEqual(body["messages"], expected_messages[index % 150])
            self.assertTrue(body["fixture_extension"])
            self.assertNotIn("extra_body", body)
            self.assertEqual(result["input_tokens"], len(body["messages"]) * 7 + 13)
            self.assertEqual(len(result["batch_results"]), 1)
            self.assertEqual(result["target_utterance_index"], 0)
            self.assertEqual(result["batch_results"][-1]["id"], result["id"])
            self.assertEqual(result["request_link"], "details.html#" + result["request_anchor"])
        for model in summary["models"]:
            wanted = sum(row["input_tokens"] for row in details["results"] if row["profile"] == model["profile"])
            self.assertEqual(model["statistics"]["known_input_tokens"], wanted)
        for path in output.iterdir():
            self.assertNotIn("test-secret-must-not-appear", path.read_text())

    def test_two_separate_three_round_commands_merge_to_six_tests(self):
        first, _, first_details = self.run_config(["perfect"], rounds=3)
        second, _, second_details = self.run_config(["perfect"], rounds=3)
        self.assertNotEqual(first, second)
        merged, details = refresh_history(first.parent, "intent")
        self.assertEqual(len(merged["models"]), 1)
        group = merged["models"][0]
        self.assertEqual(group["round_count"], 6)
        self.assertEqual([r["round"] for r in group["rounds"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual([r["source_round"] for r in group["rounds"]], [1, 2, 3, 1, 2, 3])
        self.assertEqual([r["statistics"]["total"] for r in group["rounds"]], [150] * 6)
        self.assertEqual(len(group["rows"]), 150)
        self.assertTrue(all(row["rounds"] == 6 and row["correct_count"] == 6 and row["accuracy"] == 1 for row in group["rows"]))
        self.assertEqual(group["statistics"]["accuracy"], 1)
        self.assertEqual(len({r["request_anchor"] for r in details["results"]}), 900)
        self.assertEqual(Counter(r["id"] for r in details["results"]), Counter({r["id"]: 6 for r in first_details["results"]}))
        originals = {(first.name, r["round"], r["id"]): r for r in first_details["results"]}
        originals.update({(second.name, r["round"], r["id"]): r for r in second_details["results"]})
        for row in details["results"]:
            original = originals[(row["source_run_id"], row["source_round"], row["id"])]
            self.assertEqual(row["attempts"], original["attempts"])
            self.assertEqual(len(row["attempts"]), 1)
        self.assertEqual(json.loads((first / "details.json").read_text())["results"], first_details["results"])
        self.assertEqual(json.loads((second / "details.json").read_text())["results"], second_details["results"])

    def test_grouping_separates_model_and_dataset_and_merges_profile_aliases(self):
        output, summary, details = self.run_config(["perfect"], limit=2)
        base = summary["models"][0]
        description = {key: base[key] for key in ("profile", "model", "base_url")}
        alias_rows = json.loads(json.dumps(details["results"]))
        for row in alias_rows:
            row["profile"] = "another-profile-for-the-same-model"
        write_reports(output.parent / "profile-alias", details["metadata"],
                      [{**description, "profile": alias_rows[0]["profile"]}], alias_rows)
        other_digest = "a" * 64
        write_reports(output.parent / "other-dataset", {**details["metadata"], "dataset_sha256": other_digest},
                      [description], json.loads(json.dumps(details["results"])))
        other_model_rows = json.loads(json.dumps(details["results"]))
        for row in other_model_rows:
            row["profile"] = "other-model-profile"
            row["model"] = "other-model-id"
        write_reports(output.parent / "other-model", details["metadata"],
                      [{**description, "profile": "other-model-profile", "model": "other-model-id"}], other_model_rows)
        merged, _ = refresh_history(output.parent, "intent")
        self.assertEqual(len(merged["models"]), 3)
        same = next(group for group in merged["models"] if group["model"] == "perfect" and group["dataset_sha256"] != other_digest)
        self.assertEqual(same["round_count"], 2)
        self.assertEqual(len(same["rows"]), 2)
        self.assertTrue(all(row["rounds"] == 2 for row in same["rows"]))
        self.assertEqual(set(same["profile_names"]), {"perfect", "another-profile-for-the-same-model"})

    def test_usage_missing_and_failures_never_retry(self):
        _, summary, details = self.run_config(["no-usage", "retry", "invalid", "failure"], limit=1)
        rows = {row["profile"]: row for row in details["results"]}
        self.assertIsNone(rows["no-usage"]["input_tokens"])
        self.assertEqual(rows["no-usage"]["missing_usage_count"], 1)
        self.assertTrue(rows["no-usage"]["correct"])
        self.assertEqual(len(rows["retry"]["attempts"]), 1)
        self.assertEqual(rows["retry"]["missing_usage_count"], 1)
        self.assertFalse(rows["retry"]["correct"])
        self.assertEqual(len(rows["invalid"]["attempts"]), 1)
        self.assertEqual(rows["invalid"]["missing_usage_count"], 0)
        self.assertEqual(rows["invalid"]["input_tokens"], 2 * 7 + 13)
        self.assertEqual(rows["invalid"]["known_input_tokens"], 2 * 7 + 13)
        self.assertEqual(rows["invalid"]["output_tokens"], 4)
        self.assertEqual(rows["invalid"]["known_output_tokens"], 4)
        self.assertFalse(rows["invalid"]["correct"])
        self.assertIsNone(rows["invalid"]["intent"])
        self.assertEqual(len(self.received[self.start:]), 4)
        for name in rows:
            self.assertEqual(len(rows[name]["attempts"]), 1)
        self.assertIn("disabled", summary["metadata"]["retry_policy"])
        self.assertFalse(rows["failure"]["correct"])
        self.assertIsNone(rows["failure"]["intent"])
        self.assertEqual(summary["models"][-1]["statistics"]["accuracy"], 0)
        self.assertEqual(summary["models"][-1]["statistics"]["missing_or_failed"], 1)

    def test_config_validation_and_strict_output(self):
        for text in ("addressing", "```0:ignore```", "0:ignore\n1:addressing", "<think>unfinished"):
            with self.assertRaises(ValueError):
                parse_intent(text)
        self.assertEqual(parse_intent("<think>private analysis</think>\n0:ignore"), "ignore")
        self.assertEqual(parse_intent("implicit analysis</think>0:addressing"), "addressing")
        path = self.directory / "bad.json"
        path.write_text(json.dumps({"models": [{"name": "x", "model": "x", "base_url": "http://localhost/v1",
                                               "api_key": "test", "request_options": {"messages": []}}]}))
        with self.assertRaises(ValueError):
            load_models(path, None)

    def test_complete_batch_parser_and_audit_preserve_wire_artifacts(self):
        self.assertEqual(parse_intents("0:addressing\n1:ignore", [0, 1]), {0: "addressing", 1: "ignore"})
        for output in ("0:addressing", "0:ignore\n0:addressing", "1:ignore\n0:addressing", "0:addressing\n1:ignore\n2:ignore"):
            with self.assertRaises(ValueError):
                parse_intents(output, [0, 1])
        output, _, details = self.run_config(["perfect"], limit=2)
        row = details["results"][-1]
        row["intent"], row["correct"], row["error"] = None, False, "old parser expected one line"
        row.pop("classification_protocol")
        row["attempts"][0]["error"] = row["error"]
        # Mimic the historical numbering bug without changing chronological text.
        messages = row["attempts"][0]["request"]["body"]["messages"]
        messages[1]["content"] = messages[1]["content"].rsplit("（", 1)[0] + "（unclassified）"
        messages[2]["content"] = messages[2]["content"].replace("utterance_index: 1", "utterance_index: 0")
        row["attempts"][0]["response"]["choices"][0]["message"]["content"] = "0:addressing\n1:ignore"
        original_attempt = json.loads(json.dumps(row["attempts"][0]))
        saved_wire = json.loads(json.dumps(row["attempts"][0]["request"]))
        (output / "details.json").write_text(json.dumps(details))
        audit_saved_reports(output.parent, "intent")
        corrected = json.loads((output / "details.json").read_text())["results"][-1]
        self.assertEqual(corrected["intent"], "ignore")
        self.assertTrue(corrected["correct"])
        self.assertIsNone(corrected["error"])
        self.assertEqual(len(corrected["batch_results"]), 2)
        self.assertEqual(corrected["target_utterance_index"], 1)
        self.assertEqual(corrected["attempts"][0]["request"], saved_wire)
        self.assertEqual(corrected["attempts"][0]["response"], original_attempt["response"])
        self.assertIsNone(corrected["original_evaluation"]["intent"])
        audit_saved_reports(output.parent, "intent")
        again = json.loads((output / "details.json").read_text())["results"][-1]
        self.assertEqual(again, corrected)

    def test_nonzero_retry_configuration_is_rejected(self):
        path = self.directory / "retry-config.json"
        path.write_text(json.dumps({"models": [{"name": "x", "model": "x", "base_url": "http://localhost/v1",
                                               "api_key": "test", "max_retries": 1}]}))
        with self.assertRaisesRegex(ValueError, "Retries are disabled"):
            load_models(path, None)

    def test_report_data_cannot_terminate_script(self):
        rendered = page("test", "summary", "", "", "summary.json")
        self.assertEqual(rendered.count("</script>"), 1)
        self.assertIn("await fetch(reportURL", rendered)
        self.assertNotIn("const DATA={", rendered)
        self.assertNotIn("innerHTML", rendered)

    def test_fixed_viewers_load_reports_and_include_partial_history(self):
        output, summary, details = self.run_config(["perfect"], limit=2)
        html = (self.copy / "templates" / "summary.html").read_text()
        self.assertIn("await fetch(reportURL", html)
        self.assertNotIn("fixture-completion", html)
        self.assertNotIn(details["results"][0]["text"], html)
        self.assertEqual(list(output.glob("*.html")), [])
        partial = output.parent / "partial-run"
        metadata = {**details["metadata"], "status": "interrupted", "rounds": 2,
                    "planned_evaluations": 4, "completed_evaluations": 1}
        description = {key: summary["models"][0][key] for key in ("profile", "model", "base_url")}
        write_reports(partial, metadata, [description], details["results"][:1])
        merged, _ = refresh_history(output.parent, "intent")
        self.assertEqual(len(merged["metadata"]["source_runs"]), 2)
        self.assertEqual(merged["metadata"]["completed_evaluations"], 3)
        self.assertEqual(len(merged["models"]), 1)
        group = merged["models"][0]
        interrupted = next(row for row in group["rounds"] if row["source_run_id"] == "partial-run")
        self.assertEqual(interrupted["source_status"], "interrupted")
        self.assertEqual(interrupted["statistics"]["total"], 1)
        self.assertEqual(interrupted["statistics"]["correct"], 1)
        self.assertEqual(group["round_count"], 2)  # Unstarted rounds are excluded.
        self.assertEqual((self.copy / "templates" / "summary.html").read_text(), html)
        completed, _ = refresh_history(output.parent, "intent", include_incomplete=False)
        self.assertEqual(len(completed["metadata"]["source_runs"]), 1)
        self.assertEqual(completed["metadata"]["completed_evaluations"], 2)

    def test_legacy_import_preserves_metrics_and_marks_unknown_requests(self):
        _, gold = validate()
        source = self.directory / "old-run"
        source.mkdir()
        predictions = [{"id": row["id"], "intent": row["intent"], "raw_output": "0:" + row["intent"],
                        "latency_seconds": .1} for row in gold]
        (source / "predictions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in predictions))
        original = score(source / "predictions.jsonl", "intent")
        (source / "intent_report.json").write_text(json.dumps(original))
        (source / "run.json").write_text(json.dumps({"profile": "old-model", "model": "old-model-id",
            "endpoint": "http://localhost/v1", "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:01+00:00",
            "dataset_sha256": hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(), "elapsed_seconds": 1}))
        output = import_legacy(source, self.directory / "results", "intent")
        raw = json.loads((output / "details.json").read_text())
        from reporting.intent_reports import build_reports, source_models
        summary, details = build_reports(raw["metadata"], source_models(raw["metadata"], raw["results"]), raw["results"])
        model = summary["models"][0]
        self.assertEqual(model["source_statistics"], original)
        for key in ("accuracy", "precision", "recall", "f1", "coverage", "false_activation_rate", "confusion"):
            self.assertEqual(model["statistics"][key], original[key])
        self.assertEqual(model["statistics"]["missing_usage_count"], 150)
        self.assertEqual(model["statistics"]["unrecorded_http_attempts"], 150)
        self.assertEqual(model["statistics"]["http_attempts"], 0)
        for row in details["results"]:
            self.assertIsNone(row["input_tokens"])
            self.assertIsNone(row["attempts"][0]["request"])
            self.assertEqual(row["attempts"][0]["legacy_raw_output"], "0:" + row["intent"])
        _, _, _ = self.run_config(["perfect"], rounds=2, limit=3)
        merged, merged_details = refresh_history(self.directory / "results", "intent")
        self.assertEqual(len(merged["models"]), 2)
        self.assertEqual(len(merged_details["results"]), 156)
        self.assertEqual(len({row["request_anchor"] for row in merged_details["results"]}), 156)
        self.assertEqual(merged["models"][0]["human_utterances_per_round"], 150)
        self.assertEqual(merged["models"][1]["human_utterances_per_round"], 3)


if __name__ == "__main__":
    unittest.main()
