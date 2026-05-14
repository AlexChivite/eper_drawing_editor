# PDF Tool

Herramienta Python para modificar PDFs de planos con PyMuPDF. El proyecto queda
preparado para uso local con Streamlit y para empaquetarse como contenedor.

## Estructura

```text
app/
  streamlit_app.py
src/
  pdf_tool/
    __init__.py
    processor.py
    cli.py
config/
  config.toml
requirements.txt
Dockerfile
.dockerignore
```

La logica de negocio esta en `src/pdf_tool/processor.py`. La CLI y Streamlit
llaman a la misma funcion reutilizable:

```python
process_pdf(input_pdf: Path, output_pdf: Path, config_path: Path | None = None) -> None
```

## Ejecutar en local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app/streamlit_app.py
```

Tambien se puede ejecutar la CLI compatible:

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py
```

Opciones utiles:

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py --config .\config\config.toml
.\.venv\Scripts\python.exe .\pdf_updater.py --input-dir .\input_pdfs --output-dir .\output_pdfs
.\.venv\Scripts\python.exe .\pdf_updater.py --parent-drawing-number-dry-run
```

La configuracion por defecto esta en `config/config.toml`.

## Ejecutar con Docker

```powershell
docker build -t pdf-tool .
docker run -p 8501:8501 pdf-tool
```

Despues abre `http://localhost:8501`.

## Azure Container Apps

El `Dockerfile` expone Streamlit en el puerto `8501` y arranca la app con
`--server.address=0.0.0.0`. Para publicar en Azure Container Apps, el flujo
esperado sera:

1. Construir la imagen.
2. Publicarla en un registry, por ejemplo Azure Container Registry.
3. Crear o actualizar la Container App usando esa imagen.
4. Configurar el puerto de entrada como `8501`.

Los PDFs subidos desde Streamlit se procesan en directorios temporales y no se
guardan permanentemente.
