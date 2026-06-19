"""
safe_ingest.py — Ingesta segura de una DB descargada de Colab.

Uso:
    python db/safe_ingest.py <archivo_nuevo.db>

Pasos:
    1. Aplica WAL checkpoint (para que el archivo quede auto-contenido)
    2. Verifica integridad (PRAGMA integrity_check)
    3. Compara conteos contra la DB activa (sanidad)
    4. Si todo OK: respalda la DB activa y reemplaza atómicamente

Ejemplo:
    python db/safe_ingest.py ~/Downloads/premodern.db
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR  = Path(__file__).resolve().parent
DB_ACTIVE = BASE_DIR / "premodern.db"
BACKUP_DIR = BASE_DIR / "Backup"

# Cuántas filas menos se toleran respecto a la DB activa (margen de seguridad)
TOLERANCE_DECKS     = 50
TOLERANCE_DECK_CARDS = 10_000


def get_counts(conn):
    counts = {}
    for t in ["tournaments", "decks", "cards", "deck_cards"]:
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    counts["scraped"] = conn.execute(
        "SELECT COUNT(*) FROM decks WHERE cards_scraped = 1"
    ).fetchone()[0]
    return counts


def main(new_db_path: str):
    new_path = Path(new_db_path).resolve()

    if not new_path.exists():
        print(f"❌ No se encontró el archivo: {new_path}")
        sys.exit(1)

    if new_path.resolve() == DB_ACTIVE.resolve():
        print("❌ El archivo de entrada es el mismo que la DB activa. Usá una copia.")
        sys.exit(1)

    print(f"📂 Archivo entrante:  {new_path}")
    print(f"📂 DB activa:         {DB_ACTIVE}")
    print()

    # ── 1. WAL checkpoint ─────────────────────────────────────────────────────
    print("1/4 Aplicando WAL checkpoint...")
    try:
        c = sqlite3.connect(str(new_path))
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
        print("    OK")
    except Exception as e:
        print(f"    ⚠️  checkpoint falló (puede ser normal si no hay WAL): {e}")

    # ── 2. Integridad ─────────────────────────────────────────────────────────
    print("2/4 Verificando integridad...")
    try:
        c = sqlite3.connect(str(new_path))
        result = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()
    except Exception as e:
        print(f"❌ No se pudo abrir la DB: {e}")
        sys.exit(1)

    if result != "ok":
        print(f"❌ integrity_check falló:\n{result}")
        print("   La DB activa NO fue reemplazada.")
        sys.exit(1)
    print("    OK — integrity_check: ok")

    # ── 3. Sanidad de conteos ─────────────────────────────────────────────────
    print("3/4 Comparando conteos...")
    c_new = sqlite3.connect(str(new_path))
    new_counts = get_counts(c_new)
    c_new.close()

    if DB_ACTIVE.exists():
        c_act = sqlite3.connect(str(DB_ACTIVE))
        act_counts = get_counts(c_act)
        c_act.close()

        print(f"    {'Tabla':15s} {'Activa':>12s} {'Nueva':>12s} {'Diff':>8s}")
        print(f"    {'-'*50}")
        warn = False
        for key in ["tournaments", "decks", "cards", "deck_cards", "scraped"]:
            diff = new_counts[key] - act_counts[key]
            flag = ""
            if key == "decks" and diff < -TOLERANCE_DECKS:
                flag = " ⚠️"
                warn = True
            if key == "deck_cards" and diff < -TOLERANCE_DECK_CARDS:
                flag = " ⚠️"
                warn = True
            print(f"    {key:15s} {act_counts[key]:>12,} {new_counts[key]:>12,} {diff:>+8,}{flag}")

        if warn:
            print()
            print("⚠️  La DB nueva tiene significativamente MENOS filas que la activa.")
            answer = input("   ¿Continuar de todas formas? [s/N]: ").strip().lower()
            if answer != "s":
                print("   Operación cancelada.")
                sys.exit(0)
    else:
        print("    (No hay DB activa previa — se usarán los conteos de la nueva)")
        for key, val in new_counts.items():
            print(f"    {key:15s} {val:>12,}")

    # ── 4. Backup + reemplazo atómico ─────────────────────────────────────────
    print("4/4 Reemplazando DB activa...")
    BACKUP_DIR.mkdir(exist_ok=True)

    if DB_ACTIVE.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        backup_path = BACKUP_DIR / f"premodern - {ts}.db"
        shutil.copy2(str(DB_ACTIVE), str(backup_path))
        print(f"    Backup guardado: {backup_path.name}")

    os.replace(str(new_path), str(DB_ACTIVE))
    print(f"    ✅ DB activa reemplazada con: {new_path.name}")

    # Verificación final
    c = sqlite3.connect(str(DB_ACTIVE))
    final = c.execute("PRAGMA integrity_check").fetchone()[0]
    c.close()
    print(f"\n✅ Listo. integrity_check final: {final}")
    print(f"   Decks: {new_counts['decks']:,}  |  deck_cards: {new_counts['deck_cards']:,}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
