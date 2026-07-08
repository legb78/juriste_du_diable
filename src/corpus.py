"""Chargement du corpus et chunking (stratégie décidée en Q1 du README).

Règle : 1 article = 1 chunk. Le texte embeddé est enrichi de son contexte —
numéro d'article, thème, dernier niveau de la hiérarchie du code :

    "Article L3121-27 — Durée du travail et heures supplémentaires
     (Sous-section 1 : Ordre public) : La durée légale de travail effectif..."

Chaque élément sert la recherche : le numéro fait matcher « que dit
L3121-27 ? », le thème rattache l'article à son domaine, la sous-section
apporte le contexte (Ordre public / Dispositions supplétives...). Le chemin
complet, les dates et la source restent en métadonnées : le vecteur sert à
TROUVER, les métadonnées servent à CITER, FILTRER et AFFICHER.

Cas particulier : ~7 % des articles dépassent la fenêtre de 512 tokens du
modèle e5 (seuil config.CHUNK_MAX_CHARS). Ils sont découpés aux frontières
d'alinéas — jamais en pleine phrase — et chaque morceau répète l'en-tête et
garde le même numéro d'article en métadonnée : la citation reste exacte.
"""

import json

from src import config


def decouper_texte(texte, max_chars):
    """Découpe un texte trop long aux frontières d'alinéas (les sauts de ligne
    préservés par le nettoyage du corpus). Un alinéa n'est jamais scindé, même
    s'il dépasse seul le seuil : on ne coupe pas une phrase de loi en deux.
    """
    if len(texte) <= max_chars:
        return [texte]
    morceaux = []
    courant = ""
    for alinea in texte.split("\n"):
        if courant and len(courant) + len(alinea) + 1 > max_chars:
            morceaux.append(courant)
            courant = alinea
        else:
            courant = f"{courant}\n{alinea}" if courant else alinea
    if courant:
        morceaux.append(courant)
    return morceaux


class Corpus:
    """Le corpus chunké, prêt à être indexé par ChromaDB.

    Chaque chunk est un dict {"id", "document", "metadata", "en_vigueur"} ;
    les méthodes `courant()` et `historique()` renvoient les trois listes
    parallèles (ids, documents, metadatas) attendues par la base vectorielle :
    - courant()    : uniquement les versions en vigueur (collection par défaut) ;
    - historique() : TOUTES les versions (collection des questions datées).
    """

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            documents = json.load(f)
        if not documents:
            raise ValueError(f"Corpus vide ou illisible : {path}")

        self.chunks = []
        for doc in documents:
            self.chunks.extend(self._construire_chunks(doc))

    def _construire_chunks(self, doc):
        """Transforme UN document (une version d'un article) en 1..n chunks."""
        # Dernier niveau de la hiérarchie (ex. "Sous-section 1 : Ordre public").
        sous_section = doc["titre"].split(" > ")[-1].rstrip(".").strip()
        morceaux = decouper_texte(doc["texte"], config.CHUNK_MAX_CHARS)
        total = len(morceaux)

        chunks = []
        for i, morceau in enumerate(morceaux, 1):
            partie = f" (partie {i}/{total})" if total > 1 else ""
            chunks.append(
                {
                    "id": doc["id"] if total == 1 else f"{doc['id']}#p{i}",
                    "document": (
                        f"Article {doc['numero']}{partie} — {doc['section']} "
                        f"({sous_section}) : {morceau}"
                    ),
                    # ChromaDB n'accepte pas None en métadonnée : les dates
                    # absentes deviennent des chaînes vides.
                    "metadata": {
                        "numero": doc["numero"],
                        "section": doc["section"],
                        "titre": doc["titre"],
                        "source": doc["source"],
                        "date_extraction": doc["date_extraction"],
                        "version_depuis": doc["version_depuis"] or "",
                        "version_jusqua": doc["version_jusqua"] or "",
                        "en_vigueur": doc["en_vigueur"],
                        "partie": f"{i}/{total}",
                    },
                    "en_vigueur": doc["en_vigueur"],
                }
            )
        return chunks

    def _listes(self, chunks):
        """Trois listes parallèles (ids, documents, metadatas) pour ChromaDB."""
        return (
            [c["id"] for c in chunks],
            [c["document"] for c in chunks],
            [c["metadata"] for c in chunks],
        )

    def courant(self):
        """Chunks du droit en vigueur uniquement (collection par défaut)."""
        return self._listes([c for c in self.chunks if c["en_vigueur"]])

    def historique(self):
        """Tous les chunks, toutes versions (collection des questions datées)."""
        return self._listes(self.chunks)

    def __len__(self):
        return len(self.chunks)
