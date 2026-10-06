from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_VOTES_CSV = ROOT.parent / "Eleições 2026 completas.csv"
DEFAULT_CANDIDATES_CSV = ROOT.parent / "consulta_cand_2026_BRASIL.csv"
DEFAULT_DB = ROOT / "data" / "votos.sqlite"


def detect_encoding(path: Path) -> str:
    with path.open("rb") as file:
        sample = file.read(200_000)
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"


def sniff_dialect(path: Path, encoding: str) -> csv.Dialect:
    with path.open("r", encoding=encoding, newline="") as file:
        sample = file.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        return csv.excel


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"')


def as_int(value: object, default: int = 0) -> int:
    text = clean(value)
    if not text:
        return default
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return default


def as_float(value: object) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def number_key(value: object) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        return str(int(float(text.replace(",", "."))))
    except ValueError:
        return text


def load_candidates(path: Path | None) -> dict[tuple[int, str], tuple[str, str]]:
    if not path or not path.exists():
        return {}

    encoding = detect_encoding(path)
    dialect = sniff_dialect(path, encoding)
    candidates: dict[tuple[int, str], tuple[str, str]] = {}

    with path.open("r", encoding=encoding, newline="") as file:
        reader = csv.DictReader(file, dialect=dialect)
        for row in reader:
            cargo = as_int(row.get("CD_CARGO"))
            numero = number_key(row.get("NR_CANDIDATO"))
            uf = clean(row.get("SG_UF"))
            if not cargo or not numero:
                continue
            if cargo != 1 and uf not in {"RJ", "BR"}:
                continue

            nome = clean(row.get("NM_URNA_CANDIDATO")) or clean(row.get("NM_CANDIDATO"))
            partido = clean(row.get("SG_PARTIDO"))
            if nome and nome not in {"#NULO", "NULO"}:
                candidates[(cargo, numero)] = (nome, partido)

    return candidates


def setup_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        DROP TABLE IF EXISTS votos;

        CREATE TABLE votos (
            id INTEGER PRIMARY KEY,
            codigo_cargo INTEGER NOT NULL,
            cargo TEXT NOT NULL,
            codigo_votavel TEXT,
            candidato_nome TEXT,
            partido TEXT,
            endereco TEXT,
            bairro TEXT,
            municipio TEXT,
            cep TEXT,
            latitude REAL,
            longitude REAL,
            local_votacao TEXT,
            local_nome TEXT,
            secao TEXT,
            zona TEXT,
            quantidade_votos INTEGER NOT NULL,
            tipo_voto TEXT
        );
        """
    )


def create_indexes(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_votos_cargo ON votos(cargo);
        CREATE INDEX IF NOT EXISTS idx_votos_codigo_cargo ON votos(codigo_cargo);
        CREATE INDEX IF NOT EXISTS idx_votos_municipio ON votos(municipio);
        CREATE INDEX IF NOT EXISTS idx_votos_bairro ON votos(bairro);
        CREATE INDEX IF NOT EXISTS idx_votos_local ON votos(local_nome);
        CREATE INDEX IF NOT EXISTS idx_votos_location_detail ON votos(cargo, municipio, local_votacao);
        CREATE INDEX IF NOT EXISTS idx_votos_numero ON votos(codigo_votavel);
        CREATE INDEX IF NOT EXISTS idx_votos_tipo ON votos(tipo_voto);
        CREATE INDEX IF NOT EXISTS idx_votos_zona_secao ON votos(zona, secao);
        CREATE INDEX IF NOT EXISTS idx_votos_localizacao ON votos(latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_votos_filtros ON votos(cargo, municipio, bairro, codigo_votavel, tipo_voto);
        ANALYZE;
        """
    )


