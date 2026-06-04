"""Tests for Vision API provider functionality."""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from knowcran.vision.provider import VisionProvider, _encode_image_as_data_url, _extract_content
from knowcran.vision.router import VisionRouter, create_router_from_config
from knowcran.vision.prompts import get_prompt_for_task, get_available_task_types


class TestVisionProvider:
    """Test VisionProvider functionality."""

    def test_provider_creation(self):
        provider = VisionProvider(
            name="test",
            api_base="https://api.example.com",
            api_key="test-key",
            model="gpt-4o",
        )
        assert provider.name == "test"
        assert provider.is_healthy is True

    def test_mark_unhealthy(self):
        provider = VisionProvider(
            name="test",
            api_base="https://api.example.com",
            api_key="test-key",
            model="gpt-4o",
        )
        provider.mark_unhealthy()
        assert provider.is_healthy is False
        assert provider._failure_count == 1

    def test_mark_healthy(self):
        provider = VisionProvider(
            name="test",
            api_base="https://api.example.com",
            api_key="test-key",
            model="gpt-4o",
        )
        provider.mark_unhealthy()
        provider.mark_healthy()
        assert provider.is_healthy is True
        assert provider._failure_count == 0


class TestEncodeImageAsDataUrl:
    """Test image encoding."""

    def test_encode_png(self, tmp_path):
        # Create a minimal PNG file
        png_path = tmp_path / "test.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = _encode_image_as_data_url(png_path)
        assert result.startswith("data:image/png;base64,")

    def test_encode_jpg(self, tmp_path):
        jpg_path = tmp_path / "test.jpg"
        jpg_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        result = _encode_image_as_data_url(jpg_path)
        assert result.startswith("data:image/jpeg;base64,")


class TestExtractContent:
    """Test content extraction from API response."""

    def test_extract_from_valid_response(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": "Test content"
                    }
                }
            ]
        }
        assert _extract_content(response) == "Test content"

    def test_extract_from_empty_response(self):
        response = {}
        assert _extract_content(response) == ""

    def test_extract_from_no_choices(self):
        response = {"choices": []}
        assert _extract_content(response) == ""


class TestVisionRouter:
    """Test VisionRouter functionality."""

    def test_router_creation(self):
        providers = [
            VisionProvider("test1", "https://api1.com", "key1", "model1"),
            VisionProvider("test2", "https://api2.com", "key2", "model2"),
        ]
        router = VisionRouter(providers)
        assert len(router.providers) == 2

    def test_get_healthy_provider(self):
        providers = [
            VisionProvider("test1", "https://api1.com", "key1", "model1"),
            VisionProvider("test2", "https://api2.com", "key2", "model2"),
        ]
        router = VisionRouter(providers)

        # First provider should be returned
        provider = router.get_healthy_provider()
        assert provider.name == "test1"

    def test_get_healthy_provider_all_unhealthy(self):
        providers = [
            VisionProvider("test1", "https://api1.com", "key1", "model1"),
            VisionProvider("test2", "https://api2.com", "key2", "model2"),
        ]
        router = VisionRouter(providers)

        # Mark all unhealthy
        for p in providers:
            p.mark_unhealthy()

        provider = router.get_healthy_provider()
        assert provider is None

    def test_reset_health(self):
        providers = [
            VisionProvider("test1", "https://api1.com", "key1", "model1"),
        ]
        router = VisionRouter(providers)

        providers[0].mark_unhealthy()
        router.reset_health()

        assert providers[0].is_healthy is True


class TestPrompts:
    """Test prompt functionality."""

    def test_get_describe_media_prompt(self):
        prompt = get_prompt_for_task("describe_media")
        assert "describe" in prompt.lower()
        assert "figure" in prompt.lower() or "table" in prompt.lower()

    def test_get_table_to_markdown_prompt(self):
        prompt = get_prompt_for_task("table_to_markdown")
        assert "markdown" in prompt.lower()
        assert "table" in prompt.lower()

    def test_invalid_task_type(self):
        with pytest.raises(ValueError):
            get_prompt_for_task("invalid_task")

    def test_get_available_task_types(self):
        types = get_available_task_types()
        assert "describe_media" in types
        assert "table_to_markdown" in types


class TestCreateRouterFromConfig:
    """Test router creation from config."""

    def test_create_router(self):
        config = [
            {
                "name": "test1",
                "api_base": "https://api1.com",
                "api_key": "key1",
                "model": "model1",
            },
            {
                "name": "test2",
                "api_base": "https://api2.com",
                "api_key": "key2",
                "model": "model2",
            },
        ]
        router = create_router_from_config(config)
        assert len(router.providers) == 2
        assert router.providers[0].name == "test1"
        assert router.providers[1].name == "test2"
