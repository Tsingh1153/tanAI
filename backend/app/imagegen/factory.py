"""Build the configured image generator."""

from __future__ import annotations

from ..config import Settings
from .automatic1111 import Automatic1111Generator
from .base import ImageGenerator
from .openai_images import OpenAIImagesGenerator


def build_image_generator(settings: Settings) -> ImageGenerator:
    if settings.image_backend == "openai":
        return OpenAIImagesGenerator(
            base_url=settings.image_server_url,
            api_key=settings.image_api_key or None,
            model=settings.image_model or None,
            timeout=settings.request_timeout,
        )
    # Default: AUTOMATIC1111-compatible local Stable Diffusion server.
    return Automatic1111Generator(settings.image_server_url, settings.request_timeout)
