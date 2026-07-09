"""Historique « à la volée » : les textes anciens, à la demande seulement.

Le corpus indexé ne contient que le droit en vigueur (dump legi-data). La
carte des versions (data/versions_map.json, extraite du dump : ids + dates de
chaque rédaction de chaque article) sait ce qui a existé et quand — mais pas
ce que ça disait. Ce module résout « l'article N à la date D » :

    carte (locale, instantanée)  ->  version valide à la date D
    cache disque                 ->  déjà téléchargée ? on la relit
    API Légifrance               ->  sinon UN appel getArticle, puis cache

Coût par question datée : 0 à 3 appels API, contre 10 000+ en
pré-téléchargement intégral. Contrepartie assumée : les questions datées
exigent le réseau et les identifiants PISTE.
"""

import json

from src import config
from src.build_corpus import clean_text, date_iso
from src.legifrance import LegifranceClient


class Histoire:
    """Résout les versions passées d'un article, avec cache disque."""

    def __init__(self):
        with open(config.VERSIONS_MAP_PATH, encoding="utf-8") as f:
            self.carte = json.load(f)
        self._client = None  # créé au premier appel API seulement

    def versions_de(self, numero):
        """La liste des rédactions connues d'un article (ids + dates)."""
        return (self.carte.get(numero) or {}).get("versions", [])

    def version_valide_au(self, numero, date_cible):
        """L'entrée de la carte valide à `date_cible` (ISO), sinon None.

        Les dates ISO se comparent en texte (ordre lexicographique = ordre
        chronologique). None = l'article n'existait pas à cette date, ou le
        numéro était vacant (cf. réattributions post-recodification).
        """
        for version in self.versions_de(numero):
            debut = version.get("debut") or "0000"
            fin = version.get("fin") or "9999"
            if debut <= date_cible < fin:
                return version
        return None

    def texte_version(self, version_id):
        """Le texte d'une version : cache disque d'abord, sinon UN appel API."""
        cache = config.CACHE_VERSIONS_DIR / f"{version_id}.json"
        if cache.exists():
            with open(cache, encoding="utf-8") as f:
                return json.load(f)

        if self._client is None:
            self._client = LegifranceClient()
        detail = self._client.get_article(version_id)
        resultat = {
            "id": version_id,
            "numero": detail.get("num"),
            "texte": clean_text(
                detail.get("texteHtml") or detail.get("texte") or ""
            ),
            "version_depuis": date_iso(detail.get("dateDebut")),
            "version_jusqua": date_iso(detail.get("dateFin")),
        }
        config.CACHE_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        return resultat

    def article_au(self, numero, date_cible):
        """« Que disait l'article N à la date D ? » — le service complet.

        Renvoie le dict de la version (texte + dates), ou None si aucune
        rédaction n'était en vigueur à cette date.
        """
        version = self.version_valide_au(numero, date_cible)
        if version is None:
            return None
        return self.texte_version(version["id"])
