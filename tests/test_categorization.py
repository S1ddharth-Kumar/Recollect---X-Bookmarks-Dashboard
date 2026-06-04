from bookmarks_organizer.categorization import categorize_text, extract_tags


def test_categorize_ai_content() -> None:
    text = "This paper compares LLM agents, RAG patterns, and embedding quality for search."
    assert categorize_text(text) == "AI"


def test_extract_tags_keeps_category_and_keywords() -> None:
    tags = extract_tags("Startup founders need strong product sense and customer empathy.", "Startups")
    assert "startups" in tags
    assert "product" in tags

