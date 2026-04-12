"""Classify files by type and language using filename patterns and heuristics."""

from __future__ import annotations

from pathlib import Path

from codebase_teacher.llm.context_manager import estimate_tokens
from codebase_teacher.storage.models import FileInfo

# Language detection by extension
LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".scala": "scala",
    ".kt": "kotlin",
    ".swift": "swift",
    ".r": "r",
    ".R": "r",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".tf": "terraform",
    ".hcl": "hcl",
}

# Config file patterns
CONFIG_PATTERNS = {
    ".env", ".env.example", ".env.local",
    "config.yaml", "config.yml", "config.json", "config.toml",
    "settings.yaml", "settings.yml", "settings.json", "settings.py",
    "application.properties", "application.yml",
    ".eslintrc", ".prettierrc", "tsconfig.json", "babel.config.js",
}

CONFIG_EXTENSIONS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties"}

# Infrastructure file patterns
INFRA_PATTERNS = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Jenkinsfile", "Procfile",
    ".github", ".circleci", ".gitlab-ci.yml",
}

INFRA_EXTENSIONS = {".tf", ".hcl", ".tfvars"}

# Build file patterns
BUILD_PATTERNS = {
    "pyproject.toml", "setup.py", "setup.cfg",
    "package.json", "package-lock.json", "yarn.lock",
    "pom.xml", "build.gradle", "build.sbt",
    "Cargo.toml", "go.mod", "go.sum",
    "requirements.txt", "Pipfile", "Pipfile.lock", "poetry.lock",
    "Gemfile", "Gemfile.lock",
}

# Test file patterns
TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec.", "tests/", "test/", "__tests__/"}

# Doc extensions
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}


def classify_file(path: Path, root: Path) -> FileInfo:
    """Classify a single file into a category."""
    rel_path = str(path.relative_to(root))
    name = path.name
    ext = path.suffix.lower()
    language = LANGUAGE_MAP.get(ext)

    # Determine category
    category = _determine_category(path, rel_path, name, ext)

    # Estimate tokens
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        tokens = estimate_tokens(content)
    except (OSError, UnicodeDecodeError):
        tokens = 0

    return FileInfo(
        path=rel_path,
        category=category,
        language=language,
        token_estimate=tokens,
    )


def _determine_category(path: Path, rel_path: str, name: str, ext: str) -> str:
    """Determine the file category based on patterns."""
    # Check test patterns first
    rel_lower = rel_path.lower()
    for pattern in TEST_PATTERNS:
        if pattern in rel_lower:
            return "test"

    # Check infra patterns
    if name in INFRA_PATTERNS or ext in INFRA_EXTENSIONS:
        return "infra"
    if any(part in INFRA_PATTERNS for part in path.parts):
        return "infra"

    # Check build patterns
    if name in BUILD_PATTERNS:
        return "build"

    # Check config patterns
    if name in CONFIG_PATTERNS or ext in CONFIG_EXTENSIONS:
        return "config"

    # Check documentation
    if ext in DOC_EXTENSIONS:
        return "docs"

    # Check data files
    if ext in {".csv", ".json", ".xml", ".parquet", ".avro"}:
        return "data"

    # Check if it's source code
    if ext in LANGUAGE_MAP:
        return "source"

    return "unknown"


def classify_directory(root: Path, relevant_folders: list[str]) -> list[FileInfo]:
    """Classify all files in the relevant folders."""
    files: list[FileInfo] = []

    for folder_rel in relevant_folders:
        folder = root / folder_rel if folder_rel != "." else root
        if not folder.is_dir():
            continue

        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            # Skip binary files and very large files
            if path.suffix.lower() in {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".jar", ".class"}:
                continue
            if path.stat().st_size > 1_000_000:  # Skip files > 1MB
                continue
            files.append(classify_file(path, root))

    return files
