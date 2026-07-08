"""
Lightweight in-memory RAG engine using FAISS and OpenAI embeddings.
LangChain for multi-document parsing and chunking.
"""

import json
import logging
import os
from pathlib import Path
from typing import List

import faiss
import numpy as np
from openai import AsyncOpenAI

from langchain_community.document_loaders import DirectoryLoader
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, UnstructuredHTMLLoader, TextLoader, CSVLoader, UnstructuredExcelLoader, UnstructuredMarkdownLoader, UnstructuredPowerPointLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from flashrank import Ranker, RerankRequest

logger = logging.getLogger(__name__)


class RAGEngine:
    """A RAG engine that uses LangChain to load all documents in a directory,
    chunks them using an overlapping strategy, embeds using OpenAI,
    and retrieves relevant chunks via FAISS.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            logger.warning("No OPENAI_API_KEY provided for RAGEngine")
            
        self._client = AsyncOpenAI(api_key=self._api_key)
        self._chunks: List[dict] = []
        self._index: faiss.IndexFlatL2 | None = None
        self._is_ready = False
        self._ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

    async def initialize(
        self, 
        docs_dir: str | Path, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200
    ) -> None:
        """Scan directory, parse all supported docs, chunk, and index."""
        if not self._api_key:
            return

        path = Path(docs_dir)
        if not path.exists() or not path.is_dir():
            logger.error("RAG knowledge base directory not found: %s", docs_dir)
            return

        # Setup LangChain loaders for different file types
        loaders = {
            ".txt": (TextLoader, {}),
            ".pdf": (PyPDFLoader, {}),
            ".docx": (Docx2txtLoader, {}),
            ".html": (UnstructuredHTMLLoader, {}),
            ".csv": (CSVLoader, {}),
            ".xlsx": (UnstructuredExcelLoader, {}),
            ".md": (UnstructuredMarkdownLoader, {}),
            ".pptx": (UnstructuredPowerPointLoader, {}),
        }

        index_path = path / ".faiss_index"
        chunks_path = path / ".chunks.json"

        # Check if we can use the cached index
        needs_rebuild = True
        if index_path.exists() and chunks_path.exists():
            latest_doc_mtime = 0.0
            for ext in loaders.keys():
                for file in path.rglob(f"*{ext}"):
                    mtime = file.stat().st_mtime
                    if mtime > latest_doc_mtime:
                        latest_doc_mtime = mtime
            
            if latest_doc_mtime > 0.0:
                index_mtime = index_path.stat().st_mtime
                if index_mtime >= latest_doc_mtime:
                    needs_rebuild = False

        if not needs_rebuild:
            logger.info("Loading cached RAG index from disk...")
            try:
                self._index = faiss.read_index(str(index_path))
                with open(chunks_path, "r", encoding="utf-8") as f:
                    self._chunks = json.load(f)
                self._is_ready = True
                logger.info("Loaded %d chunks from cache.", len(self._chunks))
                return
            except Exception as e:
                logger.warning("Failed to load cache: %s. Rebuilding...", e)
                needs_rebuild = True

        all_documents = []
        
        logger.info("Scanning directory: %s", path)
        
        # Load documents based on extension
        for ext, (loader_cls, kwargs) in loaders.items():
            loader = DirectoryLoader(
                str(path), 
                glob=f"**/*{ext}", 
                loader_cls=loader_cls,
                loader_kwargs=kwargs
            )
            try:
                docs = loader.load()
                all_documents.extend(docs)
                logger.info("Loaded %d %s files.", len(docs), ext)
            except Exception as e:
                logger.warning("Error loading %s files: %s", ext, e)

        if not all_documents:
            logger.warning("No parseable documents found in %s", path)
            return

        # Chunk the documents with overlap
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )
        
        chunks = text_splitter.split_documents(all_documents)
        self._chunks = [
            {"text": chunk.page_content, "metadata": chunk.metadata}
            for chunk in chunks if chunk.page_content.strip()
        ]
        
        if not self._chunks:
            logger.warning("No text extracted after chunking.")
            return

        logger.info("Generated %d overlapping chunks (size=%d, overlap=%d). Embedding...", 
                    len(self._chunks), chunk_size, chunk_overlap)
        
        try:
            response = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=[c["text"] for c in self._chunks],
            )
            embeddings = [data.embedding for data in response.data]
            
            # Convert to numpy array (FAISS requires float32)
            vectors = np.array(embeddings).astype("float32")
            
            # Create FAISS index
            dimension = vectors.shape[1]
            self._index = faiss.IndexFlatL2(dimension)
            self._index.add(vectors)
            
            # Save to disk
            try:
                faiss.write_index(self._index, str(index_path))
                with open(chunks_path, "w", encoding="utf-8") as f:
                    json.dump(self._chunks, f)
                logger.info("Saved RAG index and chunks to disk.")
            except Exception as e:
                logger.warning("Failed to cache RAG index to disk: %s", e)

            self._is_ready = True
            logger.info("RAG Engine successfully initialized with FAISS index.")
            
        except Exception:
            logger.exception("Failed to embed or build FAISS index")

    async def retrieve(self, query: str, top_k: int = 5) -> List[str]:
        """Retrieve the top-k most relevant chunks for a query using FAISS + FlashRank."""
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
            
            # Step 1: Initial Retrieval (pull more chunks than needed)
            fetch_k = max(15, top_k * 2)
            D, I = self._index.search(query_vector, k=min(fetch_k, len(self._chunks)))
            
            passages = []
            for i, idx in enumerate(I[0]):
                if 0 <= idx < len(self._chunks):
                    chunk_dict = self._chunks[idx]
                    passages.append({
                        "id": i, 
                        "text": chunk_dict["text"], 
                        "meta": chunk_dict["metadata"]
                    })
            
            if not passages:
                return []
                
            # Step 2: Rerank using FlashRank
            req = RerankRequest(query=query, passages=passages)
            reranked_results = self._ranker.rerank(req)
            
            # Return the text of the top_k reranked results with metadata
            results = []
            for res in reranked_results[:top_k]:
                meta = res.get("meta", {})
                source = meta.get("source", "Unknown Source")
                source_basename = os.path.basename(source)
                
                page = meta.get("page")
                page_str = f", Page: {page}" if page is not None else ""
                
                formatted_text = f"[Source: {source_basename}{page_str}]\n{res['text']}"
                results.append(formatted_text)
            
            return results
            
        except Exception:
            logger.exception("RAG retrieval failed")
            return []
