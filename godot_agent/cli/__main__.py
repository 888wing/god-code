# godot_agent/cli/__main__.py
"""Allow ``python -m godot_agent.cli`` to work."""
from godot_agent.cli.commands import main

if __name__ == "__main__":
    main()
