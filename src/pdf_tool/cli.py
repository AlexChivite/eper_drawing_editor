from __future__ import annotations

import argparse
import logging
import os
import tomllib
from pathlib import Path

from .processor import (
    DEFAULT_CHANGE_CONFIG,
    DRY_RUN,
    GENERATE_COORDINATE_PREVIEWS,
    INPUT_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    env_bool,
    find_input_pdfs,
    generate_previews_for_inputs,
    load_change_config,
    process_pdf,
    process_pdf_with_config,
    resolve_config_path,
    run_parent_drawing_number_dry_run,
    setup_logging,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modifica PDFs de planos usando un archivo TOML de cambios.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=os.getenv("PDF_UPDATER_CONFIG", str(DEFAULT_CHANGE_CONFIG)),
        help="Ruta al archivo TOML de cambios. Por defecto: config/config.toml",
    )
    parser.add_argument(
        "--input-dir",
        default=os.getenv("PDF_UPDATER_INPUT_DIR", str(INPUT_DIR)),
        help="Carpeta con los PDFs de entrada. Por defecto: input_pdfs",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("PDF_UPDATER_OUTPUT_DIR", str(OUTPUT_DIR)),
        help="Carpeta para PDFs de salida, logs e informes. Por defecto: output_pdfs",
    )
    parser.add_argument(
        "--parent-drawing-number-dry-run",
        action="store_true",
        help=(
            "Genera un informe CSV para rellenar NUMERO PLANO / DRW NUMBER "
            "a partir de REFERENCIA / REFERENCE y los DRW No. encontrados. No modifica PDFs."
        ),
    )
    return parser.parse_args()


def resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)
    if resolved_path.is_absolute():
        return resolved_path
    return PROJECT_ROOT / resolved_path


def log_change_config(change_config) -> None:
    logging.info("Archivo de cambios: %s", change_config.path)
    logging.info(
        "Cambios solicitados: fields=%s update_sheet=%s repair_a3_review_dates=%s "
        "clean_revision_errors=%s update_parent_drawing_numbers=%s drw_number_color=%s",
        ", ".join(change_config.fields) if change_config.fields else "(ninguno)",
        change_config.update_sheet,
        change_config.repair_a3_review_dates,
        change_config.clean_revision_errors,
        change_config.update_parent_drawing_numbers,
        change_config.drw_number_color_name or "(por defecto)",
    )


def main() -> int:
    args = parse_args()
    dry_run = env_bool("PDF_UPDATER_DRY_RUN", DRY_RUN)
    generate_previews = env_bool("PDF_UPDATER_GENERATE_PREVIEWS", GENERATE_COORDINATE_PREVIEWS)
    input_dir = resolve_project_path(args.input_dir)
    output_dir = resolve_project_path(args.output_dir)

    setup_logging(output_dir)

    if not input_dir.exists():
        logging.error("No existe la carpeta de entrada: %s", input_dir)
        return 1

    pdf_paths = find_input_pdfs(input_dir)
    if not pdf_paths:
        logging.error("No se encontraron PDFs en %s", input_dir)
        return 1

    logging.info("PDFs encontrados en %s: %s", input_dir, len(pdf_paths))

    if args.parent_drawing_number_dry_run:
        logging.info("Modo dry-run NUMERO PLANO activo. No se modificaran PDFs.")
        run_parent_drawing_number_dry_run(pdf_paths, output_dir)
        logging.info("Proceso terminado.")
        return 0

    config_path = resolve_config_path(Path(args.config))
    try:
        change_config = load_change_config(config_path)
    except (FileNotFoundError, ValueError, tomllib.TOMLDecodeError) as exc:
        logging.error("%s", exc)
        return 1

    log_change_config(change_config)

    if dry_run:
        logging.info("Modo DRY_RUN activo.")

    if generate_previews:
        generate_previews_for_inputs(pdf_paths, output_dir)

    had_errors = False
    for pdf_path in pdf_paths:
        output_path = output_dir / pdf_path.name
        try:
            if dry_run:
                process_pdf_with_config(pdf_path, output_path, dry_run=True, change_config=change_config)
            else:
                process_pdf(pdf_path, output_path, config_path)
        except Exception:
            had_errors = True
            logging.exception("Error procesando %s", pdf_path)

    logging.info("Proceso terminado.")
    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
