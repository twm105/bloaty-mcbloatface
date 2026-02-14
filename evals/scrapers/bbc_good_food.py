"""BBC Good Food recipe scraper."""

import json
import re
from typing import Optional
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedRecipe, ScrapedIngredient, NutritionInfo


class BBCGoodFoodScraper(BaseScraper):
    """Scraper for BBC Good Food recipes.

    BBC Good Food uses JSON-LD schema markup which makes extraction reliable.
    Includes nutrition info, description, and timing data.
    """

    BASE_URL = "https://www.bbcgoodfood.com"

    @property
    def source_name(self) -> str:
        return "bbc_good_food"

    def scrape_recipe(self, url: str) -> ScrapedRecipe:
        """Scrape a single BBC Good Food recipe page.

        Args:
            url: Full URL to the recipe page

        Returns:
            ScrapedRecipe with extracted data
        """
        response = self._get_with_backoff(url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Try JSON-LD first (most reliable)
        recipe_data = self._extract_json_ld(soup)

        if recipe_data:
            return self._parse_json_ld(recipe_data, url, response.text)

        # Fallback to HTML parsing
        return self._parse_html(soup, url, response.text)

    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract JSON-LD recipe schema from page."""
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)

                # Handle @graph format
                if isinstance(data, dict) and "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "Recipe":
                            return item

                # Direct Recipe type
                if isinstance(data, dict) and data.get("@type") == "Recipe":
                    return data

                # List of types
                if isinstance(data, dict) and isinstance(data.get("@type"), list):
                    if "Recipe" in data["@type"]:
                        return data

                # List format
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            item_type = item.get("@type")
                            if item_type == "Recipe" or (isinstance(item_type, list) and "Recipe" in item_type):
                                return item

            except json.JSONDecodeError:
                continue

        return None

    def _parse_duration(self, duration_str: Optional[str]) -> Optional[int]:
        """Parse ISO 8601 duration to minutes.

        Examples: PT30M -> 30, PT1H30M -> 90, PT2H -> 120
        """
        if not duration_str:
            return None

        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration_str)
        if not match:
            return None

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        return hours * 60 + minutes if (hours or minutes) else None

    def _parse_nutrition(self, nutrition_data: Optional[dict]) -> Optional[NutritionInfo]:
        """Extract nutrition info from JSON-LD nutrition object."""
        if not nutrition_data:
            return None

        def parse_value(val: str | None) -> Optional[float]:
            """Extract numeric value from strings like '250 kcal' or '15g'."""
            if not val:
                return None
            match = re.search(r"([\d.]+)", str(val))
            return float(match.group(1)) if match else None

        return NutritionInfo(
            calories=parse_value(nutrition_data.get("calories")),
            protein_g=parse_value(nutrition_data.get("proteinContent")),
            carbohydrates_g=parse_value(nutrition_data.get("carbohydrateContent")),
            fat_g=parse_value(nutrition_data.get("fatContent")),
            saturated_fat_g=parse_value(nutrition_data.get("saturatedFatContent")),
            fiber_g=parse_value(nutrition_data.get("fiberContent")),
            sugar_g=parse_value(nutrition_data.get("sugarContent")),
            sodium_mg=parse_value(nutrition_data.get("sodiumContent")),
            raw_data=nutrition_data,
        )

    def _parse_json_ld(
        self, data: dict, url: str, raw_html: str
    ) -> ScrapedRecipe:
        """Parse recipe from JSON-LD data."""
        # Extract image URL
        image_url = ""
        if "image" in data:
            img = data["image"]
            if isinstance(img, str):
                image_url = img
            elif isinstance(img, list) and img:
                image_url = img[0] if isinstance(img[0], str) else img[0].get("url", "")
            elif isinstance(img, dict):
                image_url = img.get("url", "")

        # Parse ingredients
        ingredients = []
        for ing_text in data.get("recipeIngredient", []):
            ingredient = self._parse_ingredient_text(ing_text)
            ingredients.append(ingredient)

        # Extract description
        description = data.get("description", "")

        # Extract timing
        prep_time = self._parse_duration(data.get("prepTime"))
        cook_time = self._parse_duration(data.get("cookTime"))

        # Extract servings
        servings = None
        yield_val = data.get("recipeYield")
        if yield_val:
            if isinstance(yield_val, (int, float)):
                servings = int(yield_val)
            elif isinstance(yield_val, str):
                match = re.search(r"(\d+)", yield_val)
                if match:
                    servings = int(match.group(1))
            elif isinstance(yield_val, list) and yield_val:
                # Take first numeric value
                for y in yield_val:
                    if isinstance(y, (int, float)):
                        servings = int(y)
                        break
                    elif isinstance(y, str):
                        match = re.search(r"(\d+)", y)
                        if match:
                            servings = int(match.group(1))
                            break

        # Extract nutrition
        nutrition = self._parse_nutrition(data.get("nutrition"))

        # Extract cuisine and meal type from keywords
        cuisine = None
        meal_type = None
        keywords = data.get("keywords", "")
        if isinstance(keywords, str):
            keyword_list = [k.strip().lower() for k in keywords.split(",")]
            # Common cuisines
            for kw in keyword_list:
                if kw in ["indian", "italian", "mexican", "chinese", "thai", "japanese", "french", "greek", "spanish", "american", "british", "korean", "vietnamese"]:
                    cuisine = kw
                    break
            # Meal types
            for kw in keyword_list:
                if kw in ["breakfast", "lunch", "dinner", "brunch", "snack", "dessert", "starter", "main", "side"]:
                    meal_type = kw
                    break

        return ScrapedRecipe(
            source=self.source_name,
            source_url=url,
            recipe_name=data.get("name", "Unknown Recipe"),
            image_url=image_url,
            ingredients=ingredients,
            description=description,
            cuisine=cuisine,
            meal_type=meal_type,
            servings=servings,
            prep_time_minutes=prep_time,
            cook_time_minutes=cook_time,
            nutrition=nutrition,
            raw_html=raw_html,
        )

    def _parse_html(self, soup: BeautifulSoup, url: str, raw_html: str) -> ScrapedRecipe:
        """Fallback HTML parsing when JSON-LD is not available."""
        # Recipe name
        name_elem = soup.find("h1")
        recipe_name = name_elem.get_text(strip=True) if name_elem else "Unknown Recipe"

        # Image
        image_url = ""
        img_elem = soup.find("img", class_=re.compile(r"image|hero|main", re.I))
        if img_elem:
            image_url = img_elem.get("src", "") or img_elem.get("data-src", "")

        # Description
        description = ""
        desc_elem = soup.find("div", class_=re.compile(r"description|summary|intro", re.I))
        if desc_elem:
            description = desc_elem.get_text(strip=True)

        # Ingredients - look for ingredient list
        ingredients = []
        ing_section = soup.find("section", class_=re.compile(r"ingredient", re.I))
        if ing_section:
            for li in ing_section.find_all("li"):
                text = li.get_text(strip=True)
                if text:
                    ingredients.append(self._parse_ingredient_text(text))

        return ScrapedRecipe(
            source=self.source_name,
            source_url=url,
            recipe_name=recipe_name,
            image_url=image_url,
            ingredients=ingredients,
            description=description,
            raw_html=raw_html,
        )

    def _parse_ingredient_text(self, text: str) -> ScrapedIngredient:
        """Parse ingredient text into structured format.

        Examples:
            "2 tbsp olive oil" -> ScrapedIngredient(name="olive oil", quantity="2", unit="tbsp")
            "1 large onion, diced" -> ScrapedIngredient(name="onion", quantity="1", state="cooked")
        """
        # Common cooking state indicators
        raw_indicators = ["raw", "fresh", "uncooked"]
        cooked_indicators = ["cooked", "roasted", "grilled", "fried", "baked", "steamed", "sautéed", "sauteed"]
        processed_indicators = ["canned", "tinned", "jarred", "frozen", "dried", "pickled"]

        text = text.strip()
        state = None

        # Detect state from text
        text_lower = text.lower()
        for indicator in cooked_indicators:
            if indicator in text_lower:
                state = "cooked"
                break
        if not state:
            for indicator in processed_indicators:
                if indicator in text_lower:
                    state = "processed"
                    break
        if not state:
            for indicator in raw_indicators:
                if indicator in text_lower:
                    state = "raw"
                    break

        # Extract quantity and unit using regex
        # Pattern: optional number (including fractions) + optional unit
        quantity_pattern = r"^([\d½¼¾⅓⅔⅛]+(?:\s*[-–]\s*[\d½¼¾⅓⅔⅛]+)?(?:\s*/\s*\d+)?)\s*"
        unit_pattern = r"(tbsp|tsp|tablespoon|teaspoon|cup|g|kg|ml|l|oz|lb|bunch|handful|pinch|clove|slice|piece)s?\s+"

        quantity = None
        unit = None
        name = text

        # Try to extract quantity
        qty_match = re.match(quantity_pattern, text, re.IGNORECASE)
        if qty_match:
            quantity = qty_match.group(1).strip()
            name = text[qty_match.end():].strip()

        # Try to extract unit
        unit_match = re.match(unit_pattern, name, re.IGNORECASE)
        if unit_match:
            unit = unit_match.group(1).lower()
            name = name[unit_match.end():].strip()

        # Clean up name - remove prep instructions after comma
        if "," in name:
            name = name.split(",")[0].strip()

        # Remove size descriptors
        name = re.sub(r"^(large|medium|small|big)\s+", "", name, flags=re.IGNORECASE)

        return ScrapedIngredient(
            name=name,
            quantity=quantity,
            unit=unit,
            state=state,
            raw_text=text,
        )

    def get_recipe_urls(self, category: str, limit: int) -> list[str]:
        """Get recipe URLs from a BBC Good Food page.

        Args:
            category: Category slug or full URL path. Examples:
                - 'chicken-recipes' -> /recipes/collection/chicken-recipes
                - '/recipes/collection/easy-dinner' -> as-is
                - Full URL also accepted

        Returns:
            List of recipe URLs
        """
        # Handle different input formats
        if category.startswith("http"):
            category_url = category
        elif category.startswith("/"):
            category_url = f"{self.BASE_URL}{category}"
        else:
            category_url = f"{self.BASE_URL}/recipes/collection/{category}"

        urls = []
        page = 1

        while len(urls) < limit:
            page_url = f"{category_url}?page={page}" if page > 1 else category_url

            try:
                response = self._get_with_backoff(page_url)
            except Exception as e:
                print(f"  Failed to fetch {page_url}: {e}")
                break

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for recipe links - multiple patterns for different page types
            recipe_links = []

            # Pattern 1: /recipes/name (collection pages)
            recipe_links.extend(soup.find_all("a", href=re.compile(r"^/recipes/[a-z0-9-]+$")))

            # Pattern 2: Full URLs
            recipe_links.extend(soup.find_all("a", href=re.compile(rf"^{re.escape(self.BASE_URL)}/recipes/[a-z0-9-]+$")))

            if not recipe_links:
                # Try broader pattern
                recipe_links = soup.find_all("a", href=re.compile(r"/recipes/"))

            found_new = False
            for link in recipe_links:
                href = link.get("href", "")

                # Skip collection/category links
                if "/collection/" in href or "/category/" in href:
                    continue

                # Normalize URL
                if href.startswith("/"):
                    full_url = f"{self.BASE_URL}{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue

                # Skip if already have it
                if full_url in urls:
                    continue

                urls.append(full_url)
                found_new = True

                if len(urls) >= limit:
                    break

            # If no new URLs found, stop pagination
            if not found_new:
                break

            page += 1

            # Safety limit
            if page > 10:
                break

        return urls[:limit]

    def scrape_urls(self, urls: list[str], download_images: bool = True) -> list[ScrapedRecipe]:
        """Scrape a list of explicit recipe URLs.

        Useful for ad-hoc scraping from curated lists.

        Args:
            urls: List of full recipe URLs
            download_images: Whether to download images

        Returns:
            List of ScrapedRecipe objects
        """
        recipes = []

        for i, url in enumerate(urls):
            print(f"  [{i + 1}/{len(urls)}] Scraping {url.split('/')[-1]}...")
            try:
                recipe = self.scrape_recipe(url)
                if download_images and recipe.image_url:
                    print(f"    Downloading image...")
                    self.download_image(recipe)
                recipes.append(recipe)
                print(f"    OK: {recipe.recipe_name} ({len(recipe.ingredients)} ingredients)")
                if recipe.nutrition and recipe.nutrition.calories:
                    print(f"    Nutrition: {recipe.nutrition.calories:.0f} kcal")
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

        return recipes
