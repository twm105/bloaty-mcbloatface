"""Seed initial ingredient categories."""
from app.database import SessionLocal
from app.models.ingredient_category import IngredientCategory


def seed_categories():
    """Seed the database with initial ingredient categories."""
    db = SessionLocal()

    try:
        # Check if categories already exist
        existing = db.query(IngredientCategory).count()
        if existing > 0:
            print(f"Categories already seeded ({existing} existing). Skipping.")
            return

        # Root categories (level 0)
        root_categories = [
            {
                'name': 'Dairy',
                'normalized_name': 'dairy',
                'level': 0,
                'description': 'Milk and dairy products'
            },
            {
                'name': 'Grains',
                'normalized_name': 'grains',
                'level': 0,
                'description': 'Wheat, rice, oats, and other grains'
            },
            {
                'name': 'Proteins',
                'normalized_name': 'proteins',
                'level': 0,
                'description': 'Meat, fish, poultry, and other protein sources'
            },
            {
                'name': 'Vegetables',
                'normalized_name': 'vegetables',
                'level': 0,
                'description': 'All vegetable types'
            },
            {
                'name': 'Fruits',
                'normalized_name': 'fruits',
                'level': 0,
                'description': 'All fruit types'
            },
            {
                'name': 'Legumes',
                'normalized_name': 'legumes',
                'level': 0,
                'description': 'Beans, lentils, peas, and other legumes'
            },
            {
                'name': 'Nuts & Seeds',
                'normalized_name': 'nuts_seeds',
                'level': 0,
                'description': 'Tree nuts, peanuts, and seeds'
            },
            {
                'name': 'FODMAPs',
                'normalized_name': 'fodmaps',
                'level': 0,
                'description': 'High FODMAP ingredients (fermentable carbohydrates)'
            },
            {
                'name': 'Oils & Fats',
                'normalized_name': 'oils_fats',
                'level': 0,
                'description': 'Cooking oils, butter, and other fats'
            },
            {
                'name': 'Spices & Herbs',
                'normalized_name': 'spices_herbs',
                'level': 0,
                'description': 'Seasonings, herbs, and spices'
            },
            {
                'name': 'Sweeteners',
                'normalized_name': 'sweeteners',
                'level': 0,
                'description': 'Sugar, honey, artificial sweeteners, and other sweeteners'
            },
            {
                'name': 'Processed Foods',
                'normalized_name': 'processed_foods',
                'level': 0,
                'description': 'Packaged and processed food products'
            },
        ]

        for cat_data in root_categories:
            category = IngredientCategory(**cat_data)
            db.add(category)

        db.commit()
        print(f"Successfully seeded {len(root_categories)} root categories.")

    except Exception as e:
        print(f"Error seeding categories: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_categories()
