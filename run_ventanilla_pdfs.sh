#!/bin/bash
# Descarga las actas que faltan de Ventanilla (elección distrital 4) y al terminar retoma las mesas de SMP.
# Reanudable: relanzar y continúa por el manifiesto. Si ONPE pide verificación, suena la alarma y espera.
cd "$(dirname "$0")"
until uv run python src/descargar_pdfs.py "" 240106 4 >> data/pdfs.log 2>&1; do
  echo "$(date +%T) reintento pdfs Ventanilla en 30 s" >> data/pdfs.log
  sleep 30
done
echo "$(date +%T) PDFs Ventanilla eleccion 4 listos; retomando mesas de SMP" >> data/pdfs.log
exec bash run_detalle.sh
