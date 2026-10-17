"""Sirve el tablero en http://localhost:8765 para verlo en el navegador.

index.html no trae <!doctype> ni <head> (así lo espera la publicación como
Artifact); este servidor los agrega y aplica una política de seguridad de
contenido similar a la del visor de Artifacts, para detectar recursos bloqueados.

Uso: python src/servir.py [puerto]
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

DIR = Path(__file__).resolve().parents[1] / "dashboard"
ESQUELETO = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
             '<style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>'
             '</head><body>{contenido}</body></html>')
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net/npm/ "
       "https://unpkg.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; connect-src 'self'; worker-src 'self' blob:")


class Manejador(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            cuerpo = ESQUELETO.replace("{contenido}", (DIR / "index.html").read_text()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Tablero en http://localhost:{puerto}")
    ThreadingHTTPServer(("127.0.0.1", puerto), partial(Manejador, directory=str(DIR))).serve_forever()
