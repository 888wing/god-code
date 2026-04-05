"""Web search tool for querying Godot documentation and online resources."""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field

from godot_agent.tools.base import BaseTool, ToolResult

log = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for Godot documentation, GDScript API references, "
        "tutorials, and solutions. Use when the built-in Playbook doesn't have "
        "the answer or you need the latest Godot 4.4+ information."
    )

    class Input(BaseModel):
        query: str = Field(description="Search query (e.g., 'Godot 4.4 TileMapLayer tutorial')")
        site: str = Field(default="", description="Restrict to site (e.g., 'docs.godotengine.org')")

    class Output(BaseModel):
        results: list[dict]
        result_count: int

    def is_read_only(self) -> bool:
        return True

    async def execute(self, input: Input) -> ToolResult:
        try:
            from pathlib import Path
            import json

            api_key = ""
            base_url = "https://api.openai.com/v1"
            model = "gpt-5.4"
            ctx = getattr(self, "_execution_context", None)
            llm_client = getattr(ctx, "llm_client", None) if ctx else None
            if llm_client:
                api_key = llm_client.config.api_key
                base_url = llm_client.config.base_url or base_url
                model = llm_client.config.model or model
            if not api_key:
                config_path = Path.home() / ".config" / "god-code" / "config.json"
                if config_path.exists():
                    cfg = json.loads(config_path.read_text())
                    api_key = cfg.get("api_key", "")

            if not api_key:
                return ToolResult(error="No API key for web search")

            query = input.query
            if input.site:
                query = f"site:{input.site} {query}"

            # Use OpenAI's web search via responses API
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url}/responses",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "tools": [{"type": "web_search_preview"}],
                        "input": f"Search for: {query}\n\nReturn the top 5 most relevant results with title, URL, and a brief summary of each.",
                    },
                )

            if resp.status_code != 200:
                # Fallback: return a suggestion to search manually
                return ToolResult(output=self.Output(
                    results=[{"title": "Web search unavailable", "url": f"https://docs.godotengine.org/en/stable/search.html?q={query.replace(' ', '+')}", "summary": "Search Godot docs directly"}],
                    result_count=1,
                ))

            data = resp.json()
            # Extract text from response
            output_text = ""
            for item in data.get("output", []):
                if item.get("type") == "message":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            output_text = content.get("text", "")

            return ToolResult(output=self.Output(
                results=[{"content": output_text}],
                result_count=1 if output_text else 0,
            ))

        except Exception as e:
            log.warning("Web search failed: %s", e)
            return ToolResult(error=f"Web search failed: {e}")
