from __future__ import annotations

import asyncio
import collections
import random
import re

from app.constants import (
    MOCK_SUMMARY_SENTIMENT,
    MOCK_SUMMARY_SUFFIX,
    SUMMARIZER_FAILURE_RATE,
    SUMMARIZER_MAX_DELAY,
    SUMMARIZER_MIN_DELAY,
)
from app.messages import ERR_SIMULATED_PROCESSING_FAILURE

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "it", "this", "that", "was", "are", "be", "as",
    "by", "from", "has", "had", "have", "not", "we", "he", "she", "they",
    "you", "i", "my", "your", "its", "our", "their", "so", "if", "do",
    "can", "will", "would", "could", "should", "may", "might", "also",
}


class ProcessingError(Exception):
    pass


def _extract_key_topics(content: str, n: int = 5) -> list[str]:
    words = re.findall(r"[a-zA-Z]{3,}", content.lower())
    counts = collections.Counter(w for w in words if w not in STOPWORDS)
    return [word for word, _ in counts.most_common(n)]


async def generate_summary(title: str, content: str) -> dict:
    delay = random.uniform(SUMMARIZER_MIN_DELAY, SUMMARIZER_MAX_DELAY)
    await asyncio.sleep(delay)

    if random.random() < SUMMARIZER_FAILURE_RATE:
        raise ProcessingError(ERR_SIMULATED_PROCESSING_FAILURE)

    word_count = len(content.split())
    key_topics = _extract_key_topics(content)

    return {
        "summary": f"Document '{title}' contains {word_count} words. {MOCK_SUMMARY_SUFFIX}",
        "word_count": word_count,
        "key_topics": key_topics,
        "sentiment": MOCK_SUMMARY_SENTIMENT,
    }
