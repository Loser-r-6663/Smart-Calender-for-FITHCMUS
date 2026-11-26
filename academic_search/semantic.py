"""Optional, local-only hybrid retrieval over already authorized records."""

import logging
import os
from pathlib import Path

from .matcher import SearchResults, _match_rank, search_records

MODEL_ID = "intfloat/multilingual-e5-small"
REVISION = "fd1525a9fd15316a2d503bf26ab031a61d056e98"
# Set from the frozen tuning split by run_hybrid --calibrate.
CUTOFF = 0.86


class LocalEncoder:
    def __init__(self, directory):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = Path(directory)
        if (directory / "revision.txt").read_text().strip() != REVISION:
            raise ValueError("Unreviewed model revision")
        self.np = np
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(directory / "model.onnx"), options,
                                           providers=["CPUExecutionProvider"])

    def encode(self, texts):
        np = self.np
        vectors = []
        for start in range(0, len(texts), 16):
            batch = self.tokenizer.encode_batch(texts[start:start + 16])
            ids = np.array([item.ids for item in batch], dtype=np.int64)
            mask = np.array([item.attention_mask for item in batch], dtype=np.int64)
            values = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
            output = self.session.run(None, {x.name: values[x.name] for x in self.session.get_inputs()})[0]
            pooled = (output * mask[..., None]).sum(1) / mask.sum(1)[:, None]
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)
            vectors.extend(pooled.tolist())
        return vectors


class HybridSearch:
    """Keep model weights, but never retain task/query embeddings or results."""

    def __init__(self, encoder=None, *, cutoff=CUTOFF):
        self.encoder = encoder
        self.cutoff = cutoff
        self._directory = None
        self._local_encoder = None

    def __call__(self, records, query="", *, filters=None, sort=None):
        baseline = search_records(records, query, filters=filters, sort=sort)
        if not baseline.topic or not baseline.eligible_records:
            return baseline
        topic = baseline.topic.casefold()
        if any(_match_rank(record, topic, topic.split()) == 0 for record in baseline.eligible_records):
            return baseline
        try:
            encoder = self.encoder
            if encoder is None:
                directory = os.environ.get("SEARCH_SEMANTIC_MODEL")
                if not directory:
                    return baseline
                if directory != self._directory:
                    self._local_encoder = LocalEncoder(directory)
                    self._directory = directory
                encoder = self._local_encoder
            documents = ["passage: " + r.title + "\n" + (r.description or "")
                         for r in baseline.eligible_records]
            vectors = encoder.encode(["query: " + baseline.topic] + documents)
            if len(vectors) != len(documents) + 1:
                raise ValueError("Incomplete embeddings")
            scores = {r.key: sum(a * b for a, b in zip(vectors[0], vector, strict=True))
                      for r, vector in zip(baseline.eligible_records, vectors[1:], strict=True)}
        except Exception as error:
            logging.getLogger(__name__).warning("Local semantic retrieval unavailable (%s)", type(error).__name__)
            return baseline
        literal = {r.key for r in baseline.hits}
        combined = {r.key: r for r in baseline.eligible_records
                    if r.key in literal or scores[r.key] >= self.cutoff}
        hits = sorted(combined.values(), key=lambda r: r.key)
        if baseline.sort == "best_match":
            topic = baseline.topic.casefold()
            hits.sort(key=lambda r: (_match_rank(r, topic, topic.split()), -scores[r.key]
                                    if r.key not in literal else 0))
        elif baseline.sort == "title":
            hits.sort(key=lambda r: r.title.casefold())
        else:
            dated = sorted((r for r in hits if r.deadline is not None), key=lambda r: r.deadline,
                           reverse=baseline.sort == "latest_deadline")
            hits = dated + [r for r in hits if r.deadline is None]
        return SearchResults(tuple(hits), baseline.eligible_records, baseline.effective_filters,
                             baseline.topic, baseline.sort)
