import json
from pathlib import Path
import tempfile
import unittest

from evaluate import evaluation_tasks
from evaluation.intent_parser import parse_intents
from evaluation.response_comparison import build_judge_payload, compare_json, json_needs_semantic_judge, judge_json_result, parse_text_judgment, response_references, result_samples
from reporting.intent_reports import latency_statistics
from reporting.response_reports import aggregate_rows, result_history, result_statistics


class ResultEvaluationTests(unittest.TestCase):
    def test_default_runs_both_phases_and_intent_flag_runs_only_intent(self):
        self.assertEqual(evaluation_tasks(None), ("combined",))
        self.assertEqual(evaluation_tasks("intent"), ("intent",))

    def test_text_judge_receives_only_reference_and_candidate(self):
        self.assertEqual(build_judge_payload("标准答案", "模型答案"), {
            "reference_answer": "标准答案",
            "candidate_answer": "模型答案",
        })

    def test_json_objects_ignore_key_order_but_require_fields_and_values(self):
        passed = judge_json_result('{"method":"x","parameters":{"a":1}}',
                                   '```json\n{"parameters":{"a":1},"method":"x"}\n```')
        self.assertTrue(passed["passed"])
        failed = judge_json_result('{"a":1}', '{"a":2,"extra":3}')
        self.assertFalse(failed["passed"])
        self.assertEqual({error["type"] for error in failed["errors"]}, {"value_mismatch", "extra_field"})

    def test_only_natural_language_json_fields_can_use_semantic_judge(self):
        wording = judge_json_result('{"parameters":{"reason":"住客正在撤离"}}',
                                    '{"parameters":{"reason":"客人正紧急疏散"}}')
        self.assertTrue(json_needs_semantic_judge(wording))
        control = judge_json_result('{"priority":"emergency"}', '{"priority":"normal"}')
        self.assertFalse(json_needs_semantic_judge(control))

    def test_text_judge_schema_is_strict(self):
        valid = {"passed": True, "score": .9, "reason": "语义一致", "missing_facts": [],
                 "contradictions": [], "unsupported_claims": []}
        self.assertEqual(parse_text_judgment(json.dumps(valid, ensure_ascii=False)), valid)
        with self.assertRaises(ValueError):
            parse_text_judgment(json.dumps({**valid, "unexpected": True}))

    def test_dataset_robot_results_become_samples(self):
        samples = result_samples(Path("datasets/intent_300_v1.jsonl"))
        self.assertEqual(len(samples), 50)
        self.assertEqual(samples[0]["id"], "u005")
        self.assertIn("联系安保", samples[0]["user_request"])

    def test_robot_reply_is_linked_to_last_addressing_human_not_adjacent_ignore(self):
        references = response_references(Path("datasets/conversation.jsonl"))
        self.assertIn("u001", references)
        self.assertEqual(references["u001"]["id"], "u004")
        self.assertNotIn("u003", references)

    def test_intent_parser_accepts_harmless_spaces_around_colon(self):
        self.assertEqual(parse_intents("0: addressing", [0]), {0: "addressing"})
        self.assertEqual(parse_intents("0 : ignore", [0]), {0: "ignore"})

    def test_result_statistics_accepts_skipped_null_candidate_call(self):
        statistics = result_statistics([{
            "passed": False, "result_status": "skipped_by_intent",
            "candidate_call": None, "judgment": None,
            "result_type": "not_applicable", "latency_seconds": None,
        }])
        self.assertEqual(statistics["candidate_failures"], 0)
        self.assertEqual(statistics["validation_failures"], 0)
        self.assertEqual(statistics["total"], 1)
        self.assertEqual(statistics["result_call_count"], 0)
        self.assertEqual(statistics["missing_usage_count"], 0)

    def test_result_statistics_reports_result_generation_tokens_and_missing_usage(self):
        rows = [
            {"passed": True, "result_status": "evaluated", "result_type": "text",
             "candidate_call": {"usage": {"prompt_tokens": 100, "completion_tokens": 7,
                                            "total_tokens": 107}},
             "judgment": {}, "latency_seconds": 1.0,
             "input_tokens": 100, "output_tokens": 7, "total_tokens": 107},
            {"passed": False, "result_status": "evaluated", "result_type": "json",
             "candidate_call": {"usage": None, "error": "network error"},
             "judgment": {}, "latency_seconds": 2.0,
             "input_tokens": None, "output_tokens": None, "total_tokens": None},
        ]
        statistics = result_statistics(rows)
        self.assertEqual(statistics["result_call_count"], 2)
        self.assertEqual(statistics["result_usage_count"], 1)
        self.assertEqual(statistics["missing_usage_count"], 1)
        self.assertEqual(statistics["input_tokens"], 100)
        self.assertEqual(statistics["output_tokens"], 7)
        self.assertEqual(statistics["total_tokens"], 107)

    def test_result_summary_rows_aggregate_tokens_and_preserve_unknown(self):
        base = {"id": "u001", "conversation_id": "fixture", "user_request": "请求",
                "expected_text": "答案", "result_type": "text", "tag": "问答",
                "passed": True, "round": 1, "source_run_id": "run", "source_round": 1,
                "actual_text": "答案", "error": None, "request_anchor": "one",
                "request_link": "result_details.html#one"}
        row = aggregate_rows([{**base, "input_tokens": 100, "output_tokens": 7,
                               "latency_seconds": 1.0},
                              {**base, "round": 2, "request_anchor": "two",
                               "request_link": "result_details.html#two",
                               "input_tokens": 120, "output_tokens": 8,
                               "latency_seconds": 2.0}])[0]
        self.assertEqual((row["input_tokens"], row["output_tokens"]), (220, 15))
        self.assertEqual((row["average_input_tokens"], row["average_output_tokens"]), (110, 7.5))
        self.assertEqual(row["average_latency_seconds"], 1.5)
        unknown = aggregate_rows([{**base, "input_tokens": 100, "output_tokens": 7,
                                   "latency_seconds": 1.0},
                                  {**base, "input_tokens": None, "output_tokens": None,
                                   "latency_seconds": None}])[0]
        self.assertIsNone(unknown["input_tokens"])
        self.assertIsNone(unknown["output_tokens"])
        self.assertIsNone(unknown["average_input_tokens"])
        self.assertIsNone(unknown["average_output_tokens"])
        self.assertIsNone(unknown["average_latency_seconds"])

    def test_latency_chart_points_include_output_tokens(self):
        latency = latency_statistics([{"id": "u001", "input_tokens": 100,
                                       "output_tokens": 7, "latency_seconds": 1.25}])
        self.assertEqual(latency["input_token_points"], [{"id": "u001", "input_tokens": 100,
                                                           "output_tokens": 7,
                                                           "latency_seconds": 1.25}])


if __name__ == "__main__":
    unittest.main()
