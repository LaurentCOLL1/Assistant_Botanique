"""Comparaison différentielle du catalogue avec GBIF, sans application silencieuse."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Mapping

from core import family_name, scientific_name
from assistant_botanique.infrastructure.advanced_repository import AdvancedRepository
from assistant_botanique.infrastructure.database import Database

USER_AGENT = "AssistantBotaniqueTaxonomyDiff/1.0 (+https://github.com/LaurentCOLL1/Assistant_Botanique)"
V2_MATCH = "https://api.gbif.org/v2/species/match"
V1_MATCH = "https://api.gbif.org/v1/species/match"


def compare_taxonomy(
    species_id: str,
    current_name: str,
    current_family: str,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    proposed_name = str(
        payload.get("acceptedScientificName")
        or payload.get("scientificName")
        or payload.get("canonicalName")
        or ""
    ).strip()
    proposed_family = str(payload.get("family") or "").strip()
    if not proposed_name:
        return None
    current_base = current_name.casefold().strip()
    proposed_base = proposed_name.casefold().strip()
    family_changed = bool(proposed_family and proposed_family.casefold() != current_family.casefold())
    name_changed = proposed_base != current_base
    status = str(payload.get("status") or payload.get("taxonomicStatus") or "").upper()
    if not name_changed and not family_changed and status in {"ACCEPTED", ""}:
        return None
    usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
    key = payload.get("acceptedUsageKey") or payload.get("usageKey") or usage.get("key")
    source_url = f"https://www.gbif.org/species/{key}" if key else "https://www.gbif.org/species/search"
    confidence = payload.get("confidence")
    try:
        confidence_value = int(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None
    return {
        "species_id": species_id,
        "current_name": current_name,
        "current_family": current_family,
        "proposed_name": proposed_name,
        "proposed_family": proposed_family or current_family,
        "confidence": confidence_value,
        "source_url": source_url,
        "status": "a_verifier",
        "payload": dict(payload),
    }


class TaxonomyDiffService:
    def __init__(self, database: Database):
        self.database = database
        self.repository = AdvancedRepository(database)

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        target = url + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            target,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        return payload if isinstance(payload, dict) else {}

    def match(self, name: str, family: str) -> dict[str, Any]:
        try:
            payload = self._request(
                V2_MATCH,
                {"scientificName": name, "family": family, "kingdom": "Plantae"},
            )
            if payload:
                return payload
        except Exception:
            pass
        return self._request(
            V1_MATCH,
            {"name": name, "family": family, "kingdom": "Plantae", "verbose": "true"},
        )

    def check_profile(self, profile: Mapping[str, Any]) -> dict[str, Any] | None:
        species_id = str(profile.get("id") or "").strip()
        current_name = scientific_name(profile)
        current_family = family_name(profile)
        payload = self.match(current_name, current_family)
        proposal = compare_taxonomy(species_id, current_name, current_family, payload)
        if proposal:
            proposal["id"] = self.repository.save_taxonomy_proposal(proposal)
        return proposal

    def check_profiles(
        self,
        profiles: list[Mapping[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        proposals = []
        selected = profiles[: max(0, int(limit))] if limit is not None else profiles
        for profile in selected:
            proposal = self.check_profile(profile)
            if proposal:
                proposals.append(proposal)
        return proposals

    def apply_as_local_override(
        self,
        proposal_id: str,
        profile: Mapping[str, Any],
    ) -> None:
        proposals = {
            item["id"]: item for item in self.repository.list_taxonomy_proposals()
        }
        proposal = proposals.get(proposal_id)
        if not proposal:
            raise ValueError("Proposition taxonomique introuvable.")
        species_id = proposal["species_id"]
        with self.database.connect() as conn:
            previous = conn.execute(
                "SELECT * FROM catalog_reviews WHERE species_id=?",
                (species_id,),
            ).fetchone()
        tax = dict(profile.get("taxonomie") or {})
        tax["nom_scientifique"] = proposal["proposed_name"]
        tax["famille"] = proposal["proposed_family"]
        override = dict(profile)
        override["taxonomie"] = tax
        existing = self.database.get_catalog_review(species_id)
        sources = list(existing.get("sources", [])) if existing else []
        if proposal["source_url"] not in sources:
            sources.append(proposal["source_url"])
        notes = (existing or {}).get("notes", "")
        notes = (
            f"{notes}\nProposition GBIF appliquée localement le temps d'une révision humaine."
        ).strip()
        self.database.save_catalog_review(
            species_id,
            status="a_verifier",
            confidence="elevee" if (proposal.get("confidence") or 0) >= 90 else "moyenne",
            sources=sources,
            notes=notes,
            override=override,
        )
        self.repository.record_history(
            "taxonomy_override",
            f"Révision taxonomique locale : {proposal['current_name']}",
            {
                "kind": "restore_taxonomy_review",
                "species_id": species_id,
                "review": dict(previous) if previous else None,
            },
        )
        self.repository.set_taxonomy_status(proposal_id, "applique")

    def reject(self, proposal_id: str) -> None:
        self.repository.set_taxonomy_status(proposal_id, "rejete")
