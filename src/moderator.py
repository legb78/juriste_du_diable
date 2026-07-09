"""L'agent modérateur — filtre les prompt injections (amélioration jalon 6).

Hérite d'Agent : même socle que le RAG (client Groq, prompt système chargé
depuis prompts/), mais un modèle spécialisé « safeguard » et un rôle de
vigile. La modération passe AVANT tout dans le pipeline : un message bloqué
n'atteint jamais ni le décomposeur ni le générateur.

    Agent
    ├── RAG        : répond (2 appels LLM, retrieval)
    └── Moderator  : garde la porte (1 appel LLM, aucun retrieval)
"""

import json

from src import config
from src.agent import Agent


class Moderator(Agent):
    """Décide si un message est une question légitime ou une injection."""

    def __init__(self):
        super().__init__(
            config.MODERATOR_PROMPT_PATH, config.MODERATION_MODEL, 0.0
        )

    def moderate(self, message):
        """Renvoie un dict {"is_prompt_injection": bool, "raison": str}.

        Stratégie « fail-open » assumée : si le modèle de modération est
        indisponible ou renvoie du JSON illisible, on laisse passer. Le
        modérateur est une défense EN PROFONDEUR — derrière lui, le prompt
        strict du RAG, les citations vérifiées et l'avertissement en code
        restent actifs. Bloquer tout le service quand le vigile dort serait
        pire que le risque couvert.
        """
        try:
            brut = self._complete(self.system_prompt_template, message)
            debut, fin = brut.find("{"), brut.rfind("}")
            verdict = json.loads(brut[debut : fin + 1])
            return {
                "is_prompt_injection": bool(verdict.get("is_prompt_injection")),
                "raison": str(verdict.get("raison", "")),
            }
        except Exception:
            return {"is_prompt_injection": False, "raison": "modération indisponible"}
