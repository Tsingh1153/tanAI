"""Image generation subsystem.

Generates images through an external backend behind a small interface, so a
local Stable Diffusion server (AUTOMATIC1111 / SD.Next / Forge) or an
OpenAI-compatible images API can be used interchangeably. Ollama does not do
image generation, so an external backend is required.
"""

from .base import ImageGenerator, ImageGenError
from .factory import build_image_generator

__all__ = ["ImageGenerator", "ImageGenError", "build_image_generator"]
