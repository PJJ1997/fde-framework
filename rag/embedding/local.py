"""Lightweight character n-gram embedding provider.

Zero downloads, zero model files. Uses character n-gram hashing for embedding vectors.
Quality is lower than neural embeddings but sufficient for testing and development.
"""
import hashlib
from collections import Counter
from typing import List, Optional

from langchain_core.embeddings import Embeddings

_DIM = 256
_NGRAM = 3


class NgramEmbeddings(Embeddings):
    """Embeddings based on character n-gram hashing.

    No model download required. Works offline instantly.
    """

    def __init__(self, dim: int = _DIM, ngram: int = _NGRAM):
        self._dim = dim
        self._ngram = ngram

    def _encode(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            vec = [0.0] * self._dim
            # Generate character n-grams
            normalized = text.lower()
            ngrams = Counter()
            for i in range(len(normalized) - self._ngram + 1):
                gram = normalized[i : i + self._ngram]
                ngrams[gram] += 1
            # Hash n-grams into vector positions
            for gram, count in ngrams.items():
                h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
                idx = h % self._dim
                sign = 1 if (h // self._dim) % 2 == 0 else -1
                vec[idx] += sign * count
            # Normalize
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0:
                vec = [x / norm for x in vec]
            results.append(vec)
        return results

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._encode([text])[0]


def create_embeddings(model: Optional[str] = None) -> Embeddings:
    """Create n-gram embedding instance.

    Args:
        model: Ignored. Kept for interface compatibility.

    Returns:
        Embeddings instance.
    """
    return NgramEmbeddings()
