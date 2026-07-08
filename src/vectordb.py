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

import chromadb
from sentence_transformers import SentenceTransformer


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
        """Encode tous les chunks et les insère dans la collection."""
        embeddings = self._encode(documents)
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
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
            {"text": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(
                resultats["documents"][0],
                resultats["metadatas"][0],
                resultats["distances"][0],
            )
        ]

    def count(self):
        """Nombre de chunks dans la collection."""
        return self.collection.count()
