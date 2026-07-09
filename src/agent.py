"""Classe mère des agents LLM du projet.

Un « agent » = un rôle défini par un prompt système (fichier dans prompts/),
un modèle Groq et une température. Cette classe factorise ce que tous les
agents partagent — le client Groq, le chargement du prompt, l'appel au LLM —
et chaque agent fils apporte sa spécialité :

    Agent (classe mère : client Groq, prompt, _complete)
    ├── RAG        (src/rag.py)       : répond aux questions avec citations
    └── Moderator  (src/moderator.py) : filtre les prompt injections (jalon 6)
"""

from groq import Groq

from src import config


class Agent:
    """Socle commun : un prompt système, un modèle Groq, une température."""

    def __init__(self, prompt_path, model, temperature):
        if not config.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY absente : renseignez-la dans le fichier .env "
                "(voir .env.example)."
            )
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model = model
        self.temperature = temperature

        # Le prompt système vit dans prompts/ (versionné, relisible) — jamais
        # en dur dans le code. Il peut contenir des marqueurs {{...}} que les
        # agents fils remplissent avant l'appel.
        with open(prompt_path, encoding="utf-8") as f:
            self.system_prompt_template = f.read()

    def _complete(self, system_prompt, user_message):
        """Un appel au LLM : prompt système + message utilisateur -> texte.

        Le plafond de tokens de sortie est explicite : sans lui, le défaut du
        serveur tronque les réponses multi-volets en plein mot.
        """
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            max_completion_tokens=config.LLM_MAX_TOKENS,
        )
        return completion.choices[0].message.content
