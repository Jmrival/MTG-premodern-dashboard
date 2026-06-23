"""
dashboard/db.py — Conexión centralizada a la base de datos.

En local: usa db/premodern.db directamente.
En Streamlit Cloud: descarga el .db desde la última GitHub Release al arrancar.
"""

import sqlite3
import os
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "premodern.db"

GITHUB_REPO = "Jmrival/MTG-premodern-dashboard"
RELEASE_ASSET = "premodern.db"


def _download_db() -> None:
    """Descarga premodern.db desde la última GitHub Release."""
    import requests

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {"Accept": "application/vnd.github+json"}

    # Si hay token de GitHub disponible, úsalo para evitar rate limits de la API
    gh_token = os.environ.get("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN", None)
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    with st.spinner("Descargando base de datos (primera vez, ~30s)…"):
        resp = requests.get(api_url, headers=headers, timeout=30)
        resp.raise_for_status()
        release = resp.json()

        asset_url = next(
            (a["browser_download_url"] for a in release.get("assets", [])
             if a["name"] == RELEASE_ASSET),
            None,
        )
        if not asset_url:
            st.error(
                f"No se encontró `{RELEASE_ASSET}` en la última Release de GitHub. "
                "Publicá una Release con el archivo adjunto."
            )
            st.stop()

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(asset_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(DB_PATH, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    """Devuelve la conexión SQLite compartida (cacheada por Streamlit)."""
    if not DB_PATH.exists():
        # En Streamlit Cloud la DB no existe en disco — descargarla desde Releases
        _download_db()

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
