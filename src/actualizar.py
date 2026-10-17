"""Corre todo el flujo en orden: descarga → capas base → focos → eventos →
detalle 3D → exportación del tablero → contexto.

Uso: python src/actualizar.py
El detalle 3D se regenera siempre: con datos nuevos cambian los ids de evento.
"""
from pathlib import Path
import subprocess
import sys
import time

SRC = Path(__file__).resolve().parent
PASOS = ["01_descargar.py", "02_mapa_base.py", "03_cobertura.py", "04_focos.py", "05_eventos.py",
         "06_detalle.py", "07_exportar.py", "08_contexto.py"]

if __name__ == "__main__":
    for paso in PASOS:
        t = time.time()
        print(f"▶ {paso}", flush=True)
        extra = ["--forzar"] if paso == "06_detalle.py" else []
        subprocess.run([sys.executable, "-u", str(SRC / paso), *extra], check=True)
        print(f"  {time.time() - t:.0f} s", flush=True)
