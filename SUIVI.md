# Suivi du projet — Assistant Code du travail (RAG)

> Journal de bord du binôme : décisions, difficultés, résultats mesurés.
> Alimente le compte rendu final et prépare la soutenance.
> Dernière mise à jour : 2026-07-08

---

## 1. État d'avancement

| Jalon | Contenu | Branche | Statut |
|---|---|---|---|
| 0 — Bootstrap | Structure, README (Q1–Q5), .env.example, requirements | `feature/bootstrap` | ✅ mergé (PR #1) |
| 1 — Config | Constantes de module, modèles, chemins, thèmes | `feature/config` | ✅ mergé (PR #2, #3) |
| 2 — Corpus | Client Légifrance OAuth2, extraction historisée, S3 | `feature/corpus` | ✅ extrait (1007 docs) — PR à merger |
| 3 — Chunking + indexation | corpus.py, vectordb.py, index.py | `feature/vectordb` | 🔄 code écrit — indexation à exécuter |
| 3bis — Retrieval seul | tests/eval_retrieval.py (5 questions) | `feature/vectordb` | ⏳ à exécuter |
| — | **Tag v0.1.0 sur main** | | ⏳ |
| 4 — Génération | Agent (classe mère) + RAG, prompt système, citations vérifiées, décomposition | `feature/rag` | ✅ 8 commits — PR vers dev à merger |
| 6a — Modérateur | Moderator(Agent), modèle safeguard, étape 0 du pipeline | `feature/moderator` | ✅ 4 commits, injection bloquée au smoke test — PR à faire |
| 5 — CLI | main.py (boucle interactive), README final | `feature/cli` | ⏳ |
| — | **Tag v1.0.0 sur main** | | ⏳ |
| 6 — Amélioration | recherche hybride et/ou questions datées (historique) | à définir | ⏳ |

---

## 2. Décisions de conception (et leurs justifications)

| # | Décision | Justification courte |
|---|---|---|
| D1 | **Option A — API Légifrance** (OAuth2 client credentials, renouvellement auto du jeton à −60 s) | Valorisée au barème ; source officielle consolidée ; le client tient en ~100 lignes de `requests` |
| D2 | **Embedding `intfloat/multilingual-e5-base`** | Entraîné pour le retrieval asymétrique (question familière → texte de loi), préfixes `query:`/`passage:` ; ~90 % de la qualité de Solon-large pour 2× moins de poids — contrainte CPU. Décision révisable sur mesure (voir §4) |
| D3 | **LLM `openai/gpt-oss-20b`** via Groq, température 0 | Restitution fidèle du corpus, pas de créativité |
| D4 | **Chunking : 1 article = 1 chunk**, texte embeddé enrichi `Article {n°} — {thème} ({sous-section}) : {texte}` | L'article est l'unité de citation juridique ; le numéro dans le vecteur fait matcher « que dit L3121-1 ? » ; la sous-section apporte le contexte (Ordre public / supplétif) |
| D5 | **Articles > 1500 caractères : découpe aux frontières d'alinéas** (jamais en pleine phrase), en-tête répété, même numéro en métadonnée | Fenêtre de 512 tokens d'e5 ; ne concerne que 68 docs sur 1007 (7 %) ; pas de chevauchement — la coupe suit la structure du texte, elle n'a rien à compenser |
| D6 | **Historisation complète des versions** depuis la recodification de 2008 | Demande explicite du binôme ; permet les questions datées (amélioration jalon 6) |
| D7 | **Deux collections ChromaDB** : `code_travail` (en vigueur, défaut) / `code_travail_historique` (tout) | Isolation physique : une version abrogée ne peut JAMAIS remonter dans une réponse ordinaire — citer du droit mort est la faute maximale d'un assistant juridique |
| D8 | **Nom du modèle d'embedding gravé dans les métadonnées de la collection**, relu au rechargement | Exigence du sujet ; évite d'encoder questions et documents avec deux modèles différents |
| D9 | **Avertissement juridique concaténé EN CODE** (rag.py), jamais délégué au prompt | Absence = éliminatoire ; le code garantit 100 %, le prompt non |
| D10 | **Corpus au format JSON** (pas CSV comme le mini-TP) | Textes multi-lignes (alinéas), booléens, dates nullables — le CSV l'encoderait mal |
| D11 | **`data/` non versionné dans Git** | Données publiques régénérables ≠ code ; instantanés archivés sur AWS S3 en clés datées (`corpus/<date>_...` + `corpus/latest/`) |
| D12 | **Stockage objet AWS S3 optionnel par conception** (sans clés → désactivation silencieuse) | Le correcteur doit pouvoir tout exécuter sans bucket |
| D13 | **Thèmes ordonnés du plus spécifique au plus général** dans la config | Les plages du sujet sont imbriquées (Contrat ⊃ Licenciement ⊃ Rupture conv.) — sinon 3 sections au lieu de 5 |

## 3. Difficultés rencontrées (et résolutions)

| Difficulté | Résolution | Leçon |
|---|---|---|
| **403 sur l'API** après OAuth réussi | La souscription à l'API Légifrance (+ CGU DILA) manquait sur PISTE — le jeton se délivre même sans souscription | Tester par étages : le smoke test à 3 étages a localisé le maillon en 30 s |
| **Commit fait directement sur `dev`** (jalon config) | `git branch feature/config` + `git reset --hard origin/dev` (commit préservé sur la branche) | Créer la branche AVANT de commiter ; les modifs non commitées suivent le checkout |
| **Commit « corpus » à moitié vide** (le JSON n'existait pas encore) | Le run `build_corpus` n'avait jamais eu lieu ; re-commit après vrai run | Un message de commit ne vaut que si on vérifie son contenu (`git show --stat`) |
| **Plages thématiques imbriquées** : 216 articles « Licenciement » étiquetés « Contrat de travail » | Réordonnancement des thèmes + décompte des attributions réelles | Vérifier les décomptes, pas seulement l'absence d'erreur (36+37+455 = 528 a vendu la mèche) |
| **Historique limité à 2008** sur certains articles | Recodification de 2008 : l'ancien code (L2xx-x) est un autre texte pour Légifrance ; `articleVersions` suit une identité d'article | Limite documentée, pas un bug ; généalogie via `liens` = piste « avec plus de temps » |
| **Numéros réattribués** : le L3121-27 de 2008 (repos compensateur) n'a rien à voir avec celui de 2016 (35 h) | Confirme le choix des deux collections : une « ancienne version » peut être une règle différente | Argument béton pour D7 en soutenance |
| **Mots collés** (« au-delàdu ») dans le texte nettoyé | Espace insécable HTML ajouté à la normalisation de `clean_text` | Relire les chunks, vraiment |
| `\` de continuation bash collé dans PowerShell | Commandes `gh` sur une seule ligne | Deux shells, deux syntaxes |
| `ModuleNotFoundError: src` en lançant `python tests\...py` | Toujours `python -m tests.module` depuis la racine | Le `-m` place la racine du projet dans le path |
| **Sources vides malgré des citations correctes** (jalon 4) | gpt-oss écrit « L3121‑27 » avec un trait d'union insécable U+2011 — la regex ASCII de vérification ne matchait pas → normalisation des tirets Unicode avant extraction | Les LLM n'émettent pas de l'ASCII : normaliser avant tout motif ; et c'est le smoke test qui l'a révélé, pas la relecture du code |

## 4. Résultats mesurés

### Corpus (extraction du 2026-07-08, option A)

- **1 007 documents** = 528 articles en vigueur + 479 versions antérieures (depuis 2008)
- 5 thèmes couverts : Rupture conventionnelle, Licenciement, Contrat de travail (CDI, CDD), Durée du travail, Congés payés
- Longueurs des textes : **médiane 490 car.** · p95 1 638 · max 5 570 · **68 docs > 1 500 car.** (découpés aux alinéas)
- Contrôle qualité : 10 documents relus ✅ · archivage S3 : ☐ oui ☐ non

### Smoke tests API

- OAuth2 : ✅ jeton 54 caractères, renouvellement à −60 s
- Table des matières : ✅ 11 683 articles en vigueur collectés
- Historique d'un article : ✅ L3121-27 (2 versions), L1235-3 (3 versions, ordonnances 2017 visibles)

### Indexation (à compléter après `python -m src.index`)

| Mesure | Valeur |
|---|---|
| Chunks collection `code_travail` (en vigueur) | **555** (528 articles + parties des découpés) |
| Chunks collection `code_travail_historique` | **1 100** (1007 documents + parties) |
| Durée du 1er encodage (CPU) | _à remplir_ |
| Re-lancement : rechargement sans réencodage | ✅ vérifié (chaque script de test recharge les collections sans réencoder) |
| Contrôle qualité : 3 chunks relus (aucune phrase coupée) | ✅ vérifié |

### Validation de la collection historique (2026-07-08)

- **Isolation** : 0 version abrogée dans la collection courante ✅
- **Versions datées** : L1235-3 → 3 rédactions (2008 / ordonnances 2017 / 2018-auj.) ✅
- **Droit à la date D** : L1235-3 au 2017-12-01 → rédaction du 2017-09-24 ✅
- **Numéro vacant détecté** : L3121-27 au 2010-06-15 → « aucune version valide »
  (abrogé 2008-08-22, recréé 2016-08-10) ✅
- Bonus : L1237-11 (rupture conventionnelle) né le 2008-06-27 — cohérent avec
  la loi de modernisation du marché du travail ✅

### Évaluation du retrieval (à compléter après `python -m tests.eval_retrieval`)

| Question | Article attendu | Rang | Distance | OK ? |
|---|---|---|---|---|
| Durée légale de travail par semaine | L3121-27 | 1/5 | 0.232 | ✅ |
| Congés payés acquis par mois | L3141-3 | 2/5 | 0.257 | ✅ |
| Période d'essai maximale cadre CDI | L1221-19 | 1/5 | 0.226 | ✅ |
| Fonctionnement rupture conventionnelle | L1237-11 | 1/5 | 0.291 | ✅ |
| Indemnité licenciement sans cause réelle | L1235-3 *(article découpé)* | absent du top-5 | — | ❌ |

**Bilan : 4/5** (run du 2026-07-08, e5-base, k=5), puis **calibration k=8**.
Diagnostic mesuré : L1235-3 (1652 car., découpé en 2) au rang 8/20 à distance
0.279, dans un peloton ultra-serré (top-20 entre 0.247 et 0.296, entièrement
pertinent — que des articles indemnités/licenciement). Cause : vecteur de la
partie 1 dilué par le tableau de chiffres du barème + concurrence des voisins
courts (L1235-15, L1235-2, L1233-2...). Remède retenu : **N_CHUNKS 5 → 8**
(les voisins remontés se complètent dans une réponse juridique ; coût contexte
~2 800 tokens, acceptable). Marge nulle (rang exactement 8) : à re-vérifier
après toute ré-extraction du corpus. Alternatives écartées : seuil de découpe
à 1 800 car. (grignote la fenêtre de 512 tokens sans dé-diluer le tableau),
bge-m3 (2× plus lourd pour le même problème de dilution). Re-run éval : ✅ **5/5**
(L1235-3 au rang 8/8, distance 0.279 — marge nulle assumée et documentée).

### Génération — jalon 4 (smoke test du 2026-07-08, gpt-oss-20b, temp. 0, k=8)

| Comportement exigé | Résultat |
|---|---|
| Question dans le corpus → réponse sourcée | ✅ « 35 heures » + citation L3121-27, source vérifiée |
| Question conditionnelle → règle + réserves | ✅ synthèse de 3 articles (L3121-20, -22, -27) avec calcul 48−35=13 h et la limite moyenne de 44 h sur 12 semaines |
| Question hors corpus → refus | ✅ « Je ne trouve pas cette information dans ma base. » — aucune invention |
| Avertissement juridique | ✅ 3/3 (concaténé en code) |
| Citations vérifiées contre le contexte | ✅ 4 citations, 0 non vérifiée (après correction des tirets Unicode U+2011) |
| Date du corpus affichée | ✅ 3/3 |

Point de vigilance noté : la réponse conditionnelle ne mentionne ni le
contingent annuel ni « sauf accord collectif » — règle 4 du prompt à durcir
si le comportement se répète sur d'autres questions conditionnelles.
→ Résolu au run suivant (few-shot) : « sauf disposition contraire dans une
convention ou un accord collectif » présent.

**Run du 2026-07-09 (6 cas, décomposition + modérateur actifs)** :
- MULTIPLE réparée par le prompt few-shot : congés payés répondus (L3141-3
  cité avec extrait, plafond 30 jours) + rupture conventionnelle — 10 sources
  vérifiées ;
- FAMILIÈRE désormais reformulée (« me faire virer » → « licencier ») ;
- INJECTION bloquée par le modérateur (« Ignore tes instructions... ») ;
- 3 citations non vérifiées signalées (L1234-9, L2411-1, L2411-2) : des
  RENVOIS contenus dans le texte des chunks — cas d'usage de la « boucle de
  rattrapage » (lookup par numero + une re-génération), candidate jalon 6.

### Expériences envisagées (A/B sur le jeu d'évaluation)

- ☐ e5-base vs `BAAI/bge-m3` (fenêtre 8k → plus de découpe) — seulement si un article découpé fait échouer l'éval
- ☐ Chevauchement d'alinéas (`chevauchement=1`) — seulement si une partie `#pN` rate sa question

## 5. Plan de la session du 2026-07-09 (priorisé)

**A. Clôture des branches en cours (~30 min)**
1. ☐ Vérifier/merger la PR `feature/rag` → `dev` (8 commits)
2. ☐ PR `feature/moderator` → `dev` (4 commits, smoke test 6/6)

**B. La mesure d'abord (~1 h) — prérequis de tous les A/B qui suivent**
3. ☐ `tests/eval_rag.py` : noter les réponses sur ~12 questions annotées —
   justesse (article attendu ∈ sources), fidélité (ratio citations vérifiées),
   garanties (refus hors corpus, blocage injection, avertissement) → scores au §4

**C. Recherche hybride — levier n°3 du cours (~2 h)**
4. ☐ BM25 lexical (`rank_bm25`) sur les chunks + fusion **RRF** avec le
   classement vectoriel dans le retrieve ; cas garanti : « que dit L3121-1 ? »
   (lookup direct par métadonnée `numero`) ; **A/B avant/après** sur
   eval_retrieval + eval_rag
5. ☐ (si temps) HyDE en A/B — réponse hypothétique embeddée ; à mesurer
   contre la décomposition déjà en place

**D. Corpus complet du Code du travail — ⚠ décisions de coût**
6. ☐ Étendre à TOUT le code (11 683 articles) : **en vigueur SEULEMENT hors
   des 5 thèmes** (l'historisation intégrale ferait ~30 000 appels → quotas
   PISTE). Estimation : ~12 000 appels ≈ 1 h d'extraction + ~1 h d'encodage
   CPU. Après : re-calibrer k (L1235-3 à marge nulle), re-valider le refus
   hors corpus (plus difficile avec une base large)
   → grouper avec le **RAPPEL lien Légifrance** : ajouter `legiarti` à
   `build_document()` + métadonnées chunks → URL
   `https://www.legifrance.gouv.fr/codes/article_lc/<LEGIARTI>` — une seule
   ré-extraction pour les deux besoins
7. ☐ A/B modèles d'embedding sur le jeu d'éval : e5-base (référence) vs
   bge-m3 vs e5-large — ~1-2 h d'encodage CPU **par modèle** ; scores au §4

**E. v1.0.0 — le barème avant les bonus**
8. ☐ Jalon 5 : `main.py` (CLI interactive, accueil « une question à la
   fois »), README finalisé (Q1-Q5 alignées sur le réel : e5-base, k=8,
   historisation, décomposition), `COMPTE_RENDU.md` → **tag v1.0.0**
9. ☐ Déploiement (post-v1.0.0, hors barème) : AWS Lightsail/EC2 ≥ 2 Go RAM,
   modèle pré-téléchargé au build, `chroma_db/` sur disque persistant,
   corpus depuis S3 `corpus/latest/` — nécessite une interface web

**Améliorations jalon 6 restantes (candidates)** : boucle de rattrapage des
renvois (citations non vérifiées → lookup par `numero` → une re-génération),
questions datées (collection historique + dédoublonnage), mode comparaison.

## 6. Pistes « avec plus de temps » (pour le compte rendu)

- Généalogie pré-2008 des articles via le champ `liens` de l'API (l'ancien code est un autre texte)
- Étendre aux 3 thèmes restants du sujet (SMIC, représentation du personnel, harcèlement) — ~300 articles ; le code entier (11 683) écarté pour cause de quotas PISTE (~30 000 appels)
- Métadonnée `alineas: "4-6"` sur les parties d'articles découpés (citation à la juriste)
- MMR (diversité sémantique du top-k) si quasi-doublons hors versions
- Déploiement (conteneur ≥ 2 Go RAM, modèle pré-téléchargé au build, `chroma_db/` sur volume, corpus tiré de `s3://.../corpus/latest/`) + interface web
