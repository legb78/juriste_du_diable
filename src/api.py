"""Interface web de l'assistant — API FastAPI + page statique.

Usage :
    uvicorn src.api:app
    puis ouvrir http://127.0.0.1:8000

L'agent RAG est instancié UNE SEULE FOIS au démarrage du serveur (modèle
d'embedding, collection ChromaDB, prompts), suivi d'un retrieve
d'échauffement qui construit l'index lexical BM25 (~20-30 s) — pour que la
première vraie question ne paie pas ce coût.

La base vectorielle doit exister : si elle est absente, le serveur refuse de
démarrer avec le message « lancez python -m src.index » — jamais de
réindexation implicite (exigence éliminatoire du sujet).
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.rag import RAG

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# L'agent vit ici, partagé entre toutes les requêtes (il est sans état :
# chaque question est indépendante — la mémoire conversationnelle viendra
# sur une branche ultérieure).
etat = {}


@asynccontextmanager
async def lifespan(app):
    # Échec franc si la base n'existe pas : le ValueError de VectorDB remonte
    # et le serveur ne démarre pas — mieux qu'un serveur qui répond 500.
    rag = RAG()
    # Échauffement : construit l'index BM25 maintenant plutôt qu'à la 1re question.
    rag.db.retrieve_hybride("échauffement de l'index lexical", n=1)
    etat["rag"] = rag
    yield
    etat.clear()


app = FastAPI(title="Juriste du diable — assistant Code du travail",
              lifespan=lifespan)


class Question(BaseModel):
    question: str


@app.post("/api/question")
def poser_question(entree: Question):
    """Le contrat : la question en entrée, le dict complet du RAG en sortie
    (reponse, sous_questions, sources avec legiarti, citations_non_verifiees,
    date_corpus, avertissement)."""
    question = entree.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question vide.")
    try:
        return etat["rag"].answer_question(question)
    except Exception as erreur:  # LLM injoignable, quota... : message honnête
        raise HTTPException(
            status_code=502,
            detail=f"Le service de génération est indisponible : {erreur}",
        )


@app.get("/")
def accueil():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
