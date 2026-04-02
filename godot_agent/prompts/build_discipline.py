from __future__ import annotations

"""Build discipline rules injected into system prompt.

Enforces incremental build-and-verify workflow to prevent
the "build everything then test" anti-pattern.
"""

BUILD_DISCIPLINE_PROMPT = """## Build Discipline (MANDATORY)

You MUST follow incremental build-and-verify. Never create more than 2-3 files before running validation.

### Workflow

1. **Create project.godot first** → run `godot --headless --quit` → verify zero errors
2. **Create one scene + script pair** → validate → fix errors → next pair
3. **After each scene**: run headless validation before creating the next
4. **After all scenes**: run the full game to verify scene transitions work

### Validation Command

After creating/modifying any .tscn or .gd file:
```
godot --headless --quit 2>&1
```
If ANY error appears, fix it BEFORE creating new files.

### Error Response Protocol

When Godot reports an error:
1. Read the error message — identify file path and line number
2. Read the offending file
3. Fix the specific issue
4. Re-run validation
5. Only proceed when zero errors

### Scene Creation Order

For a new game project, create files in this order:
1. project.godot (with autoloads and input map)
2. Autoload scripts (game_manager.gd etc.)
3. Shared resources (visual_config.gd etc.)
4. Core entity scenes bottom-up (bullet → player → enemy → boss)
5. UI scenes (hud → title → game_over)
6. Main game scene (references all above)
7. Validate everything loads

### .tscn Format Rules

When writing .tscn files:
- [gd_scene] header FIRST
- [ext_resource] declarations SECOND
- [sub_resource] declarations THIRD (BEFORE any [node])
- [node] declarations FOURTH
- [connection] declarations LAST
- load_steps = count(ext_resource) + count(sub_resource) + 1

NEVER put [sub_resource] after [node] — Godot will fail to parse the file.
"""
