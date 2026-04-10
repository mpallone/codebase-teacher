"""Detect infrastructure components using LLM analysis."""

from __future__ import annotations

from codebase_teacher.llm.prompt_registry import PROMPTS
from codebase_teacher.llm.provider import LLMProvider, Message
from codebase_teacher.llm.structured import parse_model_list
from codebase_teacher.storage.models import InfraComponent


async def detect_infrastructure(
    provider: LLMProvider,
    file_contents: dict[str, str],
    infra_hints: list[str] | None = None,
) -> list[InfraComponent]:
    """Detect infrastructure components from source code using LLM analysis.

    The scanner's ``infra_hints`` are treated as authoritative: every hint
    becomes at least a baseline :class:`InfraComponent` in the result, even if
    the LLM returns nothing or fails to parse. The LLM's response is then
    merged on top, so it can enrich hint-based components with usage details
    and add components the scanner missed.

    Args:
        provider: LLM provider to use.
        file_contents: Dict of {relative_path: file_content} for relevant files.
        infra_hints: Pre-detected infrastructure hints from dependency scanning.

    Returns:
        List of detected infrastructure components. Guaranteed to contain at
        least one entry per infra hint (if any were provided).
    """
    baseline = _baseline_from_hints(infra_hints or [])

    if not file_contents and not baseline:
        return []

    llm_components: list[InfraComponent] = []
    if file_contents:
        code_chunks = _build_code_chunks(file_contents, infra_hints)

        prompt = PROMPTS["detect_infrastructure"]
        messages = [
            Message(role="system", content=prompt.format_system()),
            Message(role="user", content=prompt.format_user(code_chunks=code_chunks)),
        ]

        response = await provider.complete(messages)
        try:
            llm_components = parse_model_list(response.content, InfraComponent)
        except Exception:
            llm_components = []

    return _merge_components(baseline, llm_components)


def _build_code_chunks(
    file_contents: dict[str, str],
    infra_hints: list[str] | None = None,
) -> str:
    """Format file contents and hints for inclusion in a prompt."""
    parts: list[str] = []

    if infra_hints:
        parts.append(
            "Infrastructure hints from dependency analysis (already confirmed "
            "by repo scanning — include each as a component in your response):\n"
            + "\n".join(f"- {h}" for h in infra_hints)
        )

    for path, content in file_contents.items():
        parts.append(f"### File: {path}\n```\n{content}\n```")

    return "\n\n".join(parts)


