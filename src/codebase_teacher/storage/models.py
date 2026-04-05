"""Pydantic models for analysis results and storage."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Scanner models ---


class FolderDecision(BaseModel):
    """User's decision about a folder's relevance."""

    path: str
    status: str = Field(description="relevant, irrelevant, or unknown")


class FileInfo(BaseModel):
    """Information about a single source file."""

    path: str
    category: str = Field(description="source, test, config, infra, build, docs, data, unknown")
    language: str | None = None
    token_estimate: int = 0


class DependencyInfo(BaseModel):
    """Information about a project dependency."""

    name: str
    source: str = Field(description="File where this dependency was found")
    is_available: bool = True
    is_open_source: bool = True
    install_instructions: str | None = None


class DependencyReport(BaseModel):
    """Full dependency analysis report."""

    dependencies: list[DependencyInfo] = Field(default_factory=list)
    missing: list[DependencyInfo] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    infra_hints: list[str] = Field(default_factory=list)


# --- Analyzer models ---


class FunctionInfo(BaseModel):
    """Extracted function information."""

    name: str
    file_path: str
    line_number: int = 0
    signature: str = ""
    decorators: list[str] = Field(default_factory=list)
    docstring: str | None = None
    is_async: bool = False


class ClassInfo(BaseModel):
    """Extracted class information."""

    name: str
    file_path: str
    line_number: int = 0
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionInfo] = Field(default_factory=list)
    docstring: str | None = None


class ImportInfo(BaseModel):
    """Extracted import information."""

    module: str
    names: list[str] = Field(default_factory=list)
    is_relative: bool = False


class TerraformResource(BaseModel):
    """A Terraform resource, data source, module, variable, output, or provider."""

    kind: str = Field(description="resource, data, module, variable, output, provider, terraform, locals")
    type: str = ""
    name: str = ""
    file_path: str = ""
    line_number: int = 0


class CodebaseGraph(BaseModel):
    """Structured representation of a parsed codebase."""

    functions: list[FunctionInfo] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    terraform_resources: list[TerraformResource] = Field(default_factory=list)


class APIEndpoint(BaseModel):
    """A detected API endpoint."""

    method: str = ""
    path: str = ""
    handler: str = ""
    file: str = ""
    description: str = ""


class InfraComponent(BaseModel):
    """A detected infrastructure component."""

    type: str = ""
    technology: str = ""
    explanation: str = ""
    usage: str = ""
    config: str = ""


class DataFlow(BaseModel):
    """A traced data flow through the system."""

    name: str
    entry_points: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    mermaid_diagram: str = ""


class AnalysisResult(BaseModel):
    """Complete analysis result for a project."""

    codebase_graph: CodebaseGraph = Field(default_factory=CodebaseGraph)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    infrastructure: list[InfraComponent] = Field(default_factory=list)
    data_flows: list[DataFlow] = Field(default_factory=list)
    file_summaries: dict[str, str] = Field(default_factory=dict)
    module_summaries: dict[str, str] = Field(default_factory=dict)
    project_summary: str = ""
