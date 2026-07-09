"""Sauvegarde et récupération du corpus sur AWS S3.

Cette brique est OPTIONNELLE par conception : sans identifiants AWS_* dans
.env, les fonctions se désactivent proprement (retour False) et le pipeline
local reste 100 % fonctionnel — le correcteur n'a besoin d'aucun bucket.

Deux usages :
- après build_corpus : sauvegarder l'instantané du corpus (clé datée +
  clé « latest » stable, dans l'esprit du versionnage par instantanés) ;
- au déploiement (Scaleway) : télécharger le corpus au démarrage du
  conteneur au lieu de l'embarquer dans l'image.
"""

import tempfile
import zipfile
from pathlib import Path

import boto3

from src import config

# L'archive de la base COMPLÈTE (chroma_db + data, sans le dump re-téléchargeable) :
# publiée depuis le poste local, téléchargée par le serveur au premier boot —
# ~2 min de download contre ~25 min de reconstruction.
CLE_BASE = "base/base_complete.zip"


def _client():
    """Client AWS S3, ou None si la config est absente."""
    if not (
        config.AWS_ACCESS_KEY_ID
        and config.AWS_SECRET_ACCESS_KEY
        and config.AWS_S3_BUCKET
    ):
        return None
    return boto3.client(
        "s3",
        region_name=config.AWS_REGION,
        aws_access_key_id=config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
    )


def upload_corpus(chemin_local, date_extraction):
    """Envoie le corpus dans le bucket sous deux clés.

    - `corpus/<date>_code_travail.json` : l'instantané daté (historique) ;
    - `corpus/latest/code_travail.json` : toujours le dernier (déploiement).

    Renvoie la liste des clés écrites, ou [] si le stockage n'est pas configuré.
    """
    s3 = _client()
    if s3 is None:
        return []
    cles = [
        f"corpus/{date_extraction}_{chemin_local.name}",
        f"corpus/latest/{chemin_local.name}",
    ]
    for cle in cles:
        s3.upload_file(str(chemin_local), config.AWS_S3_BUCKET, cle)
    return cles


def _ajouter_dossier(archive, dossier, prefixe):
    """Ajoute récursivement un dossier à l'archive sous le préfixe donné."""
    for chemin in sorted(dossier.rglob("*")):
        if chemin.is_file():
            archive.write(chemin, f"{prefixe}/{chemin.relative_to(dossier)}")


def publier_base():
    """Zippe la base construite localement (chroma_db + data) et l'envoie sur S3.

    Le dump legi-data (56 Mo) est exclu : re-téléchargeable gratuitement.
    Renvoie la taille de l'archive en Mo, ou None si S3 n'est pas configuré.
    """
    s3 = _client()
    if s3 is None:
        return None
    if not (config.CHROMA_PATH.exists() and config.CORPUS_PATH.exists()):
        raise FileNotFoundError(
            "Base ou corpus absents en local : rien à publier "
            "(lancez build_corpus_legidata puis index d'abord)."
        )
    with tempfile.TemporaryDirectory() as tmp:
        chemin_archive = Path(tmp) / "base_complete.zip"
        with zipfile.ZipFile(chemin_archive, "w", zipfile.ZIP_DEFLATED) as archive:
            _ajouter_dossier(archive, config.CHROMA_PATH, "chroma_db")
            for element in sorted(config.DATA_DIR.iterdir()):
                if element.name == "legidata_code_travail.json":
                    continue  # le dump : lourd et re-téléchargeable
                if element.is_file():
                    archive.write(element, f"data/{element.name}")
                else:
                    _ajouter_dossier(archive, element, f"data/{element.name}")
        taille_mo = chemin_archive.stat().st_size // (1024 * 1024)
        s3.upload_file(str(chemin_archive), config.AWS_S3_BUCKET, CLE_BASE)
    return taille_mo


def telecharger_base():
    """Récupère l'archive de base depuis S3 et la déploie sur RACINE_DONNEES.

    Renvoie True si la base a été déployée ; False si S3 n'est pas configuré
    ou si aucune archive n'a été publiée — l'appelant se rabat alors sur la
    reconstruction locale.
    """
    s3 = _client()
    if s3 is None:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        chemin_archive = Path(tmp) / "base_complete.zip"
        try:
            s3.download_file(config.AWS_S3_BUCKET, CLE_BASE, str(chemin_archive))
        except Exception:
            return False  # pas d'archive publiée, ou accès refusé
        config.RACINE_DONNEES.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(chemin_archive) as archive:
            archive.extractall(config.RACINE_DONNEES)
    return True


def download_corpus(chemin_local):
    """Télécharge `corpus/latest/...` du bucket vers `chemin_local`.

    Utilisé au déploiement : le conteneur récupère le corpus au démarrage
    plutôt que de l'embarquer. Renvoie True si téléchargé, False sinon.
    """
    s3 = _client()
    if s3 is None:
        return False
    chemin_local.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(
        config.AWS_S3_BUCKET,
        f"corpus/latest/{chemin_local.name}",
        str(chemin_local),
    )
    return True
