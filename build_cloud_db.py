"""Gera um banco SQLite reduzido (somente Governador/Presidente) para deploy em nuvem."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from import_data import create_aggregates, create_indexes, create_search_indexes, setup_database

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "data" / "votos.sqlite"
TARGET_DB = ROOT / "data" / "votos_cloud.sqlite"
ALLOWED_CARGOS = ("Governador", "Presidente")

COLUMNS = [
    "codigo_cargo",
    "cargo",
    "codigo_votavel",
    "candidato_nome",
    "partido",
    "endereco",
    "bairro",
    "municipio",
    "cep",
    "latitude",
    "longitude",
    "local_votacao",
    "local_nome",
    "secao",
    "zona",
    "quantidade_votos",
    "tipo_voto",
]


def main() -> int:
    if not SOURCE_DB.exists():
        print(f"Banco de origem nao encontrado: {SOURCE_DB}")
        return 1

    started_at = time.time()
    TARGET_DB.unlink(missing_ok=True)
    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(TARGET_DB) as target:
        setup_database(target)
        target.execute(f"ATTACH DATABASE ? AS src", (str(SOURCE_DB),))
        try:
            column_list = ", ".join(COLUMNS)
            placeholders = ", ".join("?" for _ in ALLOWED_CARGOS)
            target.execute(
                f"""
                INSERT INTO main.votos ({column_list})
                SELECT {column_list}
                FROM src.votos
                WHERE cargo IN ({placeholders})
                """,
                ALLOWED_CARGOS,
            )
        finally:
            target.commit()
            try:
                target.execute("DETACH DATABASE src")
            except sqlite3.OperationalError:
                pass
        print(f"Linhas copiadas (Governador/Presidente): {target.total_changes:,}".replace(",", "."))

        print("Criando indices...")
        create_indexes(target)
        print("Criando tabelas agregadas...")
        create_aggregates(target)
        print("Criando indices de busca (FTS5)...")
        create_search_indexes(target)
        print("Compactando (VACUUM)...")
        target.execute("VACUUM")

    size_mb = TARGET_DB.stat().st_size / 1_048_576
    elapsed = time.time() - started_at
    print(f"Pronto: {TARGET_DB} ({size_mb:,.1f} MB) em {elapsed:,.1f}s".replace(",", "x").replace("x", ","))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())