from __future__ import annotations

import re
from collections import Counter


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI": ("llm", "ai", "agent", "agents", "embedding", "prompt", "model", "rag"),
    "Programming": ("python", "typescript", "javascript", "api", "backend", "frontend", "code"),
    "Startups": ("startup", "founder", "saas", "growth", "market", "product", "customer"),
    "Research": ("paper", "research", "study", "benchmark", "arxiv", "experiment"),
    "Career": ("career", "hiring", "interview", "resume", "promotion", "leadership"),
    "System Design": ("architecture", "scaling", "system", "database", "distributed", "latency"),
    "Security": ("security", "auth", "oauth", "vulnerability", "exploit", "threat"),
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "your",
    "have",
    "just",
    "about",
    "https",
    "there",
    "their",
    "will",
    "would",
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_+#.-]{3,}", text.lower())


def categorize_text(text: str) -> str:
    tokens = tokenize(text)
    scores: Counter[str] = Counter()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            scores[category] += tokens.count(keyword)
    if not scores:
        return "General"
    category, score = scores.most_common(1)[0]
    return category if score > 0 else "General"


def extract_tags(text: str, category: str, limit: int = 5) -> list[str]:
    raw_tokens = tokenize(text)
    counts = Counter(token for token in raw_tokens if token not in STOPWORDS and not token.isdigit())
    tags: list[str] = []
    for tag in re.findall(r"#(\w+)", text):
        normalized = tag.lower()
        if normalized not in tags:
            tags.append(normalized)
    if category != "General":
        tags.append(category.lower().replace(" ", "-"))
    for keyword in CATEGORY_KEYWORDS.get(category, ()):
        if keyword in counts and keyword not in tags:
            tags.append(keyword)
        if len(tags) >= limit:
            return tags[:limit]
    for token, _ in counts.most_common(limit * 2):
        if token not in tags:
            tags.append(token)
        if len(tags) >= limit:
            break
    return tags[:limit]
