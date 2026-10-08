"""Alarma sonora para cuando ONPE pide verificación humana.

Suena en ráfagas (3 tonos fuertes cada ~20 s) hasta que: (a) el scraper vuelve a recibir datos (reto resuelto),
(b) existe el archivo data/SILENCIO (silenciar a mano: `touch data/SILENCIO`), o (c) se llama a detener().
"""
import subprocess
from pathlib import Path

SILENCIO = Path(__file__).parent.parent / "data" / "SILENCIO"
_SCRIPT = (
    'for i in $(seq 1 3000); do [ -f "{f}" ] && exit 0; '
    "afplay -v 4 /System/Library/Sounds/Sosumi.aiff 2>/dev/null || osascript -e 'beep 3'; "
    "afplay -v 4 /System/Library/Sounds/Funk.aiff 2>/dev/null; "
    'say -v Monica "reto de verificacion en Chrome" 2>/dev/null; '
    "sleep 15; done"
)
_proc: subprocess.Popen | None = None


def iniciar() -> None:
    global _proc
    SILENCIO.unlink(missing_ok=True)
    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen(["bash", "-c", _SCRIPT.format(f=SILENCIO)])


def detener() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        subprocess.run(["pkill", "-x", "afplay"], check=False)
    _proc = None


def traer_chrome_al_frente() -> None:
    """Trae la ventana de Chrome del scraper al frente (y la restaura si estaba minimizada) para que se vea el reto."""
    script = (
        'tell application "Google Chrome"\n activate\n'
        " if (count of windows) > 0 then set minimized of window 1 to false\n"
        "end tell"
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=10)
