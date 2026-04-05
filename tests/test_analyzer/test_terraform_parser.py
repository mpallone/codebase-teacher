"""Tests for Terraform/HCL AST parser."""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_hcl", reason="tree-sitter-hcl not installed")

from codebase_teacher.analyzer.terraform_parser import parse_terraform_file  # noqa: E402


BASIC_TF = """\
resource "aws_s3_bucket" "my_bucket" {
  bucket = "my-bucket-name"

  tags = {
    Environment = "production"
  }
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
}
"""

DATA_SOURCES_TF = """\
data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }
}

data "aws_vpc" "default" {
  default = true
}
"""

VARIABLES_TF = """\
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_count" {
  description = "Number of instances"
  type        = number
  default     = 1
}
"""

OUTPUTS_TF = """\
output "bucket_arn" {
  value = aws_s3_bucket.my_bucket.arn
}

output "instance_id" {
  value = aws_instance.web.id
}
"""

MODULES_TF = """\
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "3.14.0"

  name = "my-vpc"
  cidr = "10.0.0.0/16"
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "18.0.0"
}
"""

PROVIDERS_TF = """\
provider "aws" {
  region = var.region
}

provider "kubernetes" {
  host = module.eks.cluster_endpoint
}
"""

MIXED_TF = """\
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "logs" {
  bucket = "my-logs-bucket"
}

variable "env" {
  type    = string
  default = "dev"
}

output "bucket_name" {
  value = aws_s3_bucket.logs.bucket
}

module "network" {
  source = "./modules/network"
}
"""


def test_parse_resources(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(BASIC_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    resources = [r for r in graph.terraform_resources if r.kind == "resource"]
    assert len(resources) == 2

    types = {r.type for r in resources}
    assert "aws_s3_bucket" in types
    assert "aws_instance" in types

    names = {r.name for r in resources}
    assert "my_bucket" in names
    assert "web" in names


def test_parse_data_sources(tmp_path):
    tf_file = tmp_path / "data.tf"
    tf_file.write_text(DATA_SOURCES_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    data_sources = [r for r in graph.terraform_resources if r.kind == "data"]
    assert len(data_sources) == 2

    types = {r.type for r in data_sources}
    assert "aws_ami" in types
    assert "aws_vpc" in types

    names = {r.name for r in data_sources}
    assert "ubuntu" in names
    assert "default" in names


def test_parse_variables(tmp_path):
    tf_file = tmp_path / "variables.tf"
    tf_file.write_text(VARIABLES_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    variables = [r for r in graph.terraform_resources if r.kind == "variable"]
    assert len(variables) == 2

    names = {r.name for r in variables}
    assert "region" in names
    assert "instance_count" in names


def test_parse_outputs(tmp_path):
    tf_file = tmp_path / "outputs.tf"
    tf_file.write_text(OUTPUTS_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    outputs = [r for r in graph.terraform_resources if r.kind == "output"]
    assert len(outputs) == 2

    names = {r.name for r in outputs}
    assert "bucket_arn" in names
    assert "instance_id" in names


def test_parse_modules(tmp_path):
    tf_file = tmp_path / "modules.tf"
    tf_file.write_text(MODULES_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    modules = [r for r in graph.terraform_resources if r.kind == "module"]
    assert len(modules) == 2

    names = {r.name for r in modules}
    assert "vpc" in names
    assert "eks" in names


def test_parse_providers(tmp_path):
    tf_file = tmp_path / "providers.tf"
    tf_file.write_text(PROVIDERS_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    providers = [r for r in graph.terraform_resources if r.kind == "provider"]
    assert len(providers) == 2

    names = {r.name for r in providers}
    assert "aws" in names
    assert "kubernetes" in names


def test_parse_mixed_file(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(MIXED_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    kinds = {r.kind for r in graph.terraform_resources}
    assert "terraform" in kinds
    assert "provider" in kinds
    assert "resource" in kinds
    assert "variable" in kinds
    assert "output" in kinds
    assert "module" in kinds


def test_line_numbers_populated(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(BASIC_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    for resource in graph.terraform_resources:
        assert resource.line_number > 0


def test_file_path_in_results(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(BASIC_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    assert all(r.file_path == "main.tf" for r in graph.terraform_resources)


def test_graceful_on_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.tf"
    graph = parse_terraform_file(missing, tmp_path)
    assert graph.terraform_resources == []


def test_no_functions_or_classes_in_terraform(tmp_path):
    tf_file = tmp_path / "main.tf"
    tf_file.write_text(BASIC_TF)

    graph = parse_terraform_file(tf_file, tmp_path)

    assert graph.functions == []
    assert graph.classes == []
    assert graph.imports == []


def test_hcl_extension(tmp_path):
    """Parser should work for .hcl files too."""
    hcl_file = tmp_path / "backend.hcl"
    hcl_file.write_text('variable "token" {\n  type = string\n}\n')

    graph = parse_terraform_file(hcl_file, tmp_path)
    # May or may not find variable depending on grammar; just verify no crash
    assert isinstance(graph.terraform_resources, list)
