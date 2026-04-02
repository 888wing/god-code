import ast
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "godot_agent"
PYPROJECT_PATH = ROOT / "pyproject.toml"
README_PATH = ROOT / "README.md"


def _declared_min_python() -> tuple[int, int]:
    project = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))["project"]
    requires_python = project["requires-python"]
    match = re.fullmatch(r">=\s*(\d+)\.(\d+)", requires_python)
    assert match, f"Unexpected requires-python format: {requires_python!r}"
    return int(match.group(1)), int(match.group(2))


def _python_files() -> list[Path]:
    return sorted(
        path for path in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in path.parts
    )


def _has_future_annotations(module: ast.Module) -> bool:
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def _annotation_uses_pep604_union(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    return any(
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
        for node in ast.walk(annotation)
    )


def _module_uses_runtime_pep604_unions(module: ast.Module) -> bool:
    if _has_future_annotations(module):
        return False

    for node in ast.walk(module):
        if isinstance(node, ast.AnnAssign) and _annotation_uses_pep604_union(node.annotation):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _annotation_uses_pep604_union(node.returns):
                return True
            arguments = [*node.args.args, *node.args.kwonlyargs]
            if node.args.vararg is not None:
                arguments.append(node.args.vararg)
            if node.args.kwarg is not None:
                arguments.append(node.args.kwarg)
            if getattr(node.args, "posonlyargs", None):
                arguments.extend(node.args.posonlyargs)
            if any(_annotation_uses_pep604_union(arg.annotation) for arg in arguments):
                return True
    return False


def _module_uses_dataclass_slots(module: ast.Module) -> bool:
    for node in ast.walk(module):
        if not isinstance(node, ast.ClassDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func_name = None
            if isinstance(decorator.func, ast.Name):
                func_name = decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                func_name = decorator.func.attr
            if func_name != "dataclass":
                continue
            for keyword in decorator.keywords:
                if keyword.arg != "slots":
                    continue
                if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    return True
    return False


def test_requires_python_matches_documented_floor() -> None:
    assert _declared_min_python() == (3, 9)
    assert "Python 3.9+" in README_PATH.read_text(encoding="utf-8")


def test_declared_python_floor_covers_runtime_features() -> None:
    min_python = _declared_min_python()
    incompatible: list[str] = []

    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(path))
        rel_path = path.relative_to(ROOT)

        if min_python < (3, 10) and _module_uses_runtime_pep604_unions(module):
            incompatible.append(
                f"{rel_path}: uses PEP 604 union annotations without future annotations"
            )
        if min_python < (3, 10) and _module_uses_dataclass_slots(module):
            incompatible.append(
                f"{rel_path}: uses dataclass(slots=True), which requires Python 3.10+"
            )

    assert not incompatible, "Declared requires-python is too low:\n" + "\n".join(incompatible)


def test_declared_python_floor_parses_package_syntax() -> None:
    min_python = _declared_min_python()
    syntax_errors: list[str] = []

    for path in _python_files():
        source = path.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(path), feature_version=min_python)
        except SyntaxError as exc:
            rel_path = path.relative_to(ROOT)
            syntax_errors.append(f"{rel_path}:{exc.lineno}: {exc.msg}")

    assert not syntax_errors, (
        "Package source uses syntax newer than declared requires-python:\n"
        + "\n".join(syntax_errors)
    )
