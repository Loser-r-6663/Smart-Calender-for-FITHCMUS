"""Optional, local-only hybrid retrieval over already authorized records."""

import logging
import os
from array import array
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import Lock

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
    """Session/snapshot-local bounded passage vectors; queries are never cached."""

    def __init__(self, encoder=None, *, cutoff=CUTOFF, max_cache_entries=2048,
                 max_cache_bytes=8 * 1024 * 1024):
        if any(type(value) is not int or value < 0 for value in (max_cache_entries, max_cache_bytes)):
            raise ValueError('Cache bounds must be nonnegative integers')
        self.encoder = encoder
        self.cutoff = cutoff
        self._directory = None
        self._local_encoder = None
        self._max_entries = max_cache_entries
        self._max_bytes = max_cache_bytes
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._records = None
        self._cache_token = None
        self._model_tag = None
        self._epoch = 0
        self._cache_lock = Lock()
        self._inference_lock = Lock()
        self._vector_bytes = None
        self.last_mode = 'keyword'

    @property
    def enabled(self):
        return self.encoder is not None or bool(os.environ.get('SEARCH_SEMANTIC_MODEL'))

    def needs_semantic(self, result):
        topic = result.topic.casefold()
        return bool(self.enabled and topic and result.eligible_records and not any(
            _match_rank(r, topic, topic.split()) == 0 for r in result.eligible_records))

    @property
    def cached_passage_count(self):
        with self._cache_lock:
            return len(self._cache)

    @property
    def cached_vector_bytes(self):
        with self._cache_lock:
            return self._cache_bytes

    def clear_cache(self, expected_epoch=None):
        with self._cache_lock:
            if expected_epoch is not None and expected_epoch != self._epoch:
                return
            self._epoch += 1
            self._cache.clear()
            self._cache_bytes = 0
            self._records = self._cache_token = self._model_tag = None

    def _prepare_cache(self, records, token):
        tag = id(self.encoder), os.environ.get('SEARCH_SEMANTIC_MODEL')
        with self._cache_lock:
            if records is not self._records or token is not self._cache_token or tag != self._model_tag:
                if tag != self._model_tag:
                    self._vector_bytes = None
                self._epoch += 1
                self._cache.clear()
                self._cache_bytes = 0
                self._records, self._cache_token, self._model_tag = records, token, tag
            return self._epoch

    def begin_preparation(self, records, *, cache_token=None):
        """Bind an authorized immutable snapshot without loading a model."""
        return self._prepare_cache(records, cache_token)

    def _current(self, records, token, epoch):
        with self._cache_lock:
            return self._epoch == epoch and self._records is records and self._cache_token is token

    def _get_encoder(self):
        if self.encoder is not None:
            return self.encoder
        directory = os.environ.get('SEARCH_SEMANTIC_MODEL')
        if not directory:
            return None
        if directory != self._directory:
            self._local_encoder = LocalEncoder(directory)
            self._directory = directory
        return self._local_encoder

    @staticmethod
    def _passage_key(record):
        return record.key, sha256((record.title+'\n'+(record.description or '')).encode('utf-8')).digest()

    def prepare_batch(self, records, *, cache_token, expected_epoch, start=0, batch_size=16):
        """Prepare one bounded prefix batch without querying or evicting vectors."""
        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise ValueError('Preparation batches must contain 1 through 16 records')
        total, target = len(records), min(len(records), self._max_entries)
        def status(state, next_index=start):
            return dict(state=state, next_index=next_index, cached=self.cached_passage_count,
                        total=total, target=target)
        with self._inference_lock:
            if not self._current(records, cache_token, expected_epoch):
                return status('cancelled')
            if not self.enabled:
                return status('disabled')
            if self.cached_passage_count == total:
                return status('complete', target)
            with self._cache_lock:
                available = min(self._max_entries-len(self._cache),
                    (self._max_bytes-self._cache_bytes)//self._vector_bytes if self._vector_bytes else 1)
            if start >= target or available <= 0 or self._max_bytes == 0:
                return status('partial', target)
            end = min(start+min(batch_size,available), target)
            missing = [(self._passage_key(r),r) for r in records[start:end]]
            with self._cache_lock:
                missing = [(key,r) for key,r in missing if key not in self._cache][:available]
            try:
                if missing:
                    encoder = self._get_encoder()
                    if encoder is None:
                        return status('disabled')
                    if not self._current(records, cache_token, expected_epoch):
                        return status('cancelled')
                    encoded = encoder.encode(['passage: '+r.title+'\n'+(r.description or '') for _,r in missing])
                    if len(encoded) != len(missing):
                        raise ValueError('Incomplete preparation embeddings')
                    for (key,_),vector in zip(missing,encoded,strict=True):
                        packed = array('d',vector)
                        size = len(packed)*packed.itemsize
                        with self._cache_lock:
                            if self._epoch != expected_epoch:
                                return dict(state='cancelled',next_index=end,cached=0,total=total,target=target)
                            self._vector_bytes = size
                            if key not in self._cache and len(self._cache)<self._max_entries and self._cache_bytes+size<=self._max_bytes:
                                self._cache[key]=packed
                                self._cache_bytes+=size
            except Exception as error:
                self.clear_cache(expected_epoch)
                logging.getLogger(__name__).warning('Local semantic preparation unavailable (%s)',type(error).__name__)
                return status('unavailable',end)
            if not self._current(records, cache_token, expected_epoch):
                return status('cancelled',end)
            return status('complete' if self.cached_passage_count==total else
                          'partial' if end>=target else 'running',end)

    def _encode(self, encoder, topic, eligible, epoch):
        keys = [self._passage_key(r) for r in eligible]
        found, missing = {}, []
        with self._cache_lock:
            for key, record in zip(keys, eligible, strict=True):
                if self._epoch == epoch and key in self._cache:
                    self._cache.move_to_end(key)
                    found[key] = self._cache[key]
                else:
                    missing.append((key, record))
        texts = ['query: ' + topic] + ['passage: ' + r.title + '\n' + (r.description or '')
                                      for _, r in missing]
        encoded = encoder.encode(texts)
        if len(encoded) != len(texts):
            raise ValueError('Incomplete embeddings')
        for (key, _), vector in zip(missing, encoded[1:], strict=True):
            packed = array('d', vector)
            found[key] = packed
            size = len(packed) * packed.itemsize
            with self._cache_lock:
                if self._epoch != epoch or not self._max_entries or size > self._max_bytes:
                    continue
                self._vector_bytes = size
                previous = self._cache.pop(key, None)
                if previous is not None:
                    self._cache_bytes -= len(previous) * previous.itemsize
                self._cache[key] = packed
                self._cache_bytes += size
                while len(self._cache) > self._max_entries or self._cache_bytes > self._max_bytes:
                    _, evicted = self._cache.popitem(last=False)
                    self._cache_bytes -= len(evicted) * evicted.itemsize
        return [encoded[0]] + [found[key] for key in keys]

    def __call__(self, records, query="", *, filters=None, sort=None, cache_token=None, expected_epoch=None):
        self.last_mode = 'keyword'
        records = tuple(records)
        epoch = self._prepare_cache(records, cache_token) if expected_epoch is None else expected_epoch
        baseline = search_records(records, query, filters=filters, sort=sort)
        if not baseline.topic or not baseline.eligible_records:
            return baseline
        topic = baseline.topic.casefold()
        if any(_match_rank(record, topic, topic.split()) == 0 for record in baseline.eligible_records):
            return baseline
        try:
            with self._inference_lock:
                if not self._current(records, cache_token, epoch):
                    return baseline
                encoder = self._get_encoder()
                if encoder is None:
                    self.clear_cache(epoch)
                    return baseline
                if not self._current(records, cache_token, epoch):
                    return baseline
                vectors = self._encode(encoder, baseline.topic, baseline.eligible_records, epoch)
            scores = {r.key: sum(a * b for a, b in zip(vectors[0], vector, strict=True))
                      for r, vector in zip(baseline.eligible_records, vectors[1:], strict=True)}
        except Exception as error:
            self.clear_cache(epoch)
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
        self.last_mode = 'hybrid'
        return SearchResults(tuple(hits), baseline.eligible_records, baseline.effective_filters,
                             baseline.topic, baseline.sort)
