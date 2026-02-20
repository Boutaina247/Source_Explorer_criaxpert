import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TOOL_SECRET       = os.getenv("TOOL_SECRET", "change-me")
FRONTEND_URL      = os.getenv("FRONTEND_URL", "*")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL != "*" else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClaudeRequest(BaseModel):
    messages:   list
    system:     str = ""
    max_tokens: int = 1000


def check_secret(request: Request):
    if request.headers.get("x-tool-secret") != TOOL_SECRET:
        raise HTTPException(status_code=401, detail="Non autorisé")


@app.get("/")
def root():
    return {"status": "ok", "service": "LearnAI Source Explorer API"}


@app.get("/api/health")
def health(request: Request):
    check_secret(request)
    return {
        "status":    "ok",
        "anthropic": "configured" if ANTHROPIC_API_KEY else "MISSING",
    }


@app.post("/api/claude")
async def claude_proxy(payload: ClaudeRequest, request: Request):
    check_secret(request)

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante côté serveur")

    body = {
        "model":      "claude-sonnet-4-20250514",
        "max_tokens": payload.max_tokens,
        "messages":   payload.messages,
    }
    if payload.system:
        body["system"] = payload.system

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json=body,
            )
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout — réessaie")
