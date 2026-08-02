"""Stockage des fonctions transversales ajoutées à la version 3."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from core import ValidationError, parse_date
from assistant_botanique.features.inventory import normalize_barcode, subcategories_for
from assistant_botanique.infrastructure.database import Database

FEATURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_item_metadata (
    item_id TEXT PRIMARY KEY REFERENCES inventory_items(id) ON DELETE CASCADE,
    subcategory TEXT NOT NULL DEFAULT '',
    barcode TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'desktop',
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_barcode
ON inventory_item_metadata(barcode) WHERE barcode != '';

CREATE TABLE IF NOT EXISTS custom_substrate_recipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    ingredients_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS photo_diagnostics (
    id TEXT PRIMARY KEY,
    plant_id TEXT REFERENCES plants(id) ON DELETE SET NULL,
    image_name TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photo_diagnostics_plant
ON photo_diagnostics(plant_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class FeatureRepository:
    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository

        AdvancedRepository(self.database)
        with self.database.connect() as conn:
            conn.executescript(FEATURE_SCHEMA)

    def save_inventory_metadata(
        self,
        item_id: str,
        *,
        category: str,
        subcategory: str = "",
        barcode: str = "",
        brand: str = "",
        source: str = "desktop",
    ) -> None:
        item_id = str(item_id).strip()
        if not item_id:
            raise ValidationError("Produit de stock introuvable.")
        category = str(category or "Autre").strip()
        allowed = subcategories_for(category)
        subcategory = str(subcategory or "").strip()
        if subcategory and subcategory not in allowed:
            subcategory = subcategory[:120]
        try:
            barcode = normalize_barcode(barcode)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        with self.database.connect() as conn:
            if not conn.execute("SELECT 1 FROM inventory_items WHERE id=?", (item_id,)).fetchone():
                raise ValidationError("Produit de stock introuvable.")
            try:
                conn.execute(
                    """
                    INSERT INTO inventory_item_metadata(
                        item_id, subcategory, barcode, brand, source, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        subcategory=excluded.subcategory,
                        barcode=excluded.barcode,
                        brand=excluded.brand,
                        source=excluded.source,
                        updated_at=excluded.updated_at
                    """,
                    (item_id, subcategory, barcode, str(brand).strip(), str(source or "desktop"), _now()),
                )
            except Exception as exc:
                if barcode:
                    raise ValidationError("Ce code-barres est déjà associé à un autre produit.") from exc
                raise

    def inventory_metadata(self, item_id: str) -> dict[str, Any]:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM inventory_item_metadata WHERE item_id=?", (str(item_id),)).fetchone()
        return dict(row) if row else {
            "item_id": str(item_id), "subcategory": "", "barcode": "", "brand": "", "source": ""
        }

    def find_inventory_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        try:
            barcode = normalize_barcode(barcode)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        if not barcode:
            return None
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT i.*, m.subcategory, m.barcode, m.brand, m.source
                FROM inventory_items AS i
                JOIN inventory_item_metadata AS m ON m.item_id=i.id
                WHERE m.barcode=?
                """,
                (barcode,),
            ).fetchone()
        return dict(row) if row else None

    def list_inventory_enriched(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT i.*, COALESCE(m.subcategory, '') AS subcategory,
                       COALESCE(m.barcode, '') AS barcode,
                       COALESCE(m.brand, '') AS brand,
                       COALESCE(m.source, '') AS source,
                       CASE WHEN i.quantity <= i.reorder_level THEN 1 ELSE 0 END AS low_stock
                FROM inventory_items AS i
                LEFT JOIN inventory_item_metadata AS m ON m.item_id=i.id
                ORDER BY low_stock DESC, i.name COLLATE NOCASE
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def save_mobile_inventory_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository

        name = str(payload.get("name") or "").strip()
        category = str(payload.get("category") or "Autre").strip()
        subcategory = str(payload.get("subcategory") or "").strip()
        unit = str(payload.get("unit") or "unité").strip()
        brand = str(payload.get("brand") or "").strip()
        barcode = str(payload.get("barcode") or "").strip()
        notes = str(payload.get("notes") or "").strip()
        try:
            quantity = float(str(payload.get("quantity", "1")).replace(",", "."))
            threshold = float(str(payload.get("threshold", "0")).replace(",", "."))
        except ValueError as exc:
            raise ValidationError("Quantité ou seuil invalide.") from exc
        expires_on = payload.get("expires_on") or None
        if expires_on:
            expires_on = parse_date(expires_on).isoformat()
        existing = self.find_inventory_by_barcode(barcode) if barcode else None
        item_id = str(existing["id"]) if existing else None
        repository = AdvancedRepository(self.database)
        identifier = repository.save_inventory_item(
            item_id=item_id,
            name=name,
            category=category,
            unit=unit,
            quantity=quantity,
            reorder_level=threshold,
            expires_on=expires_on,
            notes=notes,
        )
        self.save_inventory_metadata(
            identifier,
            category=category,
            subcategory=subcategory,
            barcode=barcode,
            brand=brand,
            source="mobile",
        )
        return next(item for item in self.list_inventory_enriched() if item["id"] == identifier)

    def save_recipe(
        self,
        *,
        recipe_id: str | None,
        name: str,
        ingredients: dict[str, float],
        description: str = "",
    ) -> str:
        name = str(name).strip()
        if not name:
            raise ValidationError("Le nom de la recette est obligatoire.")
        cleaned: dict[str, float] = {}
        for ingredient, ratio in ingredients.items():
            ingredient = str(ingredient).strip()
            value = float(ratio)
            if ingredient and value > 0:
                cleaned[ingredient] = value
        if not cleaned:
            raise ValidationError("Ajoutez au moins un ingrédient avec une proportion positive.")
        total = sum(cleaned.values())
        normalized = {ingredient: value / total for ingredient, value in cleaned.items()}
        identifier = str(recipe_id or uuid4())
        now = _now()
        with self.database.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO custom_substrate_recipes(
                        id, name, description, ingredients_json, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        description=excluded.description,
                        ingredients_json=excluded.ingredients_json,
                        updated_at=excluded.updated_at
                    """,
                    (identifier, name, str(description).strip(), json.dumps(normalized, ensure_ascii=False), now, now),
                )
            except Exception as exc:
                raise ValidationError("Une recette portant ce nom existe déjà.") from exc
        return identifier

    def list_recipes(self) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM custom_substrate_recipes ORDER BY name COLLATE NOCASE").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["ingredients"] = json.loads(item.pop("ingredients_json") or "{}")
            result.append(item)
        return result

    def delete_recipe(self, recipe_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM custom_substrate_recipes WHERE id=?", (str(recipe_id),))

    def save_photo_diagnostic(
        self,
        *,
        plant_id: str | None,
        image_name: str,
        summary: str,
        report: dict[str, Any],
    ) -> str:
        identifier = str(uuid4())
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO photo_diagnostics(
                    id, plant_id, image_name, summary, report_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    plant_id or None,
                    str(image_name or ""),
                    str(summary),
                    json.dumps(report, ensure_ascii=False),
                    _now(),
                ),
            )
        return identifier
