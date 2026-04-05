# godot_agent/cli/engine_wiring.py
"""Engine construction, config I/O, and provider helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.llm.client import LLMClient, LLMConfig
from godot_agent.prompts.assembler import PromptAssembler, PromptContext
from godot_agent.prompts.skill_selector import (
    normalize_skill_mode,
    sanitize_skill_keys,
)
from godot_agent.runtime.config import AgentConfig, load_config
from godot_agent.runtime.engine import ConversationEngine
from godot_agent.runtime.modes import get_mode_spec
from godot_agent.runtime.providers import (
    PROVIDER_PRESETS,
    REASONING_EFFORT_LEVELS,
    infer_provider,
    normalize_provider,
)
from godot_agent.tools.analysis_tools import (
    AnalyzeImpactTool,
    CheckConsistencyTool,
    PlanUILayoutTool,
    ProjectDependencyGraphTool,
    ScaffoldAudioTool,
    ValidateAudioNodesTool,
    ValidateUILayoutTool,
    ValidateProjectTool,
)
from godot_agent.tools.editor_bridge import (
    GetRuntimeSnapshotTool,
    ListContractsTool,
    ListScenariosTool,
    RunPlaytestTool,
    RunScriptedPlaytestTool,
)
from godot_agent.tools.image_gen import GenerateSpriteTool
from godot_agent.tools.runtime_harness import (
    AdvanceTicksTool,
    CaptureViewportTool,
    CompareBaselineTool,
    GetEventsSinceTool,
    GetRuntimeStateTool,
    LoadSceneTool,
    PressActionTool,
    ReportFailureTool,
    SetFixtureTool,
    SliceSpriteSheetTool,
    ValidateSpriteImportsTool,
)
from godot_agent.tools.web_search import WebSearchTool
from godot_agent.tools.file_ops import EditFileTool, ReadFileTool, WriteFileTool
from godot_agent.tools.git import GitTool
from godot_agent.tools.godot_cli import RunGodotTool
from godot_agent.tools.list_dir import ListDirTool
from godot_agent.tools.registry import ToolRegistry
from godot_agent.tools.scene_tools import (
    AddSceneConnectionTool,
    AddSceneNodeTool,
    ReadSceneTool,
    RemoveSceneNodeTool,
    SceneTreeTool,
    WriteScenePropertyTool,
)
from godot_agent.tools.screenshot import ScreenshotTool
from godot_agent.tools.search import GlobTool, GrepTool
from godot_agent.tools.shell import RunShellTool
from godot_agent.tools.memory_tool import ReadDesignMemoryTool, UpdateDesignMemoryTool
from godot_agent.tools.script_tools import EditScriptTool, LintScriptTool, ReadScriptTool
from godot_agent.tools.vision_analysis import AnalyzeScreenshotTool
from godot_agent.tools.vision_scoring import ScoreScreenshotTool


# ── config persistence ─────────────────────────────────────────

def _save_config_data(config_path: Path, data: dict) -> Path:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2))
    config_path.chmod(0o600)
    return config_path


def _persist_config_updates(config_path: Path, updates: dict[str, object]) -> Path:
    data: dict = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return _save_config_data(config_path, data)


# ── auth helpers ───────────────────────────────────────────────

def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _provider_auth_issue(provider: str, api_key: str = "", oauth_token: str | None = None) -> str | None:
    normalized_provider = normalize_provider(provider)
    preset = PROVIDER_PRESETS.get(normalized_provider)

    if normalized_provider == "custom":
        return None

    if normalized_provider == "openai":
        if api_key or oauth_token:
            return None
        return "OpenAI requires an API key or an OAuth login."

    if not api_key:
        provider_name = preset.name if preset else normalized_provider
        return f"{provider_name} requires an API key."

    if preset and preset.key_prefix and not api_key.startswith(preset.key_prefix):
        return f"Current API key does not look like a {preset.name} key (expected prefix {preset.key_prefix})."

    return None


def _has_usable_provider_auth(cfg: AgentConfig) -> bool:
    return _provider_auth_issue(cfg.provider, cfg.api_key, cfg.oauth_token) is None


def _load_or_setup_config(config_path: Path) -> AgentConfig:
    # Resolve helpers through the *package* module so that
    # ``monkeypatch.setattr("godot_agent.cli.load_config", ...)`` works.
    import sys
    _pkg = sys.modules["godot_agent.cli"]
    _load = getattr(_pkg, "load_config", load_config)
    _interactive = getattr(_pkg, "_is_interactive_terminal", _is_interactive_terminal)

    cfg = _load(config_path)
    try:
        cfg.skill_mode = normalize_skill_mode(cfg.skill_mode)
    except ValueError:
        cfg.skill_mode = "auto"
    cfg.enabled_skills = sanitize_skill_keys(cfg.enabled_skills)
    cfg.disabled_skills = sanitize_skill_keys(cfg.disabled_skills)
    if _has_usable_provider_auth(cfg):
        return cfg

    if _interactive():
        _setup = getattr(_pkg, "_run_setup_wizard", None)
        if _setup is None:
            from godot_agent.cli.commands import _run_setup_wizard as _setup
        _setup(config_path)
        cfg = _load(config_path)
        if _has_usable_provider_auth(cfg):
            return cfg

    raise click.ClickException("Not configured. Run 'god-code setup' first.")


# ── provider preset / model helpers ────────────────────────────

def _apply_provider_preset(cfg: AgentConfig, provider_name: str) -> str:
    provider = normalize_provider(provider_name)
    if provider not in PROVIDER_PRESETS:
        available = ", ".join(PROVIDER_PRESETS.keys())
        raise ValueError(f"Unknown provider: {provider_name}. Available: {available}")
    preset = PROVIDER_PRESETS[provider]
    cfg.provider = provider
    if preset.base_url:
        cfg.base_url = preset.base_url
    if preset.model:
        cfg.model = preset.model
    return provider


def _sync_provider_from_model(cfg: AgentConfig, previous_provider: str, previous_base_url: str) -> str:
    inferred = infer_provider(base_url=cfg.base_url, model=cfg.model, provider="")
    cfg.provider = inferred
    previous_preset = PROVIDER_PRESETS.get(previous_provider)
    new_preset = PROVIDER_PRESETS.get(inferred)
    if (
        new_preset
        and new_preset.base_url
        and ((previous_preset and previous_base_url == previous_preset.base_url) or not cfg.base_url)
    ):
        cfg.base_url = new_preset.base_url
    return inferred


def _normalize_reasoning_effort(value: str) -> str:
    effort = value.strip().lower()
    if effort not in REASONING_EFFORT_LEVELS:
        allowed = ", ".join(REASONING_EFFORT_LEVELS)
        raise ValueError(f"Unknown effort: {value}. Allowed: {allowed}")
    return effort


# ── engine construction ────────────────────────────────────────

def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in [
        ReadFileTool, WriteFileTool, EditFileTool, ListDirTool,
        GrepTool, GlobTool, GitTool, RunShellTool, RunGodotTool, ScreenshotTool,
        ReadScriptTool, EditScriptTool, LintScriptTool,
        ReadSceneTool, SceneTreeTool, AddSceneNodeTool, WriteScenePropertyTool,
        AddSceneConnectionTool, RemoveSceneNodeTool,
        ValidateProjectTool, CheckConsistencyTool, ProjectDependencyGraphTool, AnalyzeImpactTool,
        PlanUILayoutTool, ValidateUILayoutTool, ScaffoldAudioTool, ValidateAudioNodesTool,
        ReadDesignMemoryTool, UpdateDesignMemoryTool,
        GetRuntimeSnapshotTool, RunPlaytestTool, RunScriptedPlaytestTool, ListScenariosTool, ListContractsTool,
        LoadSceneTool, SetFixtureTool, PressActionTool, AdvanceTicksTool,
        GetRuntimeStateTool, GetEventsSinceTool, CaptureViewportTool,
        CompareBaselineTool, ReportFailureTool,
        SliceSpriteSheetTool, ValidateSpriteImportsTool,
        GenerateSpriteTool, WebSearchTool,
        AnalyzeScreenshotTool, ScoreScreenshotTool,
    ]:
        registry.register(tool_cls())
    return registry


def build_engine(config: AgentConfig, project_root: Path) -> ConversationEngine:
    from godot_agent.tools.file_ops import set_project_root
    from godot_agent.tools.shell import set_safety_level
    set_project_root(project_root)
    set_safety_level(config.safety)

    llm_config = LLMConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        provider=config.provider,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        oauth_token=config.oauth_token,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        computer_use=config.computer_use,
        computer_use_environment=config.computer_use_environment,
        computer_use_display_width=config.computer_use_display_width,
        computer_use_display_height=config.computer_use_display_height,
        backend_url=config.backend_url,
        backend_api_key=config.backend_api_key,
        backend_provider_keys=config.backend_provider_keys,
    )
    client = LLMClient(llm_config)
    registry = build_registry()
    prompt_assembler = PromptAssembler(
        PromptContext(
            project_root=project_root,
            godot_path=config.godot_path,
            language=config.language,
            verbosity=config.verbosity,
            mode=config.mode,
            extra_prompt=config.extra_prompt,
        )
    )
    allowed_tools = set(get_mode_spec(config.mode).allowed_tools)
    dispatcher = AgentDispatcher(
        client=client,
        registry=registry,
        prompt_context=prompt_assembler.context,
        project_path=str(project_root),
        godot_path=config.godot_path,
        base_allowed_tools=allowed_tools,
    )
    system_prompt = prompt_assembler.build(
        user_hint="",
        skill_mode=config.skill_mode,
        enabled_skills=config.enabled_skills,
        disabled_skills=config.disabled_skills,
        active_tools=[tool.name for tool in registry.list_tools() if tool.name in allowed_tools],
    )
    engine = ConversationEngine(
        client=client,
        registry=registry,
        system_prompt=system_prompt,
        max_tool_rounds=config.max_turns,
        project_path=str(project_root),
        godot_path=config.godot_path,
        auto_validate=config.auto_validate,
        prompt_assembler=prompt_assembler,
        mode=config.mode,
        dispatcher=dispatcher,
    )
    engine.skill_mode = config.skill_mode
    engine.enabled_skills = list(config.enabled_skills)
    engine.disabled_skills = list(config.disabled_skills)
    engine.base_allowed_tools = set(allowed_tools)
    engine.allowed_tools = set(allowed_tools)
    engine._refresh_tool_scope()
    engine._refresh_system_prompt()
    return engine


# ── engine callbacks ───────────────────────────────────────────

def _wire_engine_callbacks(
    engine: ConversationEngine,
    display,
    cfg: AgentConfig,
) -> None:
    engine.on_tool_start = lambda name, args: display.tool_start(name, engine._summarize_args(name, args))
    engine.on_tool_end = lambda name, ok, summary: display.tool_result(name, ok, summary)
    engine.on_diff = lambda old, new, fn: display.show_diff(old, new, fn)
    engine.on_event = display.handle_event
    engine.auto_commit = cfg.auto_commit
    engine.use_streaming = cfg.streaming
    if cfg.streaming:
        engine.on_stream_start = display.agent_streaming_start
        engine.on_stream_chunk = display.agent_streaming_chunk
        engine.on_stream_end = display.agent_streaming_end
    else:
        engine.on_stream_start = None
        engine.on_stream_chunk = None
        engine.on_stream_end = None
    engine.on_commit_suggest = lambda: display.info("Changes made. Run 'git add -A && git commit' to save.")
