"""Point d'entrée : construit data/code_travail.json en SOURCE MIXTE.

Usage :
    python -m src.build_corpus_legidata

Architecture (décision du 2026-07-09, remplace le tout-API de build_corpus) :

- la MASSE COURANTE (~11 700 articles en vigueur) vient du dump JSON quotidien
  de SocialGouv/legi-data (56 Mo, tout le code consolidé, mêmes identifiants
  LEGI que l'API) : un téléchargement, ZÉRO appel API ;
- l'HISTORIQUE des 5 thèmes vient de l'API Légifrance : legi-data fournit la
  carte des versions (`articleVersions` : id, dates, état) mais PAS leurs
  textes — seuls ~500 appels getArticle restent nécessaires (~4 min) ;
- même schéma de sortie que build_corpus.py : tout l'aval (chunking,
  indexation, RAG) est inchangé. build_corpus.py reste utilisable (tout-API).
"""

import json
import random
import sys
import time
from datetime import date

import requests

from src import config
from src.build_corpus import (
    PAUSE_S,
    build_document,
    clean_text,
    date_iso,
    ecrire_corpus,
    in_range,
    section_par_defaut,
)
from src.legifrance import LegifranceClient
from src.storage import upload_corpus

URL_LEGIDATA = (
    "https://raw.githubusercontent.com/SocialGouv/legi-data/"
    "master/data/LEGITEXT000006072050.json"
)
CACHE_LEGIDATA = config.PROJECT_ROOT / "data" / "legidata_code_travail.json"


def charger_dump():
    """Télécharge le dump legi-data (une fois — cache local ensuite)."""
    if CACHE_LEGIDATA.exists():
        print(f"Dump legi-data déjà en cache : {CACHE_LEGIDATA.name}")
    else:
        print("Téléchargement du dump legi-data (~56 Mo)...")
        CACHE_LEGIDATA.parent.mkdir(parents=True, exist_ok=True)
        reponse = requests.get(URL_LEGIDATA, timeout=300)
        reponse.raise_for_status()
        CACHE_LEGIDATA.write_bytes(reponse.content)
    with open(CACHE_LEGIDATA, encoding="utf-8") as f:
        return json.load(f)


def collecter_articles(noeud, chemin, articles):
    """Parcourt l'arbre legi-data (code > sections > articles).

    Le chemin hiérarchique est reconstruit depuis les intitulés (`title`)
    des nœuds traversés — même rôle que walk_sections côté API.
    """
    data = noeud.get("data") or {}
    if noeud.get("type") == "article":
        if (data.get("etat") or "").upper().startswith("VIGUEUR"):
            articles.append({"data": data, "chemin": " > ".join(chemin)})
        return
    titre = data.get("title") or ""
    nouveau_chemin = chemin + ((titre,) if titre else ())
    for enfant in noeud.get("children") or []:
        collecter_articles(enfant, nouveau_chemin, articles)


