#!/usr/bin/env python
"""
Download images for eval dataset from existing ground truth URLs.

This script reads the source_url entries from meal_analysis.json and downloads
the corresponding images without re-scraping ingredient data.

Usage:
    docker compose exec web python scripts/download_eval_images.py
"""

import json
from pathlib import Path

from evals.scrapers.bbc_good_food import BBCGoodFoodScraper


def main():
    gt_path = Path("evals/datasets/ground_truth/meal_analysis.json")

    if not gt_path.exists():
        print(f"Error: Ground truth file not found: {gt_path}")
        return 1

    with open(gt_path) as f:
        data = json.load(f)

    test_cases = data.get("test_cases", [])
    urls = [tc["source_url"] for tc in test_cases if tc.get("source_url")]

    print(f"Found {len(urls)} URLs to process")

    # Initialize scraper
    scraper = BBCGoodFoodScraper(output_dir=Path("evals/datasets/meal_images"))

    # Download images from URLs
    recipes = scraper.scrape_urls(urls, download_images=True)

    print(f"\nSuccessfully processed {len(recipes)} recipes")

    # Show summary of downloaded images
    images_dir = Path("evals/datasets/meal_images/bbc_good_food")
    if images_dir.exists():
        image_count = len(list(images_dir.glob("*.jpg")))
        print(f"Images in {images_dir}: {image_count}")

    return 0


if __name__ == "__main__":
    exit(main())
