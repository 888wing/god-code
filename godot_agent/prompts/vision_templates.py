"""Vision prompt templates for LLM-based screenshot analysis of Godot games.

Three base prompts for different analysis modes:
- ANALYSIS_PROMPT: Comprehensive screenshot analysis (UI, visuals, layout)
- ITERATION_PROMPT: Before/after comparison with severity ratings
- SCORING_PROMPT: Structured scoring on multiple dimensions (1-5 scale, JSON)

Builder functions compose focus- or criteria-specific variants.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Base prompts
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """\
You are analyzing a screenshot from a Godot Engine game. Examine the image \
carefully and provide a structured analysis covering the following areas:

## Visual Quality
- Pixel art consistency (aliasing, palette coherence, scaling artifacts)
- Color palette harmony and contrast ratios
- Readability of text, icons, and interactive elements
- Rendering artifacts or visual glitches (z-fighting, texture bleeding, etc.)

## Layout & Composition
- Spatial arrangement of UI elements and scene objects
- Alignment, spacing, and visual hierarchy
- Screen real-estate usage (cluttered vs. wasted space)
- Responsive considerations (safe margins, aspect-ratio assumptions)

## Godot-Specific Observations
- Theme/StyleBox consistency across Control nodes
- Potential node-tree issues visible in the output (overlapping panels, wrong draw order)
- Shader artifacts or missing materials
- Font rendering quality (bitmap vs. MSDF, scaling issues)

Provide your findings as a bulleted list grouped by section. \
Flag the single most critical issue as **TOP PRIORITY**.\
"""

ITERATION_PROMPT = """\
You are comparing two screenshots from a Godot Engine game — the previous \
version and the current version. Analyze what changed and rate each change.

For every difference you detect:
1. Describe the change concisely.
2. Classify the change: IMPROVEMENT, REGRESSION, or NEUTRAL.
3. Rate the SEVERITY on a 1-5 scale:
   - 1 = cosmetic, barely noticeable
   - 2 = minor visual polish
   - 3 = noticeable UX or layout shift
   - 4 = significant quality change affecting usability
   - 5 = critical change (broken layout, missing elements, rendering failure)

Format each finding as:
- **[CLASSIFICATION] (SEVERITY N)**: <description>

End with a summary: overall direction (better / worse / mixed) and the single \
highest-severity item to address next.\
"""

SCORING_PROMPT = """\
You are scoring a Godot Engine game screenshot on multiple quality dimensions. \
For each dimension, assign an integer score from 1-5 where:
  1 = poor / broken
  2 = below average / noticeable issues
  3 = acceptable / functional
  4 = good / polished
  5 = excellent / professional quality

Return your response as a JSON object with the following structure:
{
  "scores": {
    "<dimension>": <1-5>,
    ...
  },
  "overall": <1-5>,
  "summary": "<one-sentence overall assessment>",
  "top_issue": "<single most impactful improvement opportunity>"
}

Be precise and critical. A score of 5 means genuinely professional-grade quality.\
"""

# ---------------------------------------------------------------------------
# Focus-specific sections for analysis prompt
# ---------------------------------------------------------------------------

_FOCUS_SECTIONS: dict[str, str] = {
    "general": """\

## Additional Focus: General Quality
- Overall first impression and visual coherence
- Layout clarity and information hierarchy
- Any element that feels out of place or unfinished
- Consistency between different parts of the screen\
""",
    "ui": """\

## Additional Focus: UI Element Detection
- Identify every interactive control (buttons, sliders, menus, health bars, etc.)
- Check touch/click target sizes and spacing for usability
- Verify label text is legible at the rendered size
- Assess visual feedback states (hover, pressed, disabled, focus)
- Detect overlapping or clipped UI nodes
- Evaluate theme consistency (font family, corner radius, color tokens)\
""",
    "gameplay": """\

## Additional Focus: Gameplay Scene Analysis
- Character/entity visibility and silhouette clarity
- Gameplay readability (can the player parse threats, pickups, interactables?)
- Background-foreground separation and depth cues
- HUD integration — does it inform without obscuring the play area?
- Animation frame or sprite-sheet artifacts visible in the still frame
- Collision shape alignment hints (sprites that look offset from expected bounds)\
""",
}

# ---------------------------------------------------------------------------
# Criteria-specific rubrics for scoring prompt
# ---------------------------------------------------------------------------

_SCORING_RUBRICS: dict[str, str] = {
    "demo_quality": """\

Score on these dimensions:
- "visual_polish": Art consistency, color harmony, no placeholder assets
- "ui_completeness": All expected UI elements present and functional-looking
- "layout_quality": Clean alignment, good spacing, professional composition
- "text_readability": All text legible, appropriate font sizes, good contrast
- "first_impression": Would a player trust this as a finished product?\
""",
    "visual_polish": """\

Score on these dimensions:
- "art_consistency": Uniform pixel density, palette coherence, style unity
- "color_harmony": Palette balance, contrast ratios, mood consistency
- "animation_quality": Smooth transitions, no jarring frame jumps (if visible)
- "shader_quality": Clean effects, no banding or artifacts
- "theme_cohesion": UI and game world share a unified visual language\
""",
}

_DEFAULT_RUBRIC = """\

Score on these dimensions:
- "visual_quality": Overall rendering quality and art consistency
- "layout": Spatial arrangement, alignment, spacing
- "readability": Text clarity, icon recognition, information hierarchy
- "completeness": No missing or placeholder elements visible
- "polish": Professional finish, attention to detail\
"""

# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------


def build_analysis_prompt(focus: str = "general") -> str:
    """Compose an analysis prompt with a focus-specific section.

    Parameters
    ----------
    focus:
        One of ``"general"``, ``"ui"``, ``"gameplay"``.
        Unknown values fall back to ``"general"``.

    Returns
    -------
    str
        Full analysis prompt ready to send alongside a screenshot.
    """
    section = _FOCUS_SECTIONS.get(focus, _FOCUS_SECTIONS["general"])
    return ANALYSIS_PROMPT + section


def build_scoring_prompt(criteria: str = "demo_quality") -> str:
    """Compose a scoring prompt with a criteria-specific rubric.

    Parameters
    ----------
    criteria:
        One of ``"demo_quality"``, ``"visual_polish"``.
        Unknown values use a sensible default rubric.

    Returns
    -------
    str
        Full scoring prompt requesting JSON output on a 1-5 scale.
    """
    rubric = _SCORING_RUBRICS.get(criteria, _DEFAULT_RUBRIC)
    return SCORING_PROMPT + rubric
