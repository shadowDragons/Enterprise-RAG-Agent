from collections import Counter

from app.core.config import get_settings
from app.integrations.local_embeddings import compact_text, tokenize_text


def normalize_vector_score(score: float) -> float:
    if score < 0:
        return max(0.0, min(1.0, (score + 1.0) / 2.0))
    return max(0.0, min(1.0, score))


def score_lexical_match(
    query: str,
    content: str,
    *,
    file_name: str = "",
) -> float:
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return 0.0

    query_weights = Counter(query_tokens)
    content_weights = Counter(tokenize_text(content))
    file_name_weights = Counter(tokenize_text(file_name))

    total_weight = 0.0
    content_overlap = 0.0
    file_name_overlap = 0.0
    for token, count in query_weights.items():
        token_weight = 1.6 if len(token) > 1 else 1.0
        weighted_count = count * token_weight
        total_weight += weighted_count
        content_overlap += min(count, content_weights.get(token, 0)) * token_weight
        file_name_overlap += min(count, file_name_weights.get(token, 0)) * token_weight

    if total_weight == 0:
        return 0.0

    query_phrase = compact_text(query)
    content_phrase = compact_text(content)
    phrase_boost = 1.0 if query_phrase and query_phrase in content_phrase else 0.0

    content_score = content_overlap / total_weight
    file_name_score = file_name_overlap / total_weight
    lexical_score = content_score * 0.75 + file_name_score * 0.15 + phrase_boost * 0.10
    return max(0.0, min(1.0, lexical_score))


def compute_retrieval_score(
    *,
    vector_score: float,
    lexical_score: float,
) -> float:
    settings = get_settings()
    dense_weight = settings.retrieval_dense_weight
    lexical_weight = settings.retrieval_lexical_weight
    total_weight = dense_weight + lexical_weight
    if total_weight <= 0:
        return 0.0
    score = (
        normalize_vector_score(vector_score) * dense_weight
        + lexical_score * lexical_weight
    ) / total_weight
    return max(0.0, min(1.0, score))
