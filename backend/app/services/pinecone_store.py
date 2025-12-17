from pinecone import Pinecone

class PineconeStore:
    def __init__(self, api_key: str, index_name: str):
        pc = Pinecone(api_key=api_key)
        self.index = pc.Index(index_name)

    def upsert(self, namespace: str, vectors: list[dict]):
        self.index.upsert(vectors=vectors, namespace=namespace)

    def query(self, namespace: str, vector: list[float], top_k: int = 8):
        return self.index.query(
            namespace=namespace,
            vector=vector,
            top_k=top_k,
            include_metadata=True
        )