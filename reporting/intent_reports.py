"""Report statistics and history imports; standard library only."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from math import ceil
from pathlib import Path

from evaluate import DATASET_PATH, ROOT, iter_inputs, metrics, read_jsonl, require, validate
from evaluation.intent_parser import parse_intents


def write_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def percentile(values, probability):
    """Nearest-rank percentile, suitable for operational tail-latency reporting."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(probability * len(ordered)) - 1))
    return ordered[index]


def latency_statistics(results):
    latencies = [float(row["latency_seconds"]) for row in results
                 if type(row.get("latency_seconds")) in (int, float) and row["latency_seconds"] >= 0]
    buckets = {}
    points = []
    for row in results:
        tokens, latency = row.get("input_tokens"), row.get("latency_seconds")
        if type(tokens) is not int or tokens < 0 or type(latency) not in (int, float) or latency < 0:
            continue
        start = tokens // 1000 * 1000
        buckets.setdefault(start, []).append(float(latency))
        points.append({"id": row.get("id"), "input_tokens": tokens,
                       "output_tokens": row.get("output_tokens"),
                       "latency_seconds": float(latency)})
    under_1 = sum(value < 1 for value in latencies)
    from_1_to_2 = sum(1 <= value < 2 for value in latencies)
    at_least_2 = sum(value >= 2 for value in latencies)
    total = len(latencies)
    return {
        "count": total,
        "average_seconds": sum(latencies) / total if latencies else None,
        "p50_seconds": percentile(latencies, .50),
        "p95_seconds": percentile(latencies, .95),
        "p99_seconds": percentile(latencies, .99),
        "max_seconds": max(latencies) if latencies else None,
        "missing_count": len(results) - total,
        "latency_bands": {
            "under_1_second": {"count": under_1, "ratio": under_1 / total if total else None},
            "from_1_to_2_seconds": {"count": from_1_to_2, "ratio": from_1_to_2 / total if total else None},
            "at_least_2_seconds": {"count": at_least_2, "ratio": at_least_2 / total if total else None},
        },
        "token_bucket_size": 1000,
        "charted_count": len(points),
        "input_token_points": points,
        "input_token_buckets": [
            {"start": start, "end": start + 999, "count": len(values),
             "average_seconds": sum(values) / len(values),
             "p95_seconds": percentile(values, .95), "max_seconds": max(values)}
            for start, values in sorted(buckets.items())
        ],
    }


def statistics(results, label_key):
    gold = [{"id": str(index), label_key: row["expected"]} for index, row in enumerate(results)]
    predictions = {str(index): {"intent": row["intent"]} for index, row in enumerate(results)}
    return {**metrics(gold, predictions, label_key), "latency": latency_statistics(results),
            "known_input_tokens": sum(row["known_input_tokens"] for row in results),
            "known_output_tokens": sum(row.get("known_output_tokens", 0) for row in results),
            "known_total_tokens": sum(row.get("known_total_tokens", 0) for row in results),
            "missing_usage_count": sum(row["missing_usage_count"] for row in results),
            "http_attempts": sum(attempt["request"] is not None for row in results for attempt in row["attempts"]),
            "unrecorded_http_attempts": sum(row.get("legacy_import", False) for row in results)}


