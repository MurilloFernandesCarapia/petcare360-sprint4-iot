import logging
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

log = logging.getLogger("petcare360.repositorio")

CAMPOS_ANALISE = [
    "idAnalise", "petId", "dataAnalise", "origem", "temperatura", "umidade", "atividade",
    "alimentacao", "comportamento", "nivel", "irp", "probNormal", "probAtencao", "probAlto",
]


def _linha_para_dict(linha) -> dict:
    registro = dict(zip(CAMPOS_ANALISE, linha))
    if isinstance(registro["dataAnalise"], datetime):
        registro["dataAnalise"] = registro["dataAnalise"].isoformat()
    return registro


class RepositorioSqlite:
    nome = "sqlite"

    def __init__(self, caminho: str):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conectar()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS TB_ANALISE_IA (
                    ID_ANALISE INTEGER PRIMARY KEY AUTOINCREMENT,
                    ID_PET INTEGER NOT NULL,
                    DT_ANALISE TEXT NOT NULL,
                    ORIGEM TEXT,
                    TEMPERATURA REAL,
                    UMIDADE REAL,
                    ATIVIDADE REAL,
                    ALIMENTACAO REAL,
                    COMPORTAMENTO TEXT,
                    NIVEL TEXT NOT NULL,
                    IRP INTEGER NOT NULL,
                    PROB_NORMAL REAL,
                    PROB_ATENCAO REAL,
                    PROB_ALTO REAL
                )
            """)

    def _conectar(self):
        return sqlite3.connect(self.caminho)

    def buscar_pet(self, pet_id: int) -> dict | None:
        return None

    def medicamentos_ativos(self, pet_id: int) -> list[str] | None:
        return None

    def salvar_analise(self, r: dict) -> int | None:
        with closing(self._conectar()) as conn, conn:
            cursor = conn.execute(
                """INSERT INTO TB_ANALISE_IA (ID_PET, DT_ANALISE, ORIGEM, TEMPERATURA, UMIDADE, ATIVIDADE,
                       ALIMENTACAO, COMPORTAMENTO, NIVEL, IRP, PROB_NORMAL, PROB_ATENCAO, PROB_ALTO)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (r["petId"], datetime.now().isoformat(timespec="seconds"), r["origem"], r["temperatura"],
                 r["umidade"], r["atividade"], r["alimentacao"], r["comportamento"], r["nivel"], r["irp"],
                 r["probNormal"], r["probAtencao"], r["probAlto"]),
            )
            return int(cursor.lastrowid)

    def listar_historico(self, pet_id: int, limite: int) -> list[dict]:
        with closing(self._conectar()) as conn:
            linhas = conn.execute(
                """SELECT ID_ANALISE, ID_PET, DT_ANALISE, ORIGEM, TEMPERATURA, UMIDADE, ATIVIDADE, ALIMENTACAO,
                          COMPORTAMENTO, NIVEL, IRP, PROB_NORMAL, PROB_ATENCAO, PROB_ALTO
                     FROM TB_ANALISE_IA
                    WHERE ID_PET = ?
                    ORDER BY ID_ANALISE DESC
                    LIMIT ?""",
                (pet_id, limite),
            ).fetchall()
        return [_linha_para_dict(linha) for linha in reversed(linhas)]


