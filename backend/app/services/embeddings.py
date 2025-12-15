from sentence_transformers import SentenceTransformer

class HFEmbedder:
    def __init__(self, model_name: str):
        self.model = SentenceTransformer(model_name)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        return [v.tolist() for v in vecs]
