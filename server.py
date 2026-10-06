from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DEFAULT_DB = ROOT / "data" / "votos.sqlite"


def first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    return params.get(key, [default])[0].strip()


def clamp_int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


ALLOWED_CARGOS = ("Governador", "Presidente")
FTS_TABLES = {"votos": "fts_votos", "agg_locais": "fts_locais"}
LIKE_COLUMNS = ("municipio", "bairro", "local_nome", "endereco", "candidato_nome", "codigo_votavel")


def fts_match(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " AND ".join(f'"{token}"*' for token in tokens)


def build_where(params: dict[str, list[str]], table: str = "votos", fts_available: bool = False) -> tuple[str, list[object]]:
    clauses: list[str] = []
    values: list[object] = []

    cargo = first(params, "cargo")
    if cargo:
        clauses.append("cargo = ?")
        values.append(cargo)
    else:
        clauses.append("cargo IN (?, ?)")
        values.extend(ALLOWED_CARGOS)

    filters = {
        "municipio": "municipio",
        "bairro": "bairro",
        "local": "local_nome",
        "candidato": "codigo_votavel",
        "tipo": "tipo_voto",
        "zona": "zona",
        "secao": "secao",
    }

    for param, column in filters.items():
        value = first(params, param)
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)

    query = first(params, "q")
    if query:
        fts_table = FTS_TABLES.get(table)
        match = fts_match(query)
        if match and fts_available and fts_table:
            clauses.append(f"rowid IN (SELECT rowid FROM {fts_table} WHERE {fts_table} MATCH ?)")
            values.append(match)
        else:
            like = f"%{query}%"
            clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in LIKE_COLUMNS) + ")")
            values.extend([like] * len(LIKE_COLUMNS))

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, values


def can_use_location_aggregate(params: dict[str, list[str]], connection: sqlite3.Connection | None = None) -> bool:
    if first(params, "zona") or first(params, "secao"):
        return False
    if first(params, "q") and connection is not None and not table_exists(connection, "fts_locais"):
        return False
    return True


def build_section_where(params: dict[str, list[str]]) -> tuple[str, list[object]]:
    clauses: list[str] = ["cargo IN (?, ?)"]
    values: list[object] = list(ALLOWED_CARGOS)
    cargo = first(params, "cargo")
    if cargo:
        clauses = ["cargo = ?"]
        values = [cargo]
    for param, column in {
        "cargo": "cargo",
        "municipio": "municipio",
        "bairro": "bairro",
        "local": "local_nome",
    }.items():
        value = first(params, param)
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    return (" WHERE " + " AND ".join(clauses), values) if clauses else ("", values)


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


class AppHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed.path, parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, message: str, status: HTTPStatus) -> None:
        self.send_json({"error": message}, status)

    def require_db(self) -> bool:
        if self.db_path.exists():
            return True
        self.send_error_json(
            "Banco nao encontrado. Rode `python import_data.py` antes de iniciar as consultas.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
        return False

    def handle_api(self, path: str, params: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self.send_json({"ok": True, "db_exists": self.db_path.exists()})
            return
        if not self.require_db():
            return

        try:
            if path == "/api/options":
                self.api_options(params)
            elif path == "/api/overview":
                self.api_overview(params)
            elif path == "/api/summary":
                self.api_summary(params)
            elif path == "/api/rows":
                self.api_rows(params)
            elif path == "/api/map":
                self.api_map(params)
            elif path == "/api/location":
                self.api_location(params)
            else:
                self.send_error_json("Endpoint nao encontrado", HTTPStatus.NOT_FOUND)
        except sqlite3.Error as exc:
            self.send_error_json(f"Erro SQLite: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def api_options(self, params: dict[str, list[str]]) -> None:
        cargo = first(params, "cargo")
        municipio = first(params, "municipio")
        with connect(self.db_path) as connection:
            cargos = [
                row_to_dict(row)
                for row in connection.execute(
                    "SELECT cargo, codigo_cargo, votos FROM agg_cargos WHERE cargo IN ('Governador', 'Presidente') ORDER BY codigo_cargo"
                )
            ]
            municipios = [
                row[0]
                for row in connection.execute(
                    "SELECT municipio FROM agg_municipios ORDER BY municipio"
                )
            ]

            bairro_sql = "SELECT bairro FROM agg_bairros WHERE bairro <> ''"
            bairro_args: list[object] = []
            if municipio:
                bairro_sql += " AND municipio = ?"
                bairro_args.append(municipio)
            bairro_sql += " GROUP BY bairro ORDER BY bairro LIMIT 1000"
            bairros = [row[0] for row in connection.execute(bairro_sql, bairro_args)]

            candidato_sql = """
                SELECT cargo, codigo_votavel AS numero, candidato_nome AS nome, partido, votos
                FROM agg_candidatos
                WHERE codigo_votavel <> ''
            """
            candidato_args: list[object] = []
            if cargo:
                candidato_sql += " AND cargo = ?"
                candidato_args.append(cargo)
            else:
                candidato_sql += " AND cargo IN (?, ?)"
                candidato_args.extend(ALLOWED_CARGOS)
            candidato_sql += " ORDER BY votos DESC LIMIT 500"
            candidatos = [row_to_dict(row) for row in connection.execute(candidato_sql, candidato_args)]

            tipos = [row[0] for row in connection.execute("SELECT tipo_voto FROM agg_tipos ORDER BY tipo_voto")]

        self.send_json({"cargos": cargos, "municipios": municipios, "bairros": bairros, "candidatos": candidatos, "tipos": tipos})

    def api_overview(self, params: dict[str, list[str]]) -> None:
        with connect(self.db_path) as connection:
            use_aggregate = can_use_location_aggregate(params, connection) and table_exists(connection, "agg_locais")
            table = "agg_locais" if use_aggregate else "votos"
            where, values = build_where(params, table, fts_available=table_exists(connection, FTS_TABLES[table]))
            if use_aggregate:
                totals = row_to_dict(
                    connection.execute(
                        f"""
                        SELECT
                            COALESCE(SUM(votos), 0) AS votos,
                            COALESCE(SUM(linhas), 0) AS linhas,
                            COUNT(DISTINCT municipio) AS municipios,
                            COUNT(DISTINCT municipio || '|' || local_votacao) AS locais,
                            0 AS secoes
                        FROM agg_locais{where}
                        """,
                        values,
                    ).fetchone()
                )
                if not (first(params, "candidato") or first(params, "tipo")) and table_exists(connection, "agg_secoes"):
                    if first(params, "q"):
                        votos_where, votos_values = build_where(params, "votos", fts_available=table_exists(connection, "fts_votos"))
                        totals["secoes"] = connection.execute(
                            f"SELECT COUNT(DISTINCT zona || '|' || secao || '|' || local_votacao) FROM votos{votos_where}",
                            votos_values,
                        ).fetchone()[0]
                    else:
                        section_where, section_values = build_section_where(params)
                        totals["secoes"] = connection.execute(
                            f"SELECT COUNT(*) FROM agg_secoes{section_where}", section_values
                        ).fetchone()[0]
                leaders = [
                    row_to_dict(row)
                    for row in connection.execute(
                        f"""
                        SELECT cargo, codigo_votavel AS numero, candidato_nome AS nome, partido, tipo_voto, SUM(votos) AS votos
                        FROM agg_locais{where}
                        GROUP BY cargo, codigo_votavel, candidato_nome, partido, tipo_voto
                        ORDER BY votos DESC
                        LIMIT 8
                        """,
                        values,
                    )
                ]
            else:
                totals = row_to_dict(
                    connection.execute(
                        f"""
                        SELECT
                            COALESCE(SUM(quantidade_votos), 0) AS votos,
                            COUNT(*) AS linhas,
                            COUNT(DISTINCT municipio) AS municipios,
                            COUNT(DISTINCT local_votacao || '|' || zona) AS locais,
                            COUNT(DISTINCT zona || '|' || secao || '|' || local_votacao) AS secoes
                        FROM votos{where}
                        """,
                        values,
                    ).fetchone()
                )
                leaders = [
                    row_to_dict(row)
                    for row in connection.execute(
                        f"""
                        SELECT cargo, codigo_votavel AS numero, candidato_nome AS nome, partido, tipo_voto, SUM(quantidade_votos) AS votos
                        FROM votos{where}
                        GROUP BY cargo, codigo_votavel, candidato_nome, partido, tipo_voto
                        ORDER BY votos DESC
                        LIMIT 8
                        """,
                        values,
                    )
                ]
        self.send_json({"totals": totals, "leaders": leaders})

    def api_summary(self, params: dict[str, list[str]]) -> None:
        group = first(params, "group", "candidato")
        limit = clamp_int(first(params, "limit", "25"), 25, 1, 200)

        groups = {
            "candidato": (
                "cargo, codigo_votavel AS numero, candidato_nome AS nome, partido, tipo_voto",
                "cargo, codigo_votavel, candidato_nome, partido, tipo_voto",
            ),
            "municipio": ("municipio", "municipio"),
            "bairro": ("municipio, bairro", "municipio, bairro"),
            "local": (
                "municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude",
                "municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude",
            ),
            "secao": ("municipio, bairro, local_nome, zona, secao", "municipio, bairro, local_nome, zona, secao"),
            "tipo": ("tipo_voto", "tipo_voto"),
        }
        if group not in groups:
            self.send_error_json("Agrupamento invalido", HTTPStatus.BAD_REQUEST)
            return

        with connect(self.db_path) as connection:
            use_aggregate = group != "secao" and can_use_location_aggregate(params, connection) and table_exists(connection, "agg_locais")
            select_columns, group_columns = groups[group]
            table = "agg_locais" if use_aggregate else "votos"
            vote_column = "votos" if use_aggregate else "quantidade_votos"
            count_expression = "SUM(linhas)" if use_aggregate else "COUNT(*)"
            where, values = build_where(params, table, fts_available=table_exists(connection, FTS_TABLES[table]))
            rows = [
                row_to_dict(row)
                for row in connection.execute(
                    f"""
                    SELECT {select_columns}, SUM({vote_column}) AS votos, {count_expression} AS linhas
                    FROM {table}{where}
                    GROUP BY {group_columns}
                    ORDER BY votos DESC
                    LIMIT ?
                    """,
                    [*values, limit],
                )
            ]
        self.send_json({"group": group, "rows": rows})

    def api_rows(self, params: dict[str, list[str]]) -> None:
        page = clamp_int(first(params, "page", "1"), 1, 1, 100000)
        page_size = clamp_int(first(params, "page_size", "50"), 50, 10, 200)
        offset = (page - 1) * page_size

        with connect(self.db_path) as connection:
            use_aggregate = can_use_location_aggregate(params, connection) and table_exists(connection, "agg_locais")
            table = "agg_locais" if use_aggregate else "votos"
            vote_column = "votos" if use_aggregate else "quantidade_votos"
            where, values = build_where(params, table, fts_available=table_exists(connection, FTS_TABLES[table]))
            total = connection.execute(f"SELECT COUNT(*) FROM {table}{where}", values).fetchone()[0]
            zone_columns = "NULL AS zona, NULL AS secao," if use_aggregate else "zona, secao,"
            rows = [
                row_to_dict(row)
                for row in connection.execute(
                    f"""
                    SELECT cargo, codigo_votavel AS numero, candidato_nome AS nome, partido, tipo_voto,
                        {vote_column} AS votos, municipio, bairro, local_nome, endereco, {zone_columns}
                        latitude, longitude
                    FROM {table}{where}
                    ORDER BY {vote_column} DESC, municipio, bairro, local_nome
                    LIMIT ? OFFSET ?
                    """,
                    [*values, page_size, offset],
                )
            ]
        self.send_json({"page": page, "page_size": page_size, "total": total, "rows": rows})

    def api_map(self, params: dict[str, list[str]]) -> None:
        limit = clamp_int(first(params, "limit", "600"), 600, 10, 10000)
        has_section_filter = bool(first(params, "zona") or first(params, "secao"))
        table = "votos"
        vote_column = "quantidade_votos"
        count_expression = "COUNT(*)"

        with connect(self.db_path) as connection:
            if not has_section_filter and table_exists(connection, "agg_locais"):
                table = "agg_locais"
                vote_column = "votos"
                count_expression = "SUM(linhas)"

            where, values = build_where(params, table, fts_available=table_exists(connection, FTS_TABLES[table]))
            location_filter = "latitude IS NOT NULL AND longitude IS NOT NULL"
            if where:
                where = where + " AND " + location_filter
            else:
                where = " WHERE " + location_filter

            rows = [
                row_to_dict(row)
                for row in connection.execute(
                    f"""
                    SELECT municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude,
                        SUM({vote_column}) AS votos, {count_expression} AS linhas
                    FROM {table}{where}
                    GROUP BY municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude
                    ORDER BY votos DESC
                    LIMIT ?
                    """,
                    [*values, limit],
                )
            ]
        self.send_json({"rows": rows})

    def api_location(self, params: dict[str, list[str]]) -> None:
        cargo = first(params, "cargo", "Governador") or "Governador"
        supported = first(params, "supported", "55") or "55"
        municipio = first(params, "municipio")
        local_votacao = first(params, "local_votacao")
        local_nome = first(params, "local_nome")

        if not municipio or not local_votacao:
            self.send_error_json("Informe municipio e local_votacao", HTTPStatus.BAD_REQUEST)
            return

        clauses = ["cargo = ?", "municipio = ?", "local_votacao = ?"]
        values: list[object] = [cargo, municipio, local_votacao]
        if local_nome:
            clauses.append("local_nome = ?")
            values.append(local_nome)
        where = " WHERE " + " AND ".join(clauses)

        with connect(self.db_path) as connection:
            info = None
            info_row = connection.execute(
                f"""
                SELECT municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude,
                    COUNT(DISTINCT zona || '|' || secao) AS secoes,
                    COALESCE(SUM(quantidade_votos), 0) AS votos
                FROM votos{where}
                GROUP BY municipio, bairro, local_votacao, local_nome, endereco, latitude, longitude
                ORDER BY votos DESC
                LIMIT 1
                """,
                values,
            ).fetchone()
            if info_row:
                info = row_to_dict(info_row)

            rows = [
                row_to_dict(row)
                for row in connection.execute(
                    f"""
                    SELECT codigo_votavel AS numero, candidato_nome AS nome, partido, tipo_voto,
                        SUM(quantidade_votos) AS votos
                    FROM votos{where}
                    GROUP BY codigo_votavel, candidato_nome, partido, tipo_voto
                    ORDER BY votos DESC
                    """,
                    values,
                )
            ]

        total = sum(int(row["votos"] or 0) for row in rows)
        supported_row = next((row for row in rows if row["numero"] == supported), None)
        supported_votes = int(supported_row["votos"] if supported_row else 0)
        nominal_opponents = [row for row in rows if row["numero"] != supported and row["tipo_voto"] == "nominal"]
        main_opponent = nominal_opponents[0] if nominal_opponents else None
        main_opponent_votes = int(main_opponent["votos"] if main_opponent else 0)
        blanks = sum(int(row["votos"] or 0) for row in rows if row["tipo_voto"] == "branco")
        nulls = sum(int(row["votos"] or 0) for row in rows if row["tipo_voto"] == "nulo")
        other_candidates = sum(
            int(row["votos"] or 0)
            for row in rows
            if row["tipo_voto"] == "nominal"
            and row["numero"] != supported
            and (not main_opponent or row["numero"] != main_opponent["numero"])
        )
        opportunity_votes = blanks + nulls + other_candidates
        supported_share = round((supported_votes / total) * 100, 1) if total else 0
        opponent_share = round((main_opponent_votes / total) * 100, 1) if total else 0

        conversations = []
        if blanks:
            conversations.append({"title": "Quem votou em branco", "votes": blanks, "kind": "branco"})
        if nulls:
            conversations.append({"title": "Quem anulou o voto", "votes": nulls, "kind": "nulo"})
        for row in nominal_opponents:
            if main_opponent and row["numero"] == main_opponent["numero"]:
                continue
            conversations.append(
                {
                    "title": f"Quem votou em {row['nome'] or 'outro candidato'}",
                    "votes": int(row["votos"] or 0),
                    "numero": row["numero"],
                    "partido": row["partido"],
                    "kind": "candidato",
                }
            )
        conversations.sort(key=lambda item: item["votes"], reverse=True)

        self.send_json(
            {
                "info": info,
                "supported": {
                    "numero": supported,
                    "nome": supported_row["nome"] if supported_row else "Eduardo Paes",
                    "partido": supported_row["partido"] if supported_row else "PSD",
                    "votos": supported_votes,
                    "share": supported_share,
                },
                "main_opponent": {
                    "numero": main_opponent["numero"],
                    "nome": main_opponent["nome"],
                    "partido": main_opponent["partido"],
                    "votos": main_opponent_votes,
                    "share": opponent_share,
                }
                if main_opponent
                else None,
                "totals": {
                    "votos": total,
                    "secoes": (info or {}).get("secoes", 0),
                    "brancos": blanks,
                    "nulos": nulls,
                    "outros_candidatos": other_candidates,
                    "conversaveis": opportunity_votes,
                    "margem": supported_votes - main_opponent_votes,
                },
                "candidates": rows,
                "conversations": conversations,
            }
        )

    def serve_static(self, path: str) -> None:
        clean_path = unquote(path).lstrip("/") or "index.html"
        file_path = (WEB_ROOT / clean_path).resolve()
        if WEB_ROOT.resolve() not in file_path.parents and file_path != WEB_ROOT.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Servidor local do explorador de votos.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("DB_PATH", DEFAULT_DB)))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    AppHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Servidor iniciado em http://{args.host}:{args.port}")
    print("Use Ctrl+C para encerrar.")
    server.serve_forever()


if __name__ == "__main__":
    main()