class RepositorioOracle:
    nome = "oracle"

    def __init__(self, usuario: str, senha: str, dsn: str):
        self.usuario = usuario
        self.senha = senha
        self.dsn = dsn

    def _conectar(self):
        import oracledb
        return oracledb.connect(user=self.usuario, password=self.senha, dsn=self.dsn)

    def buscar_pet(self, pet_id: int) -> dict | None:
        try:
            with self._conectar() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT NM_PET, ESPECIE, RACA, PESO,
                              TRUNC(MONTHS_BETWEEN(SYSDATE, DT_NASCIMENTO) / 12)
                         FROM TB_PET
                        WHERE ID_PET = :pet_id""",
                    {"pet_id": pet_id},
                )
                linha = cur.fetchone()
        except Exception as erro:
            log.warning("Falha ao buscar pet %s no Oracle: %s", pet_id, erro)
            return None
        if not linha:
            return None
        nome, especie, raca, peso, idade = linha
        return {
            "nome": nome,
            "especie": especie,
            "raca": raca,
            "peso": float(peso) if peso is not None else None,
            "idade": float(idade) if idade is not None else None,
        }

    def medicamentos_ativos(self, pet_id: int) -> list[str] | None:
        try:
            with self._conectar() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT NM_MEDICAMENTO
                         FROM TB_MEDICAMENTO
                        WHERE ID_PET = :pet_id
                          AND DT_INICIO <= TRUNC(SYSDATE)
                          AND (DT_FIM IS NULL OR DT_FIM >= TRUNC(SYSDATE))
                        ORDER BY DT_INICIO""",
                    {"pet_id": pet_id},
                )
                return [linha[0] for linha in cur.fetchall()]
        except Exception as erro:
            log.warning("Falha ao consultar medicamentos do pet %s: %s", pet_id, erro)
            return None

    def salvar_analise(self, r: dict) -> int | None:
        import oracledb
        try:
            with self._conectar() as conn, conn.cursor() as cur:
                novo_id = cur.var(oracledb.NUMBER)
                cur.execute(
                    """INSERT INTO TB_ANALISE_IA (ID_PET, ORIGEM, TEMPERATURA, UMIDADE, ATIVIDADE, ALIMENTACAO,
                           COMPORTAMENTO, NIVEL, IRP, PROB_NORMAL, PROB_ATENCAO, PROB_ALTO)
                       VALUES (:pet_id, :origem, :temperatura, :umidade, :atividade, :alimentacao,
                           :comportamento, :nivel, :irp, :prob_normal, :prob_atencao, :prob_alto)
                       RETURNING ID_ANALISE INTO :novo_id""",
                    {
                        "pet_id": r["petId"], "origem": r["origem"], "temperatura": r["temperatura"],
                        "umidade": r["umidade"], "atividade": r["atividade"], "alimentacao": r["alimentacao"],
                        "comportamento": r["comportamento"], "nivel": r["nivel"], "irp": r["irp"],
                        "prob_normal": r["probNormal"], "prob_atencao": r["probAtencao"],
                        "prob_alto": r["probAlto"], "novo_id": novo_id,
                    },
                )
                conn.commit()
                return int(novo_id.getvalue()[0])
        except Exception as erro:
            log.warning("Falha ao gravar análise do pet %s no Oracle: %s", r.get("petId"), erro)
            return None

    def listar_historico(self, pet_id: int, limite: int) -> list[dict]:
        try:
            with self._conectar() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT ID_ANALISE, ID_PET, DT_ANALISE, ORIGEM, TEMPERATURA, UMIDADE, ATIVIDADE, ALIMENTACAO,
                              COMPORTAMENTO, NIVEL, IRP, PROB_NORMAL, PROB_ATENCAO, PROB_ALTO
                         FROM TB_ANALISE_IA
                        WHERE ID_PET = :pet_id
                        ORDER BY DT_ANALISE DESC, ID_ANALISE DESC
                        FETCH FIRST :limite ROWS ONLY""",
                    {"pet_id": pet_id, "limite": limite},
                )
                linhas = cur.fetchall()
        except Exception as erro:
            log.warning("Falha ao listar histórico do pet %s: %s", pet_id, erro)
            return []
        return [_linha_para_dict(linha) for linha in reversed(linhas)]


def criar_repositorio():
    usuario = os.getenv("ORACLE_USER")
    senha = os.getenv("ORACLE_PASSWORD")
    dsn = os.getenv("ORACLE_DSN")
    if usuario and senha and dsn:
        log.info("Usando Oracle (%s) para persistência", dsn)
        return RepositorioOracle(usuario, senha, dsn)
    caminho = os.getenv("PETCARE360_SQLITE") or str(Path(__file__).resolve().parent.parent / "dados" / "petcare360.db")
    log.info("Oracle não configurado; usando SQLite local em %s", caminho)
    return RepositorioSqlite(caminho)