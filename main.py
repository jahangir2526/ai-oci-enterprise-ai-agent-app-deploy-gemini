import os
import uvicorn
from fastapi import FastAPI, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True) # Load environment variables from .env file if present

app = FastAPI()

# Read API key strictly from environment variable
api_key = os.environ.get("GEMINI_API_KEY")
llm_model = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY environment variable is required")

client = genai.Client(api_key=api_key)
chat = client.chats.create(
    model=llm_model,
    config=types.GenerateContentConfig(
        system_instruction=(
            "Always answer in a single short, concise sentence on exactly one line, "
            "regardless of the user's query or requested format. "
            "Never include line breaks, lists, headings, or code blocks. "
            "If asked for a detailed or multiline response, summarize the answer "
            "in one short sentence instead."
        ),
    ),
)


class InvokeRequest(BaseModel):
    prompt: str


# OCI Hosted Deployment health/readiness probe
@app.get("/health")
def health_check():
    return {"status": "healthy"}


# Agent invocation endpoint
@app.post("/invoke")
def invoke_agent(req: InvokeRequest):
    try:
        response = chat.send_message(req.prompt)
        # Keep the API response on one line even if the model inserts newlines.
        text = response.text
        return {"response": " ".join(text.splitlines()).strip() if text else text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)