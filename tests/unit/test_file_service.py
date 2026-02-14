"""
Unit tests for FileService.

Tests file handling including:
- File type validation
- Image optimization and EXIF handling
- Safe file deletion
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO

from PIL import Image
from fastapi import UploadFile

from app.services.file_service import FileService, file_service


class TestFileServiceInit:
    """Tests for FileService initialization."""

    def test_creates_upload_directory(self):
        """Test that upload directory is created on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            upload_dir = os.path.join(tmpdir, "uploads", "meals")
            service = FileService(upload_dir=upload_dir)

            assert os.path.exists(upload_dir)

    def test_uses_default_directory(self):
        """Test that default directory is used."""
        service = FileService()

        assert service.upload_dir == Path("uploads/meals")


class TestFileTypeValidation:
    """Tests for file type validation."""

    @pytest.mark.asyncio
    async def test_accepts_jpeg(self):
        """Test that JPEG files are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create a mock UploadFile with JPEG content
            mock_file = create_mock_upload_file(
                content_type="image/jpeg",
                filename="test.jpg"
            )

            path = await service.save_meal_image(mock_file)
            assert path is not None

    @pytest.mark.asyncio
    async def test_accepts_png(self):
        """Test that PNG files are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="image/png",
                filename="test.png"
            )

            path = await service.save_meal_image(mock_file)
            assert path is not None

    @pytest.mark.asyncio
    async def test_accepts_webp(self):
        """Test that WebP files are accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="image/webp",
                filename="test.webp"
            )

            path = await service.save_meal_image(mock_file)
            assert path is not None

    @pytest.mark.asyncio
    async def test_rejects_invalid_type(self):
        """Test that invalid file types are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="application/pdf",
                filename="test.pdf"
            )

            with pytest.raises(ValueError, match="Invalid file type"):
                await service.save_meal_image(mock_file)

    @pytest.mark.asyncio
    async def test_rejects_text_files(self):
        """Test that text files are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="text/plain",
                filename="test.txt"
            )

            with pytest.raises(ValueError):
                await service.save_meal_image(mock_file)


class TestFileSaving:
    """Tests for file saving."""

    @pytest.mark.asyncio
    async def test_saves_file_to_disk(self):
        """Test that files are saved to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="image/jpeg",
                filename="test.jpg"
            )

            path = await service.save_meal_image(mock_file)

            assert os.path.exists(path)

    @pytest.mark.asyncio
    async def test_generates_unique_filename(self):
        """Test that unique filenames are generated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file1 = create_mock_upload_file(
                content_type="image/jpeg",
                filename="test.jpg"
            )
            mock_file2 = create_mock_upload_file(
                content_type="image/jpeg",
                filename="test.jpg"
            )

            path1 = await service.save_meal_image(mock_file1)
            path2 = await service.save_meal_image(mock_file2)

            assert path1 != path2

    @pytest.mark.asyncio
    async def test_preserves_extension(self):
        """Test that file extension is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            mock_file = create_mock_upload_file(
                content_type="image/png",
                filename="test.png"
            )

            path = await service.save_meal_image(mock_file)

            assert path.endswith(".png")


class TestImageOptimization:
    """Tests for image optimization."""

    def test_optimizes_large_image(self):
        """Test that large images are resized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create a large image
            large_image_path = os.path.join(tmpdir, "large.jpg")
            img = Image.new('RGB', (4000, 3000), color='red')
            img.save(large_image_path)

            # Optimize it
            service._optimize_image(Path(large_image_path), max_width=1920)

            # Check new size
            optimized = Image.open(large_image_path)
            assert optimized.width <= 1920

    def test_preserves_small_image(self):
        """Test that small images are not resized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create a small image
            small_image_path = os.path.join(tmpdir, "small.jpg")
            img = Image.new('RGB', (800, 600), color='blue')
            img.save(small_image_path)

            # Optimize it
            service._optimize_image(Path(small_image_path), max_width=1920)

            # Size should be unchanged
            optimized = Image.open(small_image_path)
            assert optimized.width == 800
            assert optimized.height == 600

    def test_converts_rgba_to_rgb(self):
        """Test that RGBA images are converted to RGB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create an RGBA image
            rgba_path = os.path.join(tmpdir, "rgba.png")
            img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
            img.save(rgba_path)

            # Optimize it
            service._optimize_image(Path(rgba_path))

            # The image should still open (no error)
            optimized = Image.open(rgba_path)
            assert optimized is not None

    def test_handles_corrupt_image_gracefully(self):
        """Test that corrupt images don't crash optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create a corrupt "image" file
            corrupt_path = os.path.join(tmpdir, "corrupt.jpg")
            with open(corrupt_path, 'wb') as f:
                f.write(b"not an image")

            # Should not raise, just print warning
            service._optimize_image(Path(corrupt_path))

            # File should still exist
            assert os.path.exists(corrupt_path)


class TestFileDeletion:
    """Tests for file deletion."""

    def test_deletes_existing_file(self):
        """Test that existing files are deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            # Create a file
            file_path = os.path.join(tmpdir, "test.jpg")
            with open(file_path, 'w') as f:
                f.write("test")

            result = service.delete_file(file_path)

            assert result is True
            assert not os.path.exists(file_path)

    def test_returns_false_for_nonexistent_file(self):
        """Test that deleting non-existent file returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = FileService(upload_dir=tmpdir)

            result = service.delete_file(os.path.join(tmpdir, "nonexistent.jpg"))

            assert result is False

    def test_handles_deletion_errors_gracefully(self):
        """Test that deletion errors are handled."""
        service = FileService()

        # Try to delete a path that would cause an error
        # (permission denied, etc.)
        result = service.delete_file("/nonexistent/path/file.jpg")

        assert result is False


class TestFileUrlConversion:
    """Tests for file URL conversion."""

    def test_converts_path_to_url(self):
        """Test that file paths are converted to URLs."""
        service = FileService()

        url = service.get_file_url("uploads/meals/test.jpg")

        assert url == "/uploads/meals/test.jpg"

    def test_returns_none_for_none_path(self):
        """Test that None path returns None."""
        service = FileService()

        url = service.get_file_url(None)

        assert url is None

    def test_returns_none_for_empty_path(self):
        """Test that empty path returns None."""
        service = FileService()

        url = service.get_file_url("")

        assert url is None


# Helper function to create mock UploadFile
def create_mock_upload_file(
    content_type: str,
    filename: str,
    content: bytes = None
) -> UploadFile:
    """Create a mock UploadFile for testing."""
    if content is None:
        # Create a minimal valid image
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        if 'png' in content_type:
            img.save(buffer, format='PNG')
        elif 'webp' in content_type:
            img.save(buffer, format='WEBP')
        else:
            img.save(buffer, format='JPEG')
        content = buffer.getvalue()

    mock_file = MagicMock(spec=UploadFile)
    mock_file.content_type = content_type
    mock_file.filename = filename
    mock_file.read = AsyncMock(return_value=content)

    return mock_file
