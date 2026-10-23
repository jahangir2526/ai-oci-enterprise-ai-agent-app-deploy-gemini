import json
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv(override=True)
logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "Always answer with less than 10 words without line breaks, lists, headings, or code blocks"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is required")
    app.state.model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    app.state.client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60_000),
    )
    try:
        yield
    finally:
        client = app.state.client
        app.state.client = None
        client.close()


app = FastAPI(lifespan=lifespan)


class InvokeRequest(BaseModel):
    prompt: str


@app.get("/health", response_class=Response)
async def health_check():
    return Response(status_code=200, media_type="application/json")


@app.get("/ready", response_class=Response)
async def readiness_check(request: Request):
    ready = getattr(request.app.state, "client", None) is not None
    return Response(status_code=200 if ready else 503, media_type="application/json")


def format_answer(text: str | None) -> dict[str, str]:
    if not text or not text.strip():
        raise HTTPException(status_code=502, detail="Gemini returned no text")
    return {"response": " ".join(text.split())}


def answer_response(payload: dict[str, str], accept: str):
    if "text/event-stream" in accept.lower():
        # One completed event preserves the same one-line answer as the JSON API.
        event = f"event: completed\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        return Response(
            content=event,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    return payload


@app.post("/chat")
def invoke_agent(req: InvokeRequest, request: Request):
    client = getattr(request.app.state, "client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Application is not ready")
    try:
        # Independent generations keep requests stateless across callers/replicas.
        response = client.models.generate_content(
            model=request.app.state.model,
            contents=req.prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
        )
    except Exception:
        logger.exception("Gemini generation failed")
        raise HTTPException(status_code=502, detail="Gemini generation failed") from None
    payload = format_answer(response.text)
    return answer_response(payload, request.headers.get("accept", ""))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
