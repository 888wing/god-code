#!/usr/bin/env python3
"""
Vision Model Comparison: Game Screenshot Analysis
Compares OpenAI vs Gemini vision capabilities for game development feedback.

Usage:
  python scripts/vision_model_comparison.py <screenshot_path>

Env vars:
  OPENAI_API_KEY   - Required
  GEMINI_API_KEY   - Required

Both models receive the same screenshot + prompt. Output is a side-by-side
comparison scored on: UI detection, gameplay understanding, actionable feedback,
pixel art awareness, and technical Godot knowledge.
"""

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

# ─── Config ───

OPENAI_MODEL = "gpt-5.4"  # GPT-5.4 has native vision — never use gpt-4o
GEMINI_MODEL = "gemini-3-flash-preview"  # Gemini 3 Flash — native generateContent API

GAME_ANALYSIS_PROMPT = """\
You are a game development QA reviewer analyzing a screenshot from a 2D pixel-art roguelite card RPG built in Godot 4.4.

Analyze this screenshot and provide:

## 1. Scene Identification
- What type of screen is this? (battle, menu, map, shop, etc.)
- What is the current game state shown?

## 2. UI Element Detection
List every distinct UI element you can see:
- Labels, buttons, panels, health bars, card displays
- Their approximate positions (top-left, center, bottom, etc.)
- Text content you can read (exact text)

## 3. Visual Quality Assessment
- Pixel art consistency (are all sprites the same resolution/style?)
- Color palette coherence
- Font readability (especially small pixel fonts)
- Layout balance and spacing
- Any visual bugs or alignment issues

## 4. Gameplay Understanding
- What game mechanics can you infer from this screenshot?
- What is the player likely expected to do next?
- Any information hierarchy issues? (important info hard to find)

## 5. Actionable Improvement Suggestions
Give 3 specific, implementable suggestions to improve this screen.
For each: what to change, why, and rough implementation approach in Godot.

Be precise. Reference exact pixel positions, colors, and text you see.
"""

ITERATION_PROMPT = """\
You are a game development AI that iterates on UI improvements.

Looking at this game screenshot, I previously received feedback to improve it.
Now analyze the CURRENT state and tell me:

## 1. What's Working Well
- Specific elements that are well-executed

## 2. Remaining Issues (prioritized)
For each issue:
- SEVERITY: critical / important / minor / polish
- WHAT: exact description of the problem
- WHERE: location on screen
- HOW TO FIX: Godot-specific implementation (node type, property, value)

## 3. Next Iteration Priority
If you could only change ONE thing, what would have the most impact?
Give exact Godot implementation steps.

Be extremely specific. No vague suggestions like "improve contrast" — instead say
"Label node 'ScoreText' at (120, 45): change font_color from #808080 to #FFD700,
increase font_size from 8 to 12 for readability against dark background."
"""


async def call_openai(client: httpx.AsyncClient, api_key: str, image_b64: str, prompt: str) -> dict:
    """Call OpenAI GPT-5.4 vision API."""
    start = time.monotonic()
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "high"}},
                    ],
                }
            ],
            "max_completion_tokens": 2000,
        },
        timeout=120.0,
    )
    elapsed = time.monotonic() - start
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return {
        "model": OPENAI_MODEL,
        "provider": "openai",
        "content": data["choices"][0]["message"]["content"],
        "latency_ms": int(elapsed * 1000),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


async def call_gemini(client: httpx.AsyncClient, api_key: str, image_b64: str, prompt: str) -> dict:
    """Call Gemini 3 Flash via native generateContent API."""
    start = time.monotonic()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    resp = await client.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 2000},
        },
        timeout=120.0,
    )
    elapsed = time.monotonic() - start
    resp.raise_for_status()
    data = resp.json()

    # Parse Gemini native response format
    candidates = data.get("candidates", [])
    content = ""
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(p.get("text", "") for p in parts)

    usage_meta = data.get("usageMetadata", {})
    return {
        "model": GEMINI_MODEL,
        "provider": "gemini",
        "content": content,
        "latency_ms": int(elapsed * 1000),
        "prompt_tokens": usage_meta.get("promptTokenCount", 0),
        "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
        "total_tokens": usage_meta.get("totalTokenCount", 0),
    }


