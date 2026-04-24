"""用于测试和离线 fallback 的简易本地 embedding 实现。"""

from hashlib import sha256
from math import sqrt
import re

from app.core.config import get_settings


def compact_text(text: str) -> str:
    # 只保留字母数字和中日韩字符，避免标点影响 token 稳定性。
    normalized = text.lower().strip()
    filtered = "".join(ch for ch in normalized if ch.isalnum() or _is_cjk(ch))
    return filtered


def tokenize_text(text: str) -> list[str]:
    # 混合分词策略：
    # - ASCII 单词，适配英文术语和标识符
    # - 单字 CJK token
    # - bigram，提升中文短语匹配的敏感度
    normalized = text.lower().strip()
    if not normalized:
        return []

    ascii_words = re.findall(r"[a-z0-9_]+", normalized)
    compact = compact_text(normalized)
    char_tokens = list(compact)
    bigram_tokens = [compact[index : index + 2] for index in range(len(compact) - 1)]
    return ascii_words + char_tokens + bigram_tokens


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def embed_text(text: str) -> list[float]:
    settings = get_settings()
    vector = [0.0] * settings.embedding_dim
    for token in tokenize_text(text):
        # 把 token hash 到固定维度的 signed bag-of-words 向量里。
        # 它便宜、稳定，但效果明显弱于真实 embedding 模型。
        digest = sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % settings.embedding_dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.5 if len(token) > 1 else 1.0
        vector[index] += sign * weight

    # 做 L2 归一化，保证后续 cosine 相似度更稳定。
    norm = sqrt(sum(item * item for item in vector))
    if norm == 0:
        return vector
    return [item / norm for item in vector]
