# From Empty Project To First Verified Change

This walkthrough is meant for a brand-new user who wants to go from **an empty Godot project** to **one small change that God Code can actually verify**.

The goal is not to build a full game in one shot. The goal is to create the smallest loop that proves:

1. God Code can read your project
2. God Code can make a Godot-aware change
3. God Code can run validation/review instead of only claiming success

## What You'll Build

A minimal UI scene:

- `res://scenes/main_menu.tscn`
- `res://scripts/main_menu.gd`
- a `Control` root
- a centered `Label`
- a simple script stub

That is a good first verified change because it is:

- small
- easy to inspect
- unlikely to involve complicated gameplay assumptions
- still a real `.tscn` + `.gd` change that God Code can validate

## Before You Start

You need:

- Python 3.12+
- `god-code` installed
- a working `godot` executable, or a configured `godot_path`
- an API key or OAuth path for the provider you plan to use

Install:

```bash
pip install god-code
```

If you want MCP support too:

```bash
pip install "god-code[mcp]"
```

## Step 1: Create the Smallest Valid Godot Project

Create an empty directory and initialize a Godot project in it.

The easiest way is with the Godot editor:

1. open Godot
2. create a new project in `./my-first-god-code-demo`
3. close the editor once `project.godot` exists

At this point your directory can still be basically empty apart from:

```text
my-first-god-code-demo/
└── project.godot
```

This is enough for God Code to treat it as a project root.

## Step 2: Start God Code

```bash
god-code chat --project ./my-first-god-code-demo
```

If this is your first run in an interactive terminal, God Code will guide you through:

1. provider selection
2. API key or OAuth setup
3. optional model/base URL defaults

If you already configured it before, you will go straight into chat.

## Step 3: Check the Session State

Inside chat, run:

```text
/status
```

You want to confirm:

- provider is correct
- model is what you expect
- auth is configured
- project path points to your new Godot project

If the Godot executable is not on your `PATH`, set it now:

```text
/set godot_path /absolute/path/to/godot
```

or use:

```text
/menu -> Edit setting -> godot_path
```

## Step 4: Make a Safe First Request

Use a prompt like this:

```text
Create a safe first UI scene at res://scenes/main_menu.tscn with a Control root named MainMenu, attach res://scripts/main_menu.gd, add a centered Label that says "Hello from God Code", and validate the project after the change. Keep the implementation minimal and do not add extra systems.
```

Why this prompt works well:

- it asks for a small change
- it names exact target files
- it asks for validation
- it explicitly tells the agent not to overbuild

## Step 5: What God Code Should Do

In a normal successful run, God Code should move through something like this:

1. inspect the project
2. possibly create a short plan
3. create `scenes/main_menu.tscn`
4. create `scripts/main_menu.gd`
5. run validation / review passes
6. summarize what was verified

Depending on your current mode and project state, it may also:

- ask an intent question if your project direction is unclear
- mention warnings if validation could not fully run
- ask you to fix `godot_path` if Godot is not available

## Step 6: Inspect the Result

After the turn finishes, check:

```bash
find ./my-first-god-code-demo -maxdepth 3 -type f | sort
```

You should now see something like:

```text
my-first-god-code-demo/project.godot
my-first-god-code-demo/scenes/main_menu.tscn
my-first-god-code-demo/scripts/main_menu.gd
```

You can also inspect inside chat with:

```text
/workspace
/status
```

or ask:

```text
Explain what you created and which parts were actually validated.
```

## Step 7: Know What Counts As “Verified”

For this first example, a good result is:

- the files were created in the expected paths
- the scene/script structure is coherent
- God Code reports a validation/reviewer result
- the final answer distinguishes verified facts from assumptions

A weak result is:

- “done” with no mention of validation
- files created in unexpected paths
- extra gameplay systems added without being asked
- the agent claiming success when Godot was not actually available

## Step 8: Open the Scene in Godot

Open the project in Godot and inspect `res://scenes/main_menu.tscn`.

At this stage, you are not checking whether the game is fun yet. You are checking that the first assistant-driven change is:

- structurally clean
- visible in the editor
- easy to continue from

## Good Follow-Up Requests

Once the first change is stable, good next prompts are:

- `Set res://scenes/main_menu.tscn as the main scene and validate the project.`
- `Add a Start button under the label and keep the layout minimal.`
- `Create a design memory entry that this project is a bullet-hell prototype with scripted enemy patterns.`
- `Plan the smallest next step toward a playable prototype without editing files yet.`

## Bad Follow-Up Requests

Avoid jumping straight to:

- “build the whole game”
- “add enemy AI, bullets, upgrades, UI, audio, save system, and title screen”
- “refactor everything to a scalable architecture”

That is exactly how you lose the build-and-verify discipline that makes God Code useful.

## Recommended First Session Checklist

- `project.godot` exists
- provider/model/auth are correct
- `godot_path` is usable
- first request is small and specific
- validation was attempted
- reviewer output was surfaced
- you can open the changed files in Godot afterward

Once that loop works, you are ready to move from “installation succeeded” to “agent-assisted game iteration actually works”.
