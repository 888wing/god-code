"""Godot 4.4 Game Development Playbook — stored as structured knowledge sections.

Each section is a tuple of (title, keywords, content) for selective injection
into the system prompt based on task context.
"""
from __future__ import annotations

SECTIONS: list[tuple[str, list[str], str]] = [

("Engine Philosophy", ["godot", "architecture", "scene", "node", "design"], """
Godot uses a composition-based "everything is a node, everything is a scene" architecture:
- Scene = reusable, instantiable, inheritable node tree (can be character, weapon, UI, level)
- Composition over inheritance — split features into small scenes and nest them
- Each node is self-contained, communicates via parent-child relationships and signals
- Editor IS the engine — @tool scripts run game logic in the editor
- 2D and 3D have separate rendering engines; 2D uses pixels as base unit
"""),

("Project Structure", ["project", "structure", "directory", "organize", "folder"], """
project_root/
├── project.godot       # Project settings (don't manually edit complex fields)
├── addons/             # Third-party plugins & custom tools
├── assets/             # Art, audio, fonts (sprites/, audio/, fonts/, shaders/)
├── scenes/             # .tscn scene files (organized by feature)
├── scripts/            # .gd scripts (matching scene structure)
├── resources/          # .tres custom resource files
└── export/             # Export settings (not version controlled)

Naming: files/folders use snake_case, scene root nodes use PascalCase.
"""),

("GDScript Style", ["style", "naming", "format", "convention", "lint", "type"], """
Naming: files=snake_case, classes=PascalCase, functions/vars=snake_case, signals=snake_case(past tense), constants=CONSTANT_CASE, private=_prefix.

Code ordering (MUST follow):
1. @tool  2. class_name  3. extends  4. ## doc comment
5. signals  6. enums  7. constants  8. static vars
9. @export vars  10. regular vars  11. @onready vars
12. lifecycle methods (_ready, _process, _physics_process)
13. public methods  14. private methods

Formatting: Tab indent, max 100 chars/line, use 0.5/13.0 for floats, use and/or/not (not &&/||/!), trailing comma in multiline lists.

Type annotations (strongly recommended):
var health: int = 100
func calc_damage(base: int, mult: float) -> int:
@onready var timer: Timer = $Timer
"""),

("Node Types", ["node", "sprite", "character", "area", "control", "ui", "label", "button"], """
2D: Node2D, Sprite2D, AnimatedSprite2D, CharacterBody2D (player/NPC), RigidBody2D (physics), StaticBody2D (walls), Area2D (triggers), CollisionShape2D, TileMapLayer, Camera2D, ParallaxBackground
UI: Control, Label, Button, TextureRect, ProgressBar, HBox/VBoxContainer, GridContainer, MarginContainer, PanelContainer, ScrollContainer, TabContainer, CenterContainer
Tools: Timer, AudioStreamPlayer/2D/3D, AnimationPlayer, AnimationTree, SubViewport
"""),

("Lifecycle", ["ready", "process", "physics", "init", "enter_tree", "exit_tree", "lifecycle"], """
_init() → object constructed, NO scene tree access
_enter_tree() → node added to tree (children may not be ready)
_ready() → node + all children ready. Initialize here. Called once.
_process(delta) → every frame (follows FPS). For: visuals, UI, non-physics logic.
_physics_process(delta) → fixed rate (default 60Hz). For: movement, physics, collision.
_input(event) → any input event
_unhandled_input(event) → input not consumed by UI. Game controls go HERE.
_exit_tree() → node leaving tree (cleanup here)

CRITICAL: Use _physics_process for movement/collision, NOT _process.
"""),

("Signals", ["signal", "emit", "connect", "event", "communicate"], """
Signals are Godot's preferred node communication. Rule: "signal up, call down".

signal health_changed(new_hp: int)  # past tense names
signal died

# Connect in _ready:
$Button.pressed.connect(_on_button_pressed)
died.connect(_on_died, CONNECT_ONE_SHOT)  # one-shot

# await:
await enemy.died
await get_tree().create_timer(2.0).timeout

Naming: ALWAYS past tense (door_opened, enemy_killed, score_changed). NEVER present tense.
"""),

("Export System", ["export", "inspector", "range", "enum", "category", "group"], """
@export var speed: float = 200.0
@export_range(0, 100) var hp: int = 100
@export_enum("Warrior", "Mage") var char_class: int
@export_file("*.json") var config: String
@export_category("Stats")
@export_group("Combat")
@export var attack: int = 10
@export var items: Array[String] = []
@export_flags_2d_physics var collision_layers: int
"""),

("Physics & Collision", ["collision", "layer", "mask", "physics", "body", "area", "characterbody", "rigidbody"], """
Node selection:
- Walls/floors (static) → StaticBody2D/3D
- Player/NPC (code-controlled) → CharacterBody2D/3D
- Projectiles/boxes (physics sim) → RigidBody2D/3D
- Triggers/detection zones → Area2D/3D

STANDARD collision layer plan:
Layer 1: Player         Layer 5: Enemy Projectiles
Layer 2: Enemies        Layer 6: Pickups/Items
Layer 3: Terrain/Walls  Layer 7: Triggers/Areas
Layer 4: Player Proj    Layer 8: Interactables

Examples:
- Player: Layer=1, Mask=2,3,6,8
- Enemy: Layer=2, Mask=1,3,4
- Player bullet: Layer=4, Mask=2,3
- Enemy bullet: Layer=5, Mask=1

CharacterBody2D template:
func _physics_process(delta: float) -> void:
    if not is_on_floor(): velocity += get_gravity() * delta
    var direction := Input.get_axis("move_left", "move_right")
    velocity.x = direction * SPEED if direction else move_toward(velocity.x, 0, SPEED)
    move_and_slide()
"""),

("Animation & Tween", ["animation", "tween", "animate", "flash", "ease", "animationplayer"], """
AnimationPlayer:
anim.play("idle")
await anim.animation_finished

Tween (programmatic):
var tween := create_tween()
tween.tween_property(sprite, "modulate", Color.RED, 0.1)
tween.tween_property(sprite, "modulate", Color.WHITE, 0.1)

Parallel: create_tween().set_parallel(true)
Easing: .set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)

WARNING: create_tween() bound to node — freed when node freed.
Use get_tree().create_tween() for independent tweens.
"""),

("Input Handling", ["input", "key", "action", "move", "controller", "keyboard"], """
ALWAYS use Input Map actions, NEVER hardcode keys:
if Input.is_action_just_pressed("jump"): jump()
var dir := Input.get_vector("left", "right", "up", "down")

_input: global (pause menus). Call get_viewport().set_input_as_handled() to stop propagation.
_unhandled_input: game controls (avoids firing while UI open).
_physics_process + Input: continuous input (movement).
"""),

("UI System", ["ui", "control", "layout", "anchor", "container", "theme", "hud", "menu"], """
Layout: Anchors (0.0-1.0 relative positioning) + Containers (auto-arrange children).
Containers: HBox/VBoxContainer, GridContainer, MarginContainer, PanelContainer.
Size Flags: SIZE_EXPAND_FILL for equal-width buttons.
Theme: Set on root Control, children inherit. Override per-node as needed.
"""),

("Resources", ["resource", "preload", "load", "tres", "data", "save"], """
preload (compile-time, constant path): const Bullet := preload("res://scenes/bullet.tscn")
load (runtime, variable path): var level := load("res://levels/level_%d.tscn" % n)
Engine caches loaded resources — repeated load() doesn't re-read disk.

Custom Resource (data-driven design):
class_name WeaponData extends Resource
@export var damage: int = 10
@export var projectile: PackedScene

Save: ResourceSaver.save(data, "user://save.tres")
Load: load("user://save.tres") as SaveData

user:// = writable user data dir. res:// = read-only project dir.
"""),

("Autoload & Global", ["autoload", "global", "singleton", "manager", "event_bus", "scene_change"], """
Use Autoload for: global state, scene transitions, audio manager, event bus.
DON'T use for: single-scene logic, data modification managers.

Event Bus pattern:
# autoloads/event_bus.gd
signal player_died
signal score_changed(new_score: int)
# Any script: EventBus.player_died.emit()

NEVER free() an Autoload node.

Scene transition: call_deferred("_deferred_change") to finish current frame first.
"""),

("Design Patterns", ["pattern", "state_machine", "object_pool", "component", "pool", "fsm"], """
State Machine: StateMachine node with State children. transition_to(name) switches states.
Each State has enter(), exit(), update(delta), physics_update(delta).

Object Pool (CRITICAL for bullet hells):
Pre-instantiate N objects, hide inactive ones. get_instance() shows one, release() hides it.
Avoids instantiate/queue_free overhead for frequently spawned objects.

Component Pattern: Split functionality into child nodes.
Enemy → HealthComponent, HitboxComponent, HurtboxComponent, MovementComponent
Each component is a reusable scene with its own signals.

Command Pattern: Use Callable arrays for queueable/undoable actions.
"""),

("Performance", ["performance", "optimize", "fast", "slow", "fps", "memory", "cache"], """
1. Measure before optimizing — use built-in Profiler
2. Cache node references with @onready (NOT get_node every frame)
3. Use static types (faster than dynamic)
4. Reuse arrays instead of creating new ones each frame
5. Use is_zero_approx/is_equal_approx for float comparison
6. Physics in _physics_process, visuals in _process
7. Use Timer nodes for infrequent updates
8. call_deferred for tree modifications during iteration
9. remove_child (not just hide) for truly inactive nodes
10. set_process(false) / set_physics_process(false) when off-screen

Lightweight alternatives: Node (heavy) → Resource → RefCounted → Object (lightest)
"""),

("Common Mistakes", ["error", "mistake", "bug", "wrong", "avoid", "trap", "pitfall"], """
DON'T access scene tree in _init() → use _ready()
DON'T assume other scenes exist in _ready() → use signals or call_deferred
DON'T modify RigidBody position directly → use apply_force/impulse
DON'T do physics in _process → use _physics_process
DON'T forget CollisionShape on physics bodies → no shape = no collision
DON'T hardcode node paths → use @export or @onready
DON'T overuse Autoload → only for truly global state
DON'T modify scene tree while iterating → use call_deferred
DON'T forget queue_free() → memory leak
DON'T put all logic in one script → use Component pattern
DON'T serialize Vector2/3 to JSON directly → split to x,y,z or use var_to_str()
"""),

("Godot 4.4 Features", ["4.4", "new", "feature", "tilemaplayer", "abstract"], """
- TileMapLayer replaces old TileMap (use multiple layers as separate nodes)
- @abstract annotation for abstract classes/methods
- Variadic functions: func sum(...values)
- Typed Dictionary: Dictionary[String, int]
- Pattern guards: match value: pattern when condition
- @export_tool_button for Inspector buttons
- @export_custom for low-level export hints
- @export_storage for serialize-only (no Inspector display)
"""),

]

def get_all_keywords() -> set[str]:
    """Return all keywords across all sections."""
    keywords: set[str] = set()
    for _, kws, _ in SECTIONS:
        keywords.update(kws)
    return keywords


def get_section(title: str) -> str | None:
    """Get a section's content by title."""
    for t, _, content in SECTIONS:
        if t == title:
            return content.strip()
    return None


def get_full_text() -> str:
    """Return the entire playbook as a single string."""
    parts: list[str] = []
    for title, _, content in SECTIONS:
        parts.append(f"### {title}\n{content.strip()}")
    return "\n\n".join(parts)
