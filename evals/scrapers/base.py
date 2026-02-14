"""Abstract base scraper and data structures."""

import hashlib
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class ScrapedIngredient:
    """Standardized ingredient from a recipe."""

    name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    state: Optional[str] = None  # raw, cooked, processed
    raw_text: Optional[str] = None  # Original text from source


@dataclass
class NutritionInfo:
    """Nutritional information for a recipe (per serving)."""

    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbohydrates_g: Optional[float] = None
    fat_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    # Raw nutrition data for anything else
    raw_data: Optional[dict] = None


@dataclass
class ScrapedRecipe:
    """Standardized recipe format from any source."""

    source: str  # e.g., "bbc_good_food"
    source_url: str
    recipe_name: str
    image_url: str
    ingredients: list[ScrapedIngredient] = field(default_factory=list)
    local_image_path: Optional[Path] = None  # Set after download
    description: Optional[str] = None  # Recipe description/intro
    cuisine: Optional[str] = None
    meal_type: Optional[str] = None  # breakfast, lunch, dinner, snack
    prep_method: Optional[str] = None  # grilled, baked, raw, etc.
    servings: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    nutrition: Optional[NutritionInfo] = None
    raw_html: Optional[str] = None  # For debugging

    @property
    def slug(self) -> str:
        """Generate URL-safe slug from recipe name."""
        slug = self.recipe_name.lower()
        slug = slug.replace(" ", "-")
        # Remove non-alphanumeric except hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        # Remove multiple consecutive hyphens
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug.strip("-")[:50]


class BaseScraper(ABC):
    """Abstract base class for recipe scrapers.

    Includes rate limiting and exponential backoff to avoid being blocked.
    """

    # Rate limiting settings
    MIN_DELAY = 1.0  # Minimum seconds between requests
    MAX_DELAY = 3.0  # Maximum seconds between requests (randomized)
    MAX_RETRIES = 3  # Maximum retry attempts per request
    BACKOFF_FACTOR = 2.0  # Exponential backoff multiplier

    def __init__(
        self,
        output_dir: Path = Path("evals/datasets/meal_images"),
        min_delay: float = None,
        max_delay: float = None,
    ):
        self.output_dir = output_dir
        self.min_delay = min_delay if min_delay is not None else self.MIN_DELAY
        self.max_delay = max_delay if max_delay is not None else self.MAX_DELAY
        self._last_request_time = 0.0

        # Configure session with retry strategy
        self.session = requests.Session()

        # Retry on common transient errors
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Use a realistic browser User-Agent
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)

        if elapsed < delay:
            sleep_time = delay - elapsed
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def _get_with_backoff(self, url: str, timeout: int = 30) -> requests.Response:
        """Make GET request with rate limiting and backoff.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Response object

        Raises:
            requests.RequestException: After all retries exhausted
        """
        self._rate_limit()

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as e:
                last_error = e
                status = e.response.status_code if e.response else None

                # Don't retry on client errors (except 429)
                if status and 400 <= status < 500 and status != 429:
                    raise

                # Exponential backoff
                backoff = self.BACKOFF_FACTOR**attempt + random.uniform(0, 1)
                print(
                    f"  Retry {attempt + 1}/{self.MAX_RETRIES} after {backoff:.1f}s (status {status})"
                )
                time.sleep(backoff)

            except requests.exceptions.RequestException as e:
                last_error = e
                backoff = self.BACKOFF_FACTOR**attempt + random.uniform(0, 1)
                print(
                    f"  Retry {attempt + 1}/{self.MAX_RETRIES} after {backoff:.1f}s ({type(e).__name__})"
                )
                time.sleep(backoff)

        raise last_error or requests.exceptions.RequestException("Max retries exceeded")

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the source identifier (e.g., 'bbc_good_food')."""
        pass

    @abstractmethod
    def scrape_recipe(self, url: str) -> ScrapedRecipe:
        """Scrape a single recipe page.

        Args:
            url: Full URL to the recipe page

        Returns:
            ScrapedRecipe with all available fields populated
        """
        pass

    @abstractmethod
    def get_recipe_urls(self, category: str, limit: int) -> list[str]:
        """Get recipe URLs from a category/collection page.

        Args:
            category: Category identifier (e.g., 'chicken', 'vegetarian')
            limit: Maximum number of URLs to return

        Returns:
            List of recipe page URLs
        """
        pass

    def download_image(self, recipe: ScrapedRecipe) -> Path:
        """Download and save recipe image.

        Args:
            recipe: ScrapedRecipe with image_url set

        Returns:
            Path to the downloaded image file
        """
        # Create source subdirectory
        source_dir = self.output_dir / self.source_name
        source_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from slug
        # Add hash suffix to avoid collisions
        url_hash = hashlib.md5(recipe.image_url.encode()).hexdigest()[:8]
        ext = self._get_image_extension(recipe.image_url)
        filename = f"{recipe.slug}_{url_hash}{ext}"
        filepath = source_dir / filename

        # Download if not already present
        if not filepath.exists():
            response = self._get_with_backoff(recipe.image_url)
            filepath.write_bytes(response.content)

        recipe.local_image_path = filepath
        return filepath

    def _get_image_extension(self, url: str) -> str:
        """Extract image extension from URL."""
        # Remove query params
        path = url.split("?")[0]
        if path.lower().endswith(".png"):
            return ".png"
        elif path.lower().endswith(".webp"):
            return ".webp"
        return ".jpg"  # Default to jpg

    def scrape_category(
        self, category: str, limit: int = 50, download_images: bool = True
    ) -> list[ScrapedRecipe]:
        """Scrape multiple recipes from a category.

        Args:
            category: Category identifier
            limit: Maximum recipes to scrape
            download_images: Whether to download recipe images

        Returns:
            List of ScrapedRecipe objects
        """
        print(f"Fetching recipe URLs from {category}...")
        urls = self.get_recipe_urls(category, limit)
        print(f"Found {len(urls)} recipes to scrape")

        recipes = []

        for i, url in enumerate(urls):
            print(f"  [{i + 1}/{len(urls)}] Scraping {url.split('/')[-1]}...")
            try:
                recipe = self.scrape_recipe(url)
                if download_images and recipe.image_url:
                    print("    Downloading image...")
                    self.download_image(recipe)
                recipes.append(recipe)
                print(
                    f"    OK: {recipe.recipe_name} ({len(recipe.ingredients)} ingredients)"
                )
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

        return recipes
