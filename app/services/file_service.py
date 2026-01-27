"""File handling service for meal image uploads."""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image


class FileService:
    """Service for handling file uploads and storage."""

    def __init__(self, upload_dir: str = "uploads/meals"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_meal_image(self, file: UploadFile) -> str:
        """
        Save uploaded meal image to disk.

        Args:
            file: Uploaded file from FastAPI

        Returns:
            Relative path to saved file

        Raises:
            ValueError: If file type is invalid
        """
        # Validate file type
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise ValueError(f"Invalid file type: {file.content_type}. Allowed: {allowed_types}")

        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        extension = Path(file.filename).suffix.lower()
        filename = f"{timestamp}_{unique_id}{extension}"

        # Save file
        file_path = self.upload_dir / filename
        contents = await file.read()

        with open(file_path, "wb") as f:
            f.write(contents)

        # Optionally resize/optimize image
        self._optimize_image(file_path)

        # Return relative path for database storage
        return str(file_path)

    def _optimize_image(self, file_path: Path, max_width: int = 1920):
        """
        Optimize image size while maintaining quality.

        Args:
            file_path: Path to image file
            max_width: Maximum width in pixels
        """
        try:
            with Image.open(file_path) as img:
                # Convert RGBA to RGB if needed
                if img.mode == "RGBA":
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])
                    img = rgb_img

                # Resize if too large
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                # Save optimized version
                img.save(file_path, optimize=True, quality=85)

        except Exception as e:
            # If optimization fails, keep original
            print(f"Warning: Could not optimize image {file_path}: {e}")

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from disk.

        Args:
            file_path: Path to file

        Returns:
            True if deleted, False if file not found
        """
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            return False

    def get_file_url(self, file_path: Optional[str]) -> Optional[str]:
        """
        Convert file path to URL.

        Args:
            file_path: Relative file path

        Returns:
            URL path for serving the file
        """
        if not file_path:
            return None

        # Convert to URL path (assuming static serving)
        return f"/{file_path}"


# Singleton instance
file_service = FileService()
