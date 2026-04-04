# Install

## Requirements

- Python 3.12+
- a working Godot executable if you want validation, screenshots, runtime harness, or playtest flows

## Install From PyPI

```bash
pip install god-code
```

With MCP support:

```bash
pip install "god-code[mcp]"
```

## Local Development Install

```bash
git clone https://github.com/888wing/god-code.git
cd god-code
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp,docs]"
```

## Verify The Install

```bash
god-code --version
god-code status
```

If this is your first run and you are in an interactive terminal, `god-code` or `god-code chat` will guide you through provider setup.

## Build The Docs Locally

```bash
mkdocs serve
```

Then open the local URL shown by MkDocs.
