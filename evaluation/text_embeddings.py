"""Lazy, local Chinese text embeddings for deterministic result validation."""

from __future__ import annotations

from math import sqrt
import os
from pathlib import Path
from threading import Lock


DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / ".cache" / "fastembed"
_model = None
_model_identity = None
_model_error = None
_lock = Lock()


def _get_model():
    """Load the ONNX model once, only when semantic fallback is needed."""
    global _model, _model_identity, _model_error
    name = os.getenv("RESULT_EMBEDDING_MODEL", DEFAULT_MODEL)
    cache = Path(os.getenv("RESULT_EMBEDDING_CACHE", str(DEFAULT_CACHE))).expanduser().resolve()
    identity = (name, str(cache))
    if _model is not None and _model_identity == identity:
        return _model
    if _model_error is not None and _model_identity == identity:
        raise RuntimeError(f"本次运行无法加载本地向量模型：{_model_error}") from _model_error
    with _lock:
        if _model is None or _model_identity != identity:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "未安装 fastembed，请执行 python -m pip install -r requirements.txt"
                ) from exc
            cache.mkdir(parents=True, exist_ok=True)
            _model_identity = identity
            _model_error = None
            try:
                _model = TextEmbedding(model_name=name, cache_dir=str(cache))
            except Exception as exc:
                _model = None
                _model_error = exc
                raise RuntimeError(
                    f"无法从 {cache} 加载向量模型 {name}；请先在可联网环境完成一次模型下载"
                ) from exc
    return _model


def cosine_similarity(left: str, right: str) -> float:
    """Return cosine similarity for two texts using a local ONNX model."""
    vectors = list(_get_model().embed([left, right]))
    if len(vectors) != 2:
        raise RuntimeError(f"向量模型应返回 2 个向量，实际返回 {len(vectors)} 个")
    a, b = vectors
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = sqrt(sum(float(x) * float(x) for x in a))
    norm_b = sqrt(sum(float(y) * float(y) for y in b))
    if not norm_a or not norm_b:
        raise RuntimeError("向量模型返回了零向量")
    return dot / (norm_a * norm_b)

