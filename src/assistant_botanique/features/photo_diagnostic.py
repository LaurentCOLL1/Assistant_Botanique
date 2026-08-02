"""Analyse locale et prudente d'une photographie de plante."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from statistics import fmean
from typing import Any

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

MAX_DIAGNOSTIC_BYTES = 12 * 1024 * 1024


@dataclass(slots=True)
class DiagnosticFinding:
    title: str
    confidence: str
    explanation: str
    checks: tuple[str, ...]


@dataclass(slots=True)
class PhotoDiagnosticReport:
    summary: str
    metrics: dict[str, float]
    findings: tuple[DiagnosticFinding, ...]
    disclaimer: str = (
        "Cette analyse d'image est indicative. Confirmez toujours avec l'état du substrat, "
        "des racines, l'historique des soins et, en cas de doute important, un professionnel."
    )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["findings"] = [asdict(item) for item in self.findings]
        return payload


def _open_image(source: bytes | bytearray | Path | str) -> Image.Image:
    if isinstance(source, (bytes, bytearray)):
        if len(source) > MAX_DIAGNOSTIC_BYTES:
            raise ValueError("L'image dépasse la limite de 12 Mo.")
        stream = BytesIO(bytes(source))
        image = Image.open(stream)
    else:
        path = Path(source)
        if path.stat().st_size > MAX_DIAGNOSTIC_BYTES:
            raise ValueError("L'image dépasse la limite de 12 Mo.")
        image = Image.open(path)
    image.verify()
    if isinstance(source, (bytes, bytearray)):
        image = Image.open(BytesIO(bytes(source)))
    else:
        image = Image.open(Path(source))
    return image.convert("RGB")


def analyze_photo(source: bytes | bytearray | Path | str) -> PhotoDiagnosticReport:
    try:
        image = _open_image(source)
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Le fichier n'est pas une image JPEG, PNG ou WebP valide.") from exc

    image.thumbnail((640, 640))
    pixels = list(image.getdata())
    if not pixels:
        raise ValueError("L'image est vide.")

    brightness_values: list[float] = []
    saturation_values: list[float] = []
    yellow = brown = dark = pale = green = 0
    for red, green_value, blue in pixels:
        maximum = max(red, green_value, blue)
        minimum = min(red, green_value, blue)
        brightness = (red + green_value + blue) / 3
        saturation = 0.0 if maximum == 0 else (maximum - minimum) / maximum
        brightness_values.append(brightness)
        saturation_values.append(saturation)
        if red > 115 and green_value > 95 and blue < 105 and red >= green_value * 0.85:
            yellow += 1
        if red > 70 and red > green_value * 1.12 and green_value > blue * 1.05 and blue < 105:
            brown += 1
        if brightness < 45:
            dark += 1
        if brightness > 195 and saturation < 0.28:
            pale += 1
        if green_value > red * 1.08 and green_value > blue * 1.08 and green_value > 70:
            green += 1

    total = len(pixels)
    edge_image = image.filter(ImageFilter.FIND_EDGES).convert("L")
    edge_mean = ImageStat.Stat(edge_image).mean[0]
    metrics = {
        "luminosite_moyenne": round(fmean(brightness_values), 2),
        "saturation_moyenne": round(fmean(saturation_values), 4),
        "part_jaune": round(yellow / total, 4),
        "part_brune": round(brown / total, 4),
        "part_sombre": round(dark / total, 4),
        "part_pale": round(pale / total, 4),
        "part_verte": round(green / total, 4),
        "texture_bords": round(edge_mean, 2),
    }

    findings: list[DiagnosticFinding] = []
    if metrics["part_jaune"] >= 0.13:
        findings.append(
            DiagnosticFinding(
                "Jaunissement visible",
                "moyenne",
                "Une proportion importante de tons jaunes est détectée. Cela peut correspondre à un excès d'eau, "
                "un manque de lumière, une feuille naturellement vieillissante ou une carence.",
                (
                    "Vérifier l'humidité en profondeur avant tout nouvel arrosage.",
                    "Comparer les feuilles anciennes et les nouvelles pousses.",
                    "Contrôler le drainage et l'exposition réelle.",
                ),
            )
        )
    if metrics["part_brune"] >= 0.045:
        findings.append(
            DiagnosticFinding(
                "Zones brunes ou desséchées possibles",
                "moyenne",
                "Des tons bruns sont présents. Ils peuvent provenir d'un dessèchement, d'une brûlure, d'un choc froid, "
                "de sels accumulés ou d'une lésion ancienne.",
                (
                    "Observer si les zones sont sèches, molles ou entourées d'un halo.",
                    "Vérifier soleil direct, radiateur, courant d'air et qualité de l'eau.",
                    "Inspecter le revers des feuilles et les tiges.",
                ),
            )
        )
    if metrics["part_sombre"] >= 0.18 and metrics["texture_bords"] >= 18:
        findings.append(
            DiagnosticFinding(
                "Taches sombres possibles",
                "faible à moyenne",
                "L'image contient de nombreuses zones sombres et contrastées. Cela peut être un simple arrière-plan, "
                "mais aussi des taches foliaires ou des tissus abîmés.",
                (
                    "Refaire une photo rapprochée sur fond clair.",
                    "Vérifier si les taches progressent ou restent stables.",
                    "Éviter de mouiller le feuillage tant que la cause n'est pas clarifiée.",
                ),
            )
        )
    if metrics["part_pale"] >= 0.20 and metrics["part_verte"] < 0.18:
        findings.append(
            DiagnosticFinding(
                "Pâleur ou décoloration possible",
                "faible à moyenne",
                "La scène est claire et peu saturée. Une surexposition de la photo est possible, mais une chlorose "
                "ou une décoloration doit aussi être vérifiée.",
                (
                    "Refaire une photo en lumière naturelle indirecte.",
                    "Comparer la couleur des nervures et du limbe.",
                    "Vérifier pH, fertilisation récente et état des racines.",
                ),
            )
        )
    if metrics["luminosite_moyenne"] < 65:
        findings.append(
            DiagnosticFinding(
                "Photo trop sombre",
                "élevée",
                "La photo manque de lumière, ce qui limite fortement l'analyse des couleurs.",
                ("Reprendre la photo près d'une fenêtre, sans flash direct.",),
            )
        )
    elif metrics["luminosite_moyenne"] > 225:
        findings.append(
            DiagnosticFinding(
                "Photo surexposée",
                "élevée",
                "Les hautes lumières peuvent masquer les détails du feuillage.",
                ("Reprendre la photo à l'ombre lumineuse et verrouiller l'exposition sur la feuille.",),
            )
        )

    if not findings:
        findings.append(
            DiagnosticFinding(
                "Aucun signal visuel dominant",
                "faible",
                "L'analyse ne détecte pas de dominante jaune, brune ou sombre suffisamment nette. Cela n'exclut pas "
                "un problème invisible sur cette vue.",
                (
                    "Photographier le dessus et le dessous des feuilles.",
                    "Ajouter une vue du substrat, du collet et du pot.",
                    "Noter l'évolution sur plusieurs jours.",
                ),
            )
        )

    summary = findings[0].title
    return PhotoDiagnosticReport(summary=summary, metrics=metrics, findings=tuple(findings))


def render_report_text(report: PhotoDiagnosticReport) -> str:
    lines = [report.summary, ""]
    for finding in report.findings:
        lines.extend((f"• {finding.title} — confiance {finding.confidence}", f"  {finding.explanation}"))
        lines.extend(f"  - {check}" for check in finding.checks)
        lines.append("")
    lines.append(report.disclaimer)
    return "\n".join(lines)
