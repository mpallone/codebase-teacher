"""Named prompt templates for all LLM interactions.

All prompts live here so they can be versioned, tested, and swapped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    """A named prompt with system and user message templates."""

    system: str
    user: str
    version: str = "1.0"

    def format_system(self, **kwargs: str) -> str:
        return self.system.format(**kwargs) if kwargs else self.system

    def format_user(self, **kwargs: str) -> str:
        return self.user.format(**kwargs)


PROMPTS: dict[str, PromptTemplate] = {
    "summarize_file": PromptTemplate(
        system=(
            "You are a senior software architect analyzing a codebase to help onboard "
            "new engineers. Be precise and concise. Focus on what the code does, not how "
            "the language works. Assume the reader is a senior engineer who is smart but "
            "unfamiliar with this specific codebase."
        ),
        user=(
            "Summarize this source file. Include:\n"
            "1. Purpose: What does this file/module do? (1-2 sentences)\n"
            "2. Key abstractions: Classes, functions, or interfaces defined (with signatures)\n"
            "3. Dependencies: What does it import/depend on?\n"
            "4. Data flow role: Is this an input, transformation, output, or utility?\n"
            "5. Infrastructure: Does it interact with databases, message queues, APIs, etc.?\n\n"
            "File: {file_path}\n\n"
            "```\n{code}\n```"
        ),
    ),
    "detect_apis": PromptTemplate(
        system=(
            "You are analyzing a codebase to identify all API endpoints and external interfaces. "
            "Be thorough — find HTTP routes, gRPC services, Kafka consumers/producers, "
            "CLI commands, and any other entry points."
        ),
        user=(
            "Identify all API endpoints and external interfaces in these files.\n"
            "For each endpoint, provide:\n"
            "- Method and path (e.g., GET /api/users)\n"
            "- Handler function and file\n"
            "- Request/response format if visible\n"
            "- Authentication requirements if visible\n\n"
            "Return your answer as a JSON array of objects with keys: "
            "method, path, handler, file, description.\n\n"
            "{code_chunks}"
        ),
    ),
    "detect_infrastructure": PromptTemplate(
        system=(
            "You are analyzing a codebase to identify all infrastructure dependencies. "
            "Infrastructure includes any external system, runtime, or deployment technology "
            "the codebase relies on. Look broadly across these categories:\n"
            "- Databases: MySQL, PostgreSQL, MongoDB, SQLite, Redis, DynamoDB, etc.\n"
            "- Message queues / streaming: Kafka, RabbitMQ, SQS, Pub/Sub, etc.\n"
            "- Caches and stores: Redis, Memcached, etc.\n"
            "- Cloud services: S3, GCS, Lambda, etc.\n"
            "- Compute / data platforms: Spark, Databricks, Airflow, etc.\n"
            "- Containers and runtimes: Docker, docker-compose, containerd.\n"
            "- Orchestration: Kubernetes, ECS, Nomad, Helm.\n"
            "- Infrastructure as code: Terraform, CloudFormation, Pulumi, Ansible.\n"
            "- CI/CD: GitHub Actions, CircleCI, Jenkins, GitLab CI.\n"
            "- HTTP frameworks when they are the primary runtime (Flask, FastAPI, Django, etc.).\n"
            "A Dockerfile, docker-compose file, Terraform module, or Kubernetes manifest IS "
            "infrastructure and must be reported — do not skip it because it is not a database "
            "or queue. Explain each piece of infrastructure briefly for someone unfamiliar with it."
        ),
        user=(
            "Identify all infrastructure components used in this codebase.\n\n"
            "If 'Infrastructure hints from dependency analysis' are provided below, each hint "
            "represents infrastructure that has already been confirmed by scanning the repo "
            "(dependency files, Dockerfiles, Terraform files, etc.). You MUST include every "
            "hint as a component in your response, enriched with any details you can glean "
            "from the code. You may also add additional components that the hints missed.\n\n"
            "For each component, provide:\n"
            "- Type (database, queue, cache, storage, compute, container, orchestration, "
            "iac, ci-cd, framework, etc.)\n"
            "- Specific technology (e.g., PostgreSQL, Kafka, Docker, Terraform)\n"
            "- Brief explanation of what this technology does (1-2 sentences)\n"
            "- How it's used in this codebase (reference specific files when possible)\n"
            "- Configuration details if visible (ports, image tags, env vars, etc.)\n\n"
            "Return as JSON array with keys: type, technology, explanation, usage, config. "
            "Return at minimum one entry per hint. Write each explanation from your own "
            "knowledge — do not leave it blank. If you truly find no infrastructure and "
            "there are no hints, return an empty array [].\n\n"
            "Example — given the hint 'Docker (containerization)' and a Dockerfile:\n"
            '[{{"type": "container", "technology": "Docker", '
            '"explanation": "Docker packages applications into portable container images.", '
            '"usage": "Dockerfile builds a Python 3.11 image running gunicorn.", '
            '"config": "EXPOSE 80"}}]\n\n'
            "{code_chunks}"
        ),
    ),
    "trace_data_flow": PromptTemplate(
        system=(
            "You are a senior software architect tracing data flows through a codebase. "
            "Identify how data enters the system, how it is transformed, and where it goes. "
            "Think of each flow as a pipeline: input -> processing -> output."
        ),
        user=(
            "Given these module summaries, trace the major data flows in this system.\n"
            "For each flow:\n"
            "1. Name it descriptively\n"
            "2. Identify entry points (API endpoints, consumers, cron jobs)\n"
            "3. List the processing steps in order\n"
            "4. Identify outputs (DB writes, API responses, messages published)\n"
            "5. Generate a Mermaid sequence diagram\n\n"
            "Return as JSON array with keys: name, entry_points, steps, outputs, mermaid_diagram.\n\n"
            "{summaries}"
        ),
    ),
    "generate_architecture_doc": PromptTemplate(
        system=(
            "You are writing architecture documentation for a senior engineer who is new to "
            "this codebase. Write clearly, use examples, and explain infrastructure concepts "
            "(like Kafka, Databricks) briefly when they appear. Include Mermaid diagrams."
        ),
        user=(
            "Generate a comprehensive architecture document for this codebase.\n\n"
            "Project summary:\n{project_summary}\n\n"
            "Module summaries:\n{module_summaries}\n\n"
            "Data flows:\n{data_flows}\n\n"
            "Infrastructure:\n{infrastructure}\n\n"
            "APIs:\n{apis}\n\n"
            "Include:\n"
            "1. System overview with a Mermaid architecture diagram\n"
            "2. Component descriptions\n"
            "3. Data flow explanations\n"
            "4. Infrastructure dependencies with brief explanations\n"
            "5. Key design decisions (if apparent)\n\n"
            "Format as Markdown."
        ),
    ),
    "generate_api_doc": PromptTemplate(
        system=(
            "You are writing API documentation for a senior engineer new to this codebase. "
            "Be thorough, include examples, and explain the data model."
        ),
        user=(
            "Generate API reference documentation.\n\n"
            "APIs found:\n{apis}\n\n"
            "Data flows:\n{data_flows}\n\n"
            "Include for each endpoint:\n"
            "- Method, path, description\n"
            "- Request parameters and body\n"
            "- Response format with examples\n"
            "- Related data flows\n\n"
            "Format as Markdown."
        ),
    ),
    "generate_infra_doc": PromptTemplate(
        system=(
            "You are writing infrastructure documentation for a senior engineer who may be "
            "unfamiliar with the specific technologies used. Explain what each technology "
            "does and how it's used in this project."
        ),
        user=(
            "Generate infrastructure documentation.\n\n"
            "Infrastructure components:\n{infrastructure}\n\n"
            "Include for each component:\n"
            "- What the technology is and what it does (brief explainer)\n"
            "- How it's used in this codebase\n"
            "- Configuration details\n"
            "- A Mermaid diagram showing how components connect\n\n"
            "Format as Markdown."
        ),
    ),
}
