"""
Lightweight in-memory RAG engine using FAISS and OpenAI embeddings.
"""

import logging
import os
from pathlib import Path
from typing import List

import faiss
import numpy as np
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class RAGEngine:
    """A lightweight RAG engine that chunks a text document, embeds it
    using OpenAI, and retrieves relevant chunks via FAISS.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            logger.warning("No OPENAI_API_KEY provided for RAGEngine")
            
        self._client = AsyncOpenAI(api_key=self._api_key)
        self._chunks: List[str] = []
        self._index: faiss.IndexFlatL2 | None = None
        self._is_ready = False

    async def initialize(self, document_path: str | Path) -> None:
        """Load document, chunk it, embed it, and build FAISS index."""
        if not self._api_key:
            return

        path = Path(document_path)
        if not path.exists():
            logger.error("RAG document not found: %s", document_path)
            return

        text = path.read_text(encoding="utf-8")
        
        # Simple chunking: split by double newlines (paragraphs)
        self._chunks = [
            chunk.strip() 
            for chunk in text.split("\n\n") 
            if chunk.strip()
        ]
        
        if not self._chunks:
            logger.warning("No chunks found in document: %s", document_path)
            return

        logger.info("Generating embeddings for %d chunks...", len(self._chunks))
        
        try:
            response = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=self._chunks,
            )
            embeddings = [data.embedding for data in response.data]
            
            # Convert to numpy array (FAISS requires float32)
            vectors = np.array(embeddings).astype("float32")
            
            # Create FAISS index
            dimension = vectors.shape[1]
            self._index = faiss.IndexFlatL2(dimension)
            self._index.add(vectors)
            
            self._is_ready = True
            logger.info("RAG Engine initialized successfully.")
            
        except Exception:
            logger.exception("Failed to initialize RAG Engine")

    async def retrieve(self, query: str, top_k: int = 2) -> List[str]:
        """Retrieve the top-k most relevant chunks for a query."""
        if not self._is_ready or not self._index:
            return []

        if not query.strip():
            return []

        try:
            # Embed the query
            response = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=query,
            )
            query_embedding = response.data[0].embedding
            query_vector = np.array([query_embedding]).astype("float32")
            
            # Search the index
            # D = distances, I = indices of nearest neighbors
            D, I = self._index.search(query_vector, k=min(top_k, len(self._chunks)))
            
            results = []
            for idx in I[0]:
                if 0 <= idx < len(self._chunks):
                    results.append(self._chunks[idx])
            
            return results
            
        except Exception:
            logger.exception("RAG retrieval failed")
            return []
