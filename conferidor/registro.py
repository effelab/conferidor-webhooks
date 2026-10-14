"""O que a loja sabe: os pedidos que criou e os avisos que recebeu.

SQLite puro. A tabela de eventos so recebe insercao e a chave
(order_id, evento) torna a gravacao idempotente, como o checklist de
publicacao da plataforma exige (reentregas acontecem).
"""
import json
import sqlite3

from .contrato import (ESTAGIO, EVENTO_STATUS, EVENTOS_QUE_ENCERRAM,
                       metodo_pelo_evento, prazo_de_silencio)

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS pedidos (
    order_id       INTEGER PRIMARY KEY,
    metodo         TEXT NOT NULL,
    origem         TEXT NOT NULL,
    valor_centavos INTEGER NOT NULL DEFAULT 0,
    criado_em      REAL NOT NULL,
    status         TEXT,
    fonte_status   TEXT,
    estagio        INTEGER NOT NULL DEFAULT 0,
    prazo          REAL,
    n              INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS pedidos_prazo ON pedidos (prazo);
CREATE TABLE IF NOT EXISTS eventos (
    order_id    INTEGER NOT NULL,
    evento      TEXT NOT NULL,
    status      TEXT,
    recebido_em REAL NOT NULL,
    payload     TEXT,
    PRIMARY KEY (order_id, evento)
);
CREATE TABLE IF NOT EXISTS apontados (
    order_id INTEGER NOT NULL,
    evento   TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    PRIMARY KEY (order_id, evento)
);
"""


class Registro:
    def __init__(self, caminho=":memory:"):
        self.db = sqlite3.connect(caminho, check_same_thread=False)  # o receptor responde em varias threads, com trava
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_ESQUEMA)
        self.duplicados = 0

    def registrar_pedido(self, order_id, metodo, criado_em, origem="propria", valor_centavos=0):
        """A loja criou o pedido. A primeira consulta fica marcada para 10 minutos."""
        self.db.execute(
            "INSERT OR IGNORE INTO pedidos (order_id, metodo, origem, valor_centavos, criado_em, prazo)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, metodo, origem, valor_centavos, criado_em,
             criado_em + prazo_de_silencio(metodo, None)))

    def registrar_evento(self, order_id, evento, status=None, recebido_em=0.0, payload=None):
        """Grava um aviso. Devolve False se ele ja tinha sido recebido."""
        gravado = self.db.execute(
            "INSERT OR IGNORE INTO eventos VALUES (?, ?, ?, ?, ?)",
            (order_id, evento, status, recebido_em,
             json.dumps(payload, ensure_ascii=False) if payload is not None else None))
        if gravado.rowcount == 0:
            self.duplicados += 1
            return False
        pedido = self.pedido(order_id)
        if pedido is None:  # aviso de um pedido que a loja nao criou
            self.registrar_pedido(order_id, metodo_pelo_evento(evento), recebido_em, "desconhecida")
            pedido = self.pedido(order_id)
        atual, estagio, fonte = pedido["status"], pedido["estagio"], pedido["fonte_status"]
        novo = status or EVENTO_STATUS.get(evento)
        if novo and ESTAGIO.get(novo, 0) >= estagio:
            atual, estagio, fonte = novo, ESTAGIO.get(novo, 0), "webhook"
        silencio = None if evento in EVENTOS_QUE_ENCERRAM else prazo_de_silencio(pedido["metodo"], atual)
        self.db.execute(
            "UPDATE pedidos SET status=?, estagio=?, fonte_status=?, prazo=?, n=0 WHERE order_id=?",
            (atual, estagio, fonte, recebido_em + silencio if silencio else None, order_id))
        return True

    def pedido(self, order_id):
        return self.db.execute("SELECT * FROM pedidos WHERE order_id=?", (order_id,)).fetchone()

    def eventos_recebidos(self, order_id):
        linhas = self.db.execute("SELECT evento FROM eventos WHERE order_id=?", (order_id,))
        return {linha[0] for linha in linhas}

    def vencidos(self, agora, limite=None):
        """Pedidos cujo prazo de silencio estourou, do mais atrasado para o menos."""
        sql = "SELECT * FROM pedidos WHERE prazo IS NOT NULL AND prazo <= ? ORDER BY prazo"
        if limite:
            sql += f" LIMIT {int(limite)}"
        return self.db.execute(sql, (agora,)).fetchall()

    def sincronizar(self, order_id, status):
        """A API informou um status que a loja nao conhecia."""
        self.db.execute(
            "UPDATE pedidos SET status=?, estagio=?, fonte_status='api' WHERE order_id=?",
            (status, ESTAGIO.get(status, 0), order_id))

    def reagendar(self, order_id, prazo, n):
        self.db.execute("UPDATE pedidos SET prazo=?, n=? WHERE order_id=?", (prazo, n, order_id))

    def apontar(self, order_id, evento, tipo):
        """Marca um aviso faltando. Devolve True se e novidade ou se subiu de gravidade."""
        anterior = self.db.execute(
            "SELECT tipo FROM apontados WHERE order_id=? AND evento=?", (order_id, evento)).fetchone()
        if anterior is None:
            self.db.execute("INSERT INTO apontados VALUES (?, ?, ?)", (order_id, evento, tipo))
            return True
        if anterior[0] == "em_janela" and tipo == "aviso_perdido":
            self.db.execute(
                "UPDATE apontados SET tipo=? WHERE order_id=? AND evento=?", (tipo, order_id, evento))
            return True
        return False

    def recuperados_por_retentativa(self):
        """Avisos que pareciam perdidos e chegaram depois, por retentativa."""
        return self.db.execute(
            "SELECT COUNT(*) FROM apontados a JOIN eventos e USING (order_id, evento)"
            " WHERE a.tipo='em_janela'").fetchone()[0]
