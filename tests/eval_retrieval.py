"""Jalon « recherche seule » : valider le retrieval AVANT tout appel au LLM.

Usage (la base doit exister : python -m src.index d'abord) :
    python -m tests.eval_retrieval

Cinq questions dont on connaît l'article attendu ; pour chacune, l'article
doit remonter dans le top-k de la collection courante. Si un article ne
remonte pas, le problème vient du chunking, de l'embedding ou du corpus —
pas du LLM, qui n'est pas encore branché. Ces questions sont conservées :
elles forment le jeu d'évaluation du projet.
"""

import sys

from src import config
from src.vectordb import VectorDB

# (question, numéro d'article attendu dans le top-k)
QUESTIONS = [
    ("Quelle est la durée légale de travail par semaine ?", "L3121-27"),
    ("Combien de jours de congés payés acquiert-on par mois de travail ?", "L3141-3"),
    ("Quelle est la durée maximale de la période d'essai pour un cadre en CDI ?", "L1221-19"),
    ("Comment fonctionne la rupture conventionnelle ?", "L1237-11"),
    ("Quelle indemnité en cas de licenciement sans cause réelle et sérieuse ?", "L1235-3"),
]


def main():
    db = VectorDB(config, config.COLLECTION_NAME)  # recharge ; erreur si absente

    reussites = 0
    for question, attendu in QUESTIONS:
        chunks = db.retrieve(question)
        numeros = [c["metadata"]["numero"] for c in chunks]
        if attendu in numeros:
            rang = numeros.index(attendu) + 1
            distance = chunks[rang - 1]["distance"]
            print(f"OK  {attendu} au rang {rang}/{len(chunks)} "
                  f"(distance {distance:.3f}) — {question}")
            reussites += 1
        else:
            print(f"ÉCHEC  {attendu} absent du top-{len(chunks)} — {question}")
            print(f"       remontés : {numeros}")

    print(f"\nBilan : {reussites}/{len(QUESTIONS)} articles attendus dans le top-k")
    if reussites < len(QUESTIONS):
        sys.exit(1)


if __name__ == "__main__":
    main()
