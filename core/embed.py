"""Sentence embeddings for retrieval.

Uses the ONNX build of all-MiniLM-L6-v2 that ships with Chroma, not
sentence-transformers on PyTorch. It is the same model producing the same
vectors -- measured across all 246 indexed passages, cosine similarity between
the two was 1.00000 at every passage, and every test query ranked the same
passages with the same scores -- but it needs no PyTorch, which cuts the
server's memory from about 1 GB to a few hundred MB. That is what lets the API
run on a 512 MB free hosting tier, and it starts in seconds on the demo laptop.

The model file (about 80 MB) downloads on first use. EMBEDDING_CACHE moves it
inside the project, so a hosted build can fetch it once at build time and keep it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from core import config

SUPPORTED = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from functools import cached_property

    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    if config.settings.embedding_model not in (SUPPORTED, "all-MiniLM-L6-v2"):
        raise ValueError(
            f"EMBEDDING_MODEL={config.settings.embedding_model!r} is not supported: "
            f"the index is built with {SUPPORTED}. Rebuild it if you change models."
        )

    class LeanMiniLM(ONNXMiniLM_L6_V2):
        """Same model file and maths as Chroma's; a leaner ONNX session.

        Chroma's session keeps a memory arena sized for its largest batch and
        spreads work over every core. A server embedding one short question at
        a time on a fraction of a CPU gains nothing from either, and the arena
        alone is tens of megabytes of a 512 MB hosting tier.
        """

        @cached_property
        def model(self):
            options = self.ort.SessionOptions()
            options.log_severity_level = 3
            options.graph_optimization_level = self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.enable_cpu_mem_arena = False
            options.enable_mem_pattern = False
            options.intra_op_num_threads = int(os.environ.get("EMBEDDING_THREADS", "1"))
            return self.ort.InferenceSession(
                os.path.join(self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx"),
                providers=["CPUExecutionProvider"],
                sess_options=options,
            )

    cache = os.environ.get("EMBEDDING_CACHE")
    if cache:
        LeanMiniLM.DOWNLOAD_PATH = Path(cache) / ONNXMiniLM_L6_V2.MODEL_NAME
    return LeanMiniLM(preferred_providers=["CPUExecutionProvider"])


def embed(texts: list[str]) -> np.ndarray:
    """Unit-length vectors, one row per text."""
    vectors = np.asarray(_model()(list(texts)), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def warm() -> None:
    """Load the model (downloading it if needed) before the first question."""
    embed(["warm up"])
