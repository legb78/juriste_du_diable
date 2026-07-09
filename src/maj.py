"""Mise à jour conditionnelle de la base — « ne reconstruire que si ça a changé ».

Usage :
    python -m src.maj            # vérifie, reconstruit seulement si nécessaire
    python -m src.maj --force    # reconstruit quoi qu'il arrive

Mécanisme :
1. interroge l'API GitHub : SHA du dernier commit touchant le dump du Code du
   travail dans SocialGouv/legi-data (1 requête, sans authentification) ;
2. compare au marqueur local (data/version_source.json, sur le volume) ;
3. source INCHANGÉE + base présente -> ne fait RIEN (le boot enchaîne sur un
   rechargement en ~30 s) ;
4. source CHANGÉE (ou premier boot, ou --force) -> purge le cache du dump,
   reconstruit le corpus, réindexe la base, écrit le marqueur (~25 min).

Résilience : si l'API GitHub est injoignable mais que la base existe, on la
sert telle quelle (la disponibilité prime sur la fraîcheur du jour).
"""

import json
import shutil
import sys
from datetime import datetime, timezone

import requests

from src import build_corpus_legidata, config, index, storage

URL_DERNIER_COMMIT = (
    "https://api.github.com/repos/SocialGouv/legi-data/commits"
    "?path=data/LEGITEXT000006072050.json&per_page=1"
)
MARQUEUR = config.DATA_DIR / "version_source.json"


def sha_distant():
    """SHA du dernier commit GitHub ayant modifié le dump du Code du travail."""
    reponse = requests.get(
        URL_DERNIER_COMMIT,
        headers={"Accept": "application/vnd.github+json"},
        timeout=30,
    )
    reponse.raise_for_status()
    return reponse.json()[0]["sha"]


def sha_local():
    if MARQUEUR.exists():
        with open(MARQUEUR, encoding="utf-8") as f:
            return json.load(f).get("sha")
    return None


def base_prete():
    return config.CHROMA_PATH.exists() and config.CORPUS_PATH.exists()


def ecrire_marqueur(sha):
    """Grave la version de la source dont la base est issue (sur le volume)."""
    MARQUEUR.parent.mkdir(parents=True, exist_ok=True)
    with open(MARQUEUR, "w", encoding="utf-8") as f:
        json.dump(
            {"sha": sha, "date_maj": datetime.now(timezone.utc).isoformat()}, f
        )


def reconstruire(sha):
    """Re-télécharge le dump, reconstruit corpus + index, écrit le marqueur."""
    if build_corpus_legidata.CACHE_LEGIDATA.exists():
        build_corpus_legidata.CACHE_LEGIDATA.unlink()  # forcer le re-téléchargement
    build_corpus_legidata.main()

    if config.CHROMA_PATH.exists():
        shutil.rmtree(config.CHROMA_PATH)  # base neuve, jamais de mélange
    index.main()

    ecrire_marqueur(sha)
    print(f"[maj] Base reconstruite (source {str(sha)[:10]}).")


def recuperer_ou_reconstruire(sha_attendu):
    """Base absente : tente d'abord l'archive S3 (publiée depuis le poste
    local, ~2 min), sinon reconstruction complète (~25 min)."""
    if not base_prete() and storage.telecharger_base():
        if base_prete() and (sha_attendu is None or sha_local() == sha_attendu):
            print("[maj] Base déployée depuis l'archive S3 — à jour.")
            return
        print("[maj] Archive S3 en retard sur la source : reconstruction.")
    reconstruire(sha_attendu)


def main():
    force = "--force" in sys.argv

    try:
        distant = sha_distant()
    except Exception as erreur:
        if base_prete():
            print(f"[maj] Vérification GitHub impossible ({erreur}) — "
                  "la base actuelle est conservée.")
            return
        print(f"[maj] Vérification GitHub impossible ({erreur}) et pas de "
              "base : récupération ou construction sans marqueur de version.")
        recuperer_ou_reconstruire(None)
        return

    if not force and distant == sha_local() and base_prete():
        print(f"[maj] Source inchangée ({distant[:10]}) : rien à reconstruire.")
        return

    raison = "--force" if force else (
        "premier boot" if sha_local() is None else "source modifiée"
    )
    print(f"[maj] Mise à jour ({raison}) : {sha_local()} -> {distant}")
    if force:
        reconstruire(distant)
    else:
        recuperer_ou_reconstruire(distant)


if __name__ == "__main__":
    main()
