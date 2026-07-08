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

import boto3

from src import config


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
