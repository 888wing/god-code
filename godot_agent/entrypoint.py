import sys


MIN_VERSION = (3, 12)


def main() -> None:
    if sys.version_info < MIN_VERSION:
        version = ".".join(str(part) for part in MIN_VERSION)
        raise SystemExit(f"god-code requires Python {version}+")
    from godot_agent.cli import main as cli_main

    cli_main()
