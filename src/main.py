"""Point d'entrée : interroger l'assistant depuis le terminal (jalon 5).

Usage :
    python -m src.main "Quelle est la durée légale du travail ?"   # question directe
    python -m src.main                                             # boucle interactive

La base vectorielle doit exister (python -m src.index) : ce script la
RECHARGE et ne réindexe jamais — si elle est absente, l'erreur de VectorDB
indique la commande à lancer.
"""

import sys

from src.rag import RAG

LIGNE = "─" * 70


def afficher(resultat):
    """Affiche une réponse complète : texte, sources (avec lien Légifrance),
    citations non vérifiées, date du corpus et avertissement juridique."""
    print()
    if resultat["sous_questions"]:
        print("Recherches effectuées :")
        for sous_question in resultat["sous_questions"]:
            print(f"  · {sous_question}")
        print()

    print(resultat["reponse"])

    if resultat["sources"]:
        print("\nSources :")
        for source in resultat["sources"]:
            print(
                f"  - Article {source['numero']} ({source['section']}, "
                f"rédaction en vigueur depuis le {source['version_depuis']})"
            )
            if source.get("legiarti"):
                print(
                    "    https://www.legifrance.gouv.fr/codes/article_lc/"
                    f"{source['legiarti']}"
                )

    if resultat["citations_non_verifiees"]:
        print(
            "\n[!] Références citées mais absentes du contexte fourni "
            "(non vérifiées) : " + ", ".join(resultat["citations_non_verifiees"])
        )

    print(
        f"\nCorpus extrait le {resultat['date_corpus']} — le droit évolue, "
        "vérifiez sur legifrance.gouv.fr"
    )
    print(f"⚖  {resultat['avertissement']}")
    print(LIGNE)


def boucle_interactive(rag):
    """Saisie -> réponse, en boucle ; 'quit' ou 'exit' pour une sortie propre."""
    print(LIGNE)
    print("Assistant Code du travail — posez une question à la fois.")
    print("Tapez 'quit' ou 'exit' pour sortir.")
    print(LIGNE)
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break
        if question.lower() in ("quit", "exit"):
            print("Au revoir.")
            break
        if not question:
            continue
        afficher(rag.answer_question(question))


def main():
    rag = RAG()  # recharge la base existante ; erreur explicite sinon
    if len(sys.argv) > 1:
        afficher(rag.answer_question(" ".join(sys.argv[1:])))
    else:
        boucle_interactive(rag)


if __name__ == "__main__":
    main()
