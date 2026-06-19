"""
dashboard/db.py — Conexión centralizada a la base de datos.

Todas las páginas del dashboard deben importar get_connection() desde aquí
en lugar de abrir sqlite3.connect() directamente.

@st.cache_resource garantiza que se crea UNA sola conexión compartida
por todo el proceso de Streamlit y no se reconecta en cada rerun.
"""

import sqlite3
from pathlib import Path

import streamlit as st

# Ruta canónica: db/premodern.db relativa a la raíz del proyecto
DB_PATH = Path(__file__).resolve().parent.parent / "db" / "premodern.db"


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    """Devuelve la conexión SQLite compartida (cacheada por Streamlit)."""
    if not DB_PATH.exists():
        st.error(
            f"Base de datos no encontrada en `{DB_PATH}`. "
            "Copiá el archivo `premodern.db` a la carpeta `db/`."
        )
        st.stop()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