def main():
    aujourd_hui = date.today().isoformat()

    # --- 1. La masse courante, depuis le dump ---
    arbre = charger_dump()
    articles = []
    collecter_articles(arbre, (), articles)
    print(f"{len(articles)} articles en vigueur dans le dump legi-data.")

    # Attribution des thèmes : mêmes règles que build_corpus (plages imbriquées,
    # premier thème qui matche — config.THEMES va du plus spécifique au général).
    retenus = {}
    for theme, (debut, fin) in config.THEMES.items():
        n = 0
        for art in articles:
            num = art["data"].get("num")
            if num and num not in retenus and in_range(num, debut, fin):
                retenus[num] = {**art, "section": theme}
                n += 1
        print(f"  {theme} : {n} articles")
    if not retenus:
        sys.exit("Aucun article thématisé : structure du dump inattendue.")

    documents = []
    for art in articles:
        data = art["data"]
        num = data.get("num")
        if not num:
            continue
        entree = retenus.get(num)
        if entree is None and not config.CORPUS_COMPLET:
            continue  # mode 5 thèmes seulement
        section = entree["section"] if entree else section_par_defaut(art["chemin"])
        texte = clean_text(data.get("texteHtml") or data.get("texte") or "")
        if not texte:
            continue
        documents.append(
            build_document(
                num,
                {"chemin": art["chemin"], "section": section,
                 "historiser": config.HISTORISATION_COMPLETE
                 or entree is not None},
                texte,
                data.get("dateDebut"), data.get("dateFin"),
                True, aujourd_hui, data.get("id"),
            )
        )
    print(f"\n{len(documents)} versions courantes construites depuis le dump "
          "(0 appel API).")

    # --- 2. La CARTE des versions de tous les articles (depuis le dump) ---
    # C'est elle qui permet la récupération À LA VOLÉE (src/histoire.py) :
    # pour chaque article, la liste de ses rédactions (id, dates, état) —
    # sans les textes, qui seront demandés à l'API au besoin, avec cache.
    def borne_fin(ts_ms):
        fin = date_iso(ts_ms)
        return None if (fin and fin >= "2999") else fin

    carte = {}
    for art in articles:
        data = art["data"]
        num = data.get("num")
        if not num:
            continue
        carte[num] = {
            "courant": data.get("id"),
            "versions": [
                {
                    "id": v.get("id"),
                    "etat": v.get("etat"),
                    "debut": date_iso(v.get("dateDebut")),
                    "fin": borne_fin(v.get("dateFin")),
                }
                for v in (data.get("articleVersions") or [])
                if v.get("id")
            ],
        }
    config.VERSIONS_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.VERSIONS_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(carte, f, ensure_ascii=False)
    print(f"Carte des versions écrite : {config.VERSIONS_MAP_PATH.name} "
          f"({len(carte)} articles, 0 appel API).")

    # --- 3. Les textes des versions antérieures ---
    # Mode « à la volée » : AUCUN pré-téléchargement — src/histoire.py ira
    # chercher chaque texte à la demande. Mode alternatif : tout pré-charger.
    cibles = []
    if config.HISTORIQUE_A_LA_VOLEE:
        print(
            "Historique à la volée : aucun texte ancien pré-téléchargé — "
            "src/histoire.py les demandera à l'API au besoin (cache disque)."
        )
    else:
        for art in articles:
            num = art["data"].get("num")
            if not num:
                continue
            entree = retenus.get(num)
            if not (config.HISTORISATION_COMPLETE or entree):
                continue
            cibles.append(
                {
                    "num": num,
                    "data": art["data"],
                    "chemin": art["chemin"],
                    "section": entree["section"] if entree
                    else section_par_defaut(art["chemin"]),
                }
            )

    # La facture exacte, annoncée AVANT de payer (Ctrl+C possible : les
    # versions courantes sont déjà construites et seront sauvegardées).
    if cibles:
        total_versions = sum(
            max(0, len(c["data"].get("articleVersions") or []) - 1) for c in cibles
        )
        heures = total_versions * 0.7 / 3600
        print(
            f"\n{total_versions} versions antérieures à récupérer via l'API "
            f"(~{heures:.1f} h estimées, checkpoint tous les 500)..."
        )

        client = LegifranceClient()
    nb_anciennes, nb_echecs, traitees = 0, 0, 0
    for c in cibles:
        data = c["data"]
        for version in data.get("articleVersions") or []:
            version_id = version.get("id")
            if not version_id or version_id == data.get("id"):
                continue  # version courante : déjà prise depuis le dump
            try:
                vdetail = client.get_article(version_id)
                vtexte = clean_text(
                    vdetail.get("texteHtml") or vdetail.get("texte") or ""
                )
                if vtexte:
                    documents.append(
                        build_document(
                            c["num"],
                            {"chemin": c["chemin"], "section": c["section"],
                             "historiser": True},
                            vtexte,
                            vdetail.get("dateDebut"), vdetail.get("dateFin"),
                            False, aujourd_hui, version_id,
                        )
                    )
                    nb_anciennes += 1
            except Exception as erreur:
                nb_echecs += 1
                print(f"  [!] {c['num']} ({version_id}) : {erreur}")
            time.sleep(PAUSE_S)
            traitees += 1
            if traitees % 100 == 0:
                print(f"  {traitees}/{total_versions} versions...")
            if traitees % 500 == 0:
                ecrire_corpus(documents)  # point de sauvegarde
    if nb_echecs:
        print(f"[!] {nb_echecs} versions en échec, ignorées.")

    # Dédoublonnage par id (sécurité) puis écriture.
    uniques = {}
    for doc in documents:
        uniques.setdefault(doc["id"], doc)
    documents = list(uniques.values())

    ecrire_corpus(documents)
    en_vigueur = sum(1 for d in documents if d["en_vigueur"])
    print(
        f"\n{len(documents)} documents écrits dans {config.CORPUS_PATH} "
        f"({en_vigueur} en vigueur + {len(documents) - en_vigueur} antérieures)"
    )

    cles = upload_corpus(config.CORPUS_PATH, aujourd_hui)
    if cles:
        for cle in cles:
            print(f"Corpus envoyé : s3://{config.AWS_S3_BUCKET}/{cle}")
    else:
        print("Stockage objet non configuré (AWS_* absents) : envoi S3 ignoré.")

    print("\n--- Contrôle qualité : 10 documents au hasard ---")
    for doc in random.sample(documents, min(10, len(documents))):
        vigueur = "en vigueur" if doc["en_vigueur"] \
            else f"abrogée le {doc['version_jusqua']}"
        print(f"\n[{doc['numero']}] {doc['section']} — version "
              f"{doc['version_depuis']} ({vigueur})")
        extrait = doc["texte"][:300]
        print(extrait + ("..." if len(doc["texte"]) > 300 else ""))


if __name__ == "__main__":
    main()
