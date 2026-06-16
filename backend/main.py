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


async def call_claude(messages: list, system: str = "", max_tokens: int = 4000) -> str:
    """Internal helper to call Claude API and return text."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquante")

    body = {
        "model": "claude-sonnet-4-6",
        "max_tokens": min(max_tokens, 8000),
        "messages": messages,
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        if res.status_code != 200:
            print(f"ANTHROPIC ERROR {res.status_code}: {res.text}")
        res.raise_for_status()
        data = res.json()
        return "".join(b.get("text", "") for b in data.get("content", []))


def safe_parse_json(text: str) -> dict | list:
    import re, json
    text = text.strip()
    # Remove markdown fences
    text = re.sub(r"```json|```", "", text).strip()
    # Remove any text before first { or [
    match = re.search(r'[\{\[]', text)
    if match:
        text = text[match.start():]
    # Remove any text after last } or ]
    match = re.search(r'[\}\]](?=[^\}\]]*$)', text)
    if match:
        text = text[:match.end()]
    try:
        return json.loads(text)
    except Exception:
        # Try to find first complete JSON object or array
        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        raise ValueError("Impossible de parser la réponse JSON de Claude.")


SECTORS = ["RH / Management", "Marketing / Communication", "Santé / Médical", "Finance / Banque", "Data / IA"]

class ExtractRequest(BaseModel):
    sources: list
    query: str

class DraftRequest(BaseModel):
    query: str
    angle: str = ""
    concepts: list = []
    points: list = []

class CasePracticeRequest(BaseModel):
    query: str
    exercice_base: dict
    sector: str


@app.post("/api/extract")
async def extract_content(payload: ExtractRequest, request: Request):
    """Claude extracts rich pedagogical content from REAL source content."""
    check_secret(request)

    src_text = "\n\n---\n\n".join([
        f"SOURCE {i+1}: {s.get('title','')}\nURL: {s.get('url','')}\nContenu:\n{(s.get('full_content') or s.get('description','(vide)'))[:600]}"
        for i, s in enumerate(payload.sources[:5])
    ])

    extract_prompt = (
        f'Tu es expert en ingénierie pédagogique IA. Sujet du module: "{payload.query}"\n\n'
        f"Voici le contenu RÉEL extrait de sources web vérifiées:\n{src_text}\n\n"
        f"Analyse ce contenu et réponds en JSON compact sur UNE SEULE LIGNE.\n"
        f"Champs OBLIGATOIRES et noms EXACTS (pas de retour à la ligne dans les valeurs):\n"
        '{"angle_module":"angle pedagogique unique en 1 phrase",'
        '"concepts_cles":[{"concept":"nom court","definition":"definition claire 1 phrase","exemple":"exemple concret court"}],'
        '"points_pedagogiques":[{"titre":"titre court","paragraphe":"paragraphe informatif de 4-5 phrases expliquant le concept en profondeur avec des faits tires des sources et un exemple concret","source_url":"url de la source"}],'
        '"idees_quiz":[{"question":"question precise?","reponse_courte":"reponse correcte","distracteurs":["faux1","faux2","faux3"],"explication":"explication pedagogique courte"}],'
        '"idees_exercices":[{"titre":"titre exercice","objectif":"competence que lapprenant developpe","taches":["tache1","tache2","tache3"],"cas_etude":"texte du cas detude concret en 3-4 phrases avec un contexte realiste et des chiffres ou details specifiques"}]}\n\n'
        "LIMITE STRICTE: 4 concepts, 4 points, 3 quiz, 2 exercices. JSON sur une seule ligne."
    )

    try:
        raw = await call_claude([{"role": "user", "content": extract_prompt}], max_tokens=4000)
        print(f"RAW CLAUDE: {raw[:500]}")
        result = safe_parse_json(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction échouée: {str(e)}")


@app.post("/api/draft")
async def generate_draft(payload: DraftRequest, request: Request):
    """Claude generates a rich pedagogical module draft."""
    check_secret(request)

    concepts_str = ", ".join([c.get("concept","") if isinstance(c, dict) else str(c) for c in payload.concepts[:4]])
    points_str = " | ".join([p.get("titre","") if isinstance(p, dict) else str(p) for p in payload.points[:4]])

    draft_template = (
        '{"titre":"titre final du module","description":"2 phrases pour le catalogue","objectifs":["objectif 1","objectif 2","objectif 3"],'
        '"plan_cours":[{"section":"titre section","duree_min":15,"contenu_resume":"resume 2-3 phrases du contenu","points_cles":["point1","point2"]}],'
        '"quiz_draft":[{"question":"question precise?","options":["A. rep","B. rep","C. rep","D. rep"],"correct":"A","explication":"explication pedagogique"}],'
        '"exercice_principal":{"titre":"titre","objectif":"competence visee","mise_en_situation":"contexte realiste 3 phrases","etapes":["etape detaillee 1","etape detaillee 2","etape detaillee 3","etape detaillee 4"],"livrable":"livrable concret","duree_estimee":"45 min","criteres_reussite":["critere1","critere2"]},'
        '"variantes_sectorielles":{"RH / Management":{"contexte":"adaptation RH","personnage":"profil RH"},"Marketing / Communication":{"contexte":"adaptation Marketing","personnage":"profil Marketing"},"Sante / Medical":{"contexte":"adaptation Sante","personnage":"profil Sante"},"Finance / Banque":{"contexte":"adaptation Finance","personnage":"profil Finance"},"Data / IA":{"contexte":"adaptation Data","personnage":"profil Data"}},'
        '"tags":["tag1","tag2","tag3"],"difficulte":"beginner","duree_totale_min":60}'
    )

    prompt = (
        f'Expert ingénierie pédagogique IA. Génère un brouillon complet.\n'
        f'Titre: "{payload.query}" | Angle: {payload.angle}\n'
        f'Concepts: {concepts_str}\n'
        f'Points pédagogiques: {points_str}\n\n'
        f'JSON COMPACT sur une seule ligne, max 50 mots par champ:\n'
        f'{draft_template}\n\n'
        f'STRICT: 4 sections plan avec points_cles, 3 questions quiz, variantes_sectorielles pour les 5 secteurs. JSON sur une seule ligne.'
    )

    try:
        raw = await call_claude([{"role": "user", "content": prompt}], max_tokens=3000)
        result = safe_parse_json(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Brouillon échoué: {str(e)}")


@app.post("/api/adapt-sector")
async def adapt_sector(payload: CasePracticeRequest, request: Request):
    """Generate a sector-specific adaptation of an exercise."""
    check_secret(request)

    base = payload.exercice_base
    prompt = (
        f'Expert pédagogie IA. Adapte cet exercice pour le secteur "{payload.sector}".\n'
        f'Module: "{payload.query}"\n'
        f'Exercice original:\n'
        f'- Titre: {base.get("titre","")}\n'
        f'- Objectif: {base.get("objectif","")}\n'
        f'- Mise en situation: {base.get("mise_en_situation","")}\n'
        f'- Étapes: {" / ".join(base.get("etapes",[]))}\n'
        f'- Livrable: {base.get("livrable","")}\n\n'
        f'Génère une adaptation pour "{payload.sector}" en JSON compact sur une seule ligne:\n'
        '{"titre":"titre adapte","mise_en_situation":"contexte specifique au secteur 3 phrases","personnage":"profil type du secteur","etapes":["etape1","etape2","etape3","etape4"],"livrable":"livrable adapte au secteur","duree_estimee":"45 min"}\n\n'
        f'Garde le même objectif pédagogique, change uniquement le contexte métier.'
    )

    try:
        raw = await call_claude([{"role": "user", "content": prompt}], max_tokens=1000)
        result = safe_parse_json(raw)
        result["sector"] = payload.sector
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Adaptation échouée: {str(e)}")


class SolutionRequest(BaseModel):
    query: str
    exercice: dict


@app.post("/api/solution")
async def generate_solution(payload: SolutionRequest, request: Request):
    """Generate a model answer and evaluation grid for an exercise."""
    check_secret(request)

    exo = payload.exercice
    prompt = (
        f'Expert pédagogie IA. Module: "{payload.query}"\n'
        f'Exercice:\n'
        f'- Titre: {exo.get("titre","")}\n'
        f'- Objectif: {exo.get("objectif","")}\n'
        f'- Mise en situation: {exo.get("mise_en_situation","")}\n'
        f'- Tâches: {" / ".join(exo.get("taches", exo.get("etapes", [])))}\n'
        f'- Livrable: {exo.get("livrable","")}\n\n'
        f'Génère le corrigé type ET la grille d\'évaluation. JSON compact sur une seule ligne:\n'
        '{"corrige":{"introduction":"phrase intro du corrige","elements_reponse":[{"tache":"nom tache","reponse_attendue":"ce que lapprenant doit produire concrètement","exemple_bon":"exemple de bonne reponse","erreurs_frequentes":"erreur typique a eviter"}],"conclusion":"ce que demontre un bon livrable"},'
        '"grille_evaluation":{"total_points":20,"criteres":[{"critere":"nom critere","points":5,"indicateurs_reussite":["indicateur1","indicateur2"],"indicateurs_echec":["echec1"]}],"mention_tres_bien":"score >= 17","mention_bien":"score >= 14","mention_passable":"score >= 10"}}\n\n'
        'STRICT: 1 element_reponse par tache, 4 criteres evaluation, JSON sur une seule ligne.'
    )

    try:
        raw = await call_claude([{"role": "user", "content": prompt}], max_tokens=2000)
        result = safe_parse_json(raw)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Solution échouée: {str(e)}")
    """Generic Claude proxy (kept for compatibility)."""
    check_secret(request)
    try:
        text = await call_claude(payload.messages, payload.system, payload.max_tokens)
        return {"content": [{"type": "text", "text": text}]}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout — réessaie")
