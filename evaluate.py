"""Read the single conversation dataset and score predictions (stdlib only)."""

import argparse
from collections import Counter
import json
from pathlib import Path


"""
重启robot-evaluation服务
sudo systemctl restart robot-evaluation

查看状态
sudo systemctl status robot-evaluation --no-pager
curl http://127.0.0.1:8786/healthz

运行测试
python evaluate.py run \
  --model bailian \
  --dataset datasets/intent_300_v1.jsonl \
  --rounds 1
"""

ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "datasets" / "conversation.jsonl"
TEMPLATES_DIR = ROOT / "templates"
INTENTS = {"addressing", "ignore"}
ROBOT = {"speaker_id": "R", "name": "小露小露", "aliases": ["小路小路", "小鹿小鹿", "小璐小璐", "晓璐晓璐"]}


def evaluation_tasks(task):
    """Resolve the CLI mode without importing network-facing runners."""
    return ("intent",) if task == "intent" else ("combined",)


def read_jsonl(path):
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected a JSON object")
        rows.append(row)
    return rows


def require(condition, description):
    if not condition:
        raise ValueError(description)


def dataset_context(conversation):
    participants = {}
    for row in conversation:
        speaker_id = row["speaker_id"]
        identity = {"name": row["speaker_name"], "role": row["role"]}
        require(speaker_id not in participants or participants[speaker_id] == identity,
                f"{row['id']}: inconsistent participant identity")
        participants[speaker_id] = identity
    robots = [speaker_id for speaker_id, value in participants.items() if value["role"] == "robot"]
    require(len(robots) == 1, "Dataset must contain exactly one robot participant")
    robot_id = robots[0]
    name = participants[robot_id]["name"]
    aliases = ROBOT["aliases"] if name == ROBOT["name"] else (["小路", "小鹿", "小璐", "晓璐"] if name == "小露" else [])
    return participants, {"speaker_id": robot_id, "name": name, "aliases": aliases}


def validate(dataset_path=DATASET_PATH):
    conversation = read_jsonl(dataset_path)
    require(bool(conversation), "Dataset must not be empty")
    labels = [row for row in conversation if row.get("role") == "human"]
    require(bool(labels), "Dataset must contain scored human utterances")
    require(len({row["conversation_id"] for row in conversation}) == 1, "Dataset must contain one conversation")
    participants, robot = dataset_context(conversation)
    require(len({row["id"] for row in labels}) == len(labels), "Duplicate gold IDs")
    muted = False
    for index, row in enumerate(conversation, 1):
        uid = f"u{index:03d}"
        require(row["id"] == uid and row["turn_index"] == index, f"{uid}: invalid chronology")
        require(row["speaker_id"] in participants, f"{uid}: unknown participant")
        speaker = participants[row["speaker_id"]]
        require(row["role"] == speaker["role"] and row["speaker_name"] == speaker["name"], f"{uid}: role mismatch")
        require(isinstance(row["text"], str) and bool(row["text"].strip()), f"{uid}: empty text")
        require(type(row["evaluate"]) is bool, f"{uid}: evaluate must be boolean")
        if row["role"] == "human":
            require(row["evaluate"] is True and type(row["is_to_robot"]) is bool, f"{uid}: human missing label")
            require(bool(row["reason"]) and bool(row["tag"]), f"{uid}: missing annotation rationale")
            require(isinstance(row["addressees"], list) and set(row["addressees"]) <= participants.keys(),
                    f"{uid}: invalid addressees")
            addressing = robot["speaker_id"] in row["addressees"]
            require(row["is_to_robot"] == addressing, f"{uid}: recipient/semantic label mismatch")
            require(row["intent"] == ("addressing" if addressing else "ignore"), f"{uid}: intent/boolean mismatch")
            if row["tag"] == "named_reactivation":
                require(muted and addressing, f"{uid}: reactivation without prior stop")
                require(any(name in row["text"] for name in [robot["name"], *robot["aliases"]]), f"{uid}: no configured name")
                muted = False
            expected_policy = "ignore" if muted else row["intent"]
            require(row["policy_intent"] == expected_policy, f"{uid}: incorrect silence-policy label")
            if row["tag"] == "stop_speaking":
                require(addressing, f"{uid}: stop command must address robot")
                muted = True
        else:
            require(row["evaluate"] is False, f"{uid}: robot must not be scored")
            require(all(row[key] is None for key in ("is_to_robot", "intent", "policy_intent", "addressees")),
                    f"{uid}: robot incorrectly assigned a human label")
            require(not muted, f"{uid}: robot spoke during requested silence")
    require(not muted, "Conversation ended with unexpected silence state")
    return conversation, labels


