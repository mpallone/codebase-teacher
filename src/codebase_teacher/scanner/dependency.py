"""Detect project dependencies."""

from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

from codebase_teacher.storage.models import DependencyInfo, DependencyReport


def detect_dependencies(root: Path) -> DependencyReport:
    """Scan for dependency files and extract declared dependencies."""
    dependencies: list[DependencyInfo] = []
    config_files: list[str] = []
    infra_hints: list[str] = []

    # Check various dependency files
    for parser_name, parser_func in _PARSERS.items():
        dep_file = root / parser_name
        if dep_file.exists():
            config_files.append(parser_name)
            deps = parser_func(dep_file)
            dependencies.extend(deps)

    # Also scan for config files that hint at infrastructure
    infra_hints = _detect_infra_hints(root)

    return DependencyReport(
        dependencies=dependencies,
        config_files=config_files,
        infra_hints=infra_hints,
    )


def _parse_requirements_txt(path: Path) -> list[DependencyInfo]:
    """Parse requirements.txt format."""
    deps: list[DependencyInfo] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Extract package name (before any version specifier)
        match = re.match(r"([a-zA-Z0-9_-]+)", line)
        if match:
            deps.append(DependencyInfo(
                name=match.group(1),
                source=str(path.name),
            ))
    return deps


def _parse_pyproject_toml(path: Path) -> list[DependencyInfo]:
    """Parse dependencies from pyproject.toml."""
    deps: list[DependencyInfo] = []
    content = path.read_text()

    # Simple regex to find dependencies array
    in_deps = False
    for line in content.splitlines():
        if re.match(r'\s*dependencies\s*=\s*\[', line):
            in_deps = True
            continue
        if in_deps:
            if line.strip() == "]":
                in_deps = False
                continue
            match = re.search(r'"([a-zA-Z0-9_-]+)', line)
            if match:
                deps.append(DependencyInfo(
                    name=match.group(1),
                    source="pyproject.toml",
                ))
    return deps


def _parse_package_json(path: Path) -> list[DependencyInfo]:
    """Parse dependencies from package.json."""
    import json

    deps: list[DependencyInfo] = []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return deps

    for section in ("dependencies", "devDependencies"):
        for name in data.get(section, {}):
            deps.append(DependencyInfo(
                name=name,
                source="package.json",
            ))
    return deps


def _parse_go_mod(path: Path) -> list[DependencyInfo]:
    """Parse dependencies from go.mod."""
    deps: list[DependencyInfo] = []
    in_require = False
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("require ("):
            in_require = True
            continue
        if in_require:
            if line == ")":
                in_require = False
                continue
            parts = line.split()
            if parts:
                deps.append(DependencyInfo(
                    name=parts[0],
                    source="go.mod",
                ))
    return deps


_PARSERS: dict[str, callable] = {
    "requirements.txt": _parse_requirements_txt,
    "pyproject.toml": _parse_pyproject_toml,
    "package.json": _parse_package_json,
    "go.mod": _parse_go_mod,
}


# Known infrastructure indicators in dependency names
_INFRA_KEYWORDS = {
    "kafka": "Kafka (message queue)",
    "redis": "Redis (cache/store)",
    "celery": "Celery (task queue)",
    "sqlalchemy": "SQL Database (via SQLAlchemy)",
    "psycopg": "PostgreSQL",
    "pymongo": "MongoDB",
    "pymysql": "MySQL",
    "boto3": "AWS Services",
    "google-cloud": "Google Cloud Services",
    "azure": "Azure Services",
    "elasticsearch": "Elasticsearch",
    "pyspark": "Apache Spark",
    "databricks": "Databricks",
    "grpc": "gRPC",
    "fastapi": "FastAPI (HTTP framework)",
    "flask": "Flask (HTTP framework)",
    "django": "Django (HTTP framework)",
    "rabbitmq": "RabbitMQ (message queue)",
    "pika": "RabbitMQ (via pika)",
}


def _detect_infra_hints(root: Path) -> list[str]:
    """Detect infrastructure hints from dependency names and config files."""
    hints: list[str] = []

    # Check dependency files for infra keywords
    for dep_file_name in _PARSERS:
        dep_file = root / dep_file_name
        if not dep_file.exists():
            continue
        content = dep_file.read_text().lower()
        for keyword, description in _INFRA_KEYWORDS.items():
            if keyword in content and description not in hints:
                hints.append(description)

    # Check for Docker
    if (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists():
        hints.append("Docker (containerization)")

    # Check for Terraform
    if any(root.glob("*.tf")):
        hints.append("Terraform (infrastructure as code)")

    # Check for Kubernetes
    if any(root.glob("**/k8s/**")) or any(root.glob("**/*.k8s.yaml")):
        hints.append("Kubernetes (container orchestration)")

    return hints


def print_dependency_report(report: DependencyReport, console: Console | None = None) -> None:
    """Print a formatted dependency report."""
    console = console or Console()

    if report.config_files:
        console.print(f"\n[bold]Dependency files found:[/] {', '.join(report.config_files)}")

    if report.dependencies:
        console.print(f"[bold]Dependencies:[/] {len(report.dependencies)} packages")

    if report.infra_hints:
        console.print("\n[bold]Infrastructure detected:[/]")
        for hint in report.infra_hints:
            console.print(f"  - {hint}")
