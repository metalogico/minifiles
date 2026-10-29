"""Seed only the explicit local-data test volume, preserving existing files."""

import json
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = dict(
    line.split("=", 1)
    for line in (root / ".env.local").read_text().splitlines()
    if line and not line.startswith("#")
)
origin = "http://127.0.0.1:8090"
headers = {"Origin": origin, "X-MiniFiles": "1", "Content-Type": "application/json"}


def api(path, body=None):
    req = urllib.request.Request(
        origin + "/api" + path,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(req) as response:
        result = json.load(response)
        if "Set-Cookie" in response.headers:
            headers["Cookie"] = response.headers["Set-Cookie"].split(";", 1)[0]
        return result


api("/login", {"username": env["MINIFILES_USERNAME"], "password": env["MINIFILES_PASSWORD"]})
existing = {s["path"] for s in api("/sections")}
for name, path, color in [
    ("Books", "Books", "blue"),
    ("Movies", "Movies", "red"),
    ("TV Shows", "TV Shows", "purple"),
    ("ROMs", "ROMs", "green"),
    ("Downloads", "Downloads", "yellow"),
    ("Backups", "Backups", "slate"),
]:
    if path not in existing:
        api("/sections", {"name": name, "path": path, "color": color, "create_folder": True})
folder = root / "local-data/Books/Sci-Fi"
for name in ["Dune", "Fondazione", "Hyperion", "The Expanse", "Altri libri"]:
    (folder / name).mkdir(parents=True, exist_ok=True)
for name, content in {
    "leggimi.txt": "Dati di prova MiniFiles. Nessun contenuto personale.\n",
    "catalogo.csv": "titolo,autore\nDune,Frank Herbert\nFondazione,Isaac Asimov\n",
    "metadati.json": '{"tipo":"demo","file_reali":true}\n',
    "note.md": "# La libreria di prova\n\nOrganizza qui i tuoi file.\n",
    "da-leggere.txt": "Dune\nFondazione\nHyperion\n",
    "indice.csv": "cartella,descrizione\nDune,Serie di Dune\n",
    "preferiti.json": '{"libri":["Dune","Hyperion"]}\n',
    "appunti.txt": "Un file di testo per provare la navigazione.\n",
    "archivio.md": "# Archivio locale\n\nEsempio dimostrativo.\n",
    "licenza.txt": "Questi dati sono stati generati soltanto per le prove locali.\n",
}.items():
    target = folder / name
    if not target.exists():
        target.write_text(content)
api("/stats/refresh", {})
print("Demo data created in local-data; existing files preserved.")
