# Juriste du diable — Assistant Code du travail (RAG)

Assistant juridique capable de répondre en langage naturel à des questions sur
le droit du travail français, **en citant systématiquement les articles** du
Code du travail — et en refusant de répondre quand l'information n'est pas
dans sa base, plutôt qu'inventer. Disponible en **CLI** et en **interface web**.

🌐 **Démo en ligne : <https://juristedudiable-production.up.railway.app>**

Projet final M2 MD5 — Data & IA. Implémentation **sans framework RAG**
(LangChain et LlamaIndex interdits) : chaque brique — corpus, chunking,
embeddings, base vectorielle, recherche hybride, prompts, agents — est écrite
à la main.

> ⚠️ **Cet assistant ne fournit pas de conseil juridique. Consultez un avocat
> ou l'inspection du travail pour votre situation personnelle.** Cette mention
> accompagne chaque réponse : elle est concaténée **par le code** (`rag.py`),
> jamais déléguée au LLM.

---

## Architecture

```
CONSTRUCTION (une fois)                      CHAQUE QUESTION
─────────────────────────                    ────────────────────────────────
dump SocialGouv/legi-data                    ⓪ Modérateur (anti-injection)
  (56 Mo, public, quotidien)                 ① Décomposition LLM : 1-4 sous-
        │ nettoyage (clean_text)                questions reformulées
        ▼                                    ② Recherche HYBRIDE (100 % locale) :
corpus 11 495 articles en vigueur               vectoriel (e5) + lexical (BM25)
  + carte des versions (ids+dates)              fusionnés en RRF + garantie sur
        │ chunking : 1 article = 1 chunk        les numéros d'articles cités
        ▼                                    ③ Génération (Groq, température 0)
ChromaDB persistante                         ④ Post-traitement EN CODE :
  12 525 chunks, e5-base gravé                  citations vérifiées, sources
  dans les métadonnées                          (liens Légifrance), avertissement

HISTORIQUE DES VERSIONS : à la volée — la carte (locale) sait quelles
rédactions ont existé ; le TEXTE d'une ancienne version n'est demandé à l'API
Légifrance qu'au moment voulu, avec cache disque (src/histoire.py).
```

## Questions de réflexion (traitées avant le pipeline, mises à jour au réel)

### Q1 — Granularité du chunking

