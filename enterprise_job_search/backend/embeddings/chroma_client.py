import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# Hardcoded for development
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "../../chroma_data")

# Using BAAI/bge-large-en-v1.5 as requested for embeddings
bge_embeddings = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-large-en-v1.5"
)

class VectorStore:
    def __init__(self):
        # Persistent storage for embeddings
        self.client = chromadb.PersistentClient(path=CHROMA_DB_DIR, settings=Settings(anonymized_telemetry=False))
        
        # Collections
        self.resume_chunks = self.client.get_or_create_collection(
            name="resume_chunks",
            embedding_function=bge_embeddings,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.jobs = self.client.get_or_create_collection(
            name="jobs",
            embedding_function=bge_embeddings,
            metadata={"hnsw:space": "cosine"}
        )

    def add_resume_chunks(self, chunks: list[str], chunk_ids: list[str], metadatas: list[dict]):
        self.resume_chunks.upsert(
            documents=chunks,
            ids=chunk_ids,
            metadatas=metadatas
        )

    def add_job_descriptions(self, descriptions: list[str], job_ids: list[str], metadatas: list[dict]):
        self.jobs.upsert(
            documents=descriptions,
            ids=job_ids,
            metadatas=metadatas
        )

    def search_jobs(self, query: str, n_results: int = 10):
        return self.jobs.query(
            query_texts=[query],
            n_results=n_results
        )

    def search_resume_chunks(self, query: str, n_results: int = 5):
        return self.resume_chunks.query(
            query_texts=[query],
            n_results=n_results
        )

# Singleton instance
vector_store = VectorStore()
