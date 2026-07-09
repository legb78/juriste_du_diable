"""Point d'entrée : construit et PERSISTE la base vectorielle.

Usage :
    python -m src.index

Exigence du sujet : l'indexation est un script séparé de l'interrogation.
src/main.py rechargera la base existante et ne réindexera JAMAIS (une
réindexation à chaque lancement est une erreur éliminatoire). Relancer ce
script sur une base existante la RECHARGE sans réencoder ; pour reconstruire
de zéro (nouveau corpus, nouveau modèle), supprimer le dossier chroma_db/.

Deux collections sont créées depuis data/code_travail.json :
  - code_travail            : le droit en vigueur (interrogée par défaut) ;
  - code_travail_historique : toutes les versions (questions datées).
"""

import random

from src import config
from src.corpus import Corpus
from src.vectordb import VectorDB


def ouvrir_ou_creer(nom_collection, donnees):
    """Recharge la collection si elle existe, sinon la crée depuis `donnees`."""
    try:
        db = VectorDB(config, nom_collection)
        print(f"  {nom_collection} : rechargée sans réencodage ({db.count()} chunks)")
    except ValueError:
        db = VectorDB(config, nom_collection, donnees=donnees)
        print(f"  {nom_collection} : créée et indexée ({db.count()} chunks)")
    return db


def main():
    print(f"Chargement du corpus : {config.CORPUS_PATH}")
    corpus = Corpus(config.CORPUS_PATH)
    ids_courant, docs_courant, metas_courant = corpus.courant()
    print(
        f"{len(corpus)} chunks au total — dont {len(ids_courant)} en vigueur "
        f"(articles découpés compris)"
    )

    print(f"\nBase vectorielle : {config.CHROMA_PATH}")
    ouvrir_ou_creer(config.COLLECTION_NAME, corpus.courant())
    if config.HISTORIQUE_A_LA_VOLEE:
        print(
            f"  {config.COLLECTION_HISTORIQUE} : non créée — historique à la "
            "volée (les textes anciens sont servis par src/histoire.py)"
        )
    else:
        ouvrir_ou_creer(config.COLLECTION_HISTORIQUE, corpus.historique())

    # Contrôle qualité exigé par le sujet : quelques chunks avec métadonnées,
    # à relire (aucun article coupé en pleine phrase, en-têtes corrects).
    print("\n--- Contrôle qualité : 3 chunks au hasard (collection courante) ---")
    for i in random.sample(range(len(ids_courant)), min(3, len(ids_courant))):
        print(f"\n[id : {ids_courant[i]}]")
        print(f"métadonnées : {metas_courant[i]}")
        extrait = docs_courant[i][:400]
        print(extrait + ("..." if len(docs_courant[i]) > 400 else ""))


if __name__ == "__main__":
    main()
