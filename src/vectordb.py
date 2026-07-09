"""Base vectorielle persistante (ChromaDB + sentence-transformers).

Une instance de `VectorDB` gère UNE collection. Trois comportements, choisis
dans le constructeur :

  - la collection existe déjà sur le disque -> elle est RECHARGÉE (sans
    réencoder — une réindexation à chaque lancement est éliminatoire) ;
  - sinon, si des données sont fournies     -> elle est CRÉÉE et indexée ;
  - sinon                                    -> erreur explicite.

Deux invariants non négociables :

  - le nom du modèle d'embedding est gravé dans les métadonnées de la
    collection à la création, et relu au rechargement — jamais celui,
    peut-être différent, de la config du jour. Sinon on pourrait encoder les
    documents avec un modèle A et les questions avec un modèle B : vecteurs
    incomparables, retrieval aberrant, sans la moindre erreur pour le signaler ;
  - documents ET questions passent par la même méthode `_encode`, qui applique
    les préfixes de la famille e5 : "passage: " pour les documents, "query: "
    pour les questions. C'est ce qui matérialise la recherche ASYMÉTRIQUE
    (question familière -> texte de loi) pour laquelle e5 est entraîné.
"""

import re

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# Numéro d'article dans une question (« que dit L3121-1 ? », « L. 3121-27 »).
MOTIF_NUM_ARTICLE = re.compile(r"[LRD]\.?\s?\d{4}(?:-\d+)+", re.IGNORECASE)


def tokeniser(texte):
    """Tokenisation lexicale simple pour BM25 : minuscules, tirets Unicode
    normalisés, et les numéros d'articles (« l3121-27 ») conservés comme UN
    seul token — c'est ce qui rend la recherche lexicale imbattable sur eux.
    """
    texte = re.sub(r"[‐‑‒–—−]", "-", texte.lower())
    return re.findall(r"[a-zà-ÿ0-9]+(?:-[0-9]+)+|[a-zà-ÿ0-9]+", texte)