def create_aggregates(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS agg_cargos;
        CREATE TABLE agg_cargos AS
            SELECT cargo, codigo_cargo, SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            GROUP BY cargo, codigo_cargo;

        DROP TABLE IF EXISTS agg_municipios;
        CREATE TABLE agg_municipios AS
            SELECT municipio, SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            GROUP BY municipio;

        DROP TABLE IF EXISTS agg_bairros;
        CREATE TABLE agg_bairros AS
            SELECT municipio, bairro, SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            WHERE bairro <> ''
            GROUP BY municipio, bairro;

        DROP TABLE IF EXISTS agg_tipos;
        CREATE TABLE agg_tipos AS
            SELECT tipo_voto, SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            GROUP BY tipo_voto;

        DROP TABLE IF EXISTS agg_candidatos;
        CREATE TABLE agg_candidatos AS
            SELECT cargo, codigo_votavel, candidato_nome, partido, SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            WHERE codigo_votavel <> ''
            GROUP BY cargo, codigo_votavel, candidato_nome, partido;

        DROP TABLE IF EXISTS agg_locais;
        CREATE TABLE agg_locais AS
            SELECT cargo, codigo_votavel, candidato_nome, partido, tipo_voto,
                municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude,
                SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            GROUP BY cargo, codigo_votavel, candidato_nome, partido, tipo_voto,
                municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude;

        DROP TABLE IF EXISTS agg_secoes;
        CREATE TABLE agg_secoes AS
            SELECT cargo, municipio, bairro, local_votacao, local_nome, zona, secao,
                SUM(quantidade_votos) AS votos, COUNT(*) AS linhas
            FROM votos
            GROUP BY cargo, municipio, bairro, local_votacao, local_nome, zona, secao;

        CREATE INDEX IF NOT EXISTS idx_agg_bairros_municipio ON agg_bairros(municipio, bairro);
        CREATE INDEX IF NOT EXISTS idx_agg_candidatos_cargo ON agg_candidatos(cargo, votos DESC);
        CREATE INDEX IF NOT EXISTS idx_agg_locais_filtros ON agg_locais(cargo, municipio, bairro, codigo_votavel, tipo_voto);
        CREATE INDEX IF NOT EXISTS idx_agg_locais_geo ON agg_locais(latitude, longitude);
        CREATE INDEX IF NOT EXISTS idx_agg_locais_votos ON agg_locais(votos DESC);
        CREATE INDEX IF NOT EXISTS idx_agg_secoes_filtros ON agg_secoes(cargo, municipio, bairro, local_nome);
        """
    )


def create_search_indexes(connection: sqlite3.Connection) -> None:
    for table, fts_table in (("votos", "fts_votos"), ("agg_locais", "fts_locais")):
        connection.executescript(
            f"""
            DROP TABLE IF EXISTS {fts_table};
            CREATE VIRTUAL TABLE {fts_table} USING fts5(
                municipio, bairro, local_nome, endereco, candidato_nome, codigo_votavel, local_votacao,
                content='{table}', content_rowid='rowid', tokenize='unicode61 remove_diacritics 1'
            );
            INSERT INTO {fts_table}({fts_table}) VALUES('rebuild');
            """
        )


def vote_label(tipo_voto: str, numero: str, candidato: tuple[str, str] | None) -> tuple[str, str]:
    tipo = tipo_voto.lower()
    if tipo == "branco":
        return "Branco", ""
    if tipo == "nulo":
        return "Nulo", ""
    if candidato:
        return candidato
    if numero:
        return f"Numero {numero}", ""
    return "Sem identificacao", ""


def import_votes(votes_csv: Path, candidates_csv: Path | None, db_path: Path) -> None:
    if not votes_csv.exists():
        raise FileNotFoundError(f"CSV de votos nao encontrado: {votes_csv}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    candidates = load_candidates(candidates_csv)
    print(f"Candidatos carregados: {len(candidates):,}".replace(",", "."))

    encoding = detect_encoding(votes_csv)
    dialect = sniff_dialect(votes_csv, encoding)
    started_at = time.time()
    inserted = 0
    batch: list[tuple[object, ...]] = []

    connection = sqlite3.connect(db_path)
    try:
        setup_database(connection)
        insert_sql = """
            INSERT INTO votos (
                codigo_cargo, cargo, codigo_votavel, candidato_nome, partido,
                endereco, bairro, municipio, cep, latitude, longitude,
                local_votacao, local_nome, secao, zona, quantidade_votos, tipo_voto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with votes_csv.open("r", encoding=encoding, newline="") as file:
            reader = csv.DictReader(file, dialect=dialect)
            for row in reader:
                cargo_codigo = as_int(row.get("codigo_cargo"))
                numero = number_key(row.get("codigo_votavel"))
                tipo = clean(row.get("tipo_voto"))
                candidato_nome, partido = vote_label(tipo, numero, candidates.get((cargo_codigo, numero)))

                batch.append(
                    (
                        cargo_codigo,
                        clean(row.get("cargo")),
                        numero,
                        candidato_nome,
                        partido,
                        clean(row.get("DS_ENDERECO")),
                        clean(row.get("bairro")),
                        clean(row.get("municipio")),
                        clean(row.get("NR_CEP")),
                        as_float(row.get("NR_LATITUDE")),
                        as_float(row.get("NR_LONGITUDE")),
                        clean(row.get("local_votacao")),
                        clean(row.get("NM_LOCAL_VOTACAO")),
                        clean(row.get("secao")),
                        clean(row.get("zona")),
                        as_int(row.get("quantidade_votos")),
                        tipo,
                    )
                )

                if len(batch) >= 25_000:
                    connection.executemany(insert_sql, batch)
                    connection.commit()
                    inserted += len(batch)
                    batch.clear()
                    elapsed = max(time.time() - started_at, 1)
                    rate = inserted / elapsed
                    print(f"Linhas importadas: {inserted:,} ({rate:,.0f}/s)".replace(",", "."))

        if batch:
            connection.executemany(insert_sql, batch)
            connection.commit()
            inserted += len(batch)

        print("Criando indices...")
        create_indexes(connection)
        print("Criando tabelas agregadas...")
        create_aggregates(connection)
        print("Criando indices de busca (FTS5)...")
        create_search_indexes(connection)
        elapsed = time.time() - started_at
        print(f"Importacao concluida: {inserted:,} linhas em {elapsed:,.1f}s".replace(",", "."))
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Importa votos do CSV para SQLite.")
    parser.add_argument("--votes", type=Path, default=DEFAULT_VOTES_CSV, help="Caminho do CSV de votos")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_CSV, help="Caminho do CSV de candidatos")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Caminho do SQLite gerado")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import_votes(args.votes, args.candidates, args.db)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
