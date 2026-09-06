"""대화 탭 — 스트리밍 클라이언트 · 저장소 · 메시지 조립의 순수 로직."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from core.chat_store import (
    MAX_THREADS, ChatStore, build_ollama_messages, clean_options, inline_image_paths, normalise_threads, strip_data_url,
)
from core.ollama_client import OllamaClient


class _FakeResponse:
    """requests.post(stream=True) 흉내 — 줄 단위 JSON 을 돌려주고 닫힘을 기록한다."""

    def __init__(self, lines, status=200, error_json=None):
        self._lines = lines
        self.status_code = status
        self.closed = False
        self._error_json = error_json
        self.text = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def json(self):
        return self._error_json or {}

    def close(self):
        self.closed = True

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line


def _chunks(*texts, done_extra=None):
    out = [json.dumps({"message": {"role": "assistant", "content": t}, "done": False}) for t in texts]
    out.append(json.dumps({"message": {"role": "assistant", "content": ""}, "done": True, **(done_extra or {})}))
    return out


class ChatStreamTests(unittest.TestCase):
    def test_tokens_are_delivered_in_order_and_joined(self):
        seen = []
        fake = _FakeResponse(_chunks("안녕", "하세요", "!", done_extra={"eval_count": 3, "done_reason": "length"}))
        with patch("core.ollama_client.requests.post", return_value=fake) as post:
            result = OllamaClient(model="m").chat_stream(
                [{"role": "user", "content": "hi"}], on_token=seen.append,
            )
        self.assertEqual(seen, ["안녕", "하세요", "!"])
        self.assertEqual(result["content"], "안녕하세요!")
        self.assertFalse(result["stopped"])
        self.assertEqual(result["eval_count"], 3)
        self.assertEqual(result["done_reason"], "length", "잘렸다는 사실은 화면까지 가야 한다")
        body = post.call_args.kwargs["json"]
        self.assertTrue(body["stream"], "스트리밍이 아니면 토큰이 한 번에 온다")
        self.assertEqual(body["model"], "m")

    def test_stop_closes_the_response_and_keeps_partial_text(self):
        """중지는 그때까지 받은 글을 버리지 않는다 — 사용자가 읽던 것이 사라지면 안 된다."""
        calls = {"n": 0}

        def should_stop():
            calls["n"] += 1
            return calls["n"] >= 3   # 세 번째 줄을 읽기 전에 멈춘다

        fake = _FakeResponse(_chunks("a", "b", "c", "d"))
        with patch("core.ollama_client.requests.post", return_value=fake):
            result = OllamaClient(model="m").chat_stream([{"role": "user", "content": "x"}], should_stop=should_stop)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["content"], "ab")
        self.assertTrue(fake.closed, "응답을 닫아야 서버도 생성을 멈춘다")

    def test_server_error_line_raises_with_its_message(self):
        fake = _FakeResponse([json.dumps({"error": "model 'x' not found"})])
        with patch("core.ollama_client.requests.post", return_value=fake):
            with self.assertRaises(RuntimeError) as ctx:
                OllamaClient(model="x").chat_stream([{"role": "user", "content": "x"}])
        self.assertIn("not found", str(ctx.exception))

    def test_http_error_status_raises(self):
        fake = _FakeResponse([], status=404, error_json={"error": "no such model"})
        with patch("core.ollama_client.requests.post", return_value=fake):
            with self.assertRaises(RuntimeError) as ctx:
                OllamaClient(model="x").chat_stream([{"role": "user", "content": "x"}])
        self.assertIn("404", str(ctx.exception))

    def test_garbage_lines_are_skipped(self):
        fake = _FakeResponse(["not json", ""] + _chunks("ok"))
        with patch("core.ollama_client.requests.post", return_value=fake):
            result = OllamaClient(model="m").chat_stream([{"role": "user", "content": "x"}])
        self.assertEqual(result["content"], "ok")

    def test_eof_without_done_is_not_a_completed_answer(self):
        seen = []
        fake = _FakeResponse([json.dumps({"message": {"content": "partial"}, "done": False})])
        with patch("core.ollama_client.requests.post", return_value=fake):
            with self.assertRaisesRegex(RuntimeError, "완료.*끊어"):
                OllamaClient(model="m").chat_stream([], on_token=seen.append)
        self.assertEqual(seen, ["partial"], "이미 받은 응답은 오류 표시와 함께 유지한다")


class ThinkingModelTests(unittest.TestCase):
    """Gemma 4·Qwen3.x 는 생각부터 한다 — 생각은 따로 흐르고, 플래그는 요청에 실리고, 모르는 모델엔 빠진다."""

    def test_thinking_pieces_flow_separately_and_flag_is_sent(self):
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "", "thinking": "음, "}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": "", "thinking": "파랑"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": "파란색"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
        ]
        seen, thought = [], []
        with patch("core.ollama_client.requests.post", return_value=_FakeResponse(lines)) as post:
            result = OllamaClient(model="m").chat_stream(
                [{"role": "user", "content": "?"}], think=True, on_token=seen.append, on_thinking=thought.append,
            )
        self.assertEqual(seen, ["파란색"])
        self.assertEqual(thought, ["음, ", "파랑"])
        self.assertEqual(result["content"], "파란색")
        self.assertEqual(result["thinking"], "음, 파랑")
        self.assertIs(post.call_args.kwargs["json"]["think"], True)

    def test_think_false_is_sent_and_omitted_when_none(self):
        with patch("core.ollama_client.requests.post", return_value=_FakeResponse(_chunks("a"))) as post:
            OllamaClient(model="m").chat_stream([{"role": "user", "content": "?"}], think=False)
            self.assertIs(post.call_args.kwargs["json"]["think"], False)
            OllamaClient(model="m").chat_stream([{"role": "user", "content": "?"}])
            self.assertNotIn("think", post.call_args.kwargs["json"])

    def test_model_without_thinking_gets_a_retry_without_the_flag(self):
        refused = _FakeResponse([], status=400, error_json={"error": '"m" does not support thinking'})
        ok = _FakeResponse(_chunks("답"))
        with patch("core.ollama_client.requests.post", side_effect=[refused, ok]) as post:
            result = OllamaClient(model="m").chat_stream([{"role": "user", "content": "?"}], think=False)
        self.assertEqual(result["content"], "답")
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("think", post.call_args_list[1].kwargs["json"])
        self.assertTrue(refused.closed)

    def test_other_400s_still_raise(self):
        refused = _FakeResponse([], status=400, error_json={"error": "invalid image"})
        with patch("core.ollama_client.requests.post", return_value=refused):
            with self.assertRaises(RuntimeError):
                OllamaClient(model="m").chat_stream([{"role": "user", "content": "?"}], think=False)


class ChatStreamCompletionTests(unittest.TestCase):
    def test_worker_keeps_partial_tokens_and_reports_unexpected_eof_as_error(self):
        from workers.chat_worker import ChatWorker
        worker = ChatWorker('interrupted-stream', 'http://test-only', 'm', [])
        tokens, completed = [], []
        worker.token.connect(lambda raw: tokens.append(json.loads(raw)))
        worker.done.connect(lambda raw: completed.append(json.loads(raw)))
        fake = _FakeResponse([json.dumps({'message': {'content': 'partial'}, 'done': False})])
        with patch('core.ollama_client.requests.post', return_value=fake):
            worker.run()
        self.assertEqual(''.join(packet.get('text', '') for packet in tokens), 'partial')
        self.assertEqual(len(completed), 1)
        self.assertFalse(completed[0]['ok'])
        self.assertFalse(completed[0]['stopped'])
        self.assertIn('완료 신호', completed[0]['error'])

    def test_eof_after_user_stop_is_cancelled_not_an_incomplete_stream_error(self):
        from workers.chat_worker import ChatWorker
        worker = ChatWorker('cancelled-stream', 'http://test-only', 'm', [])
        completed = []
        worker.done.connect(lambda raw: completed.append(json.loads(raw)))

        class CancelledResponse(_FakeResponse):
            def iter_lines(self, decode_unicode=True):
                yield json.dumps({'message': {'content': 'partial'}, 'done': False})
                worker.stop()

        with patch('core.ollama_client.requests.post', return_value=CancelledResponse([])):
            worker.run()
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0]['ok'])
        self.assertTrue(completed[0]['stopped'])
        self.assertEqual(completed[0]['content'], 'partial')
        self.assertNotIn('error', completed[0])


class OptionCleaningTests(unittest.TestCase):
    def test_only_known_keys_with_sane_values_pass(self):
        out = clean_options({
            "temperature": "0.4", "top_p": "nan", "num_predict": -1, "num_ctx": 0,
            "num_gpu": 99, "seed": 7, "stop": ["x"],
        })
        self.assertEqual(out, {"temperature": 0.4, "num_predict": -1})

    def test_positive_ints_pass_and_negative_ctx_is_dropped(self):
        self.assertEqual(clean_options({"num_predict": 4096, "num_ctx": 16384}), {"num_predict": 4096, "num_ctx": 16384})
        self.assertEqual(clean_options({"num_predict": -5, "num_ctx": -1, "temperature": -0.1}), {})

    def test_garbage_input_is_empty(self):
        self.assertEqual(clean_options(None), {})
        self.assertEqual(clean_options("temperature=1"), {})
        self.assertEqual(clean_options({"temperature": object()}), {})


class MessageAssemblyTests(unittest.TestCase):
    def test_system_first_then_last_turns_only(self):
        history = [{"role": "user", "content": f"u{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"a{i}"} for i in range(30)]
        out = build_ollama_messages(history, system_prompt="너는 조수다", max_turns=4)
        self.assertEqual(out[0], {"role": "system", "content": "너는 조수다"})
        self.assertEqual([m["content"] for m in out[1:]], ["u26", "a27", "u28", "a29"])

    def test_images_are_base64_without_data_url_prefix(self):
        """Ollama 는 `data:` 접두사를 모른다 — 붙여 보내면 400 도 아니고 그냥 못 본다."""
        out = build_ollama_messages([{"role": "user", "content": "뭐야", "images": ["data:image/png;base64,AAAA", "BBBB"]}])
        self.assertEqual(out[0]["images"], ["AAAA", "BBBB"])
        self.assertEqual(strip_data_url("data:image/jpeg;base64,xyz"), "xyz")
        self.assertEqual(strip_data_url("plain"), "plain")

    def test_pending_and_unknown_roles_are_dropped(self):
        out = build_ollama_messages([
            {"role": "user", "content": "a"},
            {"role": "tool", "content": "?"},
            "junk",
            {"role": "assistant", "content": "b"},
        ])
        self.assertEqual([m["role"] for m in out], ["user", "assistant"])


class InlineImagePathTests(unittest.TestCase):
    def test_paths_become_base64_and_missing_files_are_dropped(self):
        """히스토리 카드 드롭은 경로다 — 파일을 읽어 넣고, 없는 파일은 빼고, data: 는 건드리지 않는다."""
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            png = pathlib.Path(tmp) / "a.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\n1234")
            out = inline_image_paths([{"role": "user", "content": "?", "images": [
                str(png), "data:image/png;base64,AAAA", str(pathlib.Path(tmp) / "missing.png"), "QUJD",
            ]}])
        self.assertEqual(out[0]["images"], [
            base64.b64encode(b"\x89PNG\r\n\x1a\n1234").decode("ascii"), "data:image/png;base64,AAAA", "QUJD",
        ])
        self.assertEqual(out[0]["content"], "?")

    def test_message_with_only_missing_images_loses_the_key(self):
        out = inline_image_paths([{"role": "user", "content": "x", "images": ["C:/nope/none.png"]}, {"role": "assistant", "content": "y"}])
        self.assertNotIn("images", out[0])
        self.assertEqual(out[1], {"role": "assistant", "content": "y"})


class ChatStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "nested" / "chat_threads.json"
        self.store = ChatStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _thread(self, tid, updated, **extra):
        return {"id": tid, "title": f"t{tid}", "createdAt": 1, "updatedAt": updated,
                "messages": [{"id": "m1", "role": "user", "content": "hi", "createdAt": 1}], **extra}

    def test_round_trip_creates_parent_dir_and_sorts_recent_first(self):
        saved = self.store.save([self._thread("a", 10), self._thread("b", 30), self._thread("c", 20)])
        self.assertEqual([t["id"] for t in saved], ["b", "c", "a"])
        self.assertTrue(self.path.is_file())
        self.assertEqual([t["id"] for t in self.store.load()], ["b", "c", "a"])

    def test_cap_keeps_the_newest_hundred(self):
        threads = [self._thread(str(i), i) for i in range(MAX_THREADS + 25)]
        saved = self.store.save(threads)
        self.assertEqual(len(saved), MAX_THREADS)
        self.assertEqual(saved[0]["id"], str(MAX_THREADS + 24))
        self.assertNotIn("0", [t["id"] for t in saved])

    def test_pending_flags_and_junk_are_not_persisted(self):
        raw = [{"id": "x", "updatedAt": 1, "messages": [
            {"id": "1", "role": "user", "content": "q", "pending": True, "requestId": "r"},
            {"id": "2", "role": "assistant", "content": "", "error": "boom"},
            {"role": "nobody", "content": "?"},
        ]}]
        saved = self.store.save(raw)
        msgs = saved[0]["messages"]
        self.assertEqual(len(msgs), 2)
        self.assertNotIn("pending", msgs[0])
        self.assertNotIn("requestId", msgs[0])
        self.assertEqual(msgs[1]["error"], "boom")

    def test_answer_meta_is_persisted_and_junk_meta_is_dropped(self):
        saved = self.store.save([{"id": "x", "updatedAt": 1, "messages": [
            {"id": "1", "role": "assistant", "content": "답", "evalCount": 812, "durationMs": "4100", "doneReason": "length"},
            {"id": "2", "role": "assistant", "content": "답", "evalCount": "많이", "doneReason": ""},
        ]}])
        m1, m2 = saved[0]["messages"]
        self.assertEqual((m1["evalCount"], m1["durationMs"], m1["doneReason"]), (812, 4100, "length"))
        self.assertNotIn("evalCount", m2)
        self.assertNotIn("doneReason", m2)

    def test_thinking_text_is_persisted(self):
        saved = self.store.save([{"id": "x", "updatedAt": 1, "messages": [
            {"id": "1", "role": "assistant", "content": "답", "thinking": "생각"},
        ]}])
        self.assertEqual(saved[0]["messages"][0]["thinking"], "생각")

    def test_image_budget_drops_oldest_images_first(self):
        big = "x" * 4_000_000
        raw = [{"id": "x", "updatedAt": 1, "messages": [
            {"id": "1", "role": "user", "content": "old", "images": [big]},
            {"id": "2", "role": "user", "content": "new", "images": [big]},
        ]}]
        saved = normalise_threads(raw)
        msgs = saved[0]["messages"]
        self.assertNotIn("images", msgs[0])
        self.assertTrue(msgs[0]["imagesDropped"])
        self.assertIn("images", msgs[1])

    def test_missing_or_corrupt_file_loads_empty(self):
        self.assertEqual(self.store.load(), [])
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store.load(), [])


if __name__ == "__main__":
    unittest.main()
