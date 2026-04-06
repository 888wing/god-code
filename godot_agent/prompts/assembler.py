"""Prompt assembler with static and dynamic Godot-specific sections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from godot_agent.godot.impact_analysis import ImpactAnalysisReport, format_impact_report
from godot_agent.godot.project import parse_project_godot
from godot_agent.prompts.build_discipline import BUILD_DISCIPLINE_PROMPT
from godot_agent.prompts.genre_templates import format_genre_template
from godot_agent.prompts.knowledge_selector import format_knowledge_injection, select_sections
from godot_agent.prompts.skill_selector import format_skill_injection, resolve_skills
from godot_agent.runtime.design_memory import DesignMemory, format_design_memory
from godot_agent.runtime.design_memory import GameplayIntentProfile
from godot_agent.runtime.intent_resolver import format_gameplay_intent
from godot_agent.runtime.modes import mode_prompt
from godot_agent.runtime.playtest_harness import PlaytestReport, format_playtest_report
from godot_agent.runtime.quality_gate import QualityGateReport, format_quality_gate_report
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot, format_runtime_snapshot
from godot_agent.runtime.reviewer import ReviewReport, format_review_report

SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "---DYNAMIC_BOUNDARY---"


@dataclass
class PromptContext:
    project_root: Path
    godot_path: str = "godot"
    language: str = "en"
    verbosity: str = "normal"
    mode: str = "apply"
    extra_prompt: str = ""


class PromptAssembler:
    """Builds a task-aware prompt for each model turn."""

    def __init__(self, context: PromptContext):
        self.context = context
        self._static_prompt = self._build_static_prompt()

    def _build_static_prompt(self) -> str:
        sections = [_core_identity()]

        lang_map = {
            "zh-TW": "Always respond in Traditional Chinese (繁體中文).",
            "zh-CN": "Always respond in Simplified Chinese (简体中文).",
            "ja": "Always respond in Japanese (日本語).",
            "ko": "Always respond in Korean (한국어).",
        }
        if self.context.language in lang_map:
            sections.append(f"## Language\n\n{lang_map[self.context.language]}")

        if self.context.verbosity == "concise":
            sections.append("## Response Style\n\nBe extremely concise. No explanations unless asked. Just show the code changes.")
        elif self.context.verbosity == "detailed":
            sections.append("## Response Style\n\nBe thorough and detailed. Explain reasoning, tradeoffs, and residual risks.")

        sections.append(mode_prompt(self.context.mode))
        sections.append(_behavior_rules_section())
        sections.append(BUILD_DISCIPLINE_PROMPT)
        sections.append(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
        return "\n\n".join(sections)

    def _proactive_rules_section(self) -> str:
        return """## When to Pause and Ask

Before making changes, assess scope. If your plan would:
- Modify 5+ files → state the scope and ask "proceed?"
- Delete anything → list what will be removed and confirm
- Conflict with design memory → quote the conflict and ask

When the request is vague ("fix the UI", "improve performance"):
- List what you found and ask which to address
- Do NOT guess and act on all of them

Proceed without asking when scope is clear, contained (1-3 files), and reversible."""

    def _auto_plan_format_section(self) -> str:
        return """## Plan Output Format

Output plans in this format:

### Plan: [title]

**Scope**: [N] files | **Risk**: low/medium/high | **Steps**: [N]

1. [action] [target] — [description]
   Files: `path/file.gd`

2. [action] [target] — [description]
   Files: `path/file.tscn`

