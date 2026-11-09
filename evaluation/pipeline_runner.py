"""Independent OpenAI SDK runner. No ROS or application imports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
from typing import cast
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI
from openai._types import Body
from openai.types.chat import (
    ChatCompletion, ChatCompletionAssistantMessageParam, ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming
from openai.types.completion_usage import CompletionUsage

from evaluation.intent_parser import parse_intents
from evaluate import ROOT, ROBOT, TEMPLATES_DIR, dataset_context, iter_inputs, require, validate
from hotel_tools.mock_functions import TOOL_DEFINITIONS
from reporting.intent_reports import write_json


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


@dataclass
class ModelConfig:
    name: str
    model: str
    base_url: str
    api_key: str = field(repr=False)
    parameters: CompletionCreateParamsNonStreaming
    extra_body: Body | None = None
    timeout_seconds: float = 60.0


@dataclass
class SubmittedRequest:
    method: str
    url: str
    body: CompletionCreateParamsNonStreaming

    def serialize(self):
        return {"method": self.method, "url": self.url, "body": self.body}


@dataclass
class Attempt:
    number: int
    request: SubmittedRequest | None = None
    response: ChatCompletion | None = None
    usage: CompletionUsage | None = None
    error: str | None = None
    latency_seconds: float = 0.0
    classifications: dict[int, str] | None = None

    def serialize(self):
        return {"attempt": self.number, "request": self.request.serialize() if self.request else None,
                "response": self.response.model_dump(mode="json") if self.response else None,
                "usage": self.usage.model_dump(mode="json") if self.usage else None,
                "error": self.error, "latency_seconds": self.latency_seconds,
                "classifications": ([{"utterance_index": index, "intent": intent} for index, intent in self.classifications.items()]
                                    if self.classifications is not None else None)}


def load_models(path: Path, selected: list[str] | None) -> list[ModelConfig]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(document, dict) and isinstance(document.get("models"), list) and document["models"],
            "Model config must contain a nonempty models array")
    names = set()
    configs = []
    for item in document["models"]:
        require(isinstance(item, dict), "Each model config must be an object")
        for key in ("name", "model", "base_url"):
            require(isinstance(item.get(key), str) and bool(item[key].strip()), f"Model config requires {key}")
        require(item["name"] not in names, f"Duplicate model profile: {item['name']}")
        names.add(item["name"])
        if selected and item["name"] not in selected and item["model"] not in selected:
            continue
        url = urlsplit(item["base_url"])
        require(url.scheme in ("http", "https") and bool(url.hostname) and url.username is None and url.password is None,
                f"{item['name']}: base_url must be an HTTP(S) URL without embedded credentials")
        env_name = item.get("api_key_env", "OPENAI_API_KEY")
        require(isinstance(env_name, str), "api_key_env must be a string")
        api_key = os.environ.get(env_name) or item.get("api_key", "")
        require(isinstance(api_key, str) and bool(api_key.strip()), f"{item['name']}: set {env_name} or api_key")
        options = item.get("request_options", {})
        require(isinstance(options, dict), "request_options must be an object")
        allowed = CompletionCreateParamsNonStreaming.__required_keys__ | CompletionCreateParamsNonStreaming.__optional_keys__
        require(not (options.keys() - allowed), f"{item['name']}: unsupported SDK request_options: {options.keys() - allowed}")
        require(not ({"model", "messages", "stream"} & options.keys()), "model, messages and stream are controlled by the runner")
        extra = item.get("extra_body")
        require(extra is None or isinstance(extra, dict), "extra_body must be an object or null")
        require(not isinstance(extra, dict) or not ({"model", "messages", "stream"} & extra.keys()),
                "extra_body cannot override model, messages or stream")
        timeout = item.get("timeout_seconds", 60.0)
        retries = item.get("max_retries", 0)
        require(type(timeout) in (int, float) and timeout > 0, "timeout_seconds must be positive")
        require(type(retries) is int and retries == 0, "Retries are disabled for evaluation; remove max_retries or set it to 0")
        parameters: CompletionCreateParamsNonStreaming = cast(CompletionCreateParamsNonStreaming,
            {"model": item["model"], "messages": [], "stream": False, **options})
        configs.append(ModelConfig(item["name"], item["model"], item["base_url"], api_key,
                                   parameters, extra, float(timeout)))
    if selected:
        unmatched = set(selected) - {value for config in configs for value in (config.name, config.model)}
        require(not unmatched, f"Unknown selected model(s): {sorted(unmatched)}")
    require(bool(configs), "No models selected")
    return configs


def render_prompt(path: Path, robot=ROBOT) -> str:
    template = path.read_text(encoding="utf-8").strip()
    require(bool(template), "Prompt is empty")
    values = {"robot_name": json.dumps(robot["name"], ensure_ascii=False),
              "robot_name_aliases": json.dumps(robot["aliases"], ensure_ascii=False)}
    unknown = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", template)) - values.keys()
    require(not unknown, f"Unknown prompt placeholders: {sorted(unknown)}")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda match: values[match[1]], template) + "\n"


def unclassified_utterances(sample):
    return [{"id": sample["id"], "speaker_id": sample["target"]["speaker_id"], "text": sample["target"]["text"]}]


def build_messages(sample, instructions: str) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = [ChatCompletionSystemMessageParam(role="system", content=instructions)]
    for item in sample["history"]:
        if item["role"] == "robot":
            messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=item["text"]))
        else:
            require(item.get("intent") in ("addressing", "ignore"), f"Historical utterance {item['id']} requires its dataset label")
            messages.append(ChatCompletionUserMessageParam(role="user", content=f"{item['text']}（{item['intent']}）"))
    target = sample["target"]
    content = (f"{target['text']}（unclassified）\nutterance_index: 0\n当前状态："
               + json.dumps({"robot_name": sample["robot"]["name"]}, ensure_ascii=False))
    messages.append(ChatCompletionUserMessageParam(role="user", content=content))
    return messages


def parse_intent(text: str | None) -> str:
    """Compatibility helper for an actual single-utterance batch."""
    return parse_intents(text, [0])[0]


async def classify(client: AsyncOpenAI, model: ModelConfig, sample, instructions: str,
                   capture: list[SubmittedRequest]):
    parameters: CompletionCreateParamsNonStreaming = {**model.parameters, "messages": build_messages(sample, instructions)}
    attempts: list[Attempt] = []
    batch = unclassified_utterances(sample)
    expected_indices = list(range(len(batch)))
    target_index = len(batch) - 1
    parsed = {}
    predicted = None
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    attempt = Attempt(1)
    attempts.append(attempt)
    capture.clear()
    before = time.monotonic()
    try:
        response: ChatCompletion = await client.chat.completions.create(**parameters, extra_body=model.extra_body)
        attempt.response = response
        attempt.usage = response.usage
        require(bool(response.choices), "Model returned no choices")
        require(response.choices[0].finish_reason == "stop", f"Incomplete completion: {response.choices[0].finish_reason}")
        message = response.choices[0].message
        require(not message.refusal, "Model refused the request")
        parsed = parse_intents(message.content, expected_indices)
        attempt.classifications = parsed
        predicted = parsed[target_index]
    except Exception as exc:
        attempt.error = f"{type(exc).__name__}: {str(exc) or 'request timed out'}"
    finally:
        attempt.latency_seconds = round(time.monotonic() - before, 4)
        attempt.request = capture[-1] if capture else None
    known_tokens = sum(attempt.usage.prompt_tokens for attempt in attempts if attempt.usage is not None)
    known_output_tokens = sum(attempt.usage.completion_tokens for attempt in attempts if attempt.usage is not None)
    known_total_tokens = sum(attempt.usage.total_tokens for attempt in attempts if attempt.usage is not None)
    missing_usage = sum(attempt.usage is None for attempt in attempts)
    usage = attempts[-1].usage
    return {"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
            "intent": predicted, "error": attempts[-1].error if predicted is None else None,
            "latency_seconds": round(time.monotonic() - started, 4), "known_input_tokens": known_tokens,
            "known_output_tokens": known_output_tokens, "known_total_tokens": known_total_tokens,
            "input_tokens": usage.prompt_tokens if usage is not None else None,
            "output_tokens": usage.completion_tokens if usage is not None else None,
            "total_tokens": usage.total_tokens if usage is not None else None,
            "usage_attempt": attempts[-1].number, "missing_usage_count": missing_usage,
            "unclassified_count": len(batch), "target_utterance_index": target_index,
            "classification_protocol": "single_target_labeled_history_v3",
            "batch_results": [{**item, "utterance_index": index, "intent": parsed.get(index)}
                              for index, item in enumerate(batch)],
            "attempts": [attempt.serialize() for attempt in attempts]}



async def run_evaluations(args, include_results=False):
    require(args.rounds > 0, "rounds must be positive")
    require(args.limit is None or args.limit > 0, "limit must be positive")
    configs = load_models(args.config, args.model)
    conversation, gold = validate(args.dataset)
    _, robot = dataset_context(conversation)
    instructions = render_prompt(args.prompt, robot)
    samples = list(iter_inputs(args.label_key, args.dataset))
    if args.limit is not None:
        require(args.limit <= len(samples), f"limit exceeds {len(samples)} available human utterances")
        samples = samples[:args.limit]
    answers = {row["id"]: row for row in gold}
    response_answers = {}
    if include_results:
        from evaluation.response_comparison import response_references
        response_answers = response_references(args.dataset)
        result_prompt = args.result_prompt.read_text(encoding="utf-8").strip()
        require(bool(result_prompt), "Result prompt must not be empty")
    directory = args.results_directory / datetime.now(BEIJING_TIMEZONE).strftime("%Y%m%dT%H%M%S%f")
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"schema_version": 1, "evaluation_type": "combined" if include_results else "intent", "evaluation_valid": True, "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
                "rounds": args.rounds, "model_count": len(configs), "label_key": args.label_key,
                "models": [{"profile": model.name, "model": model.model, "base_url": model.base_url} for model in configs],
                "round_started_at": {},
                "conversation_id": conversation[0]["conversation_id"], "conversation_utterances": len(conversation),
                "human_utterances_per_round": len(samples), "full_dataset_human_utterances": len(gold),
                "planned_evaluations": len(samples) * args.rounds * len(configs), "completed_evaluations": 0,
                "dataset_file": str(args.dataset.resolve()),
                "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                "prompt_file": args.prompt.name, "prompt_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
                "token_source": "OpenAI SDK CompletionUsage.prompt_tokens; unknown usage is never estimated",
                "token_accounting": "input/output/total_tokens refer to the last attempt; known_*_tokens sum all attempts",
                "classification_protocol": "single_target_labeled_history_v3",
                "retry_policy": "disabled: one SDK call per target; SDK max_retries=0",
                "history_label_source": "dataset gold labels for previous utterances only; current target label withheld",
                "history_mode": "fixed transcript with labeled prior human utterances; classify current target only"}
    if include_results:
        metadata.update({"result_validator": {"type": "deterministic_local", "version": 1},
                         "result_prompt_sha256": hashlib.sha256(result_prompt.encode()).hexdigest(),
                         "response_references_per_round": len(response_answers)})
    results = []
    started = time.monotonic()
    task = asyncio.current_task()
    assert task is not None
    loop = asyncio.get_running_loop()
    # Let finally save completed results when the process receives SIGTERM.
    signal_handler = False
    try:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
        signal_handler = True
    except (NotImplementedError, RuntimeError):
        pass
    print(f"REPORT_DIRECTORY: {directory}", flush=True)
    try:
        for model_number, model in enumerate(configs, 1):
            capture: list[SubmittedRequest] = []

            async def capture_request(request: httpx.Request) -> None:
                if request.method == "POST":
                    body: CompletionCreateParamsNonStreaming = cast(CompletionCreateParamsNonStreaming, json.loads(request.content))
                    capture.append(SubmittedRequest(request.method, str(request.url), body))

            async with httpx.AsyncClient(event_hooks={"request": [capture_request]}) as transport:
                async with AsyncOpenAI(api_key=model.api_key, base_url=model.base_url, timeout=model.timeout_seconds,
                                       max_retries=0, http_client=transport) as client:
                    for number in range(1, args.rounds + 1):
                        metadata["round_started_at"].setdefault(model.name, {})[str(number)] = datetime.now(timezone.utc).isoformat()
                        for count, sample in enumerate(samples, 1):
                            record = await classify(client, model, sample, instructions, capture)
                            expected = answers[sample["id"]]
                            for item in record["batch_results"]:
                                item["expected"] = expected[args.label_key]
                                item["correct"] = item.get("intent") == item["expected"]
                            anchor = f"request-m{model_number}-r{number}-{sample['id']}"
                            record.update({"profile": model.name, "model": model.model, "round": number,
                                           "id": sample["id"], "conversation_id": sample["conversation_id"],
                                           "text": sample["target"]["text"], "speaker_id": sample["target"]["speaker_id"],
                                           "expected": expected[args.label_key], "tag": expected["tag"], "correct": record["intent"] == expected[args.label_key],
                                           "reason": expected["reason"], "request_anchor": anchor,
                                           "request_link": f"details.html#{anchor}"})
                            if include_results:
                                from evaluation.local_result_validator import validate_result
                                from evaluation.response_comparison import parse_json_content
                                from evaluation.response_runner import build_result_messages, call_model
                                reference = response_answers.get(sample["id"])
                                record.update({"user_request": sample["target"]["text"],
                                               "expected_text": reference["text"] if reference else None,
                                               "actual_text": None, "result_type": "not_applicable",
                                               "passed": False, "judgment": {}, "candidate_call": None,
                                               "judge_call": None, "result_status": "skipped_by_intent"})
                                if record["intent"] == "addressing" and reference is None:
                                    record["result_status"] = "no_reference_answer"
                                elif record["intent"] == "addressing" and reference is not None:
                                    result_sample = {"history": [*sample["history"],
                                        {"role": "human", "text": sample["target"]["text"]}]}
                                    try:
                                        parse_json_content(reference["text"])
                                        expects_tool_call = True
                                    except (ValueError, json.JSONDecodeError):
                                        expects_tool_call = False
                                    candidate_call = await call_model(client, model,
                                        build_result_messages(result_sample, result_prompt), capture,
                                        tools=TOOL_DEFINITIONS, require_tool_call=expects_tool_call)
                                    actual = candidate_call["content"] if candidate_call["content"] is not None else candidate_call.get("raw_content")
                                    record.update({"actual_text": actual, "candidate_call": candidate_call,
                                                   "result_status": "evaluated"})
                                    judgment = validate_result(reference["text"], actual, candidate_call)
                                    record.update({"result_type": judgment["result_type"],
                                                   "passed": judgment["passed"], "judgment": judgment})
                            results.append(record)
                            metadata["completed_evaluations"] = len(results)
                            metadata["elapsed_seconds"] = round(time.monotonic() - started, 4)
                            # Persist raw records only. Statistics are computed
                            # when a viewer requests them.
                            write_json(directory / "details.json", {"metadata": metadata, "results": results})
                            if count == 1 or count % 10 == 0 or count == len(samples) or record["error"]:
                                print(f"{model.name} round {number}/{args.rounds}: {count}/{len(samples)} {sample['id']} {record['intent']}"
                                      + (f" {record['error']}" if record["error"] else ""), flush=True)
        metadata["status"] = "complete"
    except BaseException:
        metadata["status"] = "interrupted"
        raise
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        metadata["elapsed_seconds"] = round(time.monotonic() - started, 4)
        write_json(directory / "details.json", {"metadata": metadata, "results": results})
        if signal_handler:
            loop.remove_signal_handler(signal.SIGTERM)
    history = TEMPLATES_DIR
    print(f"HISTORY_PAGE: {history / 'summary.html'}", flush=True)
    print(f"SUMMARY_PAGE: {history / 'summary.html'}", flush=True)
    print(f"RUNS_PAGE: {history / 'runs.html'}", flush=True)
    print(f"RESULT_FILE: {directory / 'details.json'}", flush=True)
    print(f"DETAILS_PAGE: {history / 'details.html'}", flush=True)
    return directory