# Mapping from scanner hint strings (see scanner/dependency.py) to a baseline
# InfraComponent. Keys are matched case-insensitively as substrings of the hint
# so small phrasing changes in the scanner don't silently break the baseline.
_HINT_BASELINE: tuple[tuple[str, InfraComponent], ...] = (
    (
        "docker",
        InfraComponent(
            type="container",
            technology="Docker",
            explanation=(
                "Docker packages applications and their dependencies into "
                "portable container images that run the same way across "
                "development, CI, and production."
            ),
            usage="Dockerfile / docker-compose present in the repository.",
        ),
    ),
    (
        "kubernetes",
        InfraComponent(
            type="orchestration",
            technology="Kubernetes",
            explanation=(
                "Kubernetes is a container orchestration platform that "
                "schedules, scales, and manages containerized workloads."
            ),
            usage="Kubernetes manifests detected in the repository.",
        ),
    ),
    (
        "terraform",
        InfraComponent(
            type="iac",
            technology="Terraform",
            explanation=(
                "Terraform is an infrastructure-as-code tool that provisions "
                "cloud resources from declarative HCL configuration."
            ),
            usage="Terraform (*.tf) files detected in the repository.",
        ),
    ),
    (
        "kafka",
        InfraComponent(
            type="queue",
            technology="Kafka",
            explanation=(
                "Apache Kafka is a distributed event streaming platform used "
                "for high-throughput publish/subscribe messaging and log "
                "aggregation."
            ),
            usage="Kafka client library detected in project dependencies.",
        ),
    ),
    (
        "redis",
        InfraComponent(
            type="cache",
            technology="Redis",
            explanation=(
                "Redis is an in-memory key-value store used for caching, "
                "session storage, pub/sub, and lightweight queues."
            ),
            usage="Redis client detected in project dependencies.",
        ),
    ),
    (
        "celery",
        InfraComponent(
            type="queue",
            technology="Celery",
            explanation=(
                "Celery is a Python distributed task queue that runs "
                "background jobs against a broker like Redis or RabbitMQ."
            ),
            usage="Celery detected in project dependencies.",
        ),
    ),
    (
        "rabbitmq",
        InfraComponent(
            type="queue",
            technology="RabbitMQ",
            explanation=(
                "RabbitMQ is a message broker that implements AMQP for "
                "reliable asynchronous messaging between services."
            ),
            usage="RabbitMQ client detected in project dependencies.",
        ),
    ),
    (
        "postgresql",
        InfraComponent(
            type="database",
            technology="PostgreSQL",
            explanation=(
                "PostgreSQL is an open-source relational database with strong "
                "SQL support, ACID transactions, and rich data types."
            ),
            usage="PostgreSQL driver detected in project dependencies.",
        ),
    ),
    (
        "mysql",
        InfraComponent(
            type="database",
            technology="MySQL",
            explanation=(
                "MySQL is a widely deployed open-source relational database."
            ),
            usage="MySQL driver detected in project dependencies.",
        ),
    ),
    (
        "mongodb",
        InfraComponent(
            type="database",
            technology="MongoDB",
            explanation=(
                "MongoDB is a document-oriented NoSQL database that stores "
                "JSON-like records."
            ),
            usage="MongoDB driver detected in project dependencies.",
        ),
    ),
    (
        "sql database",
        InfraComponent(
            type="database",
            technology="SQL Database (SQLAlchemy)",
            explanation=(
                "The project uses SQLAlchemy, a Python SQL toolkit and ORM "
                "that talks to relational databases like PostgreSQL, MySQL, "
                "or SQLite."
            ),
            usage="SQLAlchemy detected in project dependencies.",
        ),
    ),
    (
        "elasticsearch",
        InfraComponent(
            type="storage",
            technology="Elasticsearch",
            explanation=(
                "Elasticsearch is a distributed search and analytics engine "
                "used for full-text search, logs, and metrics."
            ),
            usage="Elasticsearch client detected in project dependencies.",
        ),
    ),
    (
        "aws services",
        InfraComponent(
            type="cloud",
            technology="AWS",
            explanation=(
                "Amazon Web Services hosts managed cloud infrastructure — "
                "compute, storage, databases, queues, and more."
            ),
            usage="boto3 detected in project dependencies.",
        ),
    ),
    (
        "google cloud",
        InfraComponent(
            type="cloud",
            technology="Google Cloud",
            explanation=(
                "Google Cloud Platform provides managed cloud infrastructure "
                "and data services."
            ),
            usage="google-cloud client detected in project dependencies.",
        ),
    ),
    (
        "azure",
        InfraComponent(
            type="cloud",
            technology="Azure",
            explanation=(
                "Microsoft Azure provides managed cloud infrastructure and "
                "data services."
            ),
            usage="Azure SDK detected in project dependencies.",
        ),
    ),
    (
        "spark",
        InfraComponent(
            type="compute",
            technology="Apache Spark",
            explanation=(
                "Apache Spark is a distributed data processing engine for "
                "large-scale batch and streaming workloads."
            ),
            usage="PySpark detected in project dependencies.",
        ),
    ),
    (
        "databricks",
        InfraComponent(
            type="compute",
            technology="Databricks",
            explanation=(
                "Databricks is a managed Spark / lakehouse platform for "
                "running data and ML workloads at scale."
            ),
            usage="Databricks client detected in project dependencies.",
        ),
    ),
    (
        "grpc",
        InfraComponent(
            type="framework",
            technology="gRPC",
            explanation=(
                "gRPC is a high-performance RPC framework that uses Protocol "
                "Buffers over HTTP/2."
            ),
            usage="grpc detected in project dependencies.",
        ),
    ),
    (
        "fastapi",
        InfraComponent(
            type="framework",
            technology="FastAPI",
            explanation=(
                "FastAPI is a modern Python HTTP framework for building "
                "async APIs with automatic OpenAPI docs."
            ),
            usage="FastAPI detected in project dependencies.",
        ),
    ),
    (
        "flask",
        InfraComponent(
            type="framework",
            technology="Flask",
            explanation=(
                "Flask is a lightweight Python HTTP framework for building "
                "web apps and APIs."
            ),
            usage="Flask detected in project dependencies.",
        ),
    ),
    (
        "django",
        InfraComponent(
            type="framework",
            technology="Django",
            explanation=(
                "Django is a batteries-included Python web framework with "
                "an ORM, admin UI, and auth."
            ),
            usage="Django detected in project dependencies.",
        ),
    ),
)


