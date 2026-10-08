#!/bin/bash
# Relanza la descarga por mesa hasta completar (reanudable). Uso: nohup caffeinate -i bash run_detalle.sh &
cd "$(dirname "$0")"
while true; do
  uv run python src/detalle_mesas.py >> data/detalle.log 2>&1
  if [ -z "$(uv run python -c 'import sys;sys.path.insert(0,"src");import detalle_mesas as d;print(len(d.pendientes()) or "")')" ]; then break; fi
  echo "$(date +%T) reintentando en 30 s" >> data/detalle.log; sleep 30
done
echo "$(date +%T) COMPLETO" >> data/detalle.log
