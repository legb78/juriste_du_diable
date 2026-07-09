# Compte rendu — Assistant Code du travail (RAG)

## Décisions de conception marquantes

**Le corpus a connu trois architectures.** Partis de l'option A pure (API
Légifrance, OAuth2), nous avons étendu aux 11 683 articles du code — puis
découvert que le dump public SocialGouv/legi-data fournissait gratuitement la
masse courante *et la carte des versions* (mais pas leurs textes : vérifié sur
les données). Architecture finale : dump nettoyé pour l'indexé, API réservée
aux textes des rédactions passées, servis **à la volée** avec cache — « on
indexe ce qu'on cherche par le sens, on va chercher à la demande ce qu'on sait
désigner par un identifiant ».

**Les garanties vivent dans le code, pas dans le prompt.** Avertissement
juridique concaténé par `rag.py` (100 % des réponses), citations extraites de
la réponse puis **vérifiées contre les métadonnées des chunks fournis**,
sources reconstruites côté code avec lien vers le texte officiel. Le LLM
propose, le code dispose.

**Tout changement est arbitré par la mesure.** Deux jeux d'évaluation
versionnés (retrieval seul, puis bout-en-bout : justesse / fidélité /
garanties) forment une ligne de base que chaque évolution doit égaler. C'est
ainsi que la recherche hybride (BM25 + fusion RRF + garantie sur les numéros)
a été adoptée — 6/6 contre 5/6 — et que HyDE a été écarté (redondant avec
notre reformulation LLM et l'entraînement asymétrique d'e5).

## Difficultés rencontrées (et leçons)

- **403 après un OAuth réussi** : la souscription PISTE manquait — le smoke
  test « par étages » a localisé le maillon en 30 secondes.
- **Plages thématiques du sujet imbriquées** (Contrat ⊃ Licenciement ⊃ Rupture
  conventionnelle) : détecté parce que 36+37+455 = 528 ; leçon — vérifier les
  décomptes, pas seulement l'absence d'erreur.
- **Numéros d'articles réattribués** (le L3121-27 de 2008 n'a rien à voir avec
  celui de 2016) : a validé l'isolation du droit abrogé hors de la base.
- **Le LLM n'émet pas de l'ASCII** : citations en tirets insécables U+2011,
  invisibles pour notre regex — sources vides malgré des citations justes.
- **Le passage à l'échelle casse en silence** : à 12 525 chunks, le vectoriel
  pur a perdu l'éval (4/6) — l'hybride l'a sauvée (6/6) ; le plafond
  d'insertion ChromaDB (5 461) n'est apparu qu'à cette taille ; et le refus à
  tort d'une question familière (L1234-1 pourtant au rang 1) reste notre cas
  d'échec documenté : 8/9 en justesse, diagnostiqué en trois sondes
  (reformulation ✓, retrieval ✓, prompt trop timide).
- **Quotas** : Groq 8 000 tokens/min (retry + lissage), PISTE (pauses,
  checkpoints, tolérance aux pannes par article).

## Ce que nous ferions avec plus de temps

La **boucle de rattrapage des renvois** (les citations « non vérifiées » sont
presque toujours des renvois présents dans le texte des chunks : un lookup par
numéro + une re-génération les résoudrait — cible chiffrée : fidélité 9/9).
Les **questions datées** en bout-en-bout (la mécanique `histoire.py` — carte,
API ciblée, cache — est prête, il reste le routage). La **mise à jour
incrémentale** (upsert des seuls articles modifiés au lieu d'une
reconstruction, avec rebuild périodique contre la fragmentation HNSW).
L'**évaluation du fond juridique** par grille humaine en binôme, qu'aucune
métrique automatique ne remplace honnêtement. Et la **généalogie pré-2008**
des articles (l'ancien code est un autre texte pour Légifrance).
