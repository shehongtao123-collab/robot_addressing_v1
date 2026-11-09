"""Deterministic response validation without an AI judge."""

from __future__ import annotations

from math import ceil
import json
import re

from hotel_tools.mock_functions import dataset_result, normalize_dataset_parameters


SEMANTIC_FIELDS = {"reason", "notes", "query", "issue", "message", "content", "text", "description"}
GENERIC_WORDS = ("您刚才", "让我", "的是", "查询", "联系", "部门", "近期", "最新信息", "酒店", "请", "正通过", "正在", "再次", "当前")
DOMAIN_WORDS = ("安保", "撤离", "疏散", "楼梯", "接应", "火情", "起火", "冒烟", "焦味", "无烟房", "安静楼层",
                "毛巾", "前台", "雨伞", "洗手池", "漏水", "状态", "下行", "电梯", "叫醒", "消防", "房间")
ALIASES = {"住客": "客人", "疏散": "撤离", "楼梯间": "楼梯", "安保部门": "安保", "安保部": "security"}


def normalize_text(value: str):
    text = str(value).lower().strip()
    for source, target in ALIASES.items():
        text = text.replace(source, target)
    return re.sub(r"[\s，。！？、；：:,.!?;\"“”'‘’（）()]+", "", text)


def text_keywords(expected: str):
    normalized = normalize_text(expected)
    keywords = [normalize_text(word) for word in DOMAIN_WORDS if normalize_text(word) in normalized]
    quoted = re.findall(r"[“\"]([^”\"]+)[”\"]", expected)
    source = " ".join(quoted) if quoted else expected
    for word in GENERIC_WORDS:
        source = source.replace(word, " ")
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.:-]*|\d+(?:[-:T]\d+)+|\d+|[\u4e00-\u9fff]{2,}", source):
        token = normalize_text(token)
        if len(token) >= 2 and token not in keywords:
            keywords.append(token)
    # Prefer concrete domain facts over a long residual sentence fragment.
    domain = [item for item in keywords if any(item == normalize_text(word) for word in DOMAIN_WORDS)]
    return domain or keywords


def validate_text(expected: str, actual: str | None):
    if not isinstance(actual, str) or not actual.strip():
        return {"result_type": "text", "passed": False, "reason": "模型没有返回文本", "errors": []}
    wanted, received = normalize_text(expected), normalize_text(actual)
    if wanted == received:
        return {"result_type": "text", "passed": True, "reason": "标准化后文本完全一致",
                "keywords": [], "matched_keywords": [], "errors": []}
    keywords = text_keywords(expected)
    matched = [word for word in keywords if word in received]
    required = max(1, ceil(len(keywords) * .5)) if keywords else 1
    passed = len(matched) >= required
    return {"result_type": "text", "passed": passed,
            "reason": f"命中关键词 {len(matched)}/{len(keywords)}，要求至少 {required} 个",
            "keywords": keywords, "matched_keywords": matched,
            "errors": [] if passed else [{"type": "missing_keywords",
                                             "missing": [word for word in keywords if word not in matched]}]}


def _tool_call(candidate_call):
    choices = ((candidate_call or {}).get("response") or {}).get("choices") or []
    if not choices:
        raise ValueError("模型响应中没有 choices")
    calls = ((choices[0].get("message") or {}).get("tool_calls") or [])
    if len(calls) != 1:
        raise ValueError(f"必须返回一个原生 tool_call，实际为 {len(calls)} 个")
    function = calls[0].get("function") or {}
    name, arguments = function.get("name"), function.get("arguments")
    parameters = json.loads(arguments)
    if not isinstance(parameters, dict):
        raise ValueError("tool_call arguments 必须是 JSON 对象")
    return dataset_result(name, parameters)


def _compare(expected, actual, path="$"):
    errors = []
    if path.endswith(".top_k") or path.endswith(".freshness_days"):
        return errors
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [{"path": path, "type": "type_mismatch", "expected": "object"}]
        for key in expected.keys() - actual.keys():
            errors.append({"path": f"{path}.{key}", "type": "missing_field"})
        for key in actual.keys() - expected.keys():
            errors.append({"path": f"{path}.{key}", "type": "extra_field"})
        for key in expected.keys() & actual.keys():
            if key in SEMANTIC_FIELDS and isinstance(expected[key], str) and isinstance(actual[key], str):
                result = validate_text(expected[key], actual[key])
                if not result["passed"]:
                    errors.append({"path": f"{path}.{key}", "type": "keyword_mismatch",
                                   "detail": result})
            else:
                errors.extend(_compare(expected[key], actual[key], f"{path}.{key}"))
    elif isinstance(expected, list):
        if not isinstance(actual, list):
            return [{"path": path, "type": "type_mismatch", "expected": "array"}]
        if sorted(expected, key=str) != sorted(actual, key=str):
            errors.append({"path": path, "type": "value_mismatch", "expected": expected, "actual": actual})
    elif path.endswith(".wakeup_time") and isinstance(expected, str) and isinstance(actual, str):
        def canonical_time(value):
            value = re.sub(r"\s+", "", value).replace("T", "")
            return value[:-3] if value.endswith(":00") and value.count(":") >= 2 else value
        if canonical_time(expected) != canonical_time(actual):
            errors.append({"path": path, "type": "value_mismatch", "expected": expected, "actual": actual})
    elif expected != actual or type(expected) is not type(actual):
        errors.append({"path": path, "type": "value_mismatch", "expected": expected, "actual": actual})
    return errors


def validate_result(expected_text: str, actual_text: str | None, candidate_call=None):
    try:
        expected = json.loads(expected_text)
    except (TypeError, json.JSONDecodeError):
        return validate_text(expected_text, actual_text)
    if (candidate_call or {}).get("error"):
        return {"result_type": "json", "passed": False,
                "reason": f"模型调用或工具 schema 校验失败：{candidate_call['error']}",
                "errors": [{"path": "$", "type": "candidate_call_failed",
                            "message": candidate_call["error"]}]}
    try:
        actual = _tool_call(candidate_call)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"result_type": "json", "passed": False, "reason": str(exc),
                "errors": [{"path": "$", "type": "tool_call_invalid", "message": str(exc)}]}
    expected = {**expected, "parameters": normalize_dataset_parameters(expected["methed"], expected["parameters"])}
    errors = _compare(expected, actual)
    return {"result_type": "json", "passed": not errors,
            "reason": "原生工具调用及参数校验通过" if not errors else "工具调用参数不符合标准答案",
            "expected_parsed": expected, "actual_parsed": actual, "errors": errors}
