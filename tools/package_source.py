"""Create a clean source ZIP without recordings, caches or local environments."""

import hashlib
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    output = root.parent / "instrumentlab-v1.0.0.zip"
    ignored = {".git", ".venv", "venv", "__pycache__", "data", "build", "dist",
               ".pytest_cache", ".ruff_cache", ".idea", ".vscode"}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if not path.is_file() or any(part in ignored or part.endswith(".egg-info")
                                         for part in relative.parts):
                continue
            if path.suffix in {".pyc", ".sqlite3", ".whl", ".zip"}:
                continue
            archive.write(path, (Path(root.name) / relative).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        for required in ["README.md", "LICENSE", "start.cmd", "instrumentlab/__main__.py",
                         "docs/screenshot.png", "tests/test_protocol.py", ".github/workflows/tests.yml"]:
            assert "instrumentlab/" + required in names, required
        assert not any("/__pycache__/" in name or "/data/" in name for name in names)
    print(f"Archive: {output}")
    print(f"Files: {len(names)}, bytes: {output.stat().st_size}")
    print(f"SHA256: {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
