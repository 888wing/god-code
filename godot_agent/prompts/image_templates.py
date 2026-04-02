"""Pixel art prompt templates and quality enforcement rules.

The LLM decides WHAT to draw (subject, size, facing).
This module enforces HOW it's drawn (style consistency, hard edges, etc).
"""

from __future__ import annotations

# Quality enforcement — always appended regardless of LLM prompt
QUALITY_SUFFIX = (
    "hard pixel edges, no anti-aliasing, no smooth gradients, "
    "flat solid colors, no glow effects, no bloom, no soft lighting, "
    "crisp pixel boundaries, nearest-neighbor rendering style, "
    "centered on canvas with margin"
)

# Background enforcement — for chroma key removal
BG_INSTRUCTION = "solid #00FF00 bright green background, no ground, no shadows on background"

# Style presets the LLM can reference or auto-detect from project
STYLE_PRESETS: dict[str, str] = {
    "pixel_8bit": "8-bit pixel art style, limited color palette of 16 colors max, retro NES aesthetic",
    "pixel_16bit": "16-bit pixel art style, SNES-era aesthetic, richer color palette up to 64 colors",
    "pixel_modern": "modern pixel art, clean lines, vibrant colors, indie game aesthetic",
    "chibi": "chibi pixel art style, large head small body, cute proportions",
    "minimal": "minimalist pixel art, very few colors, iconic silhouette shapes",
}

# Size presets with use-case guidance
SIZE_GUIDE: dict[int, str] = {
    8: "tiny icon or particle",
    16: "small item, pickup, bullet, small UI icon",
    24: "small character or enemy",
    32: "standard character sprite, medium icon",
    48: "large character, boss, detailed sprite",
    64: "large boss, detailed scene element, portrait",
    128: "very large boss, splash art, title element",
}

# Category-specific prompt additions
CATEGORY_HINTS: dict[str, str] = {
    "character": "full body visible, clear silhouette, distinct from background",
    "enemy": "menacing pose, clear silhouette, visually distinct threat",
    "boss": "imposing, larger presence, detailed design, multiple visual elements",
    "item": "recognizable at small size, iconic shape, clear purpose",
    "projectile": "motion implied, directional, small and clear",
    "ui_icon": "clear at small size, high contrast, universally readable",
    "background": "tileable, subtle pattern, does not distract from foreground",
    "effect": "energetic, dynamic, translucent feel",
    "npc": "friendly appearance, approachable, distinct outfit or feature",
    "tileset": "seamlessly tileable edges, consistent lighting direction",
}


def build_image_prompt(
    subject: str,
    size: int = 32,
    style: str = "pixel_modern",
    facing: str = "front",
    category: str = "",
    extra: str = "",
) -> str:
    """Build a complete image generation prompt from parameters.

    The LLM provides subject/size/style/facing.
    This function adds quality enforcement and category hints.
    """
    parts: list[str] = []

    # Style preset
    style_desc = STYLE_PRESETS.get(style, style if style else STYLE_PRESETS["pixel_modern"])
    parts.append(style_desc)

    # Subject
    parts.append(subject)

    # Facing
    if facing and facing != "front":
        parts.append(f"facing {facing}")

    # Category hint
    if category:
        hint = CATEGORY_HINTS.get(category.lower(), "")
        if hint:
            parts.append(hint)

    # Size context
    size_hint = SIZE_GUIDE.get(size, "")
    if size_hint:
        parts.append(f"designed to work at {size}x{size} pixels, {size_hint}")

    # Extra user instructions
    if extra:
        parts.append(extra)

    # Background enforcement
    parts.append(BG_INSTRUCTION)

    # Quality enforcement (always last)
    parts.append(QUALITY_SUFFIX)

    return ", ".join(parts)
