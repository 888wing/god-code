# Contributing to God Code

Thank you for your interest in contributing!

## Getting Started

```bash
git clone https://github.com/888wing/god-code.git
cd god-code
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Development Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Write tests first (TDD encouraged)
3. Implement the feature
4. Run tests: `python -m pytest tests/ -v`
5. Commit with descriptive messages
6. Open a Pull Request

## Code Style

- Python 3.12+ with type annotations
- Follow existing patterns in the codebase
- Use `pydantic` for tool input/output models
- New tools inherit from `BaseTool` in `godot_agent/tools/base.py`

## Adding a New Tool

1. Create `godot_agent/tools/your_tool.py`
2. Implement a class inheriting `BaseTool` with `Input`, `Output`, and `execute()`
3. Register it in `godot_agent/cli.py:build_registry()`
4. Add tests in `tests/tools/test_your_tool.py`

## Adding Godot Knowledge

Edit `godot_agent/prompts/godot_playbook.py` to add new sections. Each section has:
- Title
- Keywords (for auto-selection)
- Content (injected into system prompt when relevant)

## Reporting Issues

- Use GitHub Issues
- Include: Python version, Godot version, god-code version, error output
- For API errors: include the status code and error message (not your API key)

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0.
