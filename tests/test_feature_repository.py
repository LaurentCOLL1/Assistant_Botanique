from assistant_botanique.features.repository import FeatureRepository
from assistant_botanique.infrastructure.database import Database


def test_custom_recipes_and_inventory_metadata(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    repository = FeatureRepository(database)

    recipe_id = repository.save_recipe(
        recipe_id=None,
        name="Mélange aroides",
        ingredients={"Fibre de coco": 50, "Perlite": 30, "Écorces de pin": 20},
    )
    recipes = repository.list_recipes()
    assert recipes[0]["id"] == recipe_id
    assert round(sum(recipes[0]["ingredients"].values()), 8) == 1

    item = repository.save_mobile_inventory_item(
        {
            "name": "Perlite 5 L",
            "category": "Substrat",
            "subcategory": "Perlite",
            "unit": "L",
            "quantity": 5,
            "threshold": 1,
            "barcode": "3760123456789",
        }
    )
    assert item["subcategory"] == "Perlite"
    assert repository.find_inventory_by_barcode("3760123456789")["id"] == item["id"]
