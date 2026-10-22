"""Arma el sitio estático del tablero para GitHub Pages.

dashboard/index.html no trae <!doctype> ni <head> porque también se publica como
Artifact, que los agrega solo. Aquí se envuelve con el mismo esqueleto que usa
src/servir.py, más las etiquetas para que el enlace se vea bien al compartirlo
(descripción, imagen de vista previa e ícono). Solo usa la biblioteca estándar:
corre en GitHub Actions sin instalar nada.

Uso: python src/sitio.py [carpeta_salida]   (por defecto, _site)
"""
from pathlib import Path
import re
import shutil
import sys

sys.path.insert(0, str(Path(__file__).parent))
from servir import ESQUELETO  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
DASH = RAIZ / "dashboard"
URL = "https://alexanderquispe.github.io/incendios-peru/"
TITULO = "Monitor de Incendios Perú"
DESCRIPCION = ("Parte de situación de los incendios forestales del Perú en 2026: focos de calor, área quemada, clima, "
               "población expuesta y respuesta del Estado, con datos satelitales públicos.")
ICONO = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
         "%3Ccircle cx='16' cy='16' r='9' fill='%23ec7a2c'/%3E%3Ccircle cx='16' cy='16' r='14' fill='none' "
         "stroke='%23ec7a2c' stroke-opacity='.35' stroke-width='4'/%3E%3C/svg%3E")


def meta():
    etiquetas = [
        f'<meta name="description" content="{DESCRIPCION}">',
        f'<link rel="icon" href="{ICONO}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{TITULO}">',
        f'<meta property="og:description" content="{DESCRIPCION}">',
        f'<meta property="og:url" content="{URL}">',
        '<meta property="og:locale" content="es_PE">',
    ]
    if (DASH / "assets" / "compartir.png").exists():
        etiquetas += [f'<meta property="og:image" content="{URL}assets/compartir.png">',
                      '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                      '<meta name="twitter:card" content="summary_large_image">']
    return "".join(etiquetas)


def main():
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else RAIZ / "_site").resolve()
    if salida.exists():
        shutil.rmtree(salida)
    shutil.copytree(DASH, salida, ignore=shutil.ignore_patterns(".DS_Store"))
    pagina = (DASH / "index.html").read_text()
    titulo = re.search(r"<title>.*?</title>\s*", pagina)  # al <head>, donde lo buscan los visores de enlaces
    pagina = pagina.replace(titulo.group(0), "") if titulo else pagina
    cabeza = (titulo.group(0).strip() if titulo else f"<title>{TITULO}</title>") + meta()
    html = ESQUELETO.replace("</head>", cabeza + "</head>").replace("{contenido}", pagina)
    (salida / "index.html").write_text(html)
    (salida / ".nojekyll").write_text("")  # sirve los archivos tal cual, sin procesarlos con Jekyll
    archivos = [p for p in salida.rglob("*") if p.is_file()]
    print(f"sitio en {salida}: {len(archivos)} archivos, {sum(p.stat().st_size for p in archivos) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
