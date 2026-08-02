"""Stabilité du consensus quand les trois variantes sont déjà persistées."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import substrate_consensus as consensus
import substrate_knowledge as knowledge


def _source_key(source: Mapping[str, Any]) -> str:
    return str(source.get("url") or source.get("titre") or "").strip().casefold()


def install() -> None:
    if getattr(knowledge, "_consensus_stability_installed", False):
        return
    previous_resolved = knowledge.resolved_substrate

    def resolved_substrate(profile: Mapping[str, Any]) -> dict[str, Any]:
        substrate = profile.get("substrat", {})
        substrate = substrate if isinstance(substrate, Mapping) else {}
        stored = substrate.get("variantes")
        if (
            isinstance(stored, list)
            and len(stored) >= 3
            and isinstance(stored[0], Mapping)
            and str(stored[0].get("nom") or "") == "Synthèse des variantes"
        ):
            rebuilt = copy.deepcopy(dict(profile))
            rebuilt_substrate = copy.deepcopy(dict(substrate))
            rebuilt_substrate["variantes"] = copy.deepcopy(stored[1:3])
            rebuilt["substrat"] = rebuilt_substrate
            return previous_resolved(rebuilt)
        return previous_resolved(profile)

    def validate_resolved_profile(profile: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        resolved = resolved_substrate(profile)
        variants = resolved.get("variantes", [])
        if len(variants) != 3:
            errors.append("Chaque fiche doit proposer exactement trois variantes.")
        if variants and str(variants[0].get("nom")) != "Synthèse des variantes":
            errors.append("La synthèse des variantes doit être placée en premier.")
        for variant in variants:
            roles = variant.get("roles", [])
            total = sum(float(role.get("ratio", 0)) for role in roles)
            if abs(total - 1.0) > 0.001:
                errors.append(f"La variante {variant.get('nom')} totalise {total:.4f}.")
            for role in roles:
                for ingredient in role.get("ing", []):
                    if ingredient not in knowledge.CANONICAL_SET:
                        errors.append(f"Ingrédient non canonique: {ingredient}")
            source_count = len({
                _source_key(source)
                for source in variant.get("sources", [])
                if isinstance(source, Mapping) and _source_key(source)
            })
            if source_count < consensus.MIN_SOURCES:
                errors.append(
                    f"La variante {variant.get('nom')} n'a que {source_count} sources distinctes."
                )
            used = {ingredient for role in roles for ingredient in role.get("ing", [])}
            conflict = used.intersection(variant.get("interdits", []))
            if conflict:
                errors.append(f"Ingrédients à la fois utilisés et interdits: {sorted(conflict)}")
        return errors

    knowledge.resolved_substrate = resolved_substrate
    knowledge.validate_resolved_profile = validate_resolved_profile
    knowledge._consensus_stability_installed = True


__all__ = ["install"]
