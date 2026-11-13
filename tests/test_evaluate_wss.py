import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluate_wss import (history_events, load_playlist, response_text,
                          result_session_update, session_update, upload_pcm)


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


class EvaluateWssTests(unittest.TestCase):
    def test_history_is_packed_into_one_snapshot_without_current_target(self):
        sample = {"history": [
            {"id": "u001", "role": "human", "text": "你们先聊", "intent": "ignore"},
            {"id": "u002", "role": "robot", "text": "好的"},
            {"id": "u003", "role": "human", "text": "小露，帮我一下", "intent": "addressing"},
        ], "target": {"text": "这句只能通过音频上传"}}
        events = history_events(sample)
        self.assertEqual(1, len(events))
        text = events[0]["item"]["content"][0]["text"]
        self.assertIn("你们先聊（ignore）", text)
        self.assertIn('"role":"assistant"', text)
        self.assertIn("小露，帮我一下（addressing）", text)
        self.assertNotIn(sample["target"]["text"], text)

    def test_empty_history_needs_no_snapshot_event(self):
        self.assertEqual([], history_events({"history": []}))

    def test_result_history_has_no_gold_intent_labels(self):
        sample = {"history": [
            {"id": "u001", "role": "human", "text": "自然对话", "intent": "ignore"},
        ]}
        text = history_events(sample, labeled=False)[0]["item"]["content"][0]["text"]
        self.assertIn("自然对话", text)
        self.assertNotIn("（ignore）", text)
        self.assertIn("当前待处理的用户请求", text)

    def test_result_session_installs_native_tools(self):
        session = result_session_update("result instructions")["session"]
        self.assertEqual(["text"], session["modalities"])
        self.assertGreater(len(session["tools"]), 0)
        self.assertTrue(all(tool["type"] == "function" for tool in session["tools"]))
        self.assertIn("不执行意图分类", session["instructions"])

    def test_session_uses_explicit_pcm_format_and_text_output(self):
        event = session_update("instructions")
        session = event["session"]
        self.assertEqual(["text"], session["modalities"])
        self.assertIsNone(session["turn_detection"])
        self.assertEqual({"type": "pcm", "sample_rate": 16000, "sample_format": "s16le",
                          "channels": 1, "packing": "interleaved", "channel_layout": "mono"},
                         session["audio"]["input"]["format"])

    def test_playlist_requires_absolute_pcm_path_and_extracts_case_id(self):
        with TemporaryDirectory() as folder:
            pcm = Path(folder) / "0001_u001_H1.pcm"
            pcm.write_bytes(b"\x00\x00")
            playlist = Path(folder) / "playlist.json"
            playlist.write_text(json.dumps([{
                "filename": pcm.name, "filepath": str(pcm), "category": "闲聊",
                "is_to_robot": False,
            }], ensure_ascii=False), encoding="utf-8")
            entries = load_playlist(playlist)
            self.assertEqual(pcm, entries["u001"]["path"])

    def test_pcm_upload_chunks_are_base64_events(self):
        with TemporaryDirectory() as folder:
            pcm = Path(folder) / "u001.pcm"
            pcm.write_bytes(bytes(range(256)) * 5)
            websocket = FakeWebSocket()
            size, chunks, _ = asyncio.run(upload_pcm(websocket, pcm, 20, 0))
            self.assertEqual(1280, size)
            self.assertEqual(2, chunks)
            self.assertTrue(all(item["type"] == "input_audio_buffer.append"
                                for item in websocket.messages))

    def test_response_done_text_fallback(self):
        event = {"response": {"output": [{"content": [{"type": "output_text",
                                                           "text": "0:addressing"}]}]}}
        self.assertEqual("0:addressing", response_text(event))


if __name__ == "__main__":
    unittest.main()
