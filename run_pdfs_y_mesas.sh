#!/bin/bash
# 1) PDFs de las 40 actas JEE de Ventanilla (prioridad) 2) retoma las mesas de San Martín de Porres
cd "$(dirname "$0")"
until uv run python src/descargar_pdfs.py 40 >> data/pdfs.log 2>&1; do echo "$(date +%T) reintento pdfs en 30 s" >> data/pdfs.log; sleep 30; done
echo "$(date +%T) PDFs JEE Ventanilla listos; retomando mesas" >> data/pdfs.log
exec bash run_detalle.sh
