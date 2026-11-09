import json
from pathlib import Path
import unittest

from hotel_tools.mock_functions import TOOL_SCHEMAS, dataset_result, dispatch_methed, normalize_dataset_parameters, tool_call_content


class MethedToolsTests(unittest.TestCase):
    def test_native_tool_call_is_converted_to_dataset_shape(self):
        self.assertEqual(json.loads(tool_call_content("call_elevator", '{"floor":15,"direction":"down"}')),
                         {"methed": "call_elevator", "parameters": {"floor": 15, "direction": "down"}})
        with self.assertRaises(ValueError):
            tool_call_content("query_room_type", '{}')

    def test_definitions_cover_every_dataset_methed_and_schema(self):
        observed = {}
        for path in Path("datasets").glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("role") != "robot":
                    continue
                try:
                    answer = json.loads(row["text"])
                except json.JSONDecodeError:
                    continue
                name = answer.get("methed")
                if not name:
                    continue
                parameters = normalize_dataset_parameters(name, answer["parameters"])
                observed.setdefault(name, set()).add(tuple(sorted(parameters)))
                self.assertTrue(dispatch_methed(name, parameters)["simulated"])
                self.assertEqual(dataset_result(name, parameters), {**answer, "parameters": parameters})
        self.assertEqual(set(observed), set(TOOL_SCHEMAS))
        self.assertTrue(all(len(shapes) == 1 for shapes in observed.values()))

    def test_strict_types_ranges_and_dates(self):
        with self.assertRaises(TypeError):
            dispatch_methed("deliver_items", {"room_number": 906, "items": ["毛巾"], "quantity": 1})
        with self.assertRaises(ValueError):
            dispatch_methed("search_hotel_knowledge", {"query": "早餐", "top_k": 0})
        with self.assertRaises(ValueError):
            dispatch_methed("book_hotel_facility", {"facility": "瑜伽", "date": "2026-02-30",
                "start_time": "09:00", "duration_minutes": 60, "guest_count": 1})
        with self.assertRaises(ValueError):
            dispatch_methed("arrange_wakeup_call", {"room_number": "906", "wakeup_time": "明天06:30",
                "repeat": "once", "language": "zh"})


if __name__ == "__main__":
    unittest.main()