**Choix : 1 chunk = 1 article, enrichi de son contexte** — le texte embeddé est
`Article {numéro} — {thème} ({sous-section}) : {texte}`. L'article est l'unité
juridique citable ; le numéro dans le vecteur fait fonctionner « que dit
L3121-1 ? » ; la sous-section (Ordre public / Dispositions supplétives…)
injecte le contexte. Les articles > 1 500 caractères (~9 % du corpus — la
fenêtre de 512 tokens d'e5) sont découpés **aux frontières d'alinéas** — jamais
en pleine phrase — chaque partie répétant l'en-tête et gardant le même numéro
en métadonnée. Le regroupement par section a été rejeté : vecteur-moyenne flou
et citation invérifiable. Pas de chevauchement : la coupe suit la structure du
texte, elle n'a rien à compenser.

### Q2 — Traçabilité

Le numéro d'article vit **aux deux endroits** : dans le texte embeddé (pour la
recherche) et dans les métadonnées (pour l'affichage). Le LLM a l'obligation de
ne citer que les numéros présents dans le contexte — mais on ne lui fait pas
confiance : le code **vérifie chaque citation** contre les métadonnées des
chunks réellement fournis (`_verifier_citations`, tirets Unicode normalisés).
Les sources affichées sont reconstruites par le code, avec **lien direct vers
le texte officiel** (`legifrance.gouv.fr/codes/article_lc/<LEGIARTI>`). Une
citation hors contexte est signalée « non vérifiée », jamais présentée comme
source.

### Q3 — Fraîcheur

Trois niveaux : `date_extraction` (l'instantané du corpus) affichée à chaque
réponse ; `version_depuis` (l'entrée en vigueur de la rédaction de chaque
article cité) ; et une **mise à jour quotidienne conditionnelle** — un cron
redéploie le service chaque nuit, et le boot compare le SHA du dump source au
marqueur local : la base n'est reconstruite **que si le droit a changé**.

### Q4 — Réponses conditionnelles

Le prompt système impose la règle légale générale **puis** les réserves
explicites (accord collectif, effectifs) quand les extraits les mentionnent.
Mesuré au jeu d'évaluation (heures supplémentaires : synthèse de 3 articles
avec la réserve « sauf accord collectif »).

### Q5 — La frontière du conseil juridique

Question factuelle → réponse sourcée. Question d'appréciation personnelle
(« mon licenciement est-il abusif ? ») → le prompt impose d'exposer le cadre
légal général et de renvoyer vers un avocat ou l'inspection du travail, sans
trancher le cas. L'avertissement, lui, est ajouté en code à 100 % des réponses.

## Choix techniques

| Brique | Choix | Justification (mesurée) |
|---|---|---|
| Corpus | **Source mixte** : dump JSON SocialGouv/legi-data (masse courante, 0 appel API) + API Légifrance OAuth2 (textes des versions passées, à la volée) | Vérifié sur les données : le dump a la *carte* des versions mais pas leurs *textes* — l'API reste la seule source de l'historique |
| Embeddings | `intfloat/multilingual-e5-base`, préfixes `query:`/`passage:` | Entraîné pour la recherche asymétrique (question familière → texte de loi) ; benchmark FR ; adapté CPU |
| Base vectorielle | ChromaDB persistante, **modèle gravé dans les métadonnées de la collection** et relu au rechargement | Exigence du sujet ; insertion par lots de 5 000 (plafond ChromaDB découvert à 12 525 chunks) |
| Recherche | **Hybride : vectoriel + BM25, fusion RRF, garantie numéros** | A/B mesuré : à 12 525 chunks, vectoriel seul 4/6, hybride **6/6** ; « que dit L3121-1 ? » garanti au rang 1 |
| LLM | `openai/gpt-oss-20b` via Groq, température 0 | Restitution fidèle du corpus ; retry à attente croissante sur les limites de débit |
| Agents | Classe mère `Agent` → `RAG` + `Moderator` (anti-injection, étape 0 du pipeline) | Une injection est bloquée avant d'atteindre le LLM principal |
| Améliorations (jalon 6) | Décomposition-reformulation LLM (1-4 sous-questions) · recherche hybride · modérateur · maj quotidienne conditionnelle | HyDE étudié et écarté : redondant avec la reformulation + l'entraînement asymétrique d'e5 |

## Résultats mesurés (jeux d'évaluation versionnés dans `tests/`)

- **Retrieval** (`eval_retrieval`) : hybride **6/6** contre vectoriel 4/6 sur
  12 525 chunks (5 questions sémantiques + 1 lexicale) ;
- **Bout en bout** (`eval_rag`, 12 cas annotés) : justesse **8/9**, fidélité
  **8/9**, garanties **15/15** (refus hors corpus 2/2, blocage injection 1/1,
  avertissement 12/12) — un cas connu de refus à tort documenté dans SUIVI.md ;
- **Persistance** : rechargement sans réencodage vérifié (12 525 chunks, ~30 s).

## Structure du projet

```
src/
  config.py                 configuration centrale (modèles, chemins, thèmes, env)
  legifrance.py             client API PISTE (OAuth2 client credentials + renouvellement)
  build_corpus_legidata.py  extraction : dump public nettoyé + carte des versions
  build_corpus.py           extraction alternative tout-API (option A pure)
  corpus.py                 chunking (1 article = 1 chunk, découpe aux alinéas)
  vectordb.py               ChromaDB persistante + recherche hybride (BM25 + RRF)
  index.py                  construit et PERSISTE la base (séparé de l'interrogation)
  agent.py                  classe mère des agents LLM (Groq, prompts, retry)
  rag.py                    l'assistant : modération, décomposition, retrieval,
                            génération, citations vérifiées, avertissement en code
  moderator.py              agent anti-injection (modèle safeguard)
  histoire.py               versions passées à la volée (carte + API + cache)
  maj.py                    mise à jour conditionnelle (SHA du dump vs marqueur)
  storage.py                S3 : instantanés du corpus, archive de la base
  publier_base.py           publie la base locale vers S3 (déploiement rapide)
  main.py                   CLI interactive (jalon 5)
  api.py                    interface web (FastAPI + static/)
prompts/                    prompts système versionnés (RAG, décomposition, modération)
tests/                      éval retrieval (A/B), éval bout-en-bout, sondes exploratoires
static/                     page chat (sources cliquables, historique localStorage)
boot.sh · railway.json · .github/workflows/   déploiement et mise à jour quotidienne
SUIVI.md                    journal de bord : décisions, difficultés, mesures
```

## Installation

```bash
git clone https://github.com/legb78/juriste_du_diable.git
cd juriste_du_diable
python -m venv juriste_du_diable
juriste_du_diable\Scripts\activate      # Windows (Linux/macOS : source .../bin/activate)
pip install -r requirements.txt
copy .env.example .env                  # puis renseigner GROQ_API_KEY (obligatoire)
```

Secrets : `GROQ_API_KEY` obligatoire (génération). `LEGIFRANCE_*` uniquement
pour les textes des versions passées (questions datées / extraction tout-API).
`AWS_*` optionnels (archivage S3). **Aucune clé dans le dépôt ni dans
l'historique Git.**

## Usage

```bash
# 1. Construire le corpus (dump public : AUCUN identifiant requis, ~3 min)
python -m src.build_corpus_legidata

# 2. Indexer — une fois, persistant (~15-20 min d'encodage CPU)
python -m src.index
#    (relancer = « rechargée sans réencodage » : jamais de réindexation au lancement)

# 3a. Interroger en CLI
python -m src.main                                   # boucle interactive
python -m src.main "Quelle est la durée légale du travail ?"

# 3b. Ou l'interface web
uvicorn src.api:app        # puis http://127.0.0.1:8000

# Évaluations
python -m tests.eval_retrieval    # A/B vectoriel vs hybride
python -m tests.eval_rag          # justesse / fidélité / garanties
```

## Workflow Git & déploiement

Workflow Scribe : `feature/*` → `dev` → `main` via pull requests relues en
binôme ; versions taguées sur `main` (`v0.1.0` : corpus + indexation +
retrieval validé ; `v1.0.0` : pipeline complet). Déploiement Railway suivant
la branche de release : `boot.sh` → `maj.py` (base récupérée depuis S3 ou
reconstruite, seulement si la source a changé) → uvicorn ; mise à jour
quotidienne par cron GitHub Actions.

**Production : <https://juristedudiable-production.up.railway.app>**

## Auteurs

Binôme M2 MD5 — projet encadré, 2026.
