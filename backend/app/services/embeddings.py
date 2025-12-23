from sentence_transformers import SentenceTransformer

class HFEmbedder:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # normalize
        texts = [t if isinstance(t, str) else "" for t in texts]
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return vecs.tolist()
