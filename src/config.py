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
# Identifiant LEGI du Code du travail (constant, publié par la DILA).
LEGIFRANCE_CODE_TRAVAIL_ID = "LEGITEXT000006072050"

# --- Thèmes du corpus (au moins 5 exigés par le sujet) ---
# Plages d'articles indicatives du Code du travail, utilisées par build_corpus.
# ATTENTION : les plages du sujet se chevauchent — « Contrat de travail »
# englobe Licenciement, qui englobe Rupture conventionnelle. build_corpus
# attribue le PREMIER thème qui matche : l'ordre ci-dessous va donc du plus
# spécifique au plus général, pour que chaque article porte le thème le plus
# précis (sinon tout finirait étiqueté « Contrat de travail »).
THEMES = {
    "Rupture conventionnelle": ("L1237-11", "L1237-19"),
    "Licenciement": ("L1231-1", "L1237-20"),
    "Contrat de travail (CDI, CDD)": ("L1221-1", "L1248-11"),
    "Durée du travail et heures supplémentaires": ("L3121-1", "L3121-36"),
    "Congés payés": ("L3141-1", "L3141-32"),
}

# --- Avertissement juridique ---
# Ajouté EN CODE à la fin de chaque réponse (src/rag.py), jamais délégué au seul
# prompt : son absence, même une fois sur dix, est une erreur éliminatoire.
AVERTISSEMENT = (
    "Cet assistant ne fournit pas de conseil juridique. Consultez un avocat "
    "ou l'inspection du travail pour votre situation personnelle."
)

# --- Stockage objet AWS S3 — OPTIONNEL ---
# Sauvegarde des instantanés du corpus et alimentation du futur déploiement.
# Sans ces clés dans .env, src/storage.py se désactive silencieusement : le
# pipeline local reste 100 % fonctionnel (aucun bucket requis pour corriger).
AWS_REGION = os.getenv("AWS_REGION", "eu-west-3")  # eu-west-3 = Paris
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# --- Secrets (chargés depuis .env, validés à l'endroit où ils servent) ---
# GROQ_API_KEY : requis par src/rag.py (génération) uniquement.
# LEGIFRANCE_* : requis par src/legifrance.py (construction du corpus) uniquement.
# On ne lève pas d'erreur ici : build_corpus doit pouvoir tourner sans clé Groq,
# et l'interrogation sans identifiants Légifrance.
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LEGIFRANCE_CLIENT_ID = os.getenv("LEGIFRANCE_CLIENT_ID")
LEGIFRANCE_CLIENT_SECRET = os.getenv("LEGIFRANCE_CLIENT_SECRET")
