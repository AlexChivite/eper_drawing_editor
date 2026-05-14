
from __future__ import annotations

import csv
import logging
import os
import re
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz


# ============================================================
# Opciones generales
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "input_pdfs"
OUTPUT_DIR = PROJECT_ROOT / "output_pdfs"
DEFAULT_CHANGE_CONFIG = PROJECT_ROOT / "config" / "config.toml"

# Cambia a True para probar el recorrido completo sin guardar PDFs modificados
# El log y las vistas previas si pueden generarse.
DRY_RUN = False

# Activa esto para generar PNGs en output_pdfs/previews con las cajas dibujadas.
# Es util para ajustar coordenadas antes de lanzar los 160 planos.
GENERATE_COORDINATE_PREVIEWS = False

# Tolerancia en puntos PDF para considerar que una pagina encaja con A3/A4.
# 72 puntos = 1 pulgada. A4 vertical: 595.28 x 841.89 pt.
# A3 horizontal: 1190.55 x 841.89 pt.
PAGE_SIZE_TOLERANCE_PT = 25.0
ORIENTATION_TOLERANCE_PT = 5.0

FONT = "helv"  # Helvetica (equivalente Arial en PDF).
FONTSIZE = 8
GREEN = (0, 0.55, 0)
RED = (1, 0, 0)
WRITE_COLORS = {
    "green": GREEN,
    "red": RED,
}

FONT_NAME = FONT

EDITABLE_TEXT_FIELDS = (
    "title",
    "drawing_title",
    "drawn",
    "verified",
    "reviewed",
    "approved",
    "control_plan_quality_specification",
)
DRAWING_CODE_PATTERN = re.compile(r"\bGP\d{6}(?:[-_A-Z0-9]+)*\b", re.IGNORECASE)
PARENT_DRAWING_NUMBER_REPORT_SUFFIX = "_parent_drawing_numbers_dry_run.csv"
PARENT_DRAWING_NUMBER_WRITE_STATUSES = {"exact_unique", "exact_multiple"}
PARENT_TABLE_FONT_SIZE = 4.0


# ============================================================
# Coordenadas editables
# ============================================================
#
# Sistema de coordenadas PyMuPDF:
# - (0, 0) esta en la esquina superior izquierda de la pagina.
# - x crece hacia la derecha.
# - y crece hacia abajo.
# - cover = (x0, y0, x1, y1): rectangulo donde se elimina el texto anterior.
# - text_pos = (x, y): punto de insercion del texto nuevo. En insert_text,
#   "y" es la linea base del texto, no la parte superior.
#
# Como ajustar tras revisar un PNG de prueba:
# - Si el rectangulo elimina demasiado poco, aumenta x1/y1 o reduce x0/y0.
# - Si toca texto que quieres conservar, separa el borde correspondiente 1-2 puntos.
# - Si el texto sale alto/bajo, cambia solo text_pos[1].
# - Si el texto sale a izquierda/derecha, cambia solo text_pos[0].
# - font_size puede ajustarse campo a campo.
#
# Las coordenadas iniciales estan tomadas de los PDFs de ejemplo de GP676417.

