"""Strict ordered classification parsing; standard library only."""

import re
from evaluate import require


def parse_intents(text: str | None, expected_indices: list[int]) -> dict[int, str]:
    require(isinstance(text, str), "Response content is missing")
    visible = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "</think>" in visible:
        visible = visible.rsplit("</think>", 1)[1]
    indices = []
    parsed = {}
    for line in visible.strip().splitlines():
        match = re.fullmatch(r"(0|[1-9][0-9]*)[ \t]*:[ \t]*(addressing|ignore)", line.strip())
        require(match is not None, "Each unclassified utterance requires one index:addressing or index:ignore line")
        index = int(match[1])
        require(index not in parsed, f"Duplicate utterance_index: {index}")
        indices.append(index)
        parsed[index] = match[2]
    require(indices == expected_indices, f"Intent indices must match all unclassified inputs: expected {expected_indices}, got {indices}")
    return parsed

