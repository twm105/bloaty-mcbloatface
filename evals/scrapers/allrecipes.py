"""AllRecipes recipe scraper."""

import json
import re
from typing import Optional
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedRecipe, ScrapedIngredient


class AllRecipesScraper(BaseScraper):
    """Scraper for AllRecipes.

    AllRecipes uses JSON-LD schema markup similar to BBC Good Food.
    Provides variety with American-style measurements and user-submitted photos.
    """

    BASE_URL = "https://www.allrecipes.com"

    @property
    def source_name(self) -> str:
        return "allrecipes"

    def scrape_recipe(self, url: str) -> ScrapedRecipe:
        """Scrape a single AllRecipes recipe page.

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
                        if isinstance(item, dict) and item.get("@type") == "Recipe":
                            return item

            except json.JSONDecodeError:
                continue

        return None

    def _parse_json_ld(self, data: dict, url: str, raw_html: str) -> ScrapedRecipe:
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

        # Extract cuisine and meal type from recipeCategory
        cuisine = None
        meal_type = None
        categories = data.get("recipeCategory", [])
        if isinstance(categories, str):
            categories = [categories]

        for cat in categories:
            cat_lower = cat.lower() if cat else ""
            if cat_lower in [
                "indian",
                "italian",
                "mexican",
                "chinese",
                "thai",
                "japanese",
                "french",
                "greek",
                "spanish",
                "american",
            ]:
                cuisine = cat_lower
            if cat_lower in [
                "breakfast",
                "lunch",
                "dinner",
                "brunch",
                "snack",
                "dessert",
                "appetizer",
                "side dish",
            ]:
                meal_type = cat_lower

        return ScrapedRecipe(
            source=self.source_name,
            source_url=url,
            recipe_name=data.get("name", "Unknown Recipe"),
            image_url=image_url,
            ingredients=ingredients,
            cuisine=cuisine,
            meal_type=meal_type,
            raw_html=raw_html,
        )

    def _parse_html(
        self, soup: BeautifulSoup, url: str, raw_html: str
    ) -> ScrapedRecipe:
        """Fallback HTML parsing when JSON-LD is not available."""
        # Recipe name
        name_elem = soup.find("h1")
        recipe_name = name_elem.get_text(strip=True) if name_elem else "Unknown Recipe"

        # Image
        image_url = ""
        # AllRecipes often uses data-src for lazy loading
        img_elem = soup.find("img", class_=re.compile(r"universal-image", re.I))
        if img_elem:
            image_url = img_elem.get("src", "") or img_elem.get("data-src", "")

        # Ingredients
        ingredients = []
        ing_list = soup.find_all("li", class_=re.compile(r"ingredient", re.I))
        for li in ing_list:
            text = li.get_text(strip=True)
            if text:
                ingredients.append(self._parse_ingredient_text(text))

        return ScrapedRecipe(
            source=self.source_name,
            source_url=url,
            recipe_name=recipe_name,
            image_url=image_url,
            ingredients=ingredients,
            raw_html=raw_html,
        )

    def _parse_ingredient_text(self, text: str) -> ScrapedIngredient:
        """Parse ingredient text into structured format.

        Examples:
            "2 tablespoons olive oil" -> ScrapedIngredient(name="olive oil", quantity="2", unit="tablespoons")
            "1 cup diced onion" -> ScrapedIngredient(name="onion", quantity="1", unit="cup")
        """
        # Common cooking state indicators
        cooked_indicators = [
            "cooked",
            "roasted",
            "grilled",
            "fried",
            "baked",
            "steamed",
            "sauteed",
        ]
        processed_indicators = [
            "canned",
            "jarred",
            "frozen",
            "dried",
            "pickled",
            "crushed",
        ]

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

        # Extract quantity and unit using regex
        # AllRecipes often uses parenthetical notes like "(8 ounce) package"
        quantity_pattern = r"^([\d½¼¾⅓⅔⅛]+(?:\s*[-–]\s*[\d½¼¾⅓⅔⅛]+)?(?:\s*/\s*\d+)?)\s*"
        unit_pattern = r"(\([^)]+\)\s*)?(tablespoons?|teaspoons?|cups?|ounces?|pounds?|cloves?|slices?|pieces?|cans?|packages?)\s+"

        quantity = None
        unit = None
        name = text

        # Try to extract quantity
        qty_match = re.match(quantity_pattern, text, re.IGNORECASE)
        if qty_match:
            quantity = qty_match.group(1).strip()
            name = text[qty_match.end() :].strip()

        # Try to extract unit (including parenthetical size like "(8 ounce)")
        unit_match = re.match(unit_pattern, name, re.IGNORECASE)
        if unit_match:
            # Combine parenthetical and unit
            paren_part = unit_match.group(1) or ""
            unit_part = unit_match.group(2) or ""
            unit = (paren_part + unit_part).strip()
            name = name[unit_match.end() :].strip()

        # Clean up name - remove prep instructions after comma
        if "," in name:
            name = name.split(",")[0].strip()

        # Remove size descriptors and prep words
        name = re.sub(
            r"^(large|medium|small|diced|chopped|minced|sliced)\s+",
            "",
            name,
            flags=re.IGNORECASE,
        )

        return ScrapedIngredient(
            name=name,
            quantity=quantity,
            unit=unit,
            state=state,
            raw_text=text,
        )

    def get_recipe_urls(self, category: str, limit: int) -> list[str]:
        """Get recipe URLs from an AllRecipes category page.

        Args:
            category: Category slug (e.g., 'quick-and-easy', 'healthy-recipes')
            limit: Maximum URLs to return

        Returns:
            List of recipe URLs
        """
        # AllRecipes category URL format
        category_url = f"{self.BASE_URL}/recipes/{category}/"

        urls = []
        page = 1

        while len(urls) < limit:
            page_url = f"{category_url}?page={page}" if page > 1 else category_url

            try:
                response = self._get_with_backoff(page_url)
            except Exception:
                break

            soup = BeautifulSoup(response.text, "html.parser")

            # Find recipe card links
            recipe_links = soup.find_all("a", href=re.compile(r"/recipe/\d+/"))

            if not recipe_links:
                break

            for link in recipe_links:
                href = link.get("href", "")
                if href and "/recipe/" in href:
                    # Normalize URL
                    if href.startswith("/"):
                        full_url = f"{self.BASE_URL}{href}"
                    else:
                        full_url = href

                    if full_url not in urls:
                        urls.append(full_url)
                        if len(urls) >= limit:
                            break

            page += 1

            # Safety limit
            if page > 10:
                break

        return urls[:limit]
