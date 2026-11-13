import json
import unittest

from evaluation.local_result_validator import validate_result, validate_text


def call(name, arguments, *, content=None):
    return {"error": None, "response": {"choices": [{"message": {
        "content": content, "tool_calls": [{"type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}}]}}


class LocalResultValidatorTests(unittest.TestCase):
    def test_embedding_fallback_accepts_chinese_paraphrase(self):
        result = validate_text("客人已从消防楼梯撤离，请安保接应",
            "宾客正在沿安全通道下楼，请保卫人员前往协助",
            similarity_fn=lambda _expected, _actual: 0.91)
        self.assertTrue(result["passed"])
        self.assertEqual(result["embedding_similarity"], 0.91)

    def test_json_result_retains_passing_embedding_score_for_report(self):
        expected = json.dumps({"methed": "report_maintenance", "parameters": {
            "room_number": "1603", "issue": "空调持续异响",
            "severity": "high", "allow_entry": True}}, ensure_ascii=False)
        candidate = call("report_maintenance", {"room_number": "1603",
            "issue": "空调关闭后依然发出咔嗒声，影响睡眠",
            "severity": "high", "allow_entry": True})
        result = validate_result(expected, None, candidate,
                                 similarity_fn=lambda _expected, _actual: 0.88)
        self.assertTrue(result["passed"])
        self.assertEqual(result["embedding_scores"][0]["path"], "$.parameters.issue")
        self.assertEqual(result["embedding_scores"][0]["similarity"], 0.88)

    def test_embedding_fallback_rejects_low_similarity(self):
        result = validate_text("客人已从消防楼梯撤离", "请送两条毛巾",
            similarity_fn=lambda _expected, _actual: 0.31)
        self.assertFalse(result["passed"])

    def test_embedding_cannot_override_missing_number(self):
        result = validate_text("联系电话尾号为4826", "联系电话尾号为4286",
            similarity_fn=lambda _expected, _actual: 0.99)
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"][0]["type"], "missing_numbers")

    def test_embedding_cannot_override_direct_contradiction(self):
        result = validate_text("允许维修人员进入房间", "不允许维修人员进入房间",
            similarity_fn=lambda _expected, _actual: 0.99)
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"][0]["type"], "direct_contradiction")

    def test_content_json_does_not_count_as_native_tool_call(self):
        expected = '{"methed":"call_elevator","parameters":{"floor":15,"direction":"down"}}'
        candidate = {"error": None, "response": {"choices": [{"message": {
            "content": expected, "tool_calls": None}}]}}
        self.assertFalse(validate_result(expected, expected, candidate)["passed"])

    def test_natural_language_parameter_uses_keywords(self):
        expected = json.dumps({"methed": "transfer_to_human", "parameters": {
            "department": "security", "reason": "住客正通过消防楼梯撤离，请接应并核查火情",
            "priority": "emergency"}}, ensure_ascii=False)
        candidate = call("transfer_to_human", {"department": "security",
            "reason": "客人正在从楼梯间撤离，再次通知安保当前撤离状态", "priority": "emergency"})
        self.assertTrue(validate_result(expected, None, candidate)["passed"])

    def test_security_reason_paraphrase_and_priority_escalation_pass(self):
        expected = json.dumps({"methed": "transfer_to_human", "parameters": {
            "department": "security", "reason": "走廊有人反复拉客房门，需要现场核查",
            "priority": "high"}}, ensure_ascii=False)
        candidate = call("transfer_to_human", {"department": "security",
            "reason": "走廊有人反复拉动客房房门把手，已发生三次，请立即派安保到场查看。",
            "priority": "emergency"})
        self.assertTrue(validate_result(expected, None, candidate)["passed"])

    def test_handoff_priority_downgrade_still_fails(self):
        expected = json.dumps({"methed": "transfer_to_human", "parameters": {
            "department": "security", "reason": "配电箱出现火花，存在用电危险",
            "priority": "emergency"}}, ensure_ascii=False)
        candidate = call("transfer_to_human", {"department": "security",
            "reason": "配电箱出现火花，存在用电危险", "priority": "high"})
        self.assertFalse(validate_result(expected, None, candidate)["passed"])

    def test_equivalent_wakeup_time_formats_pass(self):
        expected = json.dumps({"methed": "arrange_wakeup_call", "parameters": {
            "room_number": "906", "wakeup_time": "2026-11-09T07:00:00",
            "repeat": "once", "language": "en"}})
        candidate = call("arrange_wakeup_call", {"room_number": "906",
            "wakeup_time": "2026-11-09T07:00:00", "repeat": "once", "language": "en"})
        self.assertTrue(validate_result(expected, None, candidate)["passed"])

    def test_room_number_must_be_string(self):
        expected = json.dumps({"methed": "deliver_items", "parameters": {
            "room_number": "906", "items": ["毛巾"], "quantity": 2}}, ensure_ascii=False)
        self.assertFalse(validate_result(expected, None,
            call("deliver_items", {"room_number": 906, "items": ["毛巾"], "quantity": 2}))["passed"])

    def test_search_window_numbers_are_not_compared_to_gold_value(self):
        expected = json.dumps({"methed": "search_hotel_knowledge", "parameters": {
            "query": "酒店早餐", "top_k": 3}}, ensure_ascii=False)
        self.assertTrue(validate_result(expected, None,
            call("search_hotel_knowledge", {"query": "酒店早餐", "top_k": 8}))["passed"])

    def test_web_search_equivalent_traffic_query_passes(self):
        expected = json.dumps({"methed": "web_search", "parameters": {
            "query": "今天机场高速临时交通管制", "freshness_days": 1}}, ensure_ascii=False)
        candidate = call("web_search", {
            "query": "今天机场高速临时管制 封路", "freshness_days": 1})
        self.assertTrue(validate_result(expected, None, candidate)["passed"])


if __name__ == "__main__":
    unittest.main()
