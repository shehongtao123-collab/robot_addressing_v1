"""Deterministic JSON comparison and strict parsing for AI text judgments."""

from __future__ import annotations

import json
import re

from evaluate import dataset_context, validate


def build_judge_payload(expected_text: str, candidate_text: str | None):
    """Return the complete untrusted payload visible to the text judge."""
    return {"reference_answer": expected_text, "candidate_answer": candidate_text}


def response_references(dataset_path):
    """Map each robot reply to the last addressing human since the prior reply.

    A robot reply is not necessarily adjacent to the human request it answers;
    intervening human-to-human messages must not steal that reference answer.
    """
    conversation, _ = validate(dataset_path)
    references = {}
    previous_robot = -1
    for index, row in enumerate(conversation):
        if row["role"] != "robot":
            continue
        humans = [item for item in conversation[previous_robot + 1:index] if item["role"] == "human"]
        target = next((item for item in reversed(humans) if item.get("intent") == "addressing"), None)
        if target is not None:
            references[target["id"]] = row
        previous_robot = index
    return references


def result_samples(dataset_path):
    conversation, _ = validate(dataset_path)
    participants, robot = dataset_context(conversation)
    references = response_references(dataset_path)
    by_id = {row["id"]: row for row in conversation}
    samples = []
    for target_id, row in references.items():
        target = by_id[target_id]
        index = conversation.index(row)
        previous_robot = max((position for position in range(index) if conversation[position]["role"] == "robot"), default=-1)
        humans = [item for item in conversation[previous_robot + 1:index] if item["role"] == "human"]
        samples.append({"id": row["id"], "conversation_id": row["conversation_id"], "section": row["section"],
                        "target_id": target_id,
                        "tag": target.get("tag", row.get("tag", "result")), "robot": robot,
                        "participants": participants, "history": conversation[:index],
                        "user_request": target["text"],
                        "relevant_context": [item["text"] for item in humans if item is not target],
                        "expected_text": row["text"]})
    return samples


def parse_json_content(text: str | None):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty result")
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", value, re.IGNORECASE)
    if fenced:
        value = fenced.group(1)
    return json.loads(value)


def compare_json(expected, actual, path="$"):
    errors = []
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if type(actual) is not type(expected):
            return [{"path": path, "type": "type_mismatch", "expected": type(expected).__name__,
                     "actual": type(actual).__name__}]
        if actual != expected:
            errors.append({"path": path, "type": "value_mismatch", "expected": expected, "actual": actual})
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            errors.append({"path": path, "type": "type_mismatch", "expected": "number",
                           "actual": type(actual).__name__})
        elif actual != expected:
            errors.append({"path": path, "type": "value_mismatch", "expected": expected, "actual": actual})
    elif isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [{"path": path, "type": "type_mismatch", "expected": "object",
                     "actual": type(actual).__name__}]
        for key in expected.keys() - actual.keys():
            errors.append({"path": f"{path}.{key}", "type": "missing_field", "expected": expected[key]})
        for key in actual.keys() - expected.keys():
            errors.append({"path": f"{path}.{key}", "type": "extra_field", "actual": actual[key]})
        for key in expected.keys() & actual.keys():
            errors.extend(compare_json(expected[key], actual[key], f"{path}.{key}"))
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return [{"path": path, "type": "type_mismatch", "expected": "array",
                     "actual": type(actual).__name__}]
        if len(expected) != len(actual):
            errors.append({"path": path, "type": "array_length_mismatch",
                           "expected": len(expected), "actual": len(actual)})
        for index, (wanted, received) in enumerate(zip(expected, actual)):
            errors.extend(compare_json(wanted, received, f"{path}[{index}]"))
    else:
        raise TypeError(f"Unsupported expected JSON type: {type(expected).__name__}")
    return errors


def judge_json_result(expected_text: str, candidate_text: str | None):
    expected = parse_json_content(expected_text)
    try:
        actual = parse_json_content(candidate_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"result_type": "json", "passed": False, "expected_parsed": expected,
                "actual_parsed": None, "errors": [{"path": "$", "type": "json_parse_error",
                                                     "message": str(exc)}]}
    errors = compare_json(expected, actual)
    return {"result_type": "json", "passed": not errors, "expected_parsed": expected,
            "actual_parsed": actual, "errors": errors}


def json_needs_semantic_judge(judgment):
    """Allow AI review only when JSON differs in natural-language description fields."""
    errors = judgment.get("errors", [])
    semantic_fields = {"reason", "message", "content", "text", "description"}
    return bool(errors) and all(
        error.get("type") == "value_mismatch"
        and error.get("path", "").rsplit(".", 1)[-1] in semantic_fields
        and isinstance(error.get("expected"), str)
        and isinstance(error.get("actual"), str)
        for error in errors
    )


def parse_text_judgment(text: str | None):
    value = parse_json_content(text)
    if not isinstance(value, dict):
        raise ValueError("judge output must be a JSON object")
    required = {"passed", "score", "reason", "missing_facts", "contradictions", "unsupported_claims"}
    if set(value) != required:
        raise ValueError(f"judge fields must be exactly {sorted(required)}")
    if type(value["passed"]) is not bool:
        raise ValueError("passed must be boolean")
    if type(value["score"]) not in (int, float) or not 0 <= value["score"] <= 1:
        raise ValueError("score must be a number between 0 and 1")
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise ValueError("reason must be a nonempty string")
    for key in ("missing_facts", "contradictions", "unsupported_claims"):
        if not isinstance(value[key], list) or not all(isinstance(item, str) for item in value[key]):
            raise ValueError(f"{key} must be an array of strings")
    return value