CONFIG_A3_LANDSCAPE = {
    "title": {
        "cover": (928.0, 675.5, 1161.0, 694.0),
        "text_pos": (930.0, 690.0),
        "font_size": FONTSIZE,
        "max_width": 228.0,
    },
    "drawing_title": {
        "cover": (928.0, 704.0, 1161.0, 722.0),
        "text_pos": (930.0, 718.0),
        "font_size": FONTSIZE,
        "max_width": 228.0,
    },
    "drawn": {
        "cover": (708.0, 757.2, 758.5, 769.6),
        "text_pos": (708.5, 768.0),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "verified": {
        "cover": (708.0, 771.4, 758.5, 783.7),
        "text_pos": (708.5, 782.2),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "reviewed": {
        "cover": (708.0, 785.6, 758.5, 797.8),
        "text_pos": (708.5, 796.4),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "approved": {
        "cover": (708.0, 799.8, 758.5, 812.0),
        "text_pos": (708.5, 810.5),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "control_plan_quality_specification": {
        "cover": (254.0, 112.7, 368.2, 128.4),
        "cell": (253.4, 112.1, 368.7, 128.5),
        "baseline_y": 124.3,
        "font_size": FONTSIZE,
        "max_width": 112.0,
        "align": "center",
    },
    "sheet": {
        "current": {
            "cover": (1104.5, 733.0, 1119.0, 745.9),
            "cell": (1104.5, 733.0, 1119.0, 745.9),
            "baseline_y": 741.9,
            "font_size": 8.0,
            "max_width": 13.6,
        },
        "total": {
            "cover": (1128.0, 733.0, 1144.0, 745.9),
            "cell": (1128.0, 733.0, 1144.0, 745.9),
            "baseline_y": 741.9,
            "font_size": 8.0,
            "max_width": 15.0,
        },
    },
}

CONFIG_A4_PORTRAIT = {
    "title": {
        "cover": (341.0, 676.0, 566.0, 694.0),
        "text_pos": (343.0, 690.0),
        "font_size": FONTSIZE,
        "max_width": 220.0,
    },
    "drawing_title": {
        "cover": (341.0, 704.0, 566.0, 722.0),
        "text_pos": (343.0, 718.0),
        "font_size": FONTSIZE,
        "max_width": 220.0,
    },
    "drawn": {
        "cover": (126.0, 758.0, 177.0, 769.8),
        "text_pos": (126.5, 768.3),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "verified": {
        "cover": (126.0, 772.1, 177.0, 783.9),
        "text_pos": (126.5, 782.4),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "reviewed": {
        "cover": (126.0, 786.3, 177.0, 798.0),
        "text_pos": (126.5, 796.5),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "approved": {
        "cover": (126.0, 800.4, 177.0, 812.2),
        "text_pos": (126.5, 810.7),
        "font_size": FONTSIZE,
        "max_width": 52.0,
    },
    "control_plan_quality_specification": {
        "cover": (240.4, 112.8, 356.6, 128.7),
        "cell": (240.0, 112.4, 357.0, 129.0),
        "baseline_y": 124.8,
        "font_size": FONTSIZE,
        "max_width": 113.0,
        "align": "center",
    },
    "sheet": {
        "current": {
            "cover": (523.5, 733.6, 538.0, 746.4),
            "cell": (523.5, 733.6, 538.0, 746.4),
            "baseline_y": 742.5,
            "font_size": 8.0,
            "max_width": 13.6,
        },
        "total": {
            "cover": (546.8, 733.6, 562.0, 746.4),
            "cell": (546.8, 733.6, 562.0, 746.4),
            "baseline_y": 742.5,
            "font_size": 8.0,
            "max_width": 14.2,
        },
    },
}

A3_REVISION_DATE_REPAIR = {
    # Rows REVIEWED and APPROVED contain a bad value that runs into their date cells.
    # Redact only text in that area, keep title-block line art, then copy a clean date
    # cell from VERIFIED on the same page so each A3 PDF keeps its own date.
    "redact": (724.0, 785.6, 824.7, 812.2),
    "source_date_cell": (758.8, 770.72, 836.1, 784.29),
    "target_date_cells": (
        (758.8, 784.89, 836.1, 798.46),
        (758.8, 799.06, 836.1, 812.63),
    ),
}

REVISION_HISTORY_ERROR_ROWS = {
    "A3_LANDSCAPE": {
        "search": (828.0, 601.5, 1163.0, 646.8),
        "rows": (
            {"label": "R4", "rect": (828.0, 601.5, 1163.0, 613.3)},
            {"label": "R3", "rect": (828.0, 612.5, 1163.0, 624.4)},
            {"label": "R2", "rect": (828.0, 623.6, 1163.0, 635.5)},
            {"label": "R1", "rect": (828.0, 634.7, 1163.0, 646.8)},
        ),
    },
    "A4_PORTRAIT": {
        "search": (224.0, 602.3, 568.0, 647.1),
        "rows": (
            {"label": "R4", "rect": (224.0, 602.3, 568.0, 613.9)},
            {"label": "R3", "rect": (224.0, 613.2, 568.0, 625.0)},
            {"label": "R2", "rect": (224.0, 624.3, 568.0, 636.0)},
            {"label": "R1", "rect": (224.0, 635.2, 568.0, 647.1)},
        ),
    },
}


@dataclass(frozen=True)
class ParentTableMetrics:
    page_number: int
    table_number: int
    header_rect: fitz.Rect
    reference_x0: float
    reference_x1: float
    drw_number_x0: float
    drw_number_x1: float
    row_number_x0: float
    row_number_x1: float


@dataclass(frozen=True)
class ParentDrawingReference:
    page_number: int
    table_number: int
    row_number: str
    reference: str
    x0: float
    y0: float
    x1: float
    y1: float
    drw_number_x0: float
    drw_number_x1: float


@dataclass(frozen=True)
class DrawingNumberLocation:
    code: str
    page_number: int


@dataclass(frozen=True)
class ParentDrawingNumberDryRunRow:
    parent_page: int
    table_number: int
    row_number: str
    reference: str
    status: str
    match_type: str
    matches: tuple[DrawingNumberLocation, ...]


@dataclass(frozen=True)
class ParentDrawingNumberUpdate:
    reference: ParentDrawingReference
    matches: tuple[DrawingNumberLocation, ...]
    status: str


@dataclass(frozen=True)
class ChangeConfig:
    path: Path
    fields: dict[str, str]
    drw_number_color_name: str | None
    drw_number_color: tuple[float, float, float] | None
    update_sheet: bool
    repair_a3_review_dates: bool
    clean_revision_errors: bool
    update_parent_drawing_numbers: bool


def load_change_config(config_path: Path) -> ChangeConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"No existe el archivo de cambios: {config_path}")

    with config_path.open("rb") as config_file:
        raw_config = tomllib.load(config_file)

    unknown_sections = set(raw_config) - {"fields", "options"}
    if unknown_sections:
        raise ValueError("Secciones no reconocidas en el archivo de cambios: " + ", ".join(sorted(unknown_sections)))

    fields_raw = raw_config.get("fields", {})
    options_raw = raw_config.get("options", {})

    if not isinstance(fields_raw, dict):
        raise ValueError("La seccion [fields] debe ser una tabla TOML.")
    if not isinstance(options_raw, dict):
        raise ValueError("La seccion [options] debe ser una tabla TOML.")

    unknown_fields = set(fields_raw) - set(EDITABLE_TEXT_FIELDS)
    if unknown_fields:
        raise ValueError(
            "Campos no reconocidos en [fields]: "
            + ", ".join(sorted(unknown_fields))
            + ". Campos validos: "
            + ", ".join(EDITABLE_TEXT_FIELDS)
        )

    fields: dict[str, str] = {}
    for field_name, value in fields_raw.items():
        if not isinstance(value, str):
            raise ValueError(f"El campo '{field_name}' debe tener un texto entre comillas.")
        fields[field_name] = value

    boolean_options = {
        "update_sheet",
        "repair_a3_review_dates",
        "clean_revision_errors",
        "update_parent_drawing_numbers",
    }
    allowed_options = boolean_options | {"drw_number_color"}
    unknown_options = set(options_raw) - allowed_options
    if unknown_options:
        raise ValueError(
            "Opciones no reconocidas en [options]: "
            + ", ".join(sorted(unknown_options))
            + ". Opciones validas: "
            + ", ".join(sorted(allowed_options))
        )

    options: dict[str, bool] = {}
    for option_name in boolean_options:
        value = options_raw.get(option_name, False)
        if not isinstance(value, bool):
            raise ValueError(f"La opcion '{option_name}' debe ser true o false.")
        options[option_name] = value

    drw_number_color_name: str | None = None
    drw_number_color: tuple[float, float, float] | None = None
    drw_number_color_raw = options_raw.get("drw_number_color")
    if drw_number_color_raw is not None:
        if not isinstance(drw_number_color_raw, str):
            raise ValueError("La opcion 'drw_number_color' debe ser \"red\" o \"green\".")
        drw_number_color_name = drw_number_color_raw.strip().lower()
        if drw_number_color_name not in WRITE_COLORS:
            raise ValueError("La opcion 'drw_number_color' debe ser \"red\" o \"green\".")
        drw_number_color = WRITE_COLORS[drw_number_color_name]

    if not fields and not any(options.values()):
        raise ValueError("El archivo de cambios no pide ninguna modificacion.")

    return ChangeConfig(
        path=config_path,
        fields=fields,
        drw_number_color_name=drw_number_color_name,
        drw_number_color=drw_number_color,
        update_sheet=options["update_sheet"],
        repair_a3_review_dates=options["repair_a3_review_dates"],
        clean_revision_errors=options["clean_revision_errors"],
        update_parent_drawing_numbers=options["update_parent_drawing_numbers"],
    )


def resolve_config_path(config_path: Path | None = None) -> Path:
    raw_path = Path(config_path or os.getenv("PDF_UPDATER_CONFIG", str(DEFAULT_CHANGE_CONFIG)))
    if raw_path.is_absolute():
        return raw_path
    return PROJECT_ROOT / raw_path


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "process.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def page_size_matches(width: float, height: float, target_width: float, target_height: float) -> bool:
    return (
        abs(width - target_width) <= PAGE_SIZE_TOLERANCE_PT
        and abs(height - target_height) <= PAGE_SIZE_TOLERANCE_PT
    )


def detect_page_format(page: fitz.Page) -> tuple[str | None, dict[str, dict[str, Any]] | None]:
    width = float(page.rect.width)
    height = float(page.rect.height)

    if width > height + ORIENTATION_TOLERANCE_PT:
        if not page_size_matches(width, height, 1190.55, 841.89):
            logging.warning(
                "Pagina %.2f x %.2f pt: orientacion horizontal, pero fuera de tolerancia A3. "
                "Se tratara como A3 horizontal.",
                width,
                height,
            )
        return "A3_LANDSCAPE", CONFIG_A3_LANDSCAPE

    if height > width + ORIENTATION_TOLERANCE_PT:
        if not page_size_matches(width, height, 595.28, 841.89):
            logging.warning(
                "Pagina %.2f x %.2f pt: orientacion vertical, pero fuera de tolerancia A4. "
                "Se tratara como A4 vertical.",
                width,
                height,
            )
        return "A4_PORTRAIT", CONFIG_A4_PORTRAIT

    logging.warning("No se puede detectar formato A3/A4 para pagina %.2f x %.2f pt.", width, height)
    return None, None


def find_input_pdfs(input_dir: Path) -> list[Path]:
    return sorted(
        (path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.lower(),
    )


def normalized_label(text: str) -> str:
    return text.strip().upper().strip(".")


def normalize_drawing_code(text: str) -> str | None:
    match = DRAWING_CODE_PATTERN.search(text.upper())
    if match is None:
        return None
    return match.group(0).rstrip(".,;:")


def word_center_x(word: tuple[Any, ...]) -> float:
    return (float(word[0]) + float(word[2])) / 2


def word_center_y(word: tuple[Any, ...]) -> float:
    return (float(word[1]) + float(word[3])) / 2


def word_rect(word: tuple[Any, ...]) -> fitz.Rect:
    return fitz.Rect(float(word[0]), float(word[1]), float(word[2]), float(word[3]))


def words_intersecting_rect(words: list[tuple[Any, ...]], rect: fitz.Rect) -> list[tuple[Any, ...]]:
    return [word for word in words if word_rect(word).intersects(rect)]


def average_word_center(words: list[tuple[Any, ...]], labels: set[str], fallback: float) -> float:
    centers = [word_center_x(word) for word in words if normalized_label(str(word[4])) in labels]
    if not centers:
        return fallback
    return sum(centers) / len(centers)


def is_parent_table_header(text: str) -> bool:
    normalized = " ".join(text.upper().split())
    return (
        "REFERENCE" in normalized
        and "DRW NUMBER" in normalized
        and "DENOMINATION" in normalized
    )


def find_words_by_label_near(
    words: list[tuple[Any, ...]],
    labels: set[str],
    reference_word: tuple[Any, ...],
    *,
    min_x: float | None = None,
    max_x: float | None = None,
    y_tolerance: float = 12.0,
) -> list[tuple[Any, ...]]:
    reference_y = word_center_y(reference_word)
    matches: list[tuple[Any, ...]] = []

    for word in words:
        if normalized_label(str(word[4])) not in labels:
            continue
        center_x = word_center_x(word)
        if min_x is not None and center_x < min_x:
            continue
        if max_x is not None and center_x > max_x:
            continue
        if abs(word_center_y(word) - reference_y) > y_tolerance:
            continue
        matches.append(word)

    return matches


def rect_for_words(words: list[tuple[Any, ...]]) -> fitz.Rect:
    rect = word_rect(words[0])
    for word in words[1:]:
        rect |= word_rect(word)
    return rect


def header_rects_overlap(first: fitz.Rect, second: fitz.Rect) -> bool:
    return (
        abs(first.x0 - second.x0) < 8.0
        and abs(first.y0 - second.y0) < 8.0
        and abs(first.x1 - second.x1) < 8.0
        and abs(first.y1 - second.y1) < 8.0
    )


def find_parent_table_header_rects_from_words(page_words: list[tuple[Any, ...]]) -> list[fitz.Rect]:
    header_rects: list[fitz.Rect] = []

    for reference_word in page_words:
        if normalized_label(str(reference_word[4])) not in {"REFERENCIA", "REFERENCE"}:
            continue

        reference_x = word_center_x(reference_word)
        denomination_words = find_words_by_label_near(
            page_words,
            {"DENOMINACION", "DENOMINATION"},
            reference_word,
            min_x=reference_x - 180.0,
            max_x=reference_x,
        )
        drw_words = find_words_by_label_near(
            page_words,
            {"NUMERO", "PLANO", "DRW", "NUMBER"},
            reference_word,
            min_x=reference_x + 25.0,
            max_x=reference_x + 220.0,
        )
        if not denomination_words or not drw_words:
            continue

        number_words = find_words_by_label_near(
            page_words,
            {"Nº", "NO"},
            reference_word,
            min_x=reference_x - 220.0,
            max_x=reference_x - 40.0,
        )
        weight_words = find_words_by_label_near(
            page_words,
            {"PESO", "WEIGHT", "(KG)"},
            reference_word,
            min_x=reference_x + 40.0,
            max_x=reference_x + 260.0,
        )
        material_words = find_words_by_label_near(
            page_words,
            {"ESPEC", "MATERIAL", "SPEC", "STANDARD", "ESTANDAR"},
            reference_word,
            min_x=reference_x,
            max_x=reference_x + 170.0,
        )

        header_words = [
            *number_words,
            *denomination_words,
            reference_word,
            *material_words,
            *drw_words,
            *weight_words,
        ]
        header_rect = rect_for_words(header_words)

        if any(header_rects_overlap(header_rect, existing_rect) for existing_rect in header_rects):
            continue
        header_rects.append(header_rect)

    return header_rects


def build_parent_table_metrics(
    page_number: int,
    table_number: int,
    header_rect: fitz.Rect,
    page_words: list[tuple[Any, ...]],
) -> ParentTableMetrics:
    header_words = words_intersecting_rect(page_words, header_rect + (-2, -2, 2, 2))
    width = header_rect.width

    denomination_x = average_word_center(
        header_words,
        {"DENOMINACION", "DENOMINATION"},
        header_rect.x0 + width * 0.22,
    )
    reference_x = average_word_center(
        header_words,
        {"REFERENCIA", "REFERENCE"},
        header_rect.x0 + width * 0.43,
    )
    material_x = average_word_center(
        header_words,
        {"ESPEC", "MATERIAL", "SPEC", "STANDARD", "ESTANDAR"},
        header_rect.x0 + width * 0.66,
    )
    drw_number_x = average_word_center(
        header_words,
        {"NUMERO", "PLANO", "DRW", "NUMBER"},
        header_rect.x0 + width * 0.86,
    )
    weight_x = average_word_center(
        header_words,
        {"PESO", "WEIGHT", "(KG)"},
        header_rect.x0 + width * 0.97,
    )

    reference_x0 = (denomination_x + reference_x) / 2
    reference_x1 = (reference_x + material_x) / 2
    drw_number_x0 = (material_x + drw_number_x) / 2
    drw_number_x1 = (drw_number_x + weight_x) / 2

    return ParentTableMetrics(
        page_number=page_number,
        table_number=table_number,
        header_rect=header_rect,
        reference_x0=max(header_rect.x0, reference_x0),
        reference_x1=min(header_rect.x1, reference_x1),
        drw_number_x0=max(header_rect.x0, drw_number_x0),
        drw_number_x1=min(header_rect.x1, drw_number_x1),
        row_number_x0=header_rect.x0 - 2.0,
        row_number_x1=header_rect.x0 + width * 0.04,
    )


def find_parent_table_metrics(page: fitz.Page, page_number: int) -> list[ParentTableMetrics]:
    page_words = page.get_text("words")
    header_rects: list[fitz.Rect] = []

    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = block
        if not is_parent_table_header(str(text)):
            continue

        header_rects.append(fitz.Rect(float(x0), float(y0), float(x1), float(y1)))

    for header_rect in find_parent_table_header_rects_from_words(page_words):
        if any(header_rects_overlap(header_rect, existing_rect) for existing_rect in header_rects):
            continue
        header_rects.append(header_rect)

    header_rects.sort(key=lambda rect: (rect.y0, rect.x0))
    metrics: list[ParentTableMetrics] = []
    for header_rect in header_rects:
        metrics.append(
            build_parent_table_metrics(
                page_number=page_number,
                table_number=len(metrics) + 1,
                header_rect=header_rect,
                page_words=page_words,
            )
        )

    return metrics


def find_row_number_for_y(
    page_words: list[tuple[Any, ...]],
    table: ParentTableMetrics,
    row_y: float,
) -> str:
    row_number_words: list[tuple[Any, ...]] = []

    for word in page_words:
        text = str(word[4]).strip()
        if not text.isdigit():
            continue
        if abs(word_center_y(word) - row_y) > 4.0:
            continue
        center_x = word_center_x(word)
        if table.row_number_x0 <= center_x <= table.row_number_x1:
            row_number_words.append(word)

    if not row_number_words:
        return ""

    row_number_words.sort(key=lambda word: float(word[0]))
    return str(row_number_words[0][4]).strip()


def reference_candidates_for_table(
    page_words: list[tuple[Any, ...]],
    table: ParentTableMetrics,
) -> list[tuple[float, str, fitz.Rect]]:
    candidates: list[tuple[float, str, fitz.Rect]] = []

    for word in page_words:
        code = normalize_drawing_code(str(word[4]))
        if code is None:
            continue

        center_x = word_center_x(word)
        center_y = word_center_y(word)
        if not (table.reference_x0 <= center_x <= table.reference_x1):
            continue
        if center_y <= table.header_rect.y1:
            continue

        candidates.append((center_y, code, word_rect(word)))

    candidates.sort(key=lambda item: (item[0], item[2].x0))
    return candidates


def extract_parent_table_references(page: fitz.Page, page_number: int) -> list[ParentDrawingReference]:
    page_words = page.get_text("words")
    references: list[ParentDrawingReference] = []

    for table in find_parent_table_metrics(page, page_number):
        candidates = reference_candidates_for_table(page_words, table)
        last_y: float | None = None
        seen_row_keys: set[tuple[int, str]] = set()

        for row_y, code, rect in candidates:
            if last_y is None:
                if row_y - table.header_rect.y1 > 45.0:
                    break
            elif row_y - last_y > 35.0:
                break

            row_key = (round(row_y / 2.0), code)
            if row_key in seen_row_keys:
                continue
            seen_row_keys.add(row_key)

            row_number = find_row_number_for_y(page_words, table, row_y)
            references.append(
                ParentDrawingReference(
                    page_number=page_number,
                    table_number=table.table_number,
                    row_number=row_number,
                    reference=code,
                    x0=rect.x0,
                    y0=rect.y0,
                    x1=rect.x1,
                    y1=rect.y1,
                    drw_number_x0=table.drw_number_x0,
                    drw_number_x1=table.drw_number_x1,
                )
            )
            last_y = row_y

    return references


def drw_no_search_rect(page: fitz.Page) -> fitz.Rect:
    # The DRW No. value sits in the bottom title block for both A3 landscape and A4 portrait.
    return fitz.Rect(
        page.rect.width - 275.0,
        page.rect.height - 120.0,
        page.rect.width - 130.0,
        page.rect.height - 92.0,
    )


def extract_drw_no_codes(page: fitz.Page) -> list[str]:
    search_rect = drw_no_search_rect(page)
    codes: list[str] = []

    for word in page.get_text("words"):
        rect = word_rect(word)
        if not rect.intersects(search_rect):
            continue

        code = normalize_drawing_code(str(word[4]))
        if code is None or code in codes:
            continue
        codes.append(code)

    return codes


def build_drw_no_index(doc: fitz.Document) -> dict[str, list[DrawingNumberLocation]]:
    index: dict[str, list[DrawingNumberLocation]] = defaultdict(list)

    for page_index, page in enumerate(doc, start=1):
        for code in extract_drw_no_codes(page):
            index[code].append(DrawingNumberLocation(code=code, page_number=page_index))

    return dict(index)


def match_parent_reference(
    reference: str,
    source_page: int,
    drw_no_index: dict[str, list[DrawingNumberLocation]],
) -> tuple[str, str, tuple[DrawingNumberLocation, ...]]:
    all_exact_matches = tuple(drw_no_index.get(reference, []))

    if all_exact_matches:
        if len(all_exact_matches) == 1:
            return "exact_unique", "exact", all_exact_matches
        return "exact_multiple", "exact", all_exact_matches

    return "not_found", "", ()


def collect_parent_drawing_number_matches(
    doc: fitz.Document,
) -> list[tuple[ParentDrawingReference, str, str, tuple[DrawingNumberLocation, ...]]]:
    drw_no_index = build_drw_no_index(doc)
    references: list[ParentDrawingReference] = []

    for page_index, page in enumerate(doc, start=1):
        references.extend(extract_parent_table_references(page, page_index))

    logging.info(
        "NUMERO PLANO: %s DRW No. indexados, %s referencias detectadas.",
        sum(len(locations) for locations in drw_no_index.values()),
        len(references),
    )

    matches: list[tuple[ParentDrawingReference, str, str, tuple[DrawingNumberLocation, ...]]] = []
    for reference in references:
        status, match_type, locations = match_parent_reference(
            reference.reference,
            reference.page_number,
            drw_no_index,
        )
        matches.append((reference, status, match_type, locations))

    return matches


def analyze_parent_drawing_numbers(pdf_path: Path) -> list[ParentDrawingNumberDryRunRow]:
    logging.info("Dry-run NUMERO PLANO: analizando %s", pdf_path.name)
    doc = fitz.open(str(pdf_path))

    try:
        rows: list[ParentDrawingNumberDryRunRow] = []
        for reference, status, match_type, matches in collect_parent_drawing_number_matches(doc):
            rows.append(
                ParentDrawingNumberDryRunRow(
                    parent_page=reference.page_number,
                    table_number=reference.table_number,
                    row_number=reference.row_number,
                    reference=reference.reference,
                    status=status,
                    match_type=match_type,
                    matches=matches,
                )
            )
        return rows
    finally:
        doc.close()


def format_match_pages(matches: tuple[DrawingNumberLocation, ...]) -> str:
    return ", ".join(str(match.page_number) for match in matches)


def format_match_codes(matches: tuple[DrawingNumberLocation, ...]) -> str:
    return ", ".join(f"{match.code}@{match.page_number}" for match in matches)


def write_parent_drawing_number_report(
    pdf_path: Path,
    report_path: Path,
    rows: list[ParentDrawingNumberDryRunRow],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with report_path.open("w", encoding="utf-8-sig", newline="") as report_file:
        writer = csv.DictWriter(
            report_file,
            fieldnames=[
                "pdf",
                "parent_page",
                "table",
                "row",
                "reference",
                "status",
                "match_type",
                "matched_pages",
                "matched_drw_numbers",
            ],
            delimiter=";",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "pdf": pdf_path.name,
                    "parent_page": row.parent_page,
                    "table": row.table_number,
                    "row": row.row_number,
                    "reference": row.reference,
                    "status": row.status,
                    "match_type": row.match_type,
                    "matched_pages": format_match_pages(row.matches),
                    "matched_drw_numbers": format_match_codes(row.matches),
                }
            )


def log_parent_drawing_number_summary(
    pdf_path: Path,
    report_path: Path,
    rows: list[ParentDrawingNumberDryRunRow],
) -> None:
    status_counts = Counter(row.status for row in rows)
    logging.info(
        "Informe NUMERO PLANO generado: %s",
        report_path,
    )
    logging.info(
        "Resumen %s: referencias=%s exact_unique=%s exact_multiple=%s not_found=%s",
        pdf_path.name,
        len(rows),
        status_counts["exact_unique"],
        status_counts["exact_multiple"],
        status_counts["not_found"],
    )


def run_parent_drawing_number_dry_run(pdf_paths: list[Path], output_dir: Path) -> None:
    for pdf_path in pdf_paths:
        rows = analyze_parent_drawing_numbers(pdf_path)
        report_path = output_dir / f"{pdf_path.stem}{PARENT_DRAWING_NUMBER_REPORT_SUFFIX}"
        write_parent_drawing_number_report(pdf_path, report_path, rows)
        log_parent_drawing_number_summary(pdf_path, report_path, rows)


def plan_parent_drawing_number_updates(doc: fitz.Document) -> dict[int, list[ParentDrawingNumberUpdate]]:
    updates_by_page: dict[int, list[ParentDrawingNumberUpdate]] = defaultdict(list)
    status_counts: Counter[str] = Counter()

    for reference, status, _match_type, matches in collect_parent_drawing_number_matches(doc):
        status_counts[status] += 1
        if status not in PARENT_DRAWING_NUMBER_WRITE_STATUSES:
            continue
        if not matches:
            continue

        updates_by_page[reference.page_number].append(
            ParentDrawingNumberUpdate(
                reference=reference,
                matches=matches,
                status=status,
            )
        )

    update_count = sum(len(updates) for updates in updates_by_page.values())
    logging.info(
        "NUMERO PLANO: escrituras planificadas=%s exact_unique=%s exact_multiple=%s not_found=%s",
        update_count,
        status_counts["exact_unique"],
        status_counts["exact_multiple"],
        status_counts["not_found"],
    )

    return dict(updates_by_page)


def font_size_for_parent_table_text(text: str, max_width: float) -> float:
    text_width = fitz.get_text_length(text, fontname=FONT_NAME, fontsize=PARENT_TABLE_FONT_SIZE)
    if text_width <= max_width:
        return PARENT_TABLE_FONT_SIZE

    fitted_size = PARENT_TABLE_FONT_SIZE * max_width / text_width
    return max(3.0, fitted_size)


def parent_drawing_number_cell_rect(reference: ParentDrawingReference) -> fitz.Rect:
    return fitz.Rect(
        reference.drw_number_x0,
        reference.y0 - 1.2,
        reference.drw_number_x1,
        reference.y1 + 1.2,
    )


def write_parent_drawing_number(
    page: fitz.Page,
    update: ParentDrawingNumberUpdate,
    text_color: tuple[float, float, float],
) -> None:
    text = format_match_pages(update.matches)
    cell = parent_drawing_number_cell_rect(update.reference)
    font_size = font_size_for_parent_table_text(text, max(1.0, cell.width - 2.0))
    text_width = fitz.get_text_length(text, fontname=FONT_NAME, fontsize=font_size)
    text_pos = fitz.Point(
        cell.x0 + max(0.0, (cell.width - text_width) / 2),
        update.reference.y1 - 0.6,
    )

    redact_text(page, cell)
    page.insert_text(
        text_pos,
        text,
        fontname=FONT_NAME,
        fontsize=font_size,
        color=text_color,
        overlay=True,
    )

    logging.info(
        "NUMERO PLANO escrito: pagina=%s tabla=%s fila=%s referencia=%s -> paginas=%s "
        "estado=%s redact=%s text_pos=%s font_size=%.2f",
        update.reference.page_number,
        update.reference.table_number,
        update.reference.row_number or "?",
        update.reference.reference,
        text,
        update.status,
        tuple(round(v, 2) for v in cell),
        (round(text_pos.x, 2), round(text_pos.y, 2)),
        font_size,
    )


def font_size_for_width(text: str, field_config: dict[str, Any]) -> float:
    font_size = float(field_config.get("font_size", 7.0))
    max_width = field_config.get("max_width")
    if not max_width:
        return font_size

    text_width = fitz.get_text_length(text, fontname=FONT_NAME, fontsize=font_size)
    if text_width <= float(max_width):
        return font_size

    min_font_size = float(field_config.get("min_font_size", 4.0))
    fitted_size = font_size * float(max_width) / text_width
    return max(min_font_size, fitted_size)


def write_field(
    page: fitz.Page,
    field_name: str,
    text: str,
    field_config: dict[str, Any],
) -> None:
    cover = fitz.Rect(field_config["cover"])
    text_pos = fitz.Point(*field_config["text_pos"])
    font_size = font_size_for_width(text, field_config)

    redact_text(page, cover)
    page.insert_text(
        text_pos,
        text,
        fontname=FONT_NAME,
        fontsize=font_size,
        color=GREEN,
        overlay=True,
    )

    logging.info(
        "Campo escrito: %-8s valor='%s' redact=%s text_pos=%s font_size=%.2f",
        field_name,
        text,
        tuple(round(v, 2) for v in field_config["cover"]),
        tuple(round(v, 2) for v in field_config["text_pos"]),
        font_size,
    )


def write_centered_field(
    page: fitz.Page,
    field_name: str,
    text: str,
    field_config: dict[str, Any],
) -> None:
    cover = fitz.Rect(field_config["cover"])
    cell = fitz.Rect(field_config.get("cell", field_config["cover"]))
    font_size = font_size_for_width(text, field_config)
    text_width = fitz.get_text_length(text, fontname=FONT_NAME, fontsize=font_size)
    text_pos = fitz.Point(cell.x0 + max(0.0, (cell.width - text_width) / 2), field_config["baseline_y"])

    redact_text(page, cover)
    page.insert_text(
        text_pos,
        text,
        fontname=FONT_NAME,
        fontsize=font_size,
        color=GREEN,
        overlay=True,
    )

    logging.info(
        "Campo escrito: %-8s valor='%s' redact=%s text_pos=%s font_size=%.2f",
        field_name,
        text,
        tuple(round(v, 2) for v in field_config["cover"]),
        (round(text_pos.x, 2), round(text_pos.y, 2)),
        font_size,
    )


def write_sheet_field(
    page: fitz.Page,
    sheet_number: str,
    total_sheets: str,
    field_config: dict[str, Any],
) -> None:
    write_centered_field(page, "sheet_no", sheet_number, field_config["current"])
    write_centered_field(page, "sheet_total", total_sheets, field_config["total"])


def redact_text(page: fitz.Page, rect: fitz.Rect) -> None:
    page.add_redact_annot(rect, fill=None, cross_out=False)
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )


def repair_a3_reviewed_approved_date_cells(
    page: fitz.Page,
    source_doc: fitz.Document,
    source_page_index: int,
) -> None:
    repair_config = A3_REVISION_DATE_REPAIR
    redact_rect = fitz.Rect(repair_config["redact"])

    redact_text(page, redact_rect)

    source_date_cell = fitz.Rect(repair_config["source_date_cell"])
    for target_date_cell in repair_config["target_date_cells"]:
        page.show_pdf_page(
            fitz.Rect(target_date_cell),
            source_doc,
            source_page_index,
            clip=source_date_cell,
            overlay=True,
        )

    logging.info(
        "Fechas A3 reparadas desde celda VERIFIED: redact=%s source=%s targets=%s",
        tuple(round(v, 2) for v in repair_config["redact"]),
        tuple(round(v, 2) for v in repair_config["source_date_cell"]),
        [tuple(round(v, 2) for v in target) for target in repair_config["target_date_cells"]],
    )


def clean_revision_history_error_rows(page: fitz.Page, page_format: str) -> None:
    repair_config = REVISION_HISTORY_ERROR_ROWS.get(page_format)
    if repair_config is None:
        return

    search_rect = fitz.Rect(repair_config["search"])
    rows_to_clean: dict[int, str] = {}

    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if "ERROR:" not in span["text"]:
                    continue

                span_rect = fitz.Rect(span["bbox"])
                if not span_rect.intersects(search_rect):
                    continue

                span_y = (span_rect.y0 + span_rect.y1) / 2
                for row_index, row in enumerate(repair_config["rows"]):
                    row_rect = fitz.Rect(row["rect"])
                    if row_rect.y0 <= span_y <= row_rect.y1:
                        rows_to_clean[row_index] = row["label"]
                        break

    for row_index in sorted(rows_to_clean):
        redact_text(page, fitz.Rect(repair_config["rows"][row_index]["rect"]))

    if rows_to_clean:
        logging.info(
            "Filas de historico de revision limpiadas: formato=%s filas=%s",
            page_format,
            ", ".join(rows_to_clean[index] for index in sorted(rows_to_clean)),
        )


def clean_revision_code_error_text(page: fitz.Page) -> None:
    error_rects: list[fitz.Rect] = []

    for word in page.get_text("words"):
        x0, y0, x1, y1, text, *_ = word
        if "ERROR:" not in text or "REVIS" not in text or "00" not in text:
            continue

        error_rects.append(fitz.Rect(x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0))

    for rect in error_rects:
        redact_text(page, rect)

    if error_rects:
        logging.info("Textos ERROR:REVISION00 limpiados: %s", len(error_rects))


def field_values_for_page(page_index: int, total_pages: int, change_config: ChangeConfig) -> dict[str, str]:
    return {
        **change_config.fields,
        "sheet_current": str(page_index),
        "sheet_total": str(total_pages),
    }


def process_pdf(
    input_pdf: Path,
    output_pdf: Path,
    config_path: Path | None = None,
) -> None:
    """Process one PDF using a TOML change configuration."""
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    resolved_config_path = resolve_config_path(config_path)
    change_config = load_change_config(resolved_config_path)

    processed = process_pdf_with_config(
        input_pdf,
        output_pdf,
        dry_run=False,
        change_config=change_config,
    )
    if not processed:
        raise RuntimeError(f"No se proceso ninguna pagina de {input_pdf.name}.")


def process_pdf_with_config(
    pdf_path: Path,
    output_path: Path,
    dry_run: bool,
    change_config: ChangeConfig,
) -> bool:
    logging.info("Procesando archivo: %s", pdf_path.name)
    doc = fitz.open(str(pdf_path))
    source_doc = fitz.open(str(pdf_path))
    processed_any_page = False
    temp_path: Path | None = None
    parent_drawing_number_updates: dict[int, list[ParentDrawingNumberUpdate]] = {}
    parent_drawing_number_text_color = change_config.drw_number_color or RED

    try:
        if change_config.update_parent_drawing_numbers:
            parent_drawing_number_updates = plan_parent_drawing_number_updates(doc)

        for page_index, page in enumerate(doc, start=1):
            page_format, config = detect_page_format(page)
            if config is None:
                logging.warning("Archivo %s pagina %s omitida por formato no detectado.", pdf_path.name, page_index)
                continue

            processed_any_page = True
            logging.info(
                "Pagina procesada: archivo=%s pagina=%s/%s formato=%s",
                pdf_path.name,
                page_index,
                doc.page_count,
                page_format,
            )

            values = field_values_for_page(page_index, doc.page_count, change_config)

            if change_config.clean_revision_errors:
                clean_revision_history_error_rows(page, page_format)
                clean_revision_code_error_text(page)

            if change_config.repair_a3_review_dates and page_format == "A3_LANDSCAPE":
                repair_a3_reviewed_approved_date_cells(page, source_doc, page_index - 1)

            for update in parent_drawing_number_updates.get(page_index, []):
                write_parent_drawing_number(page, update, parent_drawing_number_text_color)

            for field_name in EDITABLE_TEXT_FIELDS:
                if field_name in values:
                    field_config = config[field_name]
                    if field_config.get("align") == "center":
                        write_centered_field(page, field_name, values[field_name], field_config)
                    else:
                        write_field(page, field_name, values[field_name], field_config)

            if change_config.update_sheet:
                write_sheet_field(page, values["sheet_current"], values["sheet_total"], config["sheet"])

        if not processed_any_page:
            logging.warning("No se guardara %s porque no se proceso ninguna pagina.", pdf_path.name)
            return False

        if dry_run:
            logging.info("DRY_RUN activo: no se guarda %s", output_path.name)
            return True

        temp_path = save_pdf_to_temp(doc, output_path)
    finally:
        source_doc.close()
        doc.close()

    if temp_path:
        replace_saved_pdf(temp_path, output_path)
        logging.info("PDF modificado guardado: %s", output_path)

    return True


def save_pdf_to_temp(doc: fitz.Document, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = unique_temp_path(output_path)

    doc.save(str(temp_path), garbage=4, deflate=True)
    return temp_path


def unique_temp_path(output_path: Path) -> Path:
    base_name = f".{output_path.name}.{os.getpid()}.tmp"
    temp_path = output_path.with_name(base_name)
    counter = 1

    while temp_path.exists():
        temp_path = output_path.with_name(f"{base_name}.{counter}")
        counter += 1

    return temp_path


def replace_saved_pdf(temp_path: Path, output_path: Path) -> None:
    try:
        temp_path.replace(output_path)
    except PermissionError:
        logging.error(
            "No se pudo reemplazar %s. Cierra cualquier visor de PDF que tenga abierto ese archivo "
            "o elimina el PDF de salida anterior y vuelve a ejecutar.",
            output_path,
        )
        raise


def iter_coordinate_preview_fields(config: dict[str, dict[str, Any]]):
    for field_name, field_config in config.items():
        if "cover" in field_config:
            yield field_name, field_config
            continue

        for subfield_name, subfield_config in field_config.items():
            yield f"{field_name}_{subfield_name}", subfield_config


def preview_point_for_field(field_config: dict[str, Any]) -> fitz.Point:
    if "text_pos" in field_config:
        return fitz.Point(*field_config["text_pos"])

    cell = fitz.Rect(field_config.get("cell", field_config["cover"]))
    return fitz.Point(cell.x0, field_config["baseline_y"])


def generate_coordinate_preview(pdf_path: Path, page_index: int, preview_path: Path) -> bool:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]
        page_format, config = detect_page_format(page)
        if config is None:
            return False

        logging.info(
            "Generando preview de coordenadas: archivo=%s pagina=%s formato=%s",
            pdf_path.name,
            page_index + 1,
            page_format,
        )

        for field_name, field_config in iter_coordinate_preview_fields(config):
            rect = fitz.Rect(field_config["cover"])
            point = preview_point_for_field(field_config)

            page.draw_rect(rect, color=(1, 0, 0), width=0.8, overlay=True)
            page.draw_line((point.x - 2, point.y), (point.x + 2, point.y), color=(0, 0, 1), width=0.8)
            page.draw_line((point.x, point.y - 2), (point.x, point.y + 2), color=(0, 0, 1), width=0.8)
            page.insert_text(
                (rect.x0, max(8, rect.y0 - 2)),
                field_name,
                fontname=FONT_NAME,
                fontsize=5,
                color=(1, 0, 0),
                overlay=True,
            )

        preview_path.parent.mkdir(parents=True, exist_ok=True)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pix.save(str(preview_path))
        return True
    finally:
        doc.close()


def generate_previews_for_inputs(pdf_paths: list[Path], output_dir: Path = OUTPUT_DIR) -> None:
    preview_dir = output_dir / "previews"
    for pdf_path in pdf_paths:
        doc = fitz.open(str(pdf_path))
        try:
            page_count = doc.page_count
        finally:
            doc.close()

        for page_index in range(page_count):
            preview_path = preview_dir / f"{pdf_path.stem}_page_{page_index + 1:02d}_coordinates.png"
            generate_coordinate_preview(pdf_path, page_index, preview_path)