def aggregate_utterances(results):
    """One row per utterance; every recorded test contributes to its denominator."""
    groups = {}
    for row in results:
        key = (row["conversation_id"], row["id"])
        if key not in groups:
            groups[key] = {key: row[key] for key in ("id", "conversation_id", "text", "speaker_id", "tag", "expected")}
            groups[key].update({"rounds": 0, "correct_count": 0, "failed_count": 0,
                                "known_input_tokens": 0, "known_output_tokens": 0, "known_total_tokens": 0,
                                "missing_usage_count": 0, "evaluations": []})
        group = groups[key]
        require(group["text"] == row["text"] and group["expected"] == row["expected"],
                "Cannot aggregate conflicting utterance text or reference labels")
        group["rounds"] += 1
        group["correct_count"] += row["correct"]
        group["failed_count"] += bool(row.get("error"))
        for field in ("known_input_tokens", "known_output_tokens", "known_total_tokens", "missing_usage_count"):
            group[field] += row.get(field, 0)
        group["evaluations"].append({key: row[key] for key in
            ("round", "source_run_id", "source_round", "source_evaluation_valid", "source_invalidated_reason",
             "intent", "correct", "error", "input_tokens", "output_tokens", "total_tokens", "request_link", "request_anchor")
             if key in row})
    for group in groups.values():
        group["accuracy"] = group["correct_count"] / group["rounds"]
        group["incorrect_count"] = group["rounds"] - group["correct_count"]
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            values = [row.get(field) for row in group["evaluations"]]
            known = [value for value in values if value is not None]
            group[field] = sum(known) if len(known) == len(values) else None
            group["known_final_" + field] = sum(known)
        group["request_link"] = group["evaluations"][-1].get("request_link")
    return list(groups.values())


def build_reports(metadata, descriptions, results):
    results = deepcopy(results)
    models = []
    for config in descriptions:
        rows = [row for row in results if row["profile"] == config["profile"]]
        models.append({"human_utterances_per_round": metadata["human_utterances_per_round"],
                       "full_dataset_human_utterances": metadata["full_dataset_human_utterances"],
                       **config, "statistics": statistics(rows, metadata["label_key"]),
                       "rounds": [{**next((source for source in config.get("round_sources", []) if source["round"] == number), {}),
                                   "round": number, "statistics": statistics([row for row in rows if row["round"] == number], metadata["label_key"])}
                                  for number in range(1, config.get("round_count", metadata["rounds"]) + 1)],
                       "by_speaker": {speaker: statistics([row for row in rows if row["speaker_id"] == speaker], metadata["label_key"])
                                      for speaker in sorted({row["speaker_id"] for row in rows})},
                       "by_tag": {tag: statistics([row for row in rows if row["tag"] == tag], metadata["label_key"])
                                  for tag in sorted({row["tag"] for row in rows})},
                       "rows": aggregate_utterances(rows)})
    summary = {"metadata": metadata, "models": models}
    details = {"metadata": metadata, "results": results}
    return summary, details


