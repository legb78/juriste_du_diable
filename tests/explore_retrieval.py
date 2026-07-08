"""Tests exploratoires du retrieval — au-delà du jeu d'évaluation canonique.

Usage (la base doit exister) :
    python -m tests.explore_retrieval

Trois familles de sondages, chacune préparant un jalon à venir :

1. questions FAMILIÈRES (tournures orales, argot) — le retrieval asymétrique
   d'e5 tient-il face au langage réel des utilisateurs ? (prépare le jalon 4)
2. questions HORS CORPUS — à quelles distances remontent les « meilleurs »
   résultats quand la réponse n'existe pas dans la base ? L'écart avec les
   distances des vraies questions (0.226-0.291 sur notre éval) donne le
   seuil de confiance à calibrer (amélioration jalon 6).
3. collection HISTORIQUE — retrouver les versions successives d'un article
   par filtre de métadonnées (préfigure les questions datées, jalon 6).
"""

from src import config
from src.vectordb import VectorDB

FAMILIERES = [
    "je peux me faire virer sans préavis ?",
    "mon patron peut refuser mes dates de vacances ?",
    "c'est quoi le maximum d'heures sup par semaine ?",
    "que dit l'article L3121-27 ?",
]

HORS_CORPUS = [
    "Quelle est la capitale du Japon ?",
    "Comment faire une béchamel ?",
    "Quel est le taux de TVA sur les livres ?",
]


def main():
    db = VectorDB(config, config.COLLECTION_NAME)

    print("=== 1. Questions familières (top-3) ===")
    for question in FAMILIERES:
        chunks = db.retrieve(question, n=3)
        resultats = ", ".join(
            f"{c['metadata']['numero']} ({c['distance']:.3f})" for c in chunks
        )
        print(f"\n« {question} »\n   -> {resultats}")

    print("\n\n=== 2. Hors corpus (calibration du seuil de confiance) ===")
    for question in HORS_CORPUS:
        meilleur = db.retrieve(question, n=1)[0]
        print(
            f"« {question} »\n   -> meilleur match : "
            f"{meilleur['metadata']['numero']} à distance {meilleur['distance']:.3f}"
        )
    print(
        "\nRepère : nos 5 questions de l'éval matchent entre 0.226 et 0.291.\n"
        "Le seuil de confiance candidat se situe entre ces valeurs et celles"
        " ci-dessus."
    )

    print("\n\n=== 3. Collection historique : versions de L1235-3 ===")
    db_hist = VectorDB(config, config.COLLECTION_HISTORIQUE)
    chunks = db_hist.retrieve(
        "indemnité licenciement sans cause réelle et sérieuse",
        n=6,
        where={"numero": "L1235-3"},
    )
    for c in chunks:
        m = c["metadata"]
        fin = m["version_jusqua"] or "en vigueur"
        print(
            f"   {m['numero']} [partie {m['partie']}] "
            f"du {m['version_depuis']} au {fin} (dist. {c['distance']:.3f})"
        )


if __name__ == "__main__":
    main()
