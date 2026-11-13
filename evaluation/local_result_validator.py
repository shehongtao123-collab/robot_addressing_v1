"""Deterministic response validation without an AI judge."""

from __future__ import annotations

from math import ceil
import json
import os
import re

from hotel_tools.mock_functions import dataset_result, normalize_dataset_parameters


SEMANTIC_FIELDS = {"reason", "notes", "query", "issue", "message", "content", "text", "description"}
GENERIC_WORDS = ("您刚才", "让我", "的是", "查询", "联系", "部门", "近期", "最新信息", "酒店", "请", "正通过", "正在", "再次", "当前")
DOMAIN_WORDS = ("安保", "撤离", "疏散", "楼梯", "接应", "火情", "起火", "冒烟", "焦味", "无烟房", "安静楼层",
                "毛巾", "前台", "雨伞", "洗手池", "漏水", "状态", "下行", "电梯", "叫醒", "消防", "房间")
ALIASES = {
    "住客": "客人", "疏散": "撤离", "楼梯间": "楼梯",
    "安保部门": "安保", "安保部": "security",
    # Common action paraphrases.  Normalize the concrete object/action while
    # leaving names, numbers and operational fields to strict comparison.
    "客房房门把手": "客房门", "房门把手": "房门",
    "拉动": "拉", "到现场查看": "现场核查", "到场查看": "现场核查",
    "交通管制": "管制",
}
CONTRADICTION_FORMS = (
    ("允许", ("不允许", "禁止")),
    ("可以", ("不可以", "不能", "禁止")),
    ("需要", ("不需要", "无需")),
)


def embedding_threshold():
    value = os.getenv("RESULT_EMBEDDING_THRESHOLD", "0.72")
    try:
        threshold = float(value)
    except ValueError as exc:
        raise ValueError("RESULT_EMBEDDING_THRESHOLD 必须是 0 到 1 之间的数字") from exc
    if not 0 <= threshold <= 1:
        raise ValueError("RESULT_EMBEDDING_THRESHOLD 必须是 0 到 1 之间的数字")
    return threshold


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


def _critical_facts(value: str):
    """Extract exact facts which an embedding score must never override."""
    normalized = normalize_text(value)
    numbers = re.findall(r"\d+(?::\d+|[-T]\d+)*", normalized)
    return {"numbers": numbers}


def _has_direct_contradiction(expected: str, actual: str):
    wanted, received = normalize_text(expected), normalize_text(actual)
    for positive, negatives in CONTRADICTION_FORMS:
        expected_negative = any(item in wanted for item in negatives)
        actual_negative = any(item in received for item in negatives)
        if positive in wanted and positive in received and expected_negative != actual_negative:
            return True
    return False


def validate_text(expected: str, actual: str | None, similarity_fn=None):
    if not isinstance(actual, str) or not actual.strip():
        return {"result_type": "text", "passed": False, "reason": "模型没有返回文本", "errors": []}
    wanted, received = normalize_text(expected), normalize_text(actual)
    if wanted == received:
        return {"result_type": "text", "passed": True, "reason": "标准化后文本完全一致",
                "keywords": [], "matched_keywords": [], "errors": []}
    expected_facts, actual_facts = _critical_facts(expected), _critical_facts(actual)
    fact_errors = []
    missing_numbers = [item for item in expected_facts["numbers"] if item not in actual_facts["numbers"]]
    if missing_numbers:
        fact_errors.append({"type": "missing_numbers", "missing": missing_numbers})
    if _has_direct_contradiction(expected, actual):
        fact_errors.append({"type": "direct_contradiction"})
    keywords = text_keywords(expected)
    matched = [word for word in keywords if word in received]
    required = max(1, ceil(len(keywords) * .5)) if keywords else 1
    passed = len(matched) >= required
    if passed and not fact_errors:
        return {"result_type": "text", "passed": True,
                "reason": f"命中关键词 {len(matched)}/{len(keywords)}，要求至少 {required} 个",
                "keywords": keywords, "matched_keywords": matched,
                "embedding_similarity": None, "embedding_threshold": embedding_threshold(),
                "errors": []}

    threshold, similarity, embedding_error = embedding_threshold(), None, None
    if fact_errors:
        passed = False
    else:
        try:
            if similarity_fn is None:
                from evaluation.text_embeddings import cosine_similarity
                similarity_fn = cosine_similarity
            similarity = float(similarity_fn(expected, actual))
            passed = similarity >= threshold
        except Exception as exc:  # A missing optional runtime must not abort a report.
            embedding_error = str(exc)
            passed = False

    reason = (f"向量相似度 {similarity:.4f}，阈值 {threshold:.2f}" if similarity is not None
              else "关键事实不一致" if fact_errors
              else f"向量相似度不可用：{embedding_error}")
    errors = [] if passed else fact_errors or [{"type": "semantic_similarity_below_threshold",
                                                  "similarity": similarity,
                                                  "threshold": threshold,
                                                  "message": embedding_error}]
    return {"result_type": "text", "passed": passed,
            "reason": reason,
            "keywords": keywords, "matched_keywords": matched,
            "embedding_similarity": similarity, "embedding_threshold": threshold,
            "errors": errors}


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


def _compare(expected, actual, path="$", similarity_fn=None, embedding_scores=None):
    if embedding_scores is None:
        embedding_scores = []
    errors = []
    if path.endswith(".top_k") or path.endswith(".freshness_days"):
        return errors
    if path == "$.parameters.priority" and isinstance(expected, str) and isinstance(actual, str):
        # Escalating a human handoff is safe and semantically compatible;
        # downgrading it is not.  Other enum fields remain exact matches.
        levels = {"normal": 0, "high": 1, "emergency": 2}
        if expected in levels and actual in levels and levels[actual] >= levels[expected]:
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
                result = validate_text(expected[key], actual[key], similarity_fn)
                if result.get("embedding_similarity") is not None:
                    embedding_scores.append({
                        "path": f"{path}.{key}", "expected": expected[key], "actual": actual[key],
                        "similarity": result["embedding_similarity"],
                        "threshold": result["embedding_threshold"], "passed": result["passed"],
                        "reason": result["reason"],
                    })
                if not result["passed"]:
                    errors.append({"path": f"{path}.{key}", "type": "semantic_mismatch",
                                   "detail": result})
            else:
                errors.extend(_compare(expected[key], actual[key], f"{path}.{key}", similarity_fn,
                                       embedding_scores))
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


def validate_result(expected_text: str, actual_text: str | None, candidate_call=None, similarity_fn=None):
    try:
        expected = json.loads(expected_text)
    except (TypeError, json.JSONDecodeError):
        result = validate_text(expected_text, actual_text, similarity_fn)
        result["embedding_scores"] = ([{
            "path": "$", "expected": expected_text, "actual": actual_text,
            "similarity": result["embedding_similarity"],
            "threshold": result["embedding_threshold"], "passed": result["passed"],
            "reason": result["reason"],
        }] if result.get("embedding_similarity") is not None else [])
        return result
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
    embedding_scores = []
    errors = _compare(expected, actual, similarity_fn=similarity_fn, embedding_scores=embedding_scores)
    return {"result_type": "json", "passed": not errors,
            "reason": "原生工具调用及参数校验通过" if not errors else "工具调用参数不符合标准答案",
            "expected_parsed": expected, "actual_parsed": actual,
            "embedding_scores": embedding_scores, "errors": errors}
