import pytest
from godot_agent.prompts.knowledge_selector import select_sections, format_knowledge_injection


class TestKnowledgeSelector:
    def test_collision_query(self):
        sections = select_sections("fix collision layers for player bullets")
        titles = [t for t, _ in sections]
        assert "Physics & Collision" in titles

    def test_ui_query(self):
        sections = select_sections("create a health bar UI")
        titles = [t for t, _ in sections]
        assert any("UI" in t for t in titles)

    def test_empty_query_returns_safety(self):
        sections = select_sections("")
        # Should still include Common Mistakes as safety net
        titles = [t for t, _ in sections]
        assert "Common Mistakes" in titles

    def test_max_sections_limit(self):
        sections = select_sections("collision animation ui physics", max_sections=2)
        assert len(sections) <= 2

    def test_format_injection(self):
        sections = select_sections("movement physics")
        text = format_knowledge_injection(sections)
        assert "Godot Knowledge" in text

    def test_file_extension_bonus(self):
        sections = select_sections("edit the file", file_paths=["player.gd"])
        titles = [t for t, _ in sections]
        # .gd files should boost style/type/signal sections
        assert any("Style" in t or "Signal" in t or "Lifecycle" in t for t in titles)