def _baseline_from_hints(hints: list[str]) -> list[InfraComponent]:
    """Build a baseline list of InfraComponents from scanner hints.

    Each scanner hint that matches a known technology produces a fully
    populated :class:`InfraComponent` so the result is never empty just
    because the LLM failed to infer infrastructure from source files.
    Unrecognized hints still produce a minimal component so nothing the
    scanner detected is silently dropped.
    """
    baseline: list[InfraComponent] = []
    seen: set[str] = set()
    for hint in hints:
        matched = False
        hint_lower = hint.lower()
        for keyword, template in _HINT_BASELINE:
            if keyword in hint_lower:
                tech_key = template.technology.lower()
                if tech_key in seen:
                    matched = True
                    break
                baseline.append(template.model_copy())
                seen.add(tech_key)
                matched = True
                break
        if not matched:
            # Unknown hint — keep it anyway so scanner output isn't lost.
            tech_key = hint.lower()
            if tech_key in seen:
                continue
            baseline.append(
                InfraComponent(
                    type="other",
                    technology=hint,
                    explanation="Detected by repository scanning.",
                    usage=f"Hint from dependency analysis: {hint}",
                )
            )
            seen.add(tech_key)
    return baseline


def _normalize_tech(tech: str) -> str:
    """Extract the primary technology name for dedup comparison.

    Lowercases and strips any parenthetical or slash-qualified suffix, so
    both ``"Docker"`` and ``"Docker (containerization)"`` normalize to
    ``"docker"``. Deliberately does NOT collapse distinct technologies that
    happen to share a substring: ``"SQL"`` and ``"PostgreSQL"`` remain
    different, so a generic LLM entry doesn't silently replace a specific
    baseline entry.
    """
    primary = tech.split("(")[0].split("/")[0].strip().lower()
    return primary


def _merge_components(
    baseline: list[InfraComponent],
    llm_components: list[InfraComponent],
) -> list[InfraComponent]:
    """Merge LLM components into the baseline, deduping by technology.

    If the LLM returns an entry whose normalized technology name exactly
    matches a baseline entry, the LLM entry replaces the baseline entry —
    the LLM usually has richer usage and config details pulled from actual
    source files. Any LLM entries that don't match are appended.

    Normalization (see :func:`_normalize_tech`) only strips parenthetical
    qualifiers and lowercases. It does not do substring matching, so a
    generic LLM entry like ``"SQL"`` will not collapse a specific baseline
    entry like ``"PostgreSQL"``.
    """
    if not llm_components:
        return list(baseline)

    merged: list[InfraComponent] = list(baseline)

    for llm_comp in llm_components:
        llm_tech = _normalize_tech(llm_comp.technology)
        if not llm_tech:
            merged.append(llm_comp)
            continue

        replaced = False
        for i, existing in enumerate(merged):
            existing_tech = _normalize_tech(existing.technology)
            if not existing_tech:
                continue
            if llm_tech == existing_tech:
                merged[i] = llm_comp
                replaced = True
                break
        if not replaced:
            merged.append(llm_comp)

    return merged