Risks: [if any]"""

    def build(
        self,
        *,
        user_hint: str = "",
        file_paths: list[str] | None = None,
        skill_mode: str = "auto",
        enabled_skills: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        active_tools: list[str] | None = None,
        project_scan: str = "",
        design_memory: DesignMemory | None = None,
        intent_profile: GameplayIntentProfile | None = None,
        impact_report: ImpactAnalysisReport | None = None,
        runtime_snapshot: RuntimeSnapshot | None = None,
        quality_report: QualityGateReport | None = None,
        review_report: ReviewReport | None = None,
        playtest_report: PlaytestReport | None = None,
        auto_mode: bool = False,
    ) -> str:
        sections = [self._static_prompt]

        skills = resolve_skills(
            user_hint,
            file_paths,
            max_skills=2,
            skill_mode=skill_mode,
            enabled_skills=enabled_skills,
            disabled_skills=disabled_skills,
            intent_profile=intent_profile,
        )
        if skills:
            sections.append(format_skill_injection(skills))

        knowledge_sections = select_sections(user_hint, file_paths, max_sections=4)
        if knowledge_sections:
            sections.append(format_knowledge_injection(knowledge_sections))

        sections.append(_project_context(self.context.project_root, self.context.godot_path))
        sections.append(_session_guidance(user_hint, file_paths or [], project_scan))

        if design_memory is not None:
            sections.append(format_design_memory(design_memory))
        if intent_profile is not None and not intent_profile.is_empty:
            sections.append(format_gameplay_intent(intent_profile))
            template_text = format_genre_template(intent_profile)
            if template_text:
                sections.append(template_text)

        if impact_report is not None:
            sections.append(format_impact_report(impact_report))

        if runtime_snapshot is not None:
            sections.append(format_runtime_snapshot(runtime_snapshot))

        if active_tools:
            sections.append(_available_tools(active_tools))

        if quality_report:
            sections.append("## Latest Quality Gate\n\n" + format_quality_gate_report(quality_report))

        if review_report:
            sections.append("## Latest Reviewer Report\n\n" + format_review_report(review_report))

        if playtest_report:
            sections.append("## Latest Playtest Report\n\n" + format_playtest_report(playtest_report))

        if self.context.extra_prompt:
            sections.append(f"## Custom Instructions\n\n{self.context.extra_prompt}")

        # Add proactive rules always
        sections.append(self._proactive_rules_section())
        # Add auto plan format when in auto mode
        if auto_mode:
            sections.append(self._auto_plan_format_section())

        return "\n\n".join(section for section in sections if section.strip())


def _core_identity() -> str:
    return """# God Code — Godot Game Development Agent

You are an expert coding agent specialized for Godot 4.4 game development. You understand GDScript, .tscn scene files, .tres resources, shaders, and Godot architecture deeply.

Your primary job is to ship high-quality playable game features, not merely elegant source code.

## Core Principles

1. Composition over inheritance for gameplay systems
2. Signal up, call down for scene communication
3. Data-driven design with Resources and @export values
4. Static typing for gameplay-critical scripts
5. _physics_process for movement and collision logic
6. Validate changes before claiming success"""


def _behavior_rules_section() -> str:
    return """## Behavior Rules (Mandatory)

1. Read the existing code and scene structure before editing.
2. Prefer small, local, mechanically verifiable changes.
3. Optimize for gameplay correctness, scene integrity, and maintainability.
4. Do not add features the user did not request.
5. Treat validation failures, broken resource paths, and scene graph inconsistencies as blockers.
6. Use Godot-aware tools when editing scenes or scripts.
7. Distinguish validated outcomes from inference.
8. If warnings remain, mention them explicitly instead of pretending the task is fully complete.
9. Preserve working scene hierarchies unless a structural change is required.
10. Prefer fixes that keep the project runnable at each intermediate step."""


def _project_context(project_root: Path, godot_path: str) -> str:
    project_file = project_root / "project.godot"
    if not project_file.exists():
        return "## Project Context\n\nNo project.godot found in working directory."

    proj = parse_project_godot(project_file)
    lines = [
        "## Project Context",
        "",
        f"- Project Root: `{project_root}`",
        f"- Godot Path: `{godot_path}`",
        f"- Project: {proj.name}",
        f"- Resolution: {proj.viewport_width}x{proj.viewport_height}",
    ]
    if proj.version:
        lines.append(f"- Version: {proj.version}")
    if proj.main_scene:
        lines.append(f"- Main Scene: {proj.main_scene}")
    if proj.renderer:
        lines.append(f"- Renderer: {proj.renderer}")
    if proj.autoloads:
        lines.append("\n### Autoloads")
        for name, path in proj.autoloads.items():
            lines.append(f"- `{name}` -> `{path}`")
    return "\n".join(lines)


def _session_guidance(user_hint: str, file_paths: list[str], project_scan: str) -> str:
    lines = ["## Current Task Context", ""]
    if user_hint:
        lines.append(f"- User task: {user_hint}")
    if file_paths:
        lines.append(f"- Recently touched files: {', '.join(file_paths[:20])}")
    if project_scan:
        lines.append("\n### Project Scan")
        lines.append(project_scan[:2500])
    return "\n".join(lines)


def _available_tools(active_tools: list[str]) -> str:
    return "## Available Tools\n\n" + "\n".join(f"- `{tool_name}`" for tool_name in active_tools)
