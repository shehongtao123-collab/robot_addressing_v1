"""In-memory reports for generated-result evaluation."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from reporting.intent_reports import latency_statistics, source_models, timestamp


def result_statistics(rows):
    def candidate(row):
        return row.get("candidate_call") or {}

    def judgment(row):
        return row.get("judgment") or {}

    total = len(rows)
    result_calls = [candidate(row) for row in rows if row.get("candidate_call") is not None]
    usage_calls = [call for call in result_calls if isinstance(call.get("usage"), dict)]
    passed = sum(bool(row.get("passed")) for row in rows)
    valid = sum(row.get("result_status", "evaluated") == "evaluated"
                and not candidate(row).get("error")
                and not judgment(row).get("judge_failed") for row in rows)
    types = Counter(row.get("result_type", "unknown") for row in rows)
    text_rows = [row for row in rows if row.get("result_type") == "text"]
    json_rows = [row for row in rows if row.get("result_type") == "json"]
    scores = [judgment(row)["score"] for row in text_rows if type(judgment(row).get("score")) in (int, float)]
    json_parse_ok = sum(not any(error.get("type") == "json_parse_error" for error in judgment(row).get("errors", [])) for row in json_rows)
    error_types = Counter(error.get("type", "unknown") for row in json_rows for error in judgment(row).get("errors", []))
    return {"total": total, "passed": passed, "failed": total - passed,
            "pass_rate": passed / total if total else 0, "coverage": valid / total if total else 0,
            "text_total": len(text_rows), "text_passed": sum(row.get("passed", False) for row in text_rows),
            "text_pass_rate": sum(row.get("passed", False) for row in text_rows) / len(text_rows) if text_rows else 0,
            "json_total": len(json_rows), "json_passed": sum(row.get("passed", False) for row in json_rows),
            "json_pass_rate": sum(row.get("passed", False) for row in json_rows) / len(json_rows) if json_rows else 0,
            "json_parse_rate": json_parse_ok / len(json_rows) if json_rows else 0,
            "average_text_score": sum(scores) / len(scores) if scores else None,
            "candidate_failures": sum(bool(candidate(row).get("error")) for row in rows),
            "judge_failures": sum(bool(judgment(row).get("judge_failed")) for row in rows),
            "validation_failures": sum(row.get("result_status", "evaluated") == "evaluated"
                                       and not row.get("passed", False)
                                       and not candidate(row).get("error") for row in rows),
            "result_types": dict(types), "json_error_types": dict(error_types),
            "latency": latency_statistics(rows),
            "result_call_count": len(result_calls),
            "result_usage_count": len(usage_calls),
            "missing_usage_count": len(result_calls) - len(usage_calls),
            "input_tokens": sum(row.get("input_tokens") or 0 for row in rows),
            "output_tokens": sum(row.get("output_tokens") or 0 for row in rows),
            "total_tokens": sum(row.get("total_tokens") or 0 for row in rows)}


def aggregate_rows(rows):
    groups = {}
    for row in rows:
        key = (row["conversation_id"], row["id"])
        group = groups.setdefault(key, {"id": row["id"], "conversation_id": row["conversation_id"],
            "user_request": row["user_request"], "expected_text": row["expected_text"],
            "result_type": row["result_type"], "tag": row["tag"], "tests": 0, "passed_count": 0,
            "evaluations": []})
        group["tests"] += 1
        group["passed_count"] += bool(row.get("passed"))
        group["evaluations"].append({key: row.get(key) for key in ("round", "source_run_id", "source_round",
            "passed", "actual_text", "error", "request_anchor", "request_link")})
    for group in groups.values():
        group["pass_rate"] = group["passed_count"] / group["tests"]
        group["request_link"] = group["evaluations"][-1]["request_link"]
    return list(groups.values())


def result_function(row):
    """Return a stable, user-facing functional category for a result case."""
    tag = row.get("tag") or "未分类"
    aliases = {"方法调用": "methed 调用", "上下文记忆": "历史对话问答"}
    return aliases.get(tag, str(tag))


def _sources(results_root, include_incomplete):
    sources = []
    for directory in results_root.iterdir() if results_root.exists() else ():
        if not directory.is_dir():
            continue
        try:
            raw = json.loads((directory / "details.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            continue
        meta = raw["metadata"]
        if meta.get("evaluation_type") not in ("result", "combined") or (meta["status"] != "complete" and not include_incomplete):
            continue
        sources.append((directory, raw))
    sources.sort(key=lambda item: (timestamp(item[1]["metadata"]["started_at"]), item[0].name))
    return sources


def result_history(results_root: Path, *, include_incomplete=True, per_run=False):
    sources = _sources(results_root, include_incomplete)
    groups, all_rows = {}, []
    for directory, raw in sources:
        meta = raw["metadata"]
        # Combined runs contain every human intent case.  Result metrics only
        # apply to cases that have a dataset reference response.  A missed
        # addressing prediction remains present here as a failed/skipped result.
        rows = []
        for source in raw["results"]:
            # Historical combined runs briefly attached a robot reply to any
            # immediately preceding human, including gold-ignore turns.  Such
            # rows are not result-evaluation cases.  Gold-addressing misses
            # remain included so intent gating failures stay in the denominator.
            if source.get("expected_text") is None or source.get("expected") != "addressing":
                continue
            row = deepcopy(source)
            row.pop("relevant_context", None)
            call = row.get("candidate_call") or {}
            usage = call.get("usage") or {}
            row.update({"latency_seconds": call.get("latency_seconds"),
                        "input_tokens": usage.get("prompt_tokens"),
                        "output_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "error": call.get("error")})
            rows.append(row)
        for model_number, model in enumerate(source_models(meta, rows), 1):
            validator = meta.get("result_validator") or {"type": "legacy_ai_judge",
                "model": meta.get("judge", {}).get("model"), "prompt": meta.get("judge_prompt_sha256")}
            validator_key = json.dumps(validator, ensure_ascii=False, sort_keys=True)
            key = ((directory.name,) if per_run else ()) + (model["model"], meta["dataset_sha256"], validator_key)
            group = groups.setdefault(key, {**model, "profile": "result-" + hashlib.sha256(repr(key).encode()).hexdigest()[:16],
                "dataset_sha256": meta["dataset_sha256"], "conversation_id": meta["conversation_id"],
                "validator": validator, "judge": meta.get("judge"),
                "judge_prompt_sha256": meta.get("judge_prompt_sha256"),
                "run_id": directory.name if per_run else None, "run_started_at": meta["started_at"],
                "source_run_ids": [], "round_count": 0, "rounds": [], "rows_raw": []})
            group["source_run_ids"].append(directory.name)
            model_rows = [row for row in rows if row["profile"] == model["profile"]]
            for source_round in sorted({row["round"] for row in model_rows}):
                round_rows = [row for row in model_rows if row["round"] == source_round]
                group["round_count"] += 1
                number = group["round_count"]
                group["rounds"].append({"round": number, "source_run_id": directory.name,
                    "source_round": source_round, "statistics": result_statistics(round_rows)})
                for row in round_rows:
                    anchor = f"result-{directory.name}-m{model_number}-r{source_round}-{row['id']}"
                    item = {**deepcopy(row), "profile": group["profile"], "round": number,
                            "source_run_id": directory.name, "source_round": source_round,
                            "request_anchor": anchor,
                            "request_link": f"result_details.html#{anchor}"}
                    group["rows_raw"].append(item)
                    all_rows.append(item)
    models = []
    for group in groups.values():
        rows = group.pop("rows_raw")
        group.update({"statistics": result_statistics(rows),
                      "by_tag": {tag: result_statistics([row for row in rows if row["tag"] == tag])
                                 for tag in sorted({row["tag"] for row in rows})},
                      "by_function": {name: result_statistics([row for row in rows if result_function(row) == name])
                                      for name in sorted({result_function(row) for row in rows})},
                      "rows": aggregate_rows(rows)})
        models.append(group)
    metadata = {"schema_version": 1, "evaluation_type": "result", "aggregate": True,
                "run_comparison": per_run, "status": "complete", "model_count": len(models),
                "dataset_count": len({model["dataset_sha256"] for model in models}),
                "completed_evaluations": len(all_rows), "source_runs": [directory.name for directory, _ in sources],
                "generated_at": datetime.now(timezone.utc).isoformat()}
    return {"metadata": metadata, "models": models}, {"metadata": metadata, "results": all_rows}
