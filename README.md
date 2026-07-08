# Juriste du diable — Assistant Code du travail (RAG)

Assistant juridique en ligne de commande capable de répondre en langage naturel à des
questions sur le droit du travail français, **en citant systématiquement les articles**
du Code du travail sur lesquels il s'appuie — et en refusant de répondre quand
l'information n'est pas dans sa base, plutôt qu'inventer.

Projet final M2 MD5 — Data & IA. Implémentation **sans framework RAG** (LangChain et
LlamaIndex interdits) : chaque brique (corpus, chunking, embeddings, base vectorielle,
prompt, appel LLM) est écrite à la main.

> ⚠️ **Cet assistant ne fournit pas de conseil juridique. Consultez un avocat ou
> l'inspection du travail pour votre situation personnelle.** Cette mention accompagne
> chaque réponse du système ; elle est ajoutée par le code, pas par le LLM (voir Q2/Q5).

---

## Questions de réflexion (traitées avant d'écrire le pipeline)

### Q1 — Granularité du chunking

**Par article** : les articles de loi sont courts, denses et autonomes ; un chunk = une
unité juridique citable, exactement ce que la réponse doit référencer. Inconvénient :
un article isolé perd son contexte thématique (« la présente section... »).

**Par section** : préserve le contexte et les renvois internes. Inconvénients : chunks
trop longs (le signal se dilue dans l'embedding), et une section entière remontée pour
une question précise noie le LLM.

**Notre choix — approche hybride** : *1 chunk = 1 article*, mais le texte embeddé est
enrichi du contexte de section : `"Article {numéro} — {section} : {texte}"`. On garde
la précision de citation de l'article ET la sémantique thématique de la section dans
le même vecteur.

### Q2 — Traçabilité

Le numéro d'article est stocké **aux deux endroits** :

- **dans le texte embeddé** — pour que les questions mentionnant un numéro
  (« que dit L3121-1 ? ») matchent en recherche vectorielle ;
- **dans les métadonnées** — pour l'affichage fiable des sources.

Le LLM a l'obligation (prompt) de ne citer que les numéros présents dans le contexte
fourni ; mais on ne lui fait pas confiance : la liste des articles sources affichée à
l'utilisateur est reconstruite **par le code** depuis les métadonnées des chunks
récupérés, jamais depuis la sortie du LLM. Un numéro cité par le LLM mais absent du
contexte est un signal d'hallucination.

### Q3 — Fraîcheur

Chaque document du corpus porte une métadonnée `date_extraction`. Cette date est
affichée avec chaque réponse (« Corpus extrait le JJ/MM/AAAA — le droit du travail
évolue, vérifiez sur legifrance.gouv.fr »). Le système ne prétend jamais être à jour :
il dit sur quoi il s'appuie.

### Q4 — Réponses conditionnelles

Beaucoup de réponses dépendent de la taille de l'entreprise ou de la convention
collective. Le prompt système impose une **réponse générale assortie de réserves
explicites** : le régime légal par défaut est énoncé (avec ses articles), puis les
conditions qui peuvent le modifier sont signalées. Pas de question de clarification en
v1 (la CLI reste simple) ; c'est une extension envisagée avec l'historique de
conversation.

### Q5 — La frontière du conseil juridique

Question **factuelle** (« combien de jours de congés par an ? ») : le Code répond
directement → réponse sourcée. Question d'**interprétation** (« mon licenciement
est-il abusif ? ») : elle exige une qualification juridique d'une situation
personnelle → le prompt instruit le LLM de ne pas trancher, d'exposer le cadre légal
général pertinent, et de renvoyer vers un avocat ou l'inspection du travail.
L'avertissement juridique, lui, est ajouté **en code** à chaque réponse, quelle que
soit la question : une garantie de pipeline, pas une promesse de prompt.

---

## Choix techniques

| Brique | Choix | Pourquoi |
|---|---|---|
| Corpus | **API Légifrance (PISTE), option A** — OAuth2 client credentials | Source officielle, valorisée au barème ; repli option C (JSON manuel) si blocage |
| Embeddings | `sentence-transformers` — modèle multilingue | Corpus 100 % français |
| Base vectorielle | **ChromaDB persistant** | Persistance sur disque native ; le nom du modèle d'embedding est gravé dans les métadonnées de la collection et relu au rechargement |
| LLM | **Groq**, température 0 | Restitution fidèle du corpus, pas de créativité |
| Interface | CLI (`python -m src.main`) | Exigence du sujet, jalon 5 |

**Indexation et interrogation sont deux scripts séparés** : `src/index.py` construit et
persiste la base (une fois) ; `src/main.py` la recharge **sans jamais réindexer** et
échoue avec un message clair si elle n'existe pas.

## Structure du projet

```
data/                  corpus extrait (code_travail.json)
prompts/               prompts système versionnés (rag_system.txt, ...)
src/
  config.py            configuration centrale (modèles, chemins, secrets via .env)
  legifrance.py        client API Légifrance (jeton OAuth2 + renouvellement)
  build_corpus.py      extraction API -> data/code_travail.json
  corpus.py            chargement du corpus (ids / documents / metadatas)
  vectordb.py          base vectorielle persistante (ChromaDB + sentence-transformers)
  index.py             point d'entrée : construit et persiste la base
  rag.py               orchestration : retrieval -> prompt -> LLM -> citations + avertissement
  main.py              point d'entrée : boucle de questions-réponses en CLI
tests/
  eval_retrieval.py    jeu d'évaluation du retrieval (5 questions -> article attendu)
```

## Thèmes couverts (≥ 5 exigés)

1. Durée du travail et heures supplémentaires (L3121-1 à L3121-36)
2. Congés payés (L3141-1 à L3141-32)
3. Contrat de travail — CDI, CDD (L1221-1 à L1248-11)
4. Licenciement (L1231-1 à L1237-20)
5. Rupture conventionnelle (L1237-11 à L1237-19)

## Installation

```bash
git clone https://github.com/legb78/juriste_du_diable.git
cd juriste_du_diable

python -m venv juriste_du_diable        # le venv est ignoré par Git
juriste_du_diable\Scripts\activate      # Windows  (Linux/macOS : source juriste_du_diable/bin/activate)

pip install -r requirements.txt

copy .env.example .env                  # Windows  (Linux/macOS : cp .env.example .env)
# puis renseigner GROQ_API_KEY, LEGIFRANCE_CLIENT_ID, LEGIFRANCE_CLIENT_SECRET dans .env
```

## Usage

```bash
# 1. Construire le corpus depuis l'API Légifrance (une fois)
python -m src.build_corpus

# 2. Indexer : créer et persister la base vectorielle (une fois)
python -m src.index

# 3. Interroger (recharge la base existante, ne réindexe jamais)
python -m src.main                                        # boucle interactive (quit pour sortir)
python -m src.main "Quelle est la durée légale du travail ?"   # question directe
```

## Workflow Git

Workflow Scribe : `feature/*` → `dev` → `main`, chaque jalon sur sa branche avec pull
request relue en binôme. Versions taguées : `v0.1.0` (corpus + indexation + retrieval
validé), `v1.0.0` (pipeline complet + CLI). Aucun secret versionné : `.env` est ignoré,
seul `.env.example` est commité.

## Auteurs

Binôme M2 MD5 — projet encadré, 2026.
