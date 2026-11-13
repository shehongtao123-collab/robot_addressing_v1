import json
from pathlib import Path
import unittest

from evaluate import validate
from scripts.generate_intent_300_v3 import MAX_CONTEXT_UNITS, MAX_REQUEST_UNITS, spoken_units


DATASET = Path(__file__).resolve().parents[1] / "datasets" / "intent_300_v3.jsonl"


class Intent300V3Tests(unittest.TestCase):
    def test_dataset_shape_and_short_utterances(self):
        conversation, humans = validate(DATASET)
        addressing = [row for row in humans if row["intent"] == "addressing"]
        self.assertEqual(300, len(conversation))
        self.assertEqual(250, len(humans))
        self.assertEqual(50, len(addressing))
        self.assertTrue(all(spoken_units(row["text"]) <= MAX_CONTEXT_UNITS for row in humans))
        self.assertTrue(all(spoken_units(row["text"]) <= MAX_REQUEST_UNITS for row in addressing))

    def test_every_addressing_case_has_an_immediate_reference_reply(self):
        rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
        for index, row in enumerate(rows[:-1]):
            if row.get("intent") == "addressing":
                self.assertEqual("robot", rows[index + 1]["role"], row["id"])


if __name__ == "__main__":
    unittest.main()
