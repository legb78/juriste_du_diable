"""Smoke test de l'agent RAG — les trois comportements exigés au jalon 4.

Usage (base indexée + GROQ_API_KEY dans .env) :
    python -m tests.smoke_rag

1. Question DANS le corpus     -> réponse sourcée, citations vérifiées ;
2. Question CONDITIONNELLE     -> règle générale + réserves (accords, effectifs) ;
3. Question HORS corpus        -> refus « Je ne trouve pas cette information... ».

Dans les trois cas, l'avertissement juridique doit apparaître : il est
concaténé par le code (rag.py), pas par le LLM — vérifier qu'il est là à
chaque fois, c'est vérifier la garantie anti-éliminatoire.
"""

from src.rag import RAG

QUESTIONS = [
    ("DANS LE CORPUS", "Quelle est la durée légale de travail par semaine ?"),
    ("CONDITIONNELLE", "Combien d'heures supplémentaires peut-on faire par semaine ?"),
    ("MULTIPLE", "Combien de jours de congés payés par an et comment fonctionne "
                 "la rupture conventionnelle ?"),
    ("FAMILIÈRE", "je peux me faire virer sans préavis ?"),
    ("HORS CORPUS", "Quelle est la capitale du Japon ?"),
]


def afficher(resultat):
    print("Sous-questions recherchées :")
    for sq in resultat["sous_questions"]:
        print(f"  · {sq}")
    print()
    print(resultat["reponse"])
    if resultat["sources"]:
        print("\nSources :")
        for s in resultat["sources"]:
            print(
                f"  - Article {s['numero']} ({s['section']}, rédaction en "
                f"vigueur depuis le {s['version_depuis']})"
            )
    if resultat["citations_non_verifiees"]:
        print(
            "\n[!] Citations NON vérifiées (absentes du contexte fourni) : "
            + ", ".join(resultat["citations_non_verifiees"])
        )
    print(f"\nCorpus extrait le {resultat['date_corpus']} — vérifiez sur legifrance.gouv.fr")
    print(f"⚖  {resultat['avertissement']}")


def main():
    rag = RAG()
    for etiquette, question in QUESTIONS:
        print(f"\n{'=' * 70}\n[{etiquette}]  {question}\n{'-' * 70}")
        afficher(rag.answer_question(question))


if __name__ == "__main__":
    main()