class VectorDB:
    """Encode des chunks, les persiste dans ChromaDB, retrouve les k plus proches."""

    def __init__(self, config, nom_collection, donnees=None):
        """`donnees` : triplet (ids, documents, metadatas) pour créer la
        collection ; None pour recharger une collection existante.
        """
        self.config = config
        self.nom = nom_collection

        # Client persistant : les données survivent à l'arrêt du programme.
        self.client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
        existantes = [c.name for c in self.client.list_collections()]

        if nom_collection in existantes:
            # --- Cas 1 : RECHARGER (aucun réencodage) ---
            self.collection = self.client.get_collection(nom_collection)
            nom_modele = self.collection.metadata["embedding_model"]
            self.model = SentenceTransformer(nom_modele)

        elif donnees is not None:
            # --- Cas 2 : CRÉER et indexer ---
            self.model = SentenceTransformer(config.EMBEDDING_MODEL)
            self.collection = self.client.create_collection(
                name=nom_collection,
                # Le modèle est gravé dans la collection elle-même.
                metadata={"embedding_model": config.EMBEDDING_MODEL},
            )
            self._index(*donnees)

        else:
            # --- Cas 3 : impossible de démarrer ---
            raise ValueError(
                f"La collection « {nom_collection} » n'existe pas dans "
                f"{config.CHROMA_PATH} et aucune donnée n'est fournie. "
                "Lancez d'abord :  python -m src.index"
            )

    def _encode(self, textes, is_query=False):
        """Encode des textes en vecteurs normalisés, avec le préfixe e5 adapté.

        `is_query=False` -> "passage: " (documents à l'indexation) ;
        `is_query=True`  -> "query: "   (questions au retrieval).
        La normalisation rend le produit scalaire équivalent à la similarité
        cosinus. TOUT passe par cette méthode : un seul espace vectoriel.
        """
        prefixe = (
            self.config.E5_QUERY_PREFIX if is_query else self.config.E5_PASSAGE_PREFIX
        )
        return self.model.encode(
            [prefixe + t for t in textes],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=not is_query,
        ).tolist()

    def _index(self, ids, documents, metadatas):
        """Encode tous les chunks et les insère PAR LOTS dans la collection.

        ChromaDB plafonne un add() à ~5461 entrées : au-delà (corpus complet,
        12 500+ chunks), l'insertion doit être découpée.
        """
        embeddings = self._encode(documents)
        LOT = 5000
        for debut in range(0, len(ids), LOT):
            fin = debut + LOT
            self.collection.add(
                ids=ids[debut:fin],
                documents=documents[debut:fin],
                embeddings=embeddings[debut:fin],
                metadatas=metadatas[debut:fin],
            )

    def retrieve(self, question, n=None, where=None):
        """Les `n` chunks les plus proches de `question`, du plus au moins
        pertinent : liste de dicts {"text", "metadata", "distance"}.

        `where` : filtre ChromaDB optionnel sur les métadonnées (utilisé par
        les requêtes datées sur la collection historique).
        """
        if n is None:
            n = self.config.N_CHUNKS

        query_embedding = self._encode([question], is_query=True)
        resultats = self.collection.query(
            query_embeddings=query_embedding,
            n_results=n,
            where=where,
        )

        # ChromaDB renvoie des listes de listes (une par requête) : on prend [0].
        return [
            {"id": cid, "text": doc, "metadata": meta, "distance": dist}
            for cid, doc, meta, dist in zip(
                resultats["ids"][0],
                resultats["documents"][0],
                resultats["metadatas"][0],
                resultats["distances"][0],
            )
        ]

    def _charger_bm25(self):
        """Construit (paresseusement, une fois) l'index lexical BM25 sur tous
        les chunks de la collection. ~1 s pour quelques centaines de chunks."""
        if getattr(self, "_bm25", None) is None:
            tout = self.collection.get()
            self._bm25_ids = tout["ids"]
            self._bm25_docs = tout["documents"]
            self._bm25_metas = tout["metadatas"]
            self._bm25 = BM25Okapi([tokeniser(d) for d in tout["documents"]])

    def retrieve_hybride(self, question, n=None):
        """Recherche hybride : fusion RRF du classement vectoriel et du
        classement lexical BM25, plus une GARANTIE : tout numéro d'article
        mentionné dans la question fait remonter ses chunks en tête, quels
        que soient les scores (« que dit L3121-1 ? » marche à coup sûr).

        RRF (Reciprocal Rank Fusion) : score(chunk) = Σ 1/(K + rang) sur
        chaque classement où il apparaît (K=60, valeur standard). Robuste :
        fusionne des RANGS, pas des scores hétérogènes (distance cosinus vs
        score BM25, incomparables entre eux).

        Compatibilité : le champ « distance » des résultats est une
        pseudo-distance (l'opposé du score RRF ; -1.0 pour les
        correspondances directes par numéro) — le tri croissant de
        rag._retrieve_multi reste valide.
        """
        if n is None:
            n = self.config.N_CHUNKS
        K = 60

        # 1. Classement vectoriel élargi (3n pour donner du grain à la fusion).
        rrf, entrees = {}, {}
        for rang, chunk in enumerate(self.retrieve(question, n=3 * n), 1):
            rrf[chunk["id"]] = rrf.get(chunk["id"], 0.0) + 1.0 / (K + rang)
            entrees[chunk["id"]] = chunk

        # 2. Classement lexical BM25 élargi.
        self._charger_bm25()
        scores = self._bm25.get_scores(tokeniser(question))
        meilleurs = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        for rang, idx in enumerate(meilleurs[: 3 * n], 1):
            if scores[idx] <= 0:
                break  # plus aucun terme en commun : inutile de continuer
            cid = self._bm25_ids[idx]
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (K + rang)
            entrees.setdefault(
                cid,
                {
                    "id": cid,
                    "text": self._bm25_docs[idx],
                    "metadata": self._bm25_metas[idx],
                    "distance": None,
                },
            )

        # 3. Fusion : pseudo-distance = -score RRF (tri croissant compatible).
        for cid in entrees:
            entrees[cid]["distance"] = -rrf[cid]
        classement = sorted(entrees.values(), key=lambda c: c["distance"])

        # 4. GARANTIE : les numéros d'articles cités dans la question d'abord.
        resultats, vus = [], set()
        question_ascii = re.sub(r"[‐‑‒–—−]", "-", question)
        for m in MOTIF_NUM_ARTICLE.finditer(question_ascii):
            numero = re.sub(r"[.\s]", "", m.group(0)).upper()
            direct = self.collection.get(where={"numero": numero})
            for cid, doc, meta in zip(
                direct["ids"], direct["documents"], direct["metadatas"]
            ):
                if cid not in vus:
                    vus.add(cid)
                    resultats.append(
                        {"id": cid, "text": doc, "metadata": meta, "distance": -1.0}
                    )

        # 5. Compléter jusqu'à n avec le classement fusionné.
        for chunk in classement:
            if len(resultats) >= n:
                break
            if chunk["id"] not in vus:
                vus.add(chunk["id"])
                resultats.append(chunk)
        return resultats

    def count(self):
        """Nombre de chunks dans la collection."""
        return self.collection.count()
