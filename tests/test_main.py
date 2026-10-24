"""Local contract checks; no Gemini network calls or real API keys are used."""
import json
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import main


class ProbeTests(unittest.TestCase):
    def test_startup_probes_and_shutdown(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "local-test-placeholder"}):
            with TestClient(main.app) as client:
                for path in ("/ready", "/health"):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, b"")
                    self.assertEqual(response.headers["content-type"], "application/json")
                self.assertEqual(client.post("/invoke", json={}).status_code, 422)
            self.assertIsNone(main.app.state.client)

    def test_uninitialized_client(self):
        main.app.state.client = None
        client = TestClient(main.app)  # Without context, lifespan is not entered.
        try:
            self.assertEqual(client.get("/ready").status_code, 503)
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(
                client.post("/invoke", json={"prompt": "Hello"}).status_code, 503
            )
        finally:
            client.close()

    def test_missing_key_prevents_startup(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                with TestClient(main.app):
                    pass


class AnswerTests(unittest.TestCase):
    def test_normalizes_line_breaks(self):
        self.assertEqual(
            main.format_answer(" First\tline.\r\n  Second  line.\n"),
            {"response": "First line. Second line."},
        )

    def test_rejects_empty_generation(self):
        for text in (None, "", " \n\t"):
            with self.subTest(text=text), self.assertRaises(HTTPException) as raised:
                main.format_answer(text)
            self.assertEqual(raised.exception.status_code, 502)

    def test_json_and_sse_use_same_answer(self):
        # Exercise real response serialization without invoking an upstream service.
        fixture = FastAPI()
        payload = main.format_answer("First line\n Second line")

        @fixture.get("/answer")
        def answer(request: Request):
            return main.answer_response(payload, request.headers.get("accept", ""))

        with TestClient(fixture) as client:
            response = client.get("/answer")
            self.assertEqual(response.json(), payload)
            self.assertEqual(response.headers["content-type"], "application/json")
            response = client.get(
                "/answer", headers={"Accept": "application/json, Text/Event-Stream"}
            )
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertEqual(
                response.text,
                f"event: completed\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n",
            )


if __name__ == "__main__":
    unittest.main()
