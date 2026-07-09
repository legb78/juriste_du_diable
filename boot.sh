#!/bin/sh
# Démarrage du service (Railway) : auto-initialisation idempotente.
#
# - boot ordinaire (volume déjà initialisé) : la base se RECHARGE sans
#   réencodage (~30 s), puis le serveur démarre ;
# - premier boot (volume vierge) : construction du corpus depuis le dump
#   public legi-data (~2-3 min) puis indexation (~20-25 min d'encodage CPU),
#   PUIS le serveur — d'où le healthcheck patient de railway.json.
#
# Aucun secret d'extraction requis : le dump GitHub est public. Seule
# GROQ_API_KEY est nécessaire (génération).
set -e

echo "[boot] Tentative de rechargement de la base existante..."
if ! python -m src.index; then
    echo "[boot] Base ou corpus absents : initialisation (premier boot)."
    python -m src.build_corpus_legidata
    python -m src.index
fi

echo "[boot] Base prête — démarrage du serveur."
exec uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}"
