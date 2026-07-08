"""Configuration centrale de l'assistant Code du travail.

C'est le SEUL endroit où apparaissent les noms de modèles, les chemins et les
URL : pour changer de modèle ou de corpus, on ne modifie que ce fichier.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Ce fichier vit dans src/ ; la racine du projet est un niveau au-dessus.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# --- Modèles ---
# Modèle d'embedding : multilingue, très bon en retrieval français, assez léger
# pour tourner sur CPU (~278M paramètres). La famille e5 est entraînée pour la
# recherche asymétrique (question courante -> texte de loi) et EXIGE des préfixes
# distincts pour les requêtes et les documents à l'encodage (voir vectordb.py).
EMBEDDING_MODEL = "intfloat/multilingual-e5-base"
E5_QUERY_PREFIX = "query: "
E5_PASSAGE_PREFIX = "passage: "
# LLM de génération (Groq).
LLM_MODEL = "openai/gpt-oss-20b"
# Modèle de modération (famille « safeguard » de Groq) — agent modérateur du jalon 6.
MODERATION_MODEL = "openai/gpt-oss-safeguard-20b"

# --- Génération ---
# Proche de zéro : on veut une restitution fidèle des articles, pas de créativité.
LLM_TEMPERATURE = 0.0
# Nombre de chunks récupérés et injectés dans le prompt système (à calibrer au jalon 4).
N_CHUNKS = 5

# --- Chemins & noms ---
CHROMA_PATH = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "code_travail"
CORPUS_PATH = PROJECT_ROOT / "data" / "code_travail.json"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
RAG_PROMPT_PATH = PROMPTS_DIR / "rag_system.txt"
MODERATOR_PROMPT_PATH = PROMPTS_DIR / "moderator_system.txt"

# --- API Légifrance (PISTE, option A du sujet) ---
LEGIFRANCE_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
LEGIFRANCE_API_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

# --- Thèmes du corpus (au moins 5 exigés par le sujet) ---
# Plages d'articles indicatives du Code du travail, utilisées par build_corpus.
THEMES = {
    "Durée du travail et heures supplémentaires": ("L3121-1", "L3121-36"),
    "Congés payés": ("L3141-1", "L3141-32"),
    "Contrat de travail (CDI, CDD)": ("L1221-1", "L1248-11"),
    "Licenciement": ("L1231-1", "L1237-20"),
    "Rupture conventionnelle": ("L1237-11", "L1237-19"),
}

# --- Avertissement juridique ---
# Ajouté EN CODE à la fin de chaque réponse (src/rag.py), jamais délégué au seul
# prompt : son absence, même une fois sur dix, est une erreur éliminatoire.
AVERTISSEMENT = (
    "Cet assistant ne fournit pas de conseil juridique. Consultez un avocat "
    "ou l'inspection du travail pour votre situation personnelle."
)

# --- Secrets (chargés depuis .env, validés à l'endroit où ils servent) ---
# GROQ_API_KEY : requis par src/rag.py (génération) uniquement.
# LEGIFRANCE_* : requis par src/legifrance.py (construction du corpus) uniquement.
# On ne lève pas d'erreur ici : build_corpus doit pouvoir tourner sans clé Groq,
# et l'interrogation sans identifiants Légifrance.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LEGIFRANCE_CLIENT_ID = os.getenv("LEGIFRANCE_CLIENT_ID")
LEGIFRANCE_CLIENT_SECRET = os.getenv("LEGIFRANCE_CLIENT_SECRET")
