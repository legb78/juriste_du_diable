#!/bin/sh
# Démarrage du service (Railway) : mise à jour conditionnelle puis serveur.
#
# src/maj.py décide seul :
# - source inchangée + base présente -> rien (boot total ~30-60 s) ;
# - premier boot ou source modifiée  -> reconstruction complète (~25 min,
#   couverte par le healthcheck patient de railway.json).
#
# Le cron quotidien (GitHub Actions) se contente de redéployer le service :
# c'est CE script qui garantit « pas de rebuild si rien n'a changé ».
set -e

python -m src.maj

echo "[boot] Base prête — démarrage du serveur."
exec uvicorn src.api:app --host 0.0.0.0 --port "${PORT:-8000}"
