"""Tests for kit_core.config."""

from __future__ import annotations

import os

from kit_core.config import KitConfig


class TestKitConfig:
    def test_defaults(self):
        config = KitConfig()
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.log_level == "INFO"
        assert config.environment == "development"
        assert config.debug is False

    def test_is_production(self):
        config = KitConfig(environment="production")
        assert config.is_production is True
        assert config.is_development is False

    def test_is_development(self):
        config = KitConfig(environment="development")
        assert config.is_development is True
        assert config.is_production is False

    def test_env_prefix(self, monkeypatch):
        monkeypatch.setenv("KIT_REDIS_URL", "redis://custom:6380/1")
        monkeypatch.setenv("KIT_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("KIT_ENVIRONMENT", "staging")
        monkeypatch.setenv("KIT_DEBUG", "true")

        config = KitConfig()
        assert config.redis_url == "redis://custom:6380/1"
        assert config.log_level == "DEBUG"
        assert config.environment == "staging"
        assert config.debug is True
