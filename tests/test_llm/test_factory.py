"""Tests for the provider factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codebase_teacher.core.config import Settings
from codebase_teacher.llm.factory import create_provider


class TestCreateProvider:
    def test_claude_code_provider(self):
        settings = Settings(provider="claude-code")
        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
            provider = create_provider(settings)
        from codebase_teacher.llm.cli_provider import ClaudeCodeProvider
        assert isinstance(provider, ClaudeCodeProvider)

    def test_litellm_provider(self):
        settings = Settings(provider="litellm")
        provider = create_provider(settings)
        from codebase_teacher.llm.litellm_adapter import LiteLLMProvider
        assert isinstance(provider, LiteLLMProvider)

    def test_litellm_passes_model_and_max_tokens(self):
        settings = Settings(provider="litellm", model="openai/gpt-4", max_tokens=4096)
        provider = create_provider(settings)
        assert provider.model_name == "openai/gpt-4"
        assert provider.max_tokens == 4096

    def test_claude_code_passes_max_tokens(self):
        settings = Settings(provider="claude-code", max_tokens=8192)
        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
            provider = create_provider(settings)
        assert provider.max_tokens == 8192

    def test_unknown_provider_raises(self):
        settings = Settings(provider="unknown")
        with pytest.raises(ValueError, match="Unknown provider.*unknown"):
            create_provider(settings)

    def test_default_provider_is_claude_code(self):
        settings = Settings()
        assert settings.provider == "claude-code"

    def test_claude_code_passes_timeout(self):
        settings = Settings(provider="claude-code", cli_timeout=900)
        with patch("codebase_teacher.llm.cli_provider.shutil.which", return_value="/usr/bin/claude"):
            provider = create_provider(settings)
        assert provider._timeout == 900

    def test_default_cli_timeout_is_600(self):
        settings = Settings()
        assert settings.cli_timeout == 600
