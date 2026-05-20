"""Late chunking: embed full document, pool token vectors per chunk span."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LateChunker:
    """Embed full text once, then average token embeddings per character span."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def embed_and_chunk(
        self,
        full_text: str,
        chunk_boundaries: list[tuple[int, int]],
    ) -> list[list[float]]:
        """Embed and chunk."""
        try:
            token_embeddings = self._model.encode(
                [full_text],
                output_value="token_embeddings",
                normalize_embeddings=True,
            )[0]
            tokenizer = self._model.tokenizer
            encoding = tokenizer(full_text, return_offsets_mapping=True)
            offset_mapping = encoding["offset_mapping"]
        except (AttributeError, TypeError) as exc:
            logger.warning(
                "LateChunker: model does not support token-level access: %s", exc,
            )
            full_emb = self._model.encode([full_text], normalize_embeddings=True)[0]
            return [full_emb.tolist() for _ in chunk_boundaries]

        results: list[list[float]] = []
        for start_char, end_char in chunk_boundaries:
            token_indices = [
                i
                for i, span in enumerate(offset_mapping)
                if span[0] >= start_char and span[1] <= end_char
            ]
            if not token_indices:
                full_emb = self._model.encode([full_text], normalize_embeddings=True)[0]
                results.append(full_emb.tolist())
                continue
            chunk_emb = token_embeddings[token_indices].mean(dim=0)
            results.append(chunk_emb.tolist())

        return results
