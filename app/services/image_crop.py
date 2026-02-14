"""
AI-powered image crop detection for circular meal thumbnails.

This service uses Claude API to detect the center point of food in meal images,
allowing for smart circular cropping in the meal history view.
"""

import base64
import logging
from pathlib import Path
from typing import Tuple

from anthropic import Anthropic

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = Anthropic(api_key=settings.anthropic_api_key)


async def detect_meal_center(image_path: str) -> Tuple[float, float]:
    """
    Use Claude API to detect the center point of the meal in an image.

    This function analyzes a meal image and returns coordinates for optimal
    circular cropping. The coordinates represent the center point of the food
    as percentages from the top-left corner.

    Args:
        image_path: Path to the meal image file

    Returns:
        Tuple of (x%, y%) coordinates from top-left corner (0-100)
        Defaults to (50.0, 50.0) if detection fails

    Note:
        This function is designed to run ASYNC and should not block the upload flow.
        It's called after the meal is created, and updates the crop coordinates
        in the database once complete.
    """
    try:
        # Read and encode image
        image_file = Path(image_path)
        if not image_file.exists():
            logger.error(f"Image file not found: {image_path}")
            return (50.0, 50.0)

        with open(image_file, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        # Determine media type
        media_type = _get_media_type(image_file.suffix.lower())

        # Call Claude API
        message = client.messages.create(
            model="claude-3-haiku-20240307",  # Use Haiku for fast, cost-effective analysis
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Analyze this meal image and identify the center point of the food/plate.

Return ONLY two numbers (the coordinates) in this exact format:
x,y

Where:
- x is the horizontal position as a percentage from the left edge (0-100)
- y is the vertical position as a percentage from the top edge (0-100)

If there are multiple food items, find the visual center of mass.
If there's a plate or bowl, center on the dish.

Example response: 45,52

Do not include any other text, explanation, or formatting.""",
                        },
                    ],
                }
            ],
        )

        # Parse response
        response_text = message.content[0].text.strip()
        x, y = _parse_coordinates(response_text)

        logger.info(f"Detected meal center for {image_path}: ({x}, {y})")
        return (x, y)

    except Exception as e:
        logger.error(f"Error detecting meal center for {image_path}: {str(e)}")
        # Fallback to center
        return (50.0, 50.0)


def _get_media_type(file_extension: str) -> str:
    """
    Get the media type for the image based on file extension.

    Args:
        file_extension: File extension (e.g., ".jpg", ".png")

    Returns:
        Media type string (e.g., "image/jpeg")
    """
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return media_types.get(file_extension, "image/jpeg")


def _parse_coordinates(response_text: str) -> Tuple[float, float]:
    """
    Parse coordinate response from Claude API.

    Args:
        response_text: Response text from Claude (expected format: "x,y")

    Returns:
        Tuple of (x, y) coordinates, clamped to 0-100 range
        Defaults to (50.0, 50.0) if parsing fails
    """
    try:
        # Remove any whitespace and split by comma
        parts = response_text.strip().split(",")
        if len(parts) != 2:
            raise ValueError(f"Expected 2 coordinates, got {len(parts)}")

        x = float(parts[0].strip())
        y = float(parts[1].strip())

        # Clamp to valid range (0-100)
        x = max(0.0, min(100.0, x))
        y = max(0.0, min(100.0, y))

        return (x, y)

    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse coordinates from '{response_text}': {str(e)}")
        return (50.0, 50.0)
