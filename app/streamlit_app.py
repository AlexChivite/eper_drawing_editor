from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pdf_tool.processor import DEFAULT_CHANGE_CONFIG, process_pdf


st.set_page_config(page_title="PDF Tool", layout="centered")
st.title("Modificacion de PDFs de planos")

uploaded_pdf = st.file_uploader("PDF", type=["pdf"])

if uploaded_pdf is not None:
    if st.button("Procesar PDF", type="primary"):
        original_name = Path(uploaded_pdf.name).name

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            input_pdf = temp_dir / original_name
            output_pdf = temp_dir / f"{Path(original_name).stem}_modificado.pdf"

            input_pdf.write_bytes(uploaded_pdf.getbuffer())

            try:
                process_pdf(input_pdf, output_pdf, DEFAULT_CHANGE_CONFIG)
                processed_pdf = output_pdf.read_bytes()
            except Exception as exc:
                st.error(f"No se pudo procesar el PDF: {exc}")
            else:
                st.success("PDF procesado.")
                st.download_button(
                    "Descargar PDF modificado",
                    data=processed_pdf,
                    file_name=output_pdf.name,
                    mime="application/pdf",
                )
