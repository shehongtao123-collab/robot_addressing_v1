"""Generate dataset responses and judge JSON deterministically or text with a fixed AI judge."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import signal
import time
from typing import cast

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.completion_create_params import CompletionCreateParamsNonStreaming

from evaluate import TEMPLATES_DIR, require
from reporting.intent_reports import write_json
from evaluation.response_comparison import build_judge_payload, json_needs_semantic_judge, judge_json_result, parse_json_content, parse_text_judgment, result_samples
from evaluation.pipeline_runner import ModelConfig, SubmittedRequest, load_models
from hotel_tools.mock_functions import TOOL_DEFINITIONS, tool_call_content


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


def build_result_messages(sample, instructions: str) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = [cast(ChatCompletionMessageParam,
        {"role": "system", "content": instructions})]
    for item in sample["history"]:
        role = "assistant" if item["role"] == "robot" else "user"
        messages.append(cast(ChatCompletionMessageParam, {"role": role, "content": item["text"]}))
    return messages


async def call_model(client: AsyncOpenAI, config: ModelConfig, messages, capture: list[SubmittedRequest],
                     *, tools=None, require_tool_call=False):
    parameters: CompletionCreateParamsNonStreaming = {**config.parameters, "messages": messages}
    if tools is not None:
        parameters["tools"] = tools
        parameters["tool_choice"] = "required" if require_tool_call else "auto"
    capture.clear()
    started = time.monotonic()
    response = None
    content = None
    raw_content = None
    error = None
    try:
        response = await client.chat.completions.create(**parameters, extra_body=config.extra_body)
        require(bool(response.choices), "Model returned no choices")
        require(response.choices[0].finish_reason in ("stop", "tool_calls"),
                f"Incomplete completion: {response.choices[0].finish_reason}")
        message = response.choices[0].message
        raw_content = message.content
        require(not message.refusal, "Model refused the request")
        tool_calls = message.tool_calls or []
        if require_tool_call:
            require(len(tool_calls) == 1, "Expected exactly one native function call")
        require(not tool_calls or len(tool_calls) == 1, "Multiple function calls are not supported per case")
        if tool_calls:
            require(tool_calls[0].type == "function", "Unsupported tool call type")
            content = tool_call_content(tool_calls[0].function.name, tool_calls[0].function.arguments)
        else:
            require(isinstance(message.content, str) and bool(message.content.strip()),
                    "Model returned neither text nor a function call")
            content = message.content
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc) or 'request timed out'}"
    latency = round(time.monotonic() - started, 4)
    usage = response.usage if response else None
    return {"request": capture[-1].serialize() if capture else None,
            "response": response.model_dump(mode="json") if response else None,
            "usage": usage.model_dump(mode="json") if usage else None, "error": error,
            "latency_seconds": latency,
            "raw_content": raw_content,
            "content": content if response and not error else None}


def client_for(config: ModelConfig, capture: list[SubmittedRequest]):
    async def capture_request(request: httpx.Request):
        if request.method == "POST":
            capture.append(SubmittedRequest(request.method, str(request.url),
                           cast(CompletionCreateParamsNonStreaming, json.loads(request.content))))
    transport = httpx.AsyncClient(event_hooks={"request": [capture_request]})
    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds,
                         max_retries=0, http_client=transport)
    return transport, client


async def run_result_evaluations(args):
    require(args.rounds > 0, "rounds must be positive")
    candidates = load_models(args.config, args.model)
    judges = load_models(args.judge_config, [args.judge] if args.judge else None)
    require(len(judges) == 1, "Select exactly one judge model")
    judge = judges[0]
    samples = result_samples(args.dataset)
    if args.limit is not None:
        require(0 < args.limit <= len(samples), f"limit must be between 1 and {len(samples)}")
        samples = samples[:args.limit]
    result_prompt = args.result_prompt.read_text(encoding="utf-8").strip()
    judge_prompt = args.judge_prompt.read_text(encoding="utf-8").strip()
    require(bool(result_prompt) and bool(judge_prompt), "Result and judge prompts must not be empty")
    directory = args.results_directory / datetime.now(BEIJING_TIMEZONE).strftime("%Y%m%dT%H%M%S%f")
    directory.mkdir(parents=True, exist_ok=False)
    metadata = {"schema_version": 1, "evaluation_type": "result", "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(), "rounds": args.rounds,
                "model_count": len(candidates), "models": [{"profile": m.name, "model": m.model, "base_url": m.base_url} for m in candidates],
                "judge": {"profile": judge.name, "model": judge.model, "base_url": judge.base_url},
                "judge_prompt_sha256": hashlib.sha256(judge_prompt.encode()).hexdigest(),
                "result_prompt_sha256": hashlib.sha256(result_prompt.encode()).hexdigest(),
                "dataset_file": str(args.dataset.resolve()), "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                "conversation_id": samples[0]["conversation_id"], "result_samples_per_round": len(samples),
                "planned_evaluations": len(samples) * args.rounds * len(candidates), "completed_evaluations": 0,
                "round_started_at": {}}
    results = []
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    signal_handler = False
    try:
        loop.add_signal_handler(signal.SIGTERM, task.cancel)
        signal_handler = True
    except (NotImplementedError, RuntimeError):
        pass
    print(f"REPORT_DIRECTORY: {directory}", flush=True)
    try:
        judge_capture: list[SubmittedRequest] = []
        judge_transport, judge_client = client_for(judge, judge_capture)
        async with judge_transport, judge_client:
            for model_number, candidate in enumerate(candidates, 1):
                candidate_capture: list[SubmittedRequest] = []
                candidate_transport, candidate_client = client_for(candidate, candidate_capture)
                async with candidate_transport, candidate_client:
                    for round_number in range(1, args.rounds + 1):
                        metadata["round_started_at"].setdefault(candidate.name, {})[str(round_number)] = datetime.now(timezone.utc).isoformat()
                        for count, sample in enumerate(samples, 1):
                            try:
                                parse_json_content(sample["expected_text"])
                                expects_tool_call = True
                            except (ValueError, json.JSONDecodeError):
                                expects_tool_call = False
                            candidate_call = await call_model(candidate_client, candidate,
                                build_result_messages(sample, result_prompt), candidate_capture,
                                tools=TOOL_DEFINITIONS, require_tool_call=expects_tool_call)
                            actual = candidate_call["content"] if candidate_call["content"] is not None else candidate_call.get("raw_content")
                            judge_call = None
                            if candidate_call["error"]:
                                judgment = {"result_type": "unknown", "passed": False, "errors": [],
                                            "reason": "candidate_call_failed"}
                            else:
                                try:
                                    parse_json_content(sample["expected_text"])
                                    judgment = judge_json_result(sample["expected_text"], actual)
                                    judgment["reason"] = "JSON字段和值完全一致" if judgment["passed"] else "JSON字段或值不一致"
                                    if json_needs_semantic_judge(judgment):
                                        structural = judgment
                                        payload = build_judge_payload(sample["expected_text"], actual)
                                        judge_messages = [cast(ChatCompletionMessageParam, {"role": "system", "content": judge_prompt}),
                                                          cast(ChatCompletionMessageParam, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)})]
                                        judge_call = await call_model(judge_client, judge, judge_messages, judge_capture)
                                        if judge_call["error"]:
                                            judgment = {**structural, "passed": False, "judge_failed": True,
                                                        "reason": judge_call["error"], "semantic_judgment": None}
                                        else:
                                            semantic = parse_text_judgment(judge_call["content"])
                                            judgment = {**structural, **semantic, "result_type": "json",
                                                        "semantic_judgment": semantic,
                                                        "structural_errors": structural["errors"]}
                                except (ValueError, json.JSONDecodeError):
                                    payload = build_judge_payload(sample["expected_text"], actual)
                                    judge_messages = [cast(ChatCompletionMessageParam, {"role": "system", "content": judge_prompt}),
                                                      cast(ChatCompletionMessageParam, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)})]
                                    judge_call = await call_model(judge_client, judge, judge_messages, judge_capture)
                                    if judge_call["error"]:
                                        judgment = {"result_type": "text", "passed": False, "judge_failed": True,
                                                    "reason": judge_call["error"], "errors": []}
                                    else:
                                        try:
                                            judgment = {"result_type": "text", **parse_text_judgment(judge_call["content"])}
                                        except (ValueError, json.JSONDecodeError) as exc:
                                            judgment = {"result_type": "text", "passed": False, "judge_failed": True,
                                                        "reason": f"Invalid judge output: {exc}", "errors": []}
                            usage = candidate_call["usage"]
                            anchor = f"result-m{model_number}-r{round_number}-{sample['id']}"
                            results.append({"profile": candidate.name, "model": candidate.model, "round": round_number,
                                "id": sample["id"], "conversation_id": sample["conversation_id"], "section": sample["section"],
                                "tag": sample["tag"], "user_request": sample["user_request"],
                                "expected_text": sample["expected_text"],
                                "actual_text": actual, "result_type": judgment["result_type"], "passed": judgment["passed"],
                                "judgment": judgment, "error": candidate_call["error"],
                                "latency_seconds": candidate_call["latency_seconds"],
                                "input_tokens": usage.get("prompt_tokens") if usage else None,
                                "output_tokens": usage.get("completion_tokens") if usage else None,
                                "total_tokens": usage.get("total_tokens") if usage else None,
                                "candidate_call": candidate_call, "judge_call": judge_call,
                                "request_anchor": anchor, "request_link": f"result_details.html#{anchor}"})
                            metadata["completed_evaluations"] = len(results)
                            write_json(directory / "details.json", {"metadata": metadata, "results": results})
                            if count == 1 or count % 10 == 0 or count == len(samples):
                                print(f"{candidate.name} result round {round_number}/{args.rounds}: {count}/{len(samples)} {sample['id']} {'pass' if judgment['passed'] else 'fail'}", flush=True)
        metadata["status"] = "complete"
    except BaseException:
        metadata["status"] = "interrupted"
        raise
    finally:
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(directory / "details.json", {"metadata": metadata, "results": results})
        if signal_handler:
            loop.remove_signal_handler(signal.SIGTERM)
    print(f"RESULT_SUMMARY_PAGE: {TEMPLATES_DIR / 'result_summary.html'}", flush=True)
    print(f"RESULT_FILE: {directory / 'details.json'}", flush=True)
    return directory
