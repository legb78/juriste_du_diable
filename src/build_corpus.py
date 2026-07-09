"""Point d'entrée : construit data/code_travail.json depuis l'API Légifrance.

Usage (une fois, ou pour rafraîchir le corpus) :
    python -m src.build_corpus

Déroulé :
1. table des matières du Code du travail (UN seul appel API) ;
2. parcours de l'arbre : on retient les articles en vigueur dont le numéro
   tombe dans une des plages de config.THEMES ;
3. récupération du texte de chaque article retenu ET de toutes ses versions
   successives (un appel par version, avec une pause pour les quotas PISTE) ;
4. nettoyage (balises HTML, entités, espaces) et écriture du JSON ;
5. sauvegarde optionnelle sur Scaleway Object Storage ;
6. contrôle qualité exigé par le sujet : dix documents au hasard à relire.
"""

import html
import json
import random
import re
import sys
import time
from datetime import date, datetime, timezone

from src import config
from src.legifrance import LegifranceClient
from src.storage import upload_corpus

# Pause entre deux appels getArticle (quotas PISTE).
PAUSE_S = 0.2


def parse_num(num):
    """Décompose un numéro d'article en tuple comparable.

    "L3121-27"   -> ("L", (3121, 27))
    "L1237-11-1" -> ("L", (1237, 11, 1))
    Renvoie None si le numéro n'a pas la forme attendue.
    """
    m = re.fullmatch(r"([LRD])\.?\s*([\d-]+)", (num or "").strip())
    if not m:
        return None
    try:
        composantes = tuple(int(p) for p in m.group(2).split("-") if p)
    except ValueError:
        return None
    return (m.group(1), composantes)


def in_range(num, debut, fin):
    """Vrai si `num` tombe dans la plage [debut, fin].

    La comparaison se fait sur les tuples numériques : (3121, 5) est entre
    (3121, 1) et (3121, 36). Un sous-article comme L1237-19-1 est rattaché à
    L1237-19, donc inclus si L1237-19 est la borne haute (comparaison sur le
    préfixe du tuple).
    """
    p, pd, pf = parse_num(num), parse_num(debut), parse_num(fin)
    if p is None or p[0] != pd[0]:
        return False
    return pd[1] <= p[1] and p[1][: len(pf[1])] <= pf[1]


def walk_sections(noeud, articles, chemin=()):
    """Parcourt récursivement l'arbre de la table des matières.

    Collecte, pour chaque article en vigueur : son identifiant LEGIARTI, son
    numéro, et le chemin des intitulés de sections qui y mènent (utile comme
    titre du document).
    """
    titre = noeud.get("title") or noeud.get("titre") or ""
    nouveau_chemin = chemin + ((titre,) if titre else ())
    for art in noeud.get("articles") or []:
        etat = (art.get("etat") or "").upper()
        if etat.startswith("VIGUEUR") or not etat:
            articles.append(
                {
                    "legiarti": art.get("id"),
                    "num": art.get("num"),
                    "chemin": " > ".join(nouveau_chemin),
                }
            )
    for enfant in noeud.get("sections") or []:
        walk_sections(enfant, articles, nouveau_chemin)


def date_iso(ts_ms):
    """Convertit un timestamp Légifrance (millisecondes) en date ISO.

    Légifrance date les versions d'articles en millisecondes Unix ; on stocke
    une date lisible. Renvoie None si le champ est absent ou inexploitable.
    """
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def build_document(num, art, texte, debut_ms, fin_ms, en_vigueur, date_extraction,
                   legiarti):
    """Assemble un document du corpus : UNE version d'UN article.

    Les versions antérieures reçoivent un id suffixé par leur date d'entrée
    en vigueur ("L3121-27@2008-05-01") ; la version courante garde le numéro
    nu, pour rester l'identifiant de citation naturel. L'identifiant LEGIARTI
    de la version est conservé : il permet le lien direct vers Légifrance
    (https://www.legifrance.gouv.fr/codes/article_lc/<LEGIARTI>).
    """
    depuis = date_iso(debut_ms)
    jusqua = date_iso(fin_ms)
    # Légifrance code les versions encore ouvertes avec une dateFin lointaine
    # (année 2999) : on la traduit en None (= toujours en vigueur).
    if jusqua and jusqua >= "2999":
        jusqua = None
    return {
        "id": num if en_vigueur else f"{num}@{depuis or 'inconnue'}",
        "numero": num,
        "legiarti": legiarti,
        "titre": art["chemin"],
        "texte": texte,
        "section": art["section"],
        "source": "Légifrance — Code du travail",
        "date_extraction": date_extraction,
        "version_depuis": depuis,
        "version_jusqua": jusqua,
        "en_vigueur": en_vigueur,
    }


def section_par_defaut(chemin):
    """Thème de repli pour les articles hors des 5 plages : l'intitulé du
    Livre (le niveau « sujet » de la hiérarchie), sinon celui de la Partie."""
    composantes = [c.strip() for c in chemin.split(" > ")]
    for c in composantes:
        if c.startswith("Livre"):
            return c
    for c in composantes:
        if "partie" in c.lower():
            return c
    return "Code du travail"


def ecrire_corpus(documents):
    """Écrit le JSON (aussi utilisé comme point de sauvegarde incrémental :
    un run de 2-3 h ne doit jamais être perdu sur un incident)."""
    config.CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)


def clean_text(brut):
    """Nettoie le texte d'un article : balises HTML, entités, espaces multiples."""
    texte = html.unescape(brut)
    texte = re.sub(r"<br\s*/?>|</p>", "\n", texte, flags=re.I)
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = re.sub(r"[ \t ]+", " ", texte)  #   : espace insécable HTML
    texte = re.sub(r"\s*\n\s*", "\n", texte)
    return texte.strip()


