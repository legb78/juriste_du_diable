"""Publie la base construite LOCALEMENT vers S3 — à lancer depuis ton poste.

Usage (base locale à jour + clés AWS dans .env) :
    python -m src.publier_base

Effet : le serveur, à son premier boot (ou après un reset de volume),
TÉLÉCHARGERA cette archive (~2 min) au lieu de reconstruire la base
(~25 min d'encodage sur son CPU). Ton laptop paie l'encodage une fois,
le serveur en profite.

Le marqueur de version est écrit avec l'archive : le serveur saura de quel
état de la source (SHA du dump legi-data) la base provient, et sa mise à
jour quotidienne continuera de fonctionner normalement par-dessus.
"""

from src import config, maj, storage


def main():
    # 1. Le marqueur : la version de la source dont cette base est issue.
    try:
        sha = maj.sha_distant()
        maj.ecrire_marqueur(sha)
        print(f"Marqueur de version écrit ({sha[:10]}).")
        print("  (hypothèse : ta base locale a été construite depuis le dump"
              " actuel — si elle date de plusieurs jours, relance d'abord"
              " python -m src.maj --force)")
    except Exception as erreur:
        print(f"[!] SHA de la source indisponible ({erreur}) : marqueur non "
              "écrit — le serveur revérifiera et reconstruira si besoin.")

    # 2. L'archive : chroma_db + data (sans le dump), vers S3.
    taille_mo = storage.publier_base()
    if taille_mo is None:
        raise SystemExit(
            "Clés AWS_* absentes du .env : impossible de publier sur S3."
        )
    print(
        f"Base publiée : s3://{config.AWS_S3_BUCKET}/{storage.CLE_BASE} "
        f"({taille_mo} Mo)"
    )


if __name__ == "__main__":
    main()
