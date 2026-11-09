import json
import unittest

from evaluation.local_result_validator import validate_result


def call(name, arguments, *, content=None):
    return {"error": None, "response": {"choices": [{"message": {
        "content": content, "tool_calls": [{"type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}}]}}


class LocalResultValidatorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