def main():
    aujourd_hui = date.today().isoformat()
    client = LegifranceClient()

    print("Récupération de la table des matières du Code du travail...")
    toc = client.table_matieres_code_travail(aujourd_hui)

    tous = []
    walk_sections(toc, tous)
    print(f"{len(tous)} articles en vigueur trouvés dans la table des matières.")

    # Filtrage par thème. Les plages se chevauchent : le dict indexé par numéro
    # garantit qu'un article n'est retenu qu'une fois, avec le PREMIER thème
    # qui matche — config.THEMES est ordonné du plus spécifique au plus général.
    # Le décompte affiché est celui des articles réellement attribués au thème.
    retenus = {}
    for theme, (debut, fin) in config.THEMES.items():
        n = 0
        for art in tous:
            if art["legiarti"] and art["num"] and in_range(art["num"], debut, fin):
                if art["num"] not in retenus:
                    retenus[art["num"]] = {**art, "section": theme}
                    n += 1
        print(f"  {theme} : {n} articles")

    if not retenus:
        sys.exit(
            "Aucun article retenu : la structure de la table des matières "
            "diffère de celle attendue. Inspecter la réponse de l'API."
        )

    # Liste de travail : les articles des thèmes (avec historisation), puis —
    # en mode corpus complet — tout le reste du code (version courante seule,
    # thème de repli = l'intitulé du Livre).
    travail = [{**art, "num": num, "historiser": True}
               for num, art in sorted(retenus.items())]
    if config.CORPUS_COMPLET:
        for art in tous:
            if art["legiarti"] and art["num"] and art["num"] not in retenus:
                travail.append(
                    {
                        **art,
                        "num": art["num"],
                        "section": section_par_defaut(art["chemin"]),
                        "historiser": False,
                    }
                )
        print(f"\nMode corpus complet : {len(travail)} articles au total "
              f"({len(retenus)} thématisés avec historique, "
              f"{len(travail) - len(retenus)} hors thèmes en version courante).")

    # Récupération des textes. Un run complet dure 2-3 h : chaque article est
    # protégé individuellement (une erreur = un article ignoré, pas un crash)
    # et le JSON est sauvegardé tous les 500 articles.
    print(f"\nRécupération du texte de {len(travail)} articles...")
    documents = []
    nb_anciennes, nb_echecs = 0, 0
    for i, art in enumerate(travail, 1):
        num = art["num"]
        try:
            detail = client.get_article(art["legiarti"])
            texte = clean_text(detail.get("texteHtml") or detail.get("texte") or "")
            if texte:
                documents.append(
                    build_document(
                        num, art, texte,
                        detail.get("dateDebut"), detail.get("dateFin"),
                        True, aujourd_hui, art["legiarti"],
                    )
                )

            # Versions antérieures : uniquement pour les articles thématisés.
            if art["historiser"]:
                for version in detail.get("articleVersions") or []:
                    version_id = version.get("id")
                    if not version_id or version_id == art["legiarti"]:
                        continue  # version courante : déjà traitée
                    time.sleep(PAUSE_S)
                    vdetail = client.get_article(version_id)
                    vtexte = clean_text(
                        vdetail.get("texteHtml") or vdetail.get("texte") or ""
                    )
                    if not vtexte:
                        continue  # certaines versions techniques sont vides
                    documents.append(
                        build_document(
                            num, art, vtexte,
                            vdetail.get("dateDebut"), vdetail.get("dateFin"),
                            False, aujourd_hui, version_id,
                        )
                    )
                    nb_anciennes += 1
        except Exception as erreur:  # un article ne doit jamais tuer le run
            nb_echecs += 1
            print(f"  [!] {num} : {erreur}")

        if i % 100 == 0:
            print(f"  {i}/{len(travail)} articles ({len(documents)} documents)...")
        if i % 500 == 0:
            ecrire_corpus(documents)  # point de sauvegarde
        time.sleep(PAUSE_S)

    if nb_echecs:
        print(f"\n[!] {nb_echecs} articles en échec (réseau/API), ignorés.")

    # Dédoublonnage par id (deux versions partageant la même date d'entrée
    # en vigueur produiraient le même id, que ChromaDB refuserait).
    uniques = {}
    for doc in documents:
        uniques.setdefault(doc["id"], doc)
    documents = list(uniques.values())

    ecrire_corpus(documents)
    en_vigueur = sum(1 for d in documents if d["en_vigueur"])
    print(
        f"\n{len(documents)} documents écrits dans {config.CORPUS_PATH} "
        f"({en_vigueur} versions en vigueur + {len(documents) - en_vigueur} antérieures)"
    )

    # Sauvegarde optionnelle sur Scaleway Object Storage (clé datée + latest).
    cles = upload_corpus(config.CORPUS_PATH, aujourd_hui)
    if cles:
        for cle in cles:
            print(f"Corpus envoyé : s3://{config.AWS_S3_BUCKET}/{cle}")
    else:
        print("Stockage objet non configuré (AWS_* absents) : envoi S3 ignoré.")

    # Contrôle qualité exigé par le sujet : dix documents au hasard, à relire.
    print("\n--- Contrôle qualité : 10 documents au hasard ---")
    for doc in random.sample(documents, min(10, len(documents))):
        vigueur = "en vigueur" if doc["en_vigueur"] else f"abrogée le {doc['version_jusqua']}"
        print(f"\n[{doc['numero']}] {doc['section']} — version {doc['version_depuis']} ({vigueur})")
        extrait = doc["texte"][:400]
        print(extrait + ("..." if len(doc["texte"]) > 400 else ""))


if __name__ == "__main__":
    main()
