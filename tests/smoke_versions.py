"""Test du téléchargement de l'HISTORIQUE complet d'un article de loi.

Usage :
    python -m tests.smoke_versions              # article par défaut : L3121-27
    python -m tests.smoke_versions L1237-11     # n'importe quel article du corpus

Valide, sur UN article, la mécanique d'historisation de build_corpus :
table des matières -> LEGIARTI courant -> articleVersions -> texte de chaque
rédaction successive avec ses dates de validité (version_depuis/jusqua).
"""

import sys
import time
from datetime import date

from src.build_corpus import PAUSE_S, clean_text, date_iso, walk_sections
from src.legifrance import LegifranceClient


def main():
    numero = sys.argv[1] if len(sys.argv) > 1 else "L3121-27"
    client = LegifranceClient()

    # 1. Retrouver l'identifiant LEGIARTI courant via la table des matières.
    print(f"Recherche de {numero} dans la table des matières...")
    toc = client.table_matieres_code_travail(date.today().isoformat())
    articles = []
    walk_sections(toc, articles)
    art = next((a for a in articles if a["num"] == numero), None)
    if art is None:
        sys.exit(f"{numero} introuvable (ou plus en vigueur) dans le Code du travail.")
    print(f"Trouvé : {art['legiarti']}")
    print(f"   {art['chemin']}\n")

    # 2. La version courante porte la liste de toutes les versions.
    detail = client.get_article(art["legiarti"])
    versions = detail.get("articleVersions") or []
    print(f"{len(versions)} version(s) recensée(s) par Légifrance pour {numero} :\n")

    # 3. Télécharger chaque rédaction, de la plus ancienne à la plus récente.
    for v in sorted(versions, key=lambda v: v.get("dateDebut") or 0):
        version_id = v.get("id")
        if not version_id:
            continue
        vdetail = client.get_article(version_id)
        texte = clean_text(vdetail.get("texteHtml") or vdetail.get("texte") or "")
        debut = date_iso(vdetail.get("dateDebut")) or "?"
        fin = date_iso(vdetail.get("dateFin"))
        if fin and fin >= "2999":
            fin = None  # convention Légifrance : 2999 = pas de fin = en vigueur
        periode = f"du {debut} au {fin}" if fin else f"depuis le {debut} (EN VIGUEUR)"
        marque = "  <-- version courante (id de la table des matières)" \
            if version_id == art["legiarti"] else ""
        print(f"--- {numero} | {periode} | état : {vdetail.get('etat', '?')}{marque}")
        if texte:
            print(f"    {texte[:220]}{'...' if len(texte) > 220 else ''}")
        else:
            print("    (texte vide — version technique, ignorée par build_corpus)")
        print()
        time.sleep(PAUSE_S)


if __name__ == "__main__":
    main()
