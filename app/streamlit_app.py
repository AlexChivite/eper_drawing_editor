from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pdf_tool import processor


processor = importlib.reload(processor)
EDITABLE_TEXT_FIELDS = processor.EDITABLE_TEXT_FIELDS


FIELD_LABELS = {
    "title": "Title",
    "drawing_title": "Drawing title",
    "drawn": "Drawn",
    "verified": "Verified",
    "reviewed": "Reviewed",
    "approved": "Approved",
    "control_plan_quality_specification": "Control plan quality specification",
}

OPTION_LABELS = {
    "red": "Rojo",
    "green": "Verde",
}


def selected_field_values() -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    empty_fields: list[str] = []

    for field_name in EDITABLE_TEXT_FIELDS:
        enabled = bool(st.session_state.get(f"{field_name}_enabled"))
        value = str(st.session_state.get(f"{field_name}_value", "")).strip()
        if not enabled:
            continue
        if not value:
            empty_fields.append(FIELD_LABELS[field_name])
            continue
        fields[field_name] = value

    return fields, empty_fields


st.set_page_config(page_title="PDF Tool", layout="centered")
st.title("Modificacion de PDFs de planos")

with st.form("pdf_changes_form"):
    uploaded_pdf = st.file_uploader("PDF", type=["pdf"])

    st.subheader("Campos")
    for field_name in EDITABLE_TEXT_FIELDS:
        checkbox_col, value_col = st.columns([1, 2])
        label = FIELD_LABELS[field_name]
        checkbox_col.checkbox(label, key=f"{field_name}_enabled")
        value_col.text_input(
            f"Valor para {label}",
            key=f"{field_name}_value",
            placeholder="Valor",
            label_visibility="collapsed",
        )

    st.subheader("Opciones")
    drw_number_color = st.radio(
        "Color de NUMERO PLANO / DRW NUMBER",
        options=["red", "green"],
        format_func=lambda value: OPTION_LABELS[value],
        horizontal=True,
    )
    update_sheet = st.checkbox("Actualizar hoja actual y total", value=True)
    repair_a3_review_dates = st.checkbox("Reparar fechas A3 REVIEWED/APPROVED")
    clean_revision_errors = st.checkbox("Limpiar errores de revision")
    update_parent_drawing_numbers = st.checkbox("Rellenar NUMERO PLANO / DRW NUMBER en tablas padre")

    submitted = st.form_submit_button("Procesar PDF", type="primary")

if submitted:
    st.session_state.pop("processed_pdf", None)
    st.session_state.pop("processed_pdf_name", None)

    selected_fields, empty_fields = selected_field_values()
    selected_options = {
        "update_sheet": update_sheet,
        "repair_a3_review_dates": repair_a3_review_dates,
        "clean_revision_errors": clean_revision_errors,
        "update_parent_drawing_numbers": update_parent_drawing_numbers,
    }

    if uploaded_pdf is None:
        st.error("Sube un PDF antes de procesar.")
    elif empty_fields:
        st.error("Hay campos seleccionados sin valor: " + ", ".join(empty_fields))
    elif not selected_fields and not any(selected_options.values()):
        st.error("Selecciona al menos un campo u opcion de modificacion.")
    else:
        original_name = Path(uploaded_pdf.name).name

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            input_pdf = temp_dir / original_name
            output_pdf = temp_dir / f"{Path(original_name).stem}_modificado.pdf"

            input_pdf.write_bytes(uploaded_pdf.getbuffer())

            try:
                processor.process_pdf_with_changes(
                    input_pdf,
                    output_pdf,
                    fields=selected_fields,
                    drw_number_color=drw_number_color,
                    update_sheet=update_sheet,
                    repair_a3_review_dates=repair_a3_review_dates,
                    clean_revision_errors=clean_revision_errors,
                    update_parent_drawing_numbers=update_parent_drawing_numbers,
                )
                st.session_state["processed_pdf"] = output_pdf.read_bytes()
                st.session_state["processed_pdf_name"] = output_pdf.name
            except Exception as exc:
                st.error(f"No se pudo procesar el PDF: {exc}")
            else:
                st.success("PDF procesado.")

if "processed_pdf" in st.session_state:
    st.download_button(
        "Descargar PDF modificado",
        data=st.session_state["processed_pdf"],
        file_name=st.session_state["processed_pdf_name"],
        mime="application/pdf",
    )
