import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY")
TOOL_SECRET       = os.getenv("TOOL_SECRET", "change-me")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Trusted domains with quality scores ──────────────────────────────────────
TRUSTED_DOMAINS = {
    "arxiv.org": ("arXiv", 95),
    "stanford.edu": ("Stanford", 98),
    "mit.edu": ("MIT", 98),
    "openai.com": ("OpenAI", 93),
    "anthropic.com": ("Anthropic", 93),
    "deepmind.com": ("DeepMind", 95),
    "huggingface.co": ("Hugging Face", 90),
    "nist.gov": ("NIST", 96),
    "cnil.fr": ("CNIL", 97),
    "europa.eu": ("UE", 96),
    "oecd.org": ("OCDE", 95),
    "france-strategie.fr": ("France Stratégie", 92),
    "coursera.org": ("Coursera", 88),
    "deeplearning.ai": ("DeepLearning.AI", 91),
    "ibm.com": ("IBM", 87),
    "microsoft.com": ("Microsoft", 87),
    "google.com": ("Google", 87),
    "nature.com": ("Nature", 96),
    "science.org": ("Science", 96),
    "unesco.org": ("UNESCO", 94),
    "who.int": ("WHO", 94),
    "mckinsey.com": ("McKinsey", 82),
    "hbr.org": ("Harvard Business Review", 85),
    "wired.com": ("Wired", 75),
    "techcrunch.com": ("TechCrunch", 70),
    "medium.com": ("Medium", 60),
}

def score_source(url: str, year: Optional[int], content_length: int) -> dict:
    """Score a source on domain trust, freshness, and content richness."""
    # Domain score
    domain_score = 50
    domain_label = "Externe"
    trusted = False
    for domain, (label, score) in TRUSTED_DOMAINS.items():
        if domain in url:
            domain_score = score
            domain_label = label
            trusted = True
            break

    # Freshness score
    if year and year >= 2024:
        fresh_score = 100
    elif year and year >= 2023:
        fresh_score = 85
    elif year and year >= 2022:
        fresh_score = 70
    elif year and year >= 2020:
        fresh_score = 55
    else:
        fresh_score = 40

    # Content richness score
    if content_length >= 500:
        content_score = 100
    elif content_length >= 200:
        content_score = 75
    elif content_length >= 50:
        content_score = 50
    else:
        content_score = 25

    total = round(domain_score * 0.5 + fresh_score * 0.3 + content_score * 0.2)

    return {
        "total": total,
        "domain": domain_score,
        "fresh": fresh_score,
        "content": content_score,
        "badge": domain_label,
        "trusted": trusted,
    }


# ── Models ───────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str
    max_results: int = 8

class ManualSourcesRequest(BaseModel):
    urls: list[str]
    query: str

class ClaudeRequest(BaseModel):
    messages: list
    system: str = ""
    max_tokens: int = 3000


# ── Auth ─────────────────────────────────────────────────────────────────────
def check_secret(request: Request):
    if request.headers.get("x-tool-secret") != TOOL_SECRET:
        raise HTTPException(status_code=401, detail="Non autorisé")


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "LearnAI Source Explorer API v2"}


@app.get("/api/health")
def health(request: Request):
    check_secret(request)
    return {
        "status": "ok",
        "anthropic": "configured" if ANTHROPIC_API_KEY else "MISSING",
        "tavily": "configured" if TAVILY_API_KEY else "MISSING",
    }


@app.post("/api/search")
async def search_sources(payload: SearchRequest, request: Request):
    """Search real sources via Tavily and score their quality."""
    check_secret(request)

    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY manquante côté serveur")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": payload.query,
                    "search_depth": "advanced",
                    "max_results": payload.max_results,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            res.raise_for_status()
            data = res.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Tavily error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    results = data.get("results", [])
    sources = []
    for r in results:
        url = r.get("url", "")
        content = r.get("content", "")
        year = None

        # Try to extract year from published_date
        pub = r.get("published_date", "") or ""
        if pub:
            try:
                year = int(pub[:4])
            except:
                pass

        quality = score_source(url, year, len(content))

        sources.append({
            "title": r.get("title", "Sans titre"),
            "url": url,
            "domain": url.split("/")[2] if "/" in url else url,
            "description": content[:300] if content else "",
            "full_content": content[:2000] if content else "",
            "year": year,
            "score": quality,
        })

    # Sort by quality score descending
    sources.sort(key=lambda x: x["score"]["total"], reverse=True)

    return {"sources": sources, "query": payload.query}


@app.post("/api/fetch-urls")
async def fetch_manual_urls(payload: ManualSourcesRequest, request: Request):
    """Fetch and score manually provided URLs via Tavily extract."""
    check_secret(request)

    if not TAVILY_API_KEY:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY manquante côté serveur")

    sources = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in payload.urls:
            if not url.strip():
                continue
            try:
                res = await client.post(
                    "https://api.tavily.com/extract",
                    json={
                        "api_key": TAVILY_API_KEY,
                        "urls": [url],
                    },
                )
                res.raise_for_status()
                data = res.json()
                result = data.get("results", [{}])[0]
                content = result.get("raw_content", "")[:2000]
                title = result.get("title") or url.split("/")[-1] or url

                quality = score_source(url, None, len(content))
                sources.append({
                    "title": title,
                    "url": url,
                    "domain": url.split("/")[2] if "/" in url else url,
                    "description": content[:300],
                    "full_content": content,
                    "year": None,
                    "score": quality,
                })
            except Exception as e:
                # Still include the URL but with low score
                sources.append({
                    "title": url,
                    "url": url,
                    "domain": url.split("/")[2] if "/" in url else url,
                    "description": f"Impossible de récupérer le contenu : {str(e)[:100]}",
                    "full_content": "",
                    "year": None,
                    "score": score_source(url, None, 0),
                })

    sources.sort(key=lambda x: x["score"]["total"], reverse=True)
    return {"sources": sources, "query": payload.query}


@app.post("/api/claude")
async def claude_proxy(payload: ClaudeRequest, request: Request):
    """Proxy Claude API calls — Claude only extracts/structures, never invents sources."""
    check_secret(request)

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante côté serveur")

    max_tokens = min(payload.max_tokens, 8000)

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": payload.messages,
    }
    if payload.system:
        body["system"] = payload.system

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout — réessaie")