def source_models(metadata, results):
    """Read model identity from raw metadata, with a fallback for older records."""
    if metadata.get("models"):
        return metadata["models"]
    models = {}
    for row in results:
        if row["profile"] in models:
            continue
        endpoint = next((attempt["request"]["url"].rsplit("/chat/completions", 1)[0]
                         for attempt in row.get("attempts", []) if attempt.get("request")), "not recorded")
        models[row["profile"]] = {"profile": row["profile"], "model": row["model"], "base_url": endpoint}
    return list(models.values())


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def import_legacy(source: Path, results_root: Path, label_key: str, dataset_path=DATASET_PATH):
    """Import retained predictions without inventing old requests or usage."""
    run = json.loads((source / "run.json").read_text(encoding="utf-8"))
    original = json.loads((source / f"{label_key}_report.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    require(run.get("dataset_sha256") == digest, "Legacy report belongs to a different or unverifiable dataset")
    conversation, gold = validate(dataset_path)
    predictions = read_jsonl(source / "predictions.jsonl")
    answers = {row["id"]: row for row in gold}
    require(len({row["id"] for row in predictions}) == len(predictions), "Legacy predictions contain duplicate IDs")
    rows = []
    for number, prediction in enumerate(predictions):
        require(prediction.get("id") in answers, "Legacy predictions contain an unknown/non-human ID")
        require(prediction.get("intent") in ("addressing", "ignore", None), "Legacy prediction has an invalid intent")
        require(prediction.get("intent") is not None or bool(prediction.get("error")), "Legacy failure requires an error")
        answer = answers[prediction["id"]]
        anchor = f"request-m1-r1-{prediction['id']}"
        rows.append({"profile": run["profile"], "model": run["model"], "round": 1,
                     "id": answer["id"], "conversation_id": answer["conversation_id"], "text": answer["text"],
                     "speaker_id": answer["speaker_id"], "tag": answer["tag"], "expected": answer[label_key],
                     "intent": prediction["intent"], "correct": prediction["intent"] == answer[label_key],
                     "reason": answer["reason"], "error": prediction.get("error"),
                     "latency_seconds": prediction.get("latency_seconds", 0), "known_input_tokens": 0,
                     "input_tokens": None, "output_tokens": None, "total_tokens": None,
                     "known_output_tokens": 0, "known_total_tokens": 0, "missing_usage_count": 1, "legacy_import": True,
                     "request_anchor": anchor, "request_link": f"details.html#{anchor}",
                     "attempts": [{"attempt": None, "request": None, "response": None, "usage": None,
                                   "request_capture_status": "not_recorded", "error": prediction.get("error"),
                                   "legacy_raw_output": prediction.get("raw_output"),
                                   "latency_seconds": prediction.get("latency_seconds", 0)}]})
    observed = statistics(rows, label_key)
    for key in ("total", "correct", "accuracy", "precision", "recall", "f1", "coverage", "false_activation_rate", "confusion"):
        require(observed[key] == original[key], f"Legacy metric mismatch: {key}")
    metadata = {"schema_version": 1, "legacy_import": True, "source_directory": str(source.resolve()),
                "source_run_id": source.name, "started_at": run["started_at"], "finished_at": run.get("finished_at"),
                "status": "complete" if len(rows) == len(gold) else "interrupted", "rounds": 1, "model_count": 1,
                "label_key": label_key, "conversation_id": gold[0]["conversation_id"], "conversation_utterances": len(conversation),
                "human_utterances_per_round": len(gold), "full_dataset_human_utterances": len(gold),
                "planned_evaluations": len(gold), "completed_evaluations": len(rows), "dataset_sha256": digest,
                "prompt_sha256": run.get("instructions_sha256", "not recorded"), "prompt_file": "legacy snapshot",
                "elapsed_seconds": run.get("elapsed_seconds", 0), "history_mode": run.get("history_mode"),
                "token_source": "Legacy run did not retain token usage or full HTTP requests"}
    target = results_root / ("legacy_" + source.name + "_" + label_key)
    if target.exists():
        saved = json.loads((target / "details.json").read_text())
        require(saved["metadata"].get("source_directory") == str(source.resolve()), "Legacy destination belongs to another source")
    config = {"profile": run["profile"], "model": run["model"], "base_url": run["endpoint"],
              "source_run_id": source.name, "legacy_import": True, "source_statistics": original}
    metadata["models"] = [config]
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / "details.json", {"metadata": metadata, "results": rows})
    return target


def refresh_history(results_root: Path, label_key: str, *, include_incomplete=True):
    """Read current raw results and compute both views in memory. Never write files."""
    sources, flagged = [], []
    for directory in results_root.iterdir() if results_root.exists() else ():
        if not directory.is_dir() or directory.name == "history":
            continue
        try:
            details = json.loads((directory / "details.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            continue
        meta = details["metadata"]
        if meta.get("evaluation_type", "intent") not in ("intent", "combined"):
            continue
        if meta["label_key"] != label_key or (meta["status"] != "complete" and not include_incomplete):
            continue
        if meta.get("evaluation_valid") is False:
            flagged.append({"id": directory.name, "reason": meta["invalidated_reason"]})
        sources.append((directory, details))
    if not sources:
        conversation, gold = validate()
        metadata = {"schema_version": 1, "aggregate": True, "status": "complete", "model_count": 0,
                    "rounds": 0, "label_key": label_key, "conversation_id": conversation[0]["conversation_id"],
                    "conversation_utterances": len(conversation), "human_utterances_per_round": len(gold),
                    "full_dataset_human_utterances": len(gold), "completed_evaluations": 0,
                    "planned_evaluations": 0, "elapsed_seconds": 0, "source_runs": [], "flagged_runs": [],
                    "dataset_sha256": hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
                    "prompt_sha256": "no test results", "evaluation_valid": True}
        return build_reports(metadata, [], [])
    sources.sort(key=lambda source: (timestamp(source[1]["metadata"]["started_at"]), source[0].name))
    hashes = {source[1]["metadata"]["dataset_sha256"] for source in sources}
    groups, results, rounds = {}, [], []
    for directory, details in sources:
        source_meta = details["metadata"]
        digest = source_meta["dataset_sha256"]
        for model_number, model in enumerate(source_models(source_meta, details["results"]), 1):
            key = (model["model"], digest)
            if key not in groups:
                group_id = "group-" + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:20]
                groups[key] = {"profile": group_id, "model": model["model"], "base_url": model["base_url"],
                               "dataset_sha256": digest, "conversation_id": source_meta["conversation_id"],
                               "human_utterances_per_round": source_meta["human_utterances_per_round"],
                               "full_dataset_human_utterances": source_meta["full_dataset_human_utterances"],
                               "round_count": 0, "round_sources": [], "profile_names": [], "source_run_ids": [],
                               "has_legacy_import": False}
            group = groups[key]
            if model["profile"] not in group["profile_names"]:
                group["profile_names"].append(model["profile"])
            if directory.name not in group["source_run_ids"]:
                group["source_run_ids"].append(directory.name)
            group["has_legacy_import"] |= source_meta.get("legacy_import", False)
            source_rows = [row for row in details["results"] if row["profile"] == model["profile"]]
            for source_round in sorted({row["round"] for row in source_rows}):
                rows = [row for row in source_rows if row["round"] == source_round]
                started = source_meta.get("round_started_at", {}).get(model["profile"], {}).get(str(source_round))
                started = started or next((row["started_at"] for row in rows if row.get("started_at")), source_meta["started_at"])
                rounds.append({"key": key, "directory": directory, "model": model, "model_number": model_number,
                               "metadata": source_meta, "source_round": source_round, "rows": rows, "started_at": started})
    rounds.sort(key=lambda item: (timestamp(item["started_at"]), timestamp(item["metadata"]["started_at"]),
                                  item["directory"].name, item["source_round"], item["model_number"]))
    for item in rounds:
        group = groups[item["key"]]
        group["round_count"] += 1
        number = group["round_count"]
        source_meta, model, directory = item["metadata"], item["model"], item["directory"]
        source_round = item["source_round"]
        group["round_sources"].append({"round": number, "source_round": source_round,
            "source_run_id": directory.name, "source_profile": model["profile"],
            "started_at": item["started_at"], "source_status": source_meta["status"],
            "source_started_at": source_meta["started_at"],
            "source_evaluation_valid": source_meta.get("evaluation_valid", True),
            "source_invalidated_reason": source_meta.get("invalidated_reason"),
            "human_utterances_per_round": source_meta["human_utterances_per_round"],
            "prompt_sha256": source_meta["prompt_sha256"], "base_url": model["base_url"],
            "source_statistics": model.get("source_statistics")})
        for row in item["rows"]:
            anchor = f"request-{directory.name}-m{item['model_number']}-r{source_round}-{row['id']}"
            results.append({**row, "profile": group["profile"], "round": number,
                            "dataset_sha256": item["key"][1], "source_run_id": directory.name,
                            "source_round": source_round, "source_profile": model["profile"],
                            "source_status": source_meta["status"],
                            "source_evaluation_valid": source_meta.get("evaluation_valid", True),
                            "source_invalidated_reason": source_meta.get("invalidated_reason"),
                            "request_anchor": anchor, "request_link": f"details.html#{anchor}"})
    descriptions = list(groups.values())
    first = sources[0][1]["metadata"]
    metadata = {**first, "aggregate": True, "legacy_import": False, "model_count": len(descriptions),
                "grouping": "model ID + dataset SHA-256 + utterance ID; accuracy = correct count / test count",
                "round_order": "ascending round start time; earliest round is 1",
                "dataset_sha256": next(iter(hashes)) if len(hashes) == 1 else "multiple datasets; see model groups",
                "dataset_count": len(hashes), "excluded_runs": [], "flagged_runs": flagged,
                "evaluation_valid": not bool(flagged),
                "status": "complete" if all(source[1]["metadata"]["status"] == "complete" for source in sources) else "interrupted",
                "rounds": max((group["round_count"] for group in descriptions), default=0),
                "started_at": first["started_at"], "finished_at": datetime.now(timezone.utc).isoformat(),
                "prompt_sha256": "multiple snapshots; see each round source", "completed_evaluations": len(results),
                "planned_evaluations": sum(source[1]["metadata"]["planned_evaluations"] for source in sources),
                "elapsed_seconds": sum(source[1]["metadata"].get("elapsed_seconds", 0) for source in sources),
                "source_runs": [{"id": directory.name, "status": details["metadata"]["status"],
                                 "started_at": details["metadata"]["started_at"], "prompt_sha256": details["metadata"]["prompt_sha256"]}
                                for directory, details in sources]}
    return build_reports(metadata, descriptions, results)


def compare_runs(results_root: Path, label_key: str, *, include_incomplete=True):
    """Build one independent report group per saved command run and model profile."""
    models, source_runs = [], []
    for directory in sorted(results_root.iterdir()) if results_root.exists() else ():
        if not directory.is_dir() or directory.name == "history":
            continue
        try:
            raw = json.loads((directory / "details.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, NotADirectoryError):
            continue
        metadata, results = raw["metadata"], raw["results"]
        if metadata.get("evaluation_type", "intent") not in ("intent", "combined"):
            continue
        if metadata["label_key"] != label_key or (metadata["status"] != "complete" and not include_incomplete):
            continue
        descriptions = source_models(metadata, results)
        summary, _ = build_reports(metadata, descriptions, results)
        source_runs.append({"id": directory.name, "status": metadata["status"],
                            "started_at": metadata["started_at"], "finished_at": metadata.get("finished_at"),
                            "dataset_sha256": metadata["dataset_sha256"],
                            "completed_evaluations": metadata["completed_evaluations"]})
        for model in summary["models"]:
            for row in model["rows"]:
                anchor = row["request_anchor"] if "request_anchor" in row else row["evaluations"][-1].get("request_anchor")
                row["request_link"] = f"details.html?run={directory.name}#{anchor}"
            model.update({"profile": f"run-{directory.name}-{model['profile']}",
                          "run_id": directory.name, "run_status": metadata["status"],
                          "run_started_at": metadata["started_at"], "run_finished_at": metadata.get("finished_at"),
                          "dataset_sha256": metadata["dataset_sha256"],
                          "conversation_id": metadata["conversation_id"],
                          "source_run_ids": [directory.name]})
            models.append(model)
    models.sort(key=lambda model: (timestamp(model["run_started_at"]), model["run_id"], model["model"]))
    if source_runs:
        first_meta = json.loads((results_root / source_runs[0]["id"] / "details.json").read_text(encoding="utf-8"))["metadata"]
        metadata = {**first_meta, "aggregate": True, "run_comparison": True,
                    "model_count": len(models), "dataset_count": len({model["dataset_sha256"] for model in models}),
                    "dataset_sha256": "multiple datasets; see run groups",
                    "conversation_id": "multiple runs; see run groups",
                    "rounds": sum(len(model["rounds"]) for model in models),
                    "completed_evaluations": sum(run["completed_evaluations"] for run in source_runs),
                    "source_runs": source_runs, "prompt_sha256": "see each saved run"}
    else:
        conversation, gold = validate()
        metadata = {"schema_version": 1, "aggregate": True, "run_comparison": True, "status": "complete",
                    "label_key": label_key, "model_count": 0, "dataset_count": 0, "rounds": 0,
                    "conversation_id": conversation[0]["conversation_id"], "conversation_utterances": len(conversation),
                    "human_utterances_per_round": len(gold), "full_dataset_human_utterances": len(gold),
                    "completed_evaluations": 0, "planned_evaluations": 0, "source_runs": [],
                    "dataset_sha256": hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest(),
                    "prompt_sha256": "no test results", "evaluation_valid": True}
    return {"metadata": metadata, "models": models}



def audit_saved_reports(results_root: Path, label_key: str, dataset_path=DATASET_PATH):
    """Regrade provable full-batch outputs and normalize tokens from retained usage.

    Original wire artifacts stay intact. Missing artifacts are never reconstructed.
    Earlier accepted target-only outputs retain their original protocol and grade.
    """
    samples = {sample["id"]: sample for sample in iter_inputs(label_key, dataset_path)}
    changed = []
    for directory in sorted(results_root.iterdir()):
        if directory.name == "history" or not (directory / "details.json").exists():
            continue
        details = json.loads((directory / "details.json").read_text())
        metadata = details["metadata"]
        if metadata["label_key"] != label_key:
            continue
        require(metadata["dataset_sha256"] == hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                "Saved report dataset does not match current dataset")
        corrections = 0
        for row in details["results"]:
            attempts = row["attempts"]
            usages = [attempt["usage"] for attempt in attempts if attempt.get("usage") is not None]
            if not row.get("token_accounting_audit"):
                row["token_accounting_audit"] = {"previous_input_tokens": row.get("input_tokens"),
                                                   "previous_known_input_tokens": row.get("known_input_tokens")}
            for field, key in (("input", "prompt_tokens"), ("output", "completion_tokens"), ("total", "total_tokens")):
                row[f"known_{field}_tokens"] = sum(usage[key] for usage in usages)
                row[f"{field}_tokens"] = attempts[-1]["usage"][key] if attempts[-1].get("usage") is not None else None
            row["usage_attempt"] = attempts[-1]["attempt"]
            row["missing_usage_count"] = sum(attempt.get("usage") is None for attempt in attempts)
            row.setdefault("classification_protocol", "legacy_target_only_v1")
            sample = samples[row["id"]]
            humans = [item for item in sample["history"] if item["role"] == "human"] + [
                {"id": sample["id"], **sample["target"]}]
            for attempt in attempts:
                request = attempt.get("request")
                response = attempt.get("response")
                if not request or not response or not response.get("choices"):
                    continue
                messages = [m for m in request["body"]["messages"] if m["role"] == "user" and
                            isinstance(m.get("content"), str) and "（unclassified）" in m["content"]]
                # Validate against the actual captured messages before associating any index.
                if len(messages) != len(humans) or any(
                    message["content"].split("说：", 1)[-1].split("（unclassified）", 1)[0] != item["text"]
                    for message, item in zip(messages, humans)):
                    continue
                choice = response["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    continue
                try:
                    parsed = parse_intents(choice["message"].get("content"), list(range(len(humans))))
                except ValueError:
                    continue
                attempt["classifications"] = [{"utterance_index": index, "intent": intent} for index, intent in parsed.items()]
                if attempt.get("error") and not attempt.get("original_error"):
                    attempt["original_error"] = attempt["error"]
                    attempt["error"] = None
                if attempt is not attempts[-1]:
                    continue
                if row.get("error"):
                    row.setdefault("original_evaluation", {key: row.get(key) for key in ("intent", "correct", "error")})
                    row["intent"] = parsed[len(humans) - 1]
                    row["correct"] = row["intent"] == row["expected"]
                    row["error"] = None
                    row["parser_correction"] = "旧脚本只接受一条分类；按实际请求中全部 unclassified 的顺序关联完整返回。原请求未修改，旧请求仅为当前句标注了 index 0，编号歧义已保留。此结果为离线复核，未重新调用模型。"
                row["batch_results"] = [{"id": item["id"], "speaker_id": item["speaker_id"], "text": item["text"],
                                          "utterance_index": index, "intent": parsed[index]} for index, item in enumerate(humans)]
                row["unclassified_count"] = len(humans)
                row["target_utterance_index"] = len(humans) - 1
                if row["classification_protocol"] != "all_unclassified_v2":
                    row["classification_protocol"] = "legacy_full_batch_audited"
            corrections += bool(row.get("original_evaluation"))
        metadata["token_accounting"] = "input/output/total_tokens refer to the last attempt; known_*_tokens sum all attempts"
        metadata["offline_audit"] = {"parser_corrected_rows": corrections, "raw_requests_and_responses_preserved": True}
        write_json(directory / "details.json", {"metadata": metadata, "results": details["results"]})
        changed.append({"directory": directory.name, "parser_corrected_rows": corrections})
    return changed
