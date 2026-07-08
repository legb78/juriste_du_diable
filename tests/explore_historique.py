"""Tests exploratoires de la collection HISTORIQUE (versions d'articles).

Usage (la base doit exister) :
    python -m tests.explore_historique                      # L1235-3 au 2017-12-01
    python -m tests.explore_historique L3121-27 2010-06-15  # article et date au choix

Trois vérifications, chacune une promesse de l'architecture à deux collections :

1. ISOLATION — la collection courante ne contient AUCUNE version abrogée
   (une réponse ordinaire ne peut jamais citer du droit mort) ;
2. COMPLÉTUDE — les versions successives d'un article sont présentes dans
   l'historique, datées et bornées ;
3. LE DROIT À LA DATE D — sélection de la version valide à une date donnée.
   Les dates ISO se comparent en texte (ordre lexicographique = ordre
   chronologique) : c'est la brique des questions datées du jalon 6.
"""

import sys

from src import config
from src.vectordb import VectorDB


def version_valide_au(metas, date_iso):
    """La version dont l'intervalle [version_depuis, version_jusqua) contient
    date_iso ; None si l'article n'existait pas (ou plus) à cette date."""
    for meta in metas:
        debut = meta["version_depuis"] or "0000"
        fin = meta["version_jusqua"] or "9999"
        if debut <= date_iso < fin:
            return meta
    return None


def main():
    numero = sys.argv[1] if len(sys.argv) > 1 else "L1235-3"
    date_test = sys.argv[2] if len(sys.argv) > 2 else "2017-12-01"

    db_courante = VectorDB(config, config.COLLECTION_NAME)
    db_hist = VectorDB(config, config.COLLECTION_HISTORIQUE)
    print(
        f"Chunks : courante = {db_courante.count()} | "
        f"historique = {db_hist.count()}\n"
    )

    # --- 1. Isolation de la collection courante ---
    abroges = db_courante.collection.get(where={"en_vigueur": False}, limit=5)
    n_abroges = len(abroges["ids"])
    verdict = "OK (isolation respectée)" if n_abroges == 0 else "PROBLEME !"
    print(f"1) Versions abrogées dans la collection COURANTE : {n_abroges} — {verdict}\n")

    # --- 2. Les versions de l'article dans l'historique ---
    # .get() filtre par métadonnées sans classement sémantique (pas de question
    # ici). On ne garde que les parties 1/N pour la lisibilité.
    resultat = db_hist.collection.get(where={"numero": numero})
    metas = [m for m in resultat["metadatas"] if m["partie"].startswith("1/")]
    metas.sort(key=lambda m: m["version_depuis"])
    print(f"2) Versions de {numero} dans l'HISTORIQUE :")
    if not metas:
        print("   aucune — numéro absent du corpus ?")
        return
    for m in metas:
        fin = m["version_jusqua"] or "aujourd'hui (en vigueur)"
        print(f"   rédaction du {m['version_depuis']} au {fin}")

    # --- 3. Le droit tel qu'à la date demandée ---
    valide = version_valide_au(metas, date_test)
    print(f"\n3) Version de {numero} applicable au {date_test} :")
    if valide is None:
        print(
            "   aucune version valide à cette date — l'article n'existait pas"
            " (ou le numéro était vacant, cf. réattributions de numéros)."
        )
    else:
        fin = valide["version_jusqua"] or "en vigueur"
        statut = "encore en vigueur aujourd'hui" if not valide["version_jusqua"] \
            else f"abrogée/modifiée le {fin}"
        print(f"   rédaction entrée en vigueur le {valide['version_depuis']} ({statut})")


if __name__ == "__main__":
    main()