def score_response(content: str) -> dict:
    """Heuristic scoring of response quality."""
    scores = {}

    # UI detection: count specific UI element mentions
    ui_terms = ["label", "button", "panel", "bar", "text", "icon", "container", "sprite", "hp", "health", "mana", "energy", "card"]
    ui_hits = sum(1 for term in ui_terms if term.lower() in content.lower())
    scores["ui_detection"] = min(5, ui_hits)

    # Pixel art awareness
    pixel_terms = ["pixel", "sprite", "resolution", "nearest", "filter", "palette", "8-bit", "retro", "aliasing"]
    pixel_hits = sum(1 for term in pixel_terms if term.lower() in content.lower())
    scores["pixel_art_awareness"] = min(5, pixel_hits * 2)

    # Actionable specificity: mentions of exact positions, colors, sizes
    specific_terms = ["px", "pixel", "#", "rgb", "x:", "y:", "position", "size", "font_size", "Vector2", "Color("]
    specific_hits = sum(1 for term in specific_terms if term in content)
    scores["specificity"] = min(5, specific_hits)

    # Godot knowledge
    godot_terms = ["Node", "Control", "Label", "Button", "TextureRect", "HBox", "VBox", "Container",
                   "theme", "StyleBox", "shader", "AnimatedSprite", "CanvasLayer", "ColorRect",
                   "RichTextLabel", "ProgressBar", "NinePatch", "margin", "anchor"]
    godot_hits = sum(1 for term in godot_terms if term in content)
    scores["godot_knowledge"] = min(5, godot_hits)

    # Gameplay understanding: mentions of game mechanics
    gameplay_terms = ["turn", "card", "deck", "monster", "battle", "attack", "defend",
                      "roguelite", "roguelike", "run", "encounter", "position", "vanguard",
                      "rearguard", "formation", "fusion", "resonance", "energy", "mana"]
    gameplay_hits = sum(1 for term in gameplay_terms if term.lower() in content.lower())
    scores["gameplay_understanding"] = min(5, gameplay_hits)

    # Overall: word count as proxy for thoroughness
    word_count = len(content.split())
    scores["thoroughness"] = min(5, word_count // 100)

    scores["total"] = sum(scores.values())
    scores["max_possible"] = 30
    return scores


def print_comparison(results: list[dict], screenshot_name: str):
    """Print side-by-side comparison."""
    print(f"\n{'=' * 80}")
    print(f"  VISION MODEL COMPARISON: {screenshot_name}")
    print(f"{'=' * 80}\n")

    for r in results:
        scores = score_response(r["content"])
        r["scores"] = scores

        print(f"┌─ {r['provider'].upper()}: {r['model']} ─────────────────────────")
        print(f"│ Latency: {r['latency_ms']}ms | Tokens: {r['total_tokens']} (in:{r['prompt_tokens']} out:{r['completion_tokens']})")
        print(f"│")
        print(f"│ Scores:")
        print(f"│   UI Detection:        {'█' * scores['ui_detection']}{'░' * (5 - scores['ui_detection'])} {scores['ui_detection']}/5")
        print(f"│   Pixel Art Awareness: {'█' * scores['pixel_art_awareness']}{'░' * (5 - scores['pixel_art_awareness'])} {scores['pixel_art_awareness']}/5")
        print(f"│   Specificity:         {'█' * scores['specificity']}{'░' * (5 - scores['specificity'])} {scores['specificity']}/5")
        print(f"│   Godot Knowledge:     {'█' * scores['godot_knowledge']}{'░' * (5 - scores['godot_knowledge'])} {scores['godot_knowledge']}/5")
        print(f"│   Gameplay:            {'█' * scores['gameplay_understanding']}{'░' * (5 - scores['gameplay_understanding'])} {scores['gameplay_understanding']}/5")
        print(f"│   Thoroughness:        {'█' * scores['thoroughness']}{'░' * (5 - scores['thoroughness'])} {scores['thoroughness']}/5")
        print(f"│   TOTAL:               {scores['total']}/{scores['max_possible']}")
        print(f"│")
        # Print first 40 lines of content
        lines = r["content"].split("\n")
        for line in lines[:40]:
            print(f"│ {line}")
        if len(lines) > 40:
            print(f"│ ... ({len(lines) - 40} more lines)")
        print(f"└{'─' * 70}\n")

    # Summary comparison
    print(f"\n{'─' * 80}")
    print(f"  SUMMARY")
    print(f"{'─' * 80}")
    print(f"{'Dimension':<25} ", end="")
    for r in results:
        print(f"{r['provider']:>15}", end="")
    print()
    print(f"{'─' * 55}")

    dimensions = ["ui_detection", "pixel_art_awareness", "specificity", "godot_knowledge", "gameplay_understanding", "thoroughness", "total"]
    for dim in dimensions:
        label = dim.replace("_", " ").title()
        print(f"{label:<25} ", end="")
        for r in results:
            val = r["scores"][dim]
            mx = 30 if dim == "total" else 5
            print(f"{val:>10}/{mx}", end="")
        print()

    print(f"\n{'Latency':<25} ", end="")
    for r in results:
        print(f"{r['latency_ms']:>10}ms", end="")
    print()

    print(f"{'Tokens':<25} ", end="")
    for r in results:
        print(f"{r['total_tokens']:>10}", end="")
    print()

    # Winner
    winner = max(results, key=lambda r: r["scores"]["total"])
    print(f"\n  Winner: {winner['provider'].upper()} ({winner['model']}) — {winner['scores']['total']}/{winner['scores']['max_possible']}")
    print()


async def run_comparison(screenshot_path: str, prompt: str = GAME_ANALYSIS_PROMPT):
    """Run comparison between available vision models."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if not openai_key:
        # Try god-code config
        config_path = Path.home() / ".config" / "god-code" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text())
            openai_key = cfg.get("api_key", "")
            if not gemini_key:
                gemini_key = cfg.get("backend_provider_keys", {}).get("gemini", "")

    if not openai_key and not gemini_key:
        print("ERROR: Set OPENAI_API_KEY and/or GEMINI_API_KEY")
        sys.exit(1)

    # Load and encode image
    path = Path(screenshot_path)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    image_b64 = base64.b64encode(path.read_bytes()).decode()
    print(f"Image: {path.name} ({path.stat().st_size // 1024}KB)")

    results = []
    async with httpx.AsyncClient() as client:
        tasks = []
        if openai_key:
            print(f"Calling {OPENAI_MODEL}...")
            tasks.append(("openai", call_openai(client, openai_key, image_b64, prompt)))
        if gemini_key:
            print(f"Calling {GEMINI_MODEL}...")
            tasks.append(("gemini", call_gemini(client, gemini_key, image_b64, prompt)))

        if not tasks:
            print("ERROR: No API keys available")
            sys.exit(1)

        # Run in parallel
        coros = [t[1] for t in tasks]
        responses = await asyncio.gather(*coros, return_exceptions=True)

        for (provider, _), response in zip(tasks, responses):
            if isinstance(response, Exception):
                print(f"ERROR ({provider}): {response}")
            else:
                results.append(response)

    if results:
        print_comparison(results, path.name)

        # Save raw results
        output_path = path.parent / f"vision_comparison_{path.stem}.json"
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Raw results saved to: {output_path}")

    return results


async def run_iteration_test(screenshot_path: str):
    """Test iteration capability — can the model give progressively better feedback?"""
    print("\n" + "=" * 80)
    print("  ITERATION TEST: Can the model refine feedback across rounds?")
    print("=" * 80 + "\n")

    results = await run_comparison(screenshot_path, ITERATION_PROMPT)
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/vision_model_comparison.py <screenshot_path> [--iterate]")
        print("\nExamples:")
        print("  python scripts/vision_model_comparison.py screenshots/battle_scene_02_battlefield.png")
        print("  python scripts/vision_model_comparison.py screenshots/team_select_01.png --iterate")
        sys.exit(1)

    screenshot = sys.argv[1]
    iterate = "--iterate" in sys.argv

    if iterate:
        asyncio.run(run_iteration_test(screenshot))
    else:
        asyncio.run(run_comparison(screenshot))
