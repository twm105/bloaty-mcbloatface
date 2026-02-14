"""
Unit tests for image_crop module.

Tests the AI-powered meal center detection for circular cropping:
- Coordinate parsing
- Media type detection
- API integration with mocking
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.image_crop import (
    detect_meal_center,
    _get_media_type,
    _parse_coordinates,
)


class TestParseCoordinates:
    """Tests for _parse_coordinates helper."""

    def test_valid_coordinates(self):
        """Test parsing valid coordinate string."""
        x, y = _parse_coordinates("45,52")

        assert x == 45.0
        assert y == 52.0

    def test_coordinates_with_whitespace(self):
        """Test parsing coordinates with whitespace."""
        x, y = _parse_coordinates("  30 , 70  ")

        assert x == 30.0
        assert y == 70.0

    def test_decimal_coordinates(self):
        """Test parsing decimal coordinates."""
        x, y = _parse_coordinates("50.5,49.5")

        assert x == 50.5
        assert y == 49.5

    def test_clamping_high_values(self):
        """Test that values over 100 are clamped."""
        x, y = _parse_coordinates("150,200")

        assert x == 100.0
        assert y == 100.0

    def test_clamping_low_values(self):
        """Test that values below 0 are clamped."""
        x, y = _parse_coordinates("-10,-20")

        assert x == 0.0
        assert y == 0.0

    def test_invalid_format_returns_center(self):
        """Test that invalid format returns center (50, 50)."""
        x, y = _parse_coordinates("invalid")

        assert x == 50.0
        assert y == 50.0

    def test_too_few_parts_returns_center(self):
        """Test that single value returns center."""
        x, y = _parse_coordinates("45")

        assert x == 50.0
        assert y == 50.0

    def test_too_many_parts_returns_center(self):
        """Test that too many values returns center."""
        x, y = _parse_coordinates("10,20,30")

        assert x == 50.0
        assert y == 50.0

    def test_non_numeric_returns_center(self):
        """Test that non-numeric values return center."""
        x, y = _parse_coordinates("abc,def")

        assert x == 50.0
        assert y == 50.0


class TestGetMediaType:
    """Tests for _get_media_type helper."""

    def test_jpeg_extension(self):
        """Test JPEG extension detection."""
        assert _get_media_type(".jpg") == "image/jpeg"
        assert _get_media_type(".jpeg") == "image/jpeg"

    def test_png_extension(self):
        """Test PNG extension detection."""
        assert _get_media_type(".png") == "image/png"

    def test_gif_extension(self):
        """Test GIF extension detection."""
        assert _get_media_type(".gif") == "image/gif"

    def test_webp_extension(self):
        """Test WebP extension detection."""
        assert _get_media_type(".webp") == "image/webp"

    def test_unknown_extension_defaults_to_jpeg(self):
        """Test that unknown extensions default to JPEG."""
        assert _get_media_type(".bmp") == "image/jpeg"
        assert _get_media_type(".tiff") == "image/jpeg"
        assert _get_media_type(".xyz") == "image/jpeg"


class TestDetectMealCenter:
    """Tests for detect_meal_center function."""

    @pytest.mark.asyncio
    async def test_file_not_found_returns_center(self):
        """Test that missing file returns center coordinates."""
        x, y = await detect_meal_center("/nonexistent/path/image.jpg")

        assert x == 50.0
        assert y == 50.0

    @pytest.mark.asyncio
    async def test_successful_detection(self):
        """Test successful meal center detection."""
        # Create a temporary image file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00')  # Minimal JPEG
            temp_path = f.name

        try:
            mock_response = MagicMock()
            mock_content = MagicMock()
            mock_content.text = "35,65"
            mock_response.content = [mock_content]

            with patch('app.services.image_crop.client') as mock_client:
                mock_client.messages.create.return_value = mock_response

                x, y = await detect_meal_center(temp_path)

            assert x == 35.0
            assert y == 65.0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_api_error_returns_center(self):
        """Test that API errors return center coordinates."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00')
            temp_path = f.name

        try:
            with patch('app.services.image_crop.client') as mock_client:
                mock_client.messages.create.side_effect = Exception("API Error")

                x, y = await detect_meal_center(temp_path)

            assert x == 50.0
            assert y == 50.0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_invalid_api_response_returns_center(self):
        """Test that invalid API response returns center coordinates."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00')
            temp_path = f.name

        try:
            mock_response = MagicMock()
            mock_content = MagicMock()
            mock_content.text = "not valid coordinates"
            mock_response.content = [mock_content]

            with patch('app.services.image_crop.client') as mock_client:
                mock_client.messages.create.return_value = mock_response

                x, y = await detect_meal_center(temp_path)

            # Should fallback to center due to parse failure
            assert x == 50.0
            assert y == 50.0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_png_image(self):
        """Test detection with PNG image."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Minimal PNG header
            f.write(b'\x89PNG\r\n\x1a\n')
            temp_path = f.name

        try:
            mock_response = MagicMock()
            mock_content = MagicMock()
            mock_content.text = "25,75"
            mock_response.content = [mock_content]

            with patch('app.services.image_crop.client') as mock_client:
                mock_client.messages.create.return_value = mock_response

                x, y = await detect_meal_center(temp_path)

            assert x == 25.0
            assert y == 75.0

            # Verify PNG media type was used
            call_args = mock_client.messages.create.call_args
            messages = call_args.kwargs["messages"]
            assert messages[0]["content"][0]["source"]["media_type"] == "image/png"
        finally:
            Path(temp_path).unlink(missing_ok=True)
