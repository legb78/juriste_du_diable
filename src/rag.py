"""L'assistant RAG — l'agent qui répond aux questions avec citations.

Hérite d'Agent (client Groq, prompt, _complete) et orchestre le pipeline :

    question
      -> _decompose        v1 : passe-plat [question] ; jalon 6 : un appel LLM
                           découpera les questions multiples/complexes
      -> _retrieve_multi   UN retrieval PAR sous-question, fusion dédoublonnée
      -> _build_system_prompt   contexte numéroté + métadonnées + date corpus
      -> _complete         l'appel Groq (température 0)
      -> post-traitement EN CODE :
           - citations vérifiées contre les métadonnées des chunks fournis
             (le LLM propose, le code contrôle — un numéro absent du contexte
             est signalé comme non vérifié) ;
           - avertissement juridique TOUJOURS concaténé ici : sa présence ne
             dépend jamais de l'obéissance du LLM (exigence éliminatoire).

Le constructeur RECHARGE la base existante et ne réindexe jamais : si elle
n'existe pas, l'erreur invite à lancer python -m src.index.
"""

import re

from src import config
from src.agent import Agent
from src.vectordb import VectorDB

# Motif d'un numéro d'article de la partie législative (tolère « L. 3121-27 »).
MOTIF_ARTICLE = re.compile(r"[LRD]\.?\s?\d{4}(?:-\d+)+")


class RAG(Agent):
    """Orchestre retrieval, génération et garanties de traçabilité."""

    def __init__(self):
        super().__init__(
            config.RAG_PROMPT_PATH, config.LLM_MODEL, config.LLM_TEMPERATURE
        )
        # Recharge la collection courante (droit en vigueur uniquement).
        self.db = VectorDB(config, config.COLLECTION_NAME)

    # ------------------------------------------------------------------ #
    # 1. Décomposition                                                    #
    # ------------------------------------------------------------------ #
    def _decompose(self, question):
        """v1 : une question = une recherche (liste à un élément).

        Toute la chaîne aval travaille déjà sur des listes : au jalon 6, la
        décomposition des questions multiples/complexes (ou le mode
        comparaison) remplacera ce corps par un appel LLM court, sans toucher
        au reste du pipeline.
        """
        return [question]

    # ------------------------------------------------------------------ #
    # 2. Retrieval (un par sous-question, fusion dédoublonnée)            #
    # ------------------------------------------------------------------ #
    def _retrieve_multi(self, questions):
        """Un retrieve PAR sous-question ; fusion dédoublonnée par chunk
        (clé numéro + partie), la meilleure distance gagne ; tri global."""
        vus = {}
        for question in questions:
            for chunk in self.db.retrieve(question):
                cle = (chunk["metadata"]["numero"], chunk["metadata"]["partie"])
                if cle not in vus or chunk["distance"] < vus[cle]["distance"]:
                    vus[cle] = chunk
        chunks = sorted(vus.values(), key=lambda c: c["distance"])
        # Garde-fou : au plus N_CHUNKS par sous-question dans le contexte.
        return chunks[: config.N_CHUNKS * len(questions)]

    # ------------------------------------------------------------------ #
    # 3. Prompt système                                                   #
    # ------------------------------------------------------------------ #
    def _build_system_prompt(self, chunks):
        """Remplit {{Chunks}} (contexte numéroté) et {{DateCorpus}}."""
        lignes = []
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            depuis = meta["version_depuis"] or "?"
            lignes.append(
                f"[{i}] (rédaction en vigueur depuis le {depuis})\n{chunk['text']}"
            )
        date_corpus = chunks[0]["metadata"]["date_extraction"] if chunks else "inconnue"
        prompt = self.system_prompt_template.replace("{{Chunks}}", "\n\n".join(lignes))
        return prompt.replace("{{DateCorpus}}", date_corpus)

    # ------------------------------------------------------------------ #
    # 4. Vérification des citations (le LLM propose, le code contrôle)    #
    # ------------------------------------------------------------------ #
    def _verifier_citations(self, reponse, chunks):
        """Sépare les numéros cités en (vérifiés, non vérifiés).

        Vérifié = présent dans les métadonnées des chunks fournis au LLM.
        Un numéro « non vérifié » est le symptôme d'une hallucination.
        """
        fournis = {c["metadata"]["numero"] for c in chunks}
        # Les LLM émettent souvent des tirets Unicode (insécable U+2011,
        # demi-cadratin U+2013...) : on les normalise en tiret ASCII avant le
        # motif, sinon « L3121‑27 » échappe à la vérification.
        texte = re.sub(r"[‐‑‒–—−]", "-", reponse)
        cites = {
            re.sub(r"[.\s]", "", m.group(0)) for m in MOTIF_ARTICLE.finditer(texte)
        }
        return sorted(cites & fournis), sorted(cites - fournis)

    # ------------------------------------------------------------------ #
    # Pipeline complet                                                    #
    # ------------------------------------------------------------------ #
    def answer_question(self, question):
        """Renvoie un dict structuré ; l'affichage est l'affaire de main.py.

        Clés : reponse, sources (articles cités ET vérifiés, avec leurs
        métadonnées), citations_non_verifiees, date_corpus, avertissement.
        """
        sous_questions = self._decompose(question)
        chunks = self._retrieve_multi(sous_questions)
        reponse = self._complete(self._build_system_prompt(chunks), question)

        verifiees, non_verifiees = self._verifier_citations(reponse, chunks)
        par_numero = {c["metadata"]["numero"]: c["metadata"] for c in chunks}
        sources = [
            {
                "numero": numero,
                "section": par_numero[numero]["section"],
                "version_depuis": par_numero[numero]["version_depuis"],
            }
            for numero in verifiees
        ]

        return {
            "reponse": reponse,
            "sources": sources,
            "citations_non_verifiees": non_verifiees,
            "date_corpus": chunks[0]["metadata"]["date_extraction"]
            if chunks
            else "inconnue",
            # Concaténé ICI, en code : jamais délégué au LLM (éliminatoire).
            "avertissement": config.AVERTISSEMENT,
        }
