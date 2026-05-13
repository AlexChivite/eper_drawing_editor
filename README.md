# Uso de pdf_updater.py

Este proyecto procesa los PDFs de `input_pdfs/` y crea copias modificadas en
`output_pdfs/`. Cada PDF se numera por sus paginas internas: hoja actual =
posicion real de la pagina dentro del PDF, y total = numero total de paginas de
ese mismo PDF. El script no genera un PDF unido final.

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si ya existe `.venv`, solo instala o actualiza requisitos:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecucion normal

Antes de ejecutar, edita `changes.toml` para indicar que cambios quieres aplicar.
El script solo modifica los campos y opciones que aparezcan ahi.

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py
```

Tambien puedes indicar otro archivo de cambios:

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py --config .\mi_config.toml
```

Resultados:

- PDFs modificados: `output_pdfs/<nombre_original>.pdf`
- Log: `output_pdfs/process.log`

## Archivo de cambios

`changes.toml` tiene dos secciones:

```toml
[fields]
title = "TK FA TRN NAC FIBERS SG7.0-7.X"
drawing_title = "TK FA TRN NAC FIBERS SG7.0-7.X"
drawn = "EPER"
verified = "AHURTADO"
reviewed = "JACAMPOS"
approved = "CMF"
control_plan_quality_specification = "1"

[options]
drw_number_color = "green"
update_sheet = true
repair_a3_review_dates = false
clean_revision_errors = false
update_parent_drawing_numbers = false
```

- Si un campo aparece en `[fields]`, se elimina el texto antiguo y se escribe ese valor.
- Si un campo no aparece, se deja intacto.
- `control_plan_quality_specification` modifica la celda superior izquierda situada a la derecha de `PLAN DE CONTROL / CONTROL PLAN (QUALITY SPECIFICATION)` y se escribe siempre en verde.
- `drw_number_color` controla solo el color de `NUMERO PLANO / DRW NUMBER`. Valores validos: `"red"` o `"green"`. Si se omite, se escribe en rojo. Los demas campos y la paginacion se escriben siempre en verde.
- `update_sheet` actualiza la paginacion con la posicion real de cada pagina dentro del PDF.
- `repair_a3_review_dates` activa la reparacion especifica de fechas A3.
- `clean_revision_errors` activa la limpieza de filas/textos `ERROR:`.
- `update_parent_drawing_numbers` rellena `NUMERO PLANO / DRW NUMBER` en tablas padre usando `REFERENCE` y el `DRW No.` del cajetin inferior.

El `changes.toml` incluido por defecto deja `[fields]` vacio, activa
`update_parent_drawing_numbers = true` y usa `drw_number_color = "red"`.

## Prueba sin guardar PDFs

Puedes cambiar `DRY_RUN = True` al principio de `pdf_updater.py` o ejecutar:

```powershell
$env:PDF_UPDATER_DRY_RUN = "1"
.\.venv\Scripts\python.exe .\pdf_updater.py
Remove-Item Env:\PDF_UPDATER_DRY_RUN
```

## Dry run de NUMERO PLANO / DRW NUMBER

Para comprobar que referencias de las tablas padre pueden enlazarse con paginas
del mismo PDF por el campo inferior `DRW No.`, ejecuta:

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py --parent-drawing-number-dry-run
```

El informe CSV se guarda en `output_pdfs/` y no se modifica ningun PDF. El
script usa solo coincidencias exactas entre `REFERENCE` y el `DRW No.` del
cajetin inferior. Si hay varias coincidencias exactas, se listan todas sus
paginas separadas por coma y espacio.

Para aplicar la escritura real, activa esta opcion en `changes.toml`:

```toml
[options]
drw_number_color = "red"
update_parent_drawing_numbers = true
```

Solo se escriben coincidencias exactas. Los estados `exact_unique` y
`exact_multiple` se rellenan; en `exact_multiple` se escriben todas las paginas
en la celda, por ejemplo `76, 77`. Los `not_found` se dejan sin tocar.

Tambien puedes probar una carpeta concreta:

```powershell
.\.venv\Scripts\python.exe .\pdf_updater.py --input-dir ".\Planos a numerar" --parent-drawing-number-dry-run
```

## Vista previa de coordenadas

Para generar PNGs con las cajas de coordenadas dibujadas encima, cambia
`GENERATE_COORDINATE_PREVIEWS = True` o ejecuta:

```powershell
$env:PDF_UPDATER_GENERATE_PREVIEWS = "1"
$env:PDF_UPDATER_DRY_RUN = "1"
.\.venv\Scripts\python.exe .\pdf_updater.py
Remove-Item Env:\PDF_UPDATER_GENERATE_PREVIEWS
Remove-Item Env:\PDF_UPDATER_DRY_RUN
```

Los PNGs se guardan en `output_pdfs/previews/`.

## Ajuste de coordenadas

Edita los diccionarios `CONFIG_A3_LANDSCAPE` y `CONFIG_A4_PORTRAIT` al inicio
de `pdf_updater.py`.

- `FONT` y `FONTSIZE` controlan fuente y tamano base; `GREEN` se usa siempre para campos/paginacion, y `drw_number_color` elige si `NUMERO PLANO / DRW NUMBER` usa `RED` o `GREEN`.
- `cover = (x0, y0, x1, y1)` es el rectangulo donde se elimina el texto antiguo.
- `text_pos = (x, y)` es la posicion del texto nuevo.
- En `sheet`, `current` y `total` eliminan y reescriben solo los numeros de
  hoja; el texto original `DE/OF` se conserva.
- En PyMuPDF el origen `(0, 0)` esta arriba a la izquierda.
- Aumentar `x` mueve a la derecha.
- Aumentar `y` mueve hacia abajo.
- Si el texto no cabe, baja `font_size` en ese campo.
- Si el rectangulo toca texto que quieres conservar, acerca sus bordes 1 o 2 puntos hacia dentro.

Primero genera previews con PDFs de muestra, ajusta coordenadas y despues
ejecuta el modo normal sobre el PDF multipagina.

## Reparacion especifica A3

Si `repair_a3_review_dates = true`, en planos A3 horizontales el script elimina el texto erroneo que invade las
celdas de fecha de `REVISADO/REVIEWED` y `APROBADO/APPROVED`. Despues copia la
celda de fecha desde `VERIFICADO/VERIFIED` en la misma pagina, de forma que cada
PDF conserva su propia fecha y esa fecha se aplica a las cuatro filas.

## Limpieza de historico de revision

Si `clean_revision_errors = true` y una fila `R1`-`R4` de la tabla de historico de revision contiene textos
`ERROR:`, el script elimina el texto de toda esa fila con redaccion real. Las
lineas rojas de la tabla se conservan. Tambien se eliminan textos sueltos con el
patron `ERROR:REVISION00` / `ERROR:REVISIÓN00`.
