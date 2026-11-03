"""Bundle clean repository files into public/blogger-content-engine.zip."""

import os
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ZIP = ROOT_DIR / "public" / "blogger-content-engine.zip"

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".idea",
    ".vscode",
}

EXCLUDE_FILES = {
    ".env",
    "public/blogger-content-engine.zip",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".zip",
}

INCLUDED_PREFIXES = [
    ".github",
    "config",
    "data",
    "scripts",
    "src",
    "templates",
    "tests",
    "worker",
    "LICENSE",
    "README.md",
    "package.json",
    "server.ts",
    "tsconfig.json",
    "vite.config.ts",
    "index.html",
    ".gitignore",
    ".env.example",
]


def bundle():
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    print(f"Bundling repository files to {OUTPUT_ZIP}...")
    file_count = 0

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zipf:
        for prefix in INCLUDED_PREFIXES:
            target = ROOT_DIR / prefix
            if not target.exists():
                continue

            if target.is_file():
                rel = target.relative_to(ROOT_DIR)
                zipf.write(target, arcname=str(rel))
                file_count += 1
            else:
                for root, dirs, files in os.walk(target):
                    # Filter directories in place
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

                    for f in files:
                        p = Path(root) / f
                        rel = p.relative_to(ROOT_DIR)
                        if any(rel.match(f"*{suf}") for suf in EXCLUDE_SUFFIXES):
                            continue
                        if str(rel) in EXCLUDE_FILES:
                            continue
                        zipf.write(p, arcname=str(rel))
                        file_count += 1

    print(f"Successfully packaged {file_count} files into {OUTPUT_ZIP} ({OUTPUT_ZIP.stat().st_size} bytes).")


if __name__ == "__main__":
    bundle()
