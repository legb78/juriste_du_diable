"""Client de l'API Légifrance (PISTE) — option A du sujet.

Deux responsabilités :

- l'authentification OAuth2 « client credentials » : on échange client_id /
  client_secret contre un jeton d'accès temporaire, joint à chaque requête ;
  le jeton expire, il est donc renouvelé automatiquement un peu avant
  l'échéance (marge de 60 s) ;
- les appels métier : table des matières du Code du travail, texte d'un
  article à partir de son identifiant LEGIARTI.

Seule la brique élémentaire `requests` est utilisée — pas de SDK.
"""

import time

import requests

from src import config


class LegifranceError(Exception):
    """Erreur d'appel à l'API Légifrance (authentification ou requête métier)."""


class LegifranceClient:
    """Encapsule le jeton OAuth2 et les points d'accès utilisés par le projet."""

    def __init__(self):
        if not config.LEGIFRANCE_CLIENT_ID or not config.LEGIFRANCE_CLIENT_SECRET:
            raise LegifranceError(
                "LEGIFRANCE_CLIENT_ID / LEGIFRANCE_CLIENT_SECRET absents : "
                "renseignez-les dans le fichier .env (voir .env.example)."
            )
        self._token = None
        self._token_expiry = 0.0  # timestamp Unix de péremption du jeton

    def _get_token(self):
        """Renvoie un jeton valide, en le renouvelant s'il est (presque) expiré.

        On garde 60 s de marge : un jeton à la limite de l'expiration pourrait
        mourir entre l'envoi de la requête et son traitement côté serveur.
        """
        if self._token is None or time.time() > self._token_expiry - 60:
            reponse = requests.post(
                config.LEGIFRANCE_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": config.LEGIFRANCE_CLIENT_ID,
                    "client_secret": config.LEGIFRANCE_CLIENT_SECRET,
                    "scope": "openid",
                },
                timeout=30,
            )
            if reponse.status_code != 200:
                raise LegifranceError(
                    f"Échec OAuth2 ({reponse.status_code}) : {reponse.text[:300]}"
                )
            donnees = reponse.json()
            self._token = donnees["access_token"]
            self._token_expiry = time.time() + donnees.get("expires_in", 3600)
        return self._token

    def _post(self, endpoint, payload):
        """POST authentifié sur l'API métier (tous ses points d'accès sont en POST)."""
        reponse = requests.post(
            config.LEGIFRANCE_API_URL + endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._get_token()}",
                "Content-Type": "application/json",
            },
            timeout=60,
        )
        if reponse.status_code != 200:
            raise LegifranceError(
                f"{endpoint} -> HTTP {reponse.status_code} : {reponse.text[:300]}"
            )
        return reponse.json()

    def table_matieres_code_travail(self, date_iso):
        """Table des matières du Code du travail à une date donnée.

        Un seul appel renvoie tout l'arbre des sections, avec pour chaque
        article son identifiant LEGIARTI, son numéro et son état (VIGUEUR...).
        """
        return self._post(
            "/consult/legi/tableMatieres",
            {
                "textId": config.LEGIFRANCE_CODE_TRAVAIL_ID,
                "nature": "CODE",
                "date": date_iso,
            },
        )

    def get_article(self, article_id):
        """Texte complet d'un article à partir de son identifiant LEGIARTI."""
        donnees = self._post("/consult/getArticle", {"id": article_id})
        return donnees.get("article") or {}