def iter_inputs(label_key="intent", dataset_path=DATASET_PATH):
    """Yield clean model inputs in memory, using only prior conversation turns.

    Previous human utterances carry the selected dataset labels as context.
    Only the current target is unclassified; its gold label is never included.
    Snapshots contain no future utterances.
    """
    require(label_key in ("intent", "policy_intent"), "Unknown history label key")
    conversation, _ = validate(dataset_path)
    participants, robot = dataset_context(conversation)
    history = []
    for row in conversation:
        if row["evaluate"]:
            yield {"id": row["id"], "conversation_id": row["conversation_id"],
                   "robot": {**robot, "aliases": list(robot["aliases"])},
                   "participants": {speaker: dict(value) for speaker, value in participants.items()},
                   "history": [dict(message) for message in history],
                   "target": {"utterance_index": 0, "speaker_id": row["speaker_id"], "text": row["text"]}}
        message = {key: row[key] for key in ("id", "speaker_id", "role", "text")}
        if row["role"] == "human":
            message["intent"] = row[label_key]
        history.append(message)


def metrics(gold, predictions, label_key):
    counts = Counter()
    for row in gold:
        actual = row[label_key]
        predicted = predictions.get(row["id"], {}).get("intent")
        if predicted not in INTENTS:
            counts["missing_positive" if actual == "addressing" else "missing_negative"] += 1
        elif actual == "addressing":
            counts["tp" if predicted == "addressing" else "fn"] += 1
        else:
            counts["fp" if predicted == "addressing" else "tn"] += 1
    size = len(gold)
    tp, tn, fp, fn = (counts[key] for key in ("tp", "tn", "fp", "fn"))
    positives = tp + fn + counts["missing_positive"]
    negatives = tn + fp + counts["missing_negative"]
    missing = counts["missing_positive"] + counts["missing_negative"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else 0.0
    return {"total": size, "correct": tp + tn, "missing_or_failed": missing,
            "coverage": (size - missing) / size if size else 0.0,
            "accuracy": (tp + tn) / size if size else 0.0,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "false_activation_rate": fp / negatives if negatives else 0.0,
            "confusion": {key: counts[key] for key in ("tp", "tn", "fp", "fn", "missing_positive", "missing_negative")}}


def score(path, label_key, dataset_path=DATASET_PATH):
    conversation, gold = validate(dataset_path)
    valid_ids = {row["id"] for row in gold}
    predictions = {}
    for row in read_jsonl(path):
        uid = row.get("id")
        require(isinstance(uid, str) and uid in valid_ids, f"Unknown or non-human prediction ID: {uid!r}")
        require(uid not in predictions, f"Duplicate prediction ID: {uid}")
        intent = row.get("intent")
        require(intent in ("addressing", "ignore", None), f"{uid}: intent must be addressing, ignore, or null")
        if intent is None:
            require(isinstance(row.get("error"), str) and bool(row["error"].strip()), f"{uid}: null intent requires an error string")
        else:
            require(not row.get("error"), f"{uid}: prediction cannot contain both a valid intent and an error")
        predictions[uid] = row
    transcript = {row["id"]: row for row in conversation}
    errors = [{"id": row["id"], "speaker": transcript[row["id"]]["speaker_name"], "text": transcript[row["id"]]["text"],
               "expected": row[label_key], "predicted": predictions.get(row["id"], {}).get("intent"),
               "error": predictions.get(row["id"], {}).get("error", ""), "reason": row["reason"]}
              for row in gold if predictions.get(row["id"], {}).get("intent") != row[label_key]]
    return {"label_key": label_key, **metrics(gold, predictions, label_key),
            "by_tag": {tag: metrics([row for row in gold if row["tag"] == tag], predictions, label_key)
                       for tag in sorted({row["tag"] for row in gold})},
            "by_speaker": {speaker: metrics([row for row in gold if transcript[row["id"]]["speaker_id"] == speaker], predictions, label_key)
                           for speaker in ("H1", "H2", "H3")}, "errors": errors}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    viewer = commands.add_parser("serve", help="Serve the two static report viewers over local HTTP")
    viewer.add_argument("--host", default="127.0.0.1")
    viewer.add_argument("--port", type=int, default=8786)
    viewer.add_argument("--results-directory", type=Path, default=ROOT / "results",
                        help="Read-only results directory exposed through the report API")
    validator = commands.add_parser("validate", help="Check chronology, participants, labels and silence state")
    validator.add_argument("--dataset", type=Path, default=DATASET_PATH)
    runner = commands.add_parser("run", help="Run independent OpenAI SDK evaluations and write two reports")
    runner.add_argument("--task", choices=("intent",),
                        help="Run intent classification only; omit this option to run intent and result evaluation")
    runner.add_argument("--config", type=Path, default=ROOT / "config" / "model_profiles.json")
    runner.add_argument("--dataset", type=Path, default=DATASET_PATH)
    runner.add_argument("--model", action="append", help="Select a profile name or model ID; repeat to select multiple models")
    runner.add_argument("--rounds", type=int, default=1, help="Repeat the complete selected conversation independently")
    runner.add_argument("--prompt", type=Path, default=ROOT / "prompts" / "intent_classification.md")
    runner.add_argument("--result-prompt", type=Path, default=ROOT / "prompts" / "response_generation.md")
    runner.add_argument("--label-key", choices=("intent", "policy_intent"), default="intent")
    runner.add_argument("--limit", type=int,
                        help="Smoke test only the first N cases for the selected evaluation mode")
    runner.add_argument("--results-directory", type=Path, default=ROOT / "results")
    history = commands.add_parser("report", help="Show report viewer locations; optionally import or audit raw results")
    history.add_argument("--results-directory", type=Path, default=ROOT / "results")
    history.add_argument("--dataset", type=Path, default=DATASET_PATH,
                         help="Dataset used when importing or auditing saved reports")
    history.add_argument("--import-legacy", type=Path, help="Directory containing run.json, predictions.jsonl and *_report.json")
    history.add_argument("--label-key", choices=("intent", "policy_intent"), default="intent")
    history.add_argument("--include-incomplete", action="store_true", default=True, help="Include partial runs (default)")
    history.add_argument("--complete-only", dest="include_incomplete", action="store_false", help="Show completed runs only")
    history.add_argument("--audit-saved", action="store_true", help="Recheck retained full-batch outputs and token accounting without model calls")
    scorer = commands.add_parser("score", help="Score model predictions, counting missing/failed items as incorrect")
    scorer.add_argument("predictions", type=Path)
    scorer.add_argument("--dataset", type=Path, default=DATASET_PATH)
    scorer.add_argument("--label-key", choices=("intent", "policy_intent"), default="intent")
    scorer.add_argument("--output", type=Path, help="Optionally save the full JSON report")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from reporting.server import ReportHTTPServer
            require(1 <= args.port <= 65535, "port must be between 1 and 65535")
            server = ReportHTTPServer((args.host, args.port), ROOT,
                                      results_directory=args.results_directory)
            print(f"SUMMARY_PAGE: http://{args.host}:{server.server_port}/templates/summary.html", flush=True)
            print(f"RUNS_PAGE: http://{args.host}:{server.server_port}/templates/runs.html", flush=True)
            print(f"DETAILS_PAGE: http://{args.host}:{server.server_port}/templates/details.html", flush=True)
            print(f"RESULT_SUMMARY_PAGE: http://{args.host}:{server.server_port}/templates/result_summary.html", flush=True)
            print(f"RESULT_RUNS_PAGE: http://{args.host}:{server.server_port}/templates/result_runs.html", flush=True)
            print(f"RESULT_DETAILS_PAGE: http://{args.host}:{server.server_port}/templates/result_details.html", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return
        if args.command == "report":
            from reporting.intent_reports import audit_saved_reports, import_legacy
            if args.import_legacy:
                imported = import_legacy(args.import_legacy, args.results_directory, args.label_key, args.dataset)
                print(f"IMPORTED: {imported}")
            if args.audit_saved:
                print(json.dumps(audit_saved_reports(args.results_directory, args.label_key, args.dataset), ensure_ascii=False))
            from urllib.parse import urlencode
            query = {"label_key": args.label_key}
            if not args.include_incomplete:
                query["complete_only"] = "1"
            if args.results_directory.resolve() != (ROOT / "results").resolve():
                query["results"] = str(args.results_directory.resolve().relative_to(ROOT))
            suffix = "?" + urlencode(query)
            print(f"SUMMARY_PAGE: {TEMPLATES_DIR / 'summary.html'}{suffix}")
            print(f"RUNS_PAGE: {TEMPLATES_DIR / 'runs.html'}{suffix}")
            print(f"DETAILS_PAGE: {TEMPLATES_DIR / 'details.html'}{suffix}")
            print(f"RESULT_SUMMARY_PAGE: {TEMPLATES_DIR / 'result_summary.html'}{suffix}")
            print(f"RESULT_RUNS_PAGE: {TEMPLATES_DIR / 'result_runs.html'}{suffix}")
            print(f"RESULT_DETAILS_PAGE: {TEMPLATES_DIR / 'result_details.html'}{suffix}")
            return
        if args.command == "run":
            import asyncio
            for phase in evaluation_tasks(args.task):
                print(f"EVALUATION_PHASE: {phase}", flush=True)
                from evaluation.pipeline_runner import run_evaluations
                asyncio.run(run_evaluations(args, include_results=phase == "combined"))
            return
        if args.command == "validate":
            conversation, labels = validate(args.dataset)
            counts = Counter(row["intent"] for row in labels)
            robots = sum(row["role"] == "robot" for row in conversation)
            print(f"OK: 1 conversation, {len(conversation)} utterances, "
                  f"{len({row['speaker_id'] for row in conversation})} participants, {len(labels)} human labels "
                  f"({counts['addressing']} addressing / {counts['ignore']} ignore), {robots} robot replies.")
            return
        report = score(args.predictions, args.label_key, args.dataset)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            protected = {path.resolve() for path in ROOT.iterdir() if path.is_file()}
            protected.add(args.predictions.resolve())
            protected.add(args.dataset.resolve())
            require(args.output.resolve() not in protected, "Report output would overwrite the dataset, scripts, or prediction input")
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()
