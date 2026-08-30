#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catalogo do acervo em SQLite.

POR QUE
-------
Hoje o jukebox (e os utilitarios avulsos) leem a pasta de musicas direto do
disco toda vez que precisam saber "quais generos existem" ou "quantas
musicas tem este artista" -- com cache de alguns segundos, mas sempre
reconstruido do zero a partir do sistema de arquivos. Isso e suficiente para
navegar (e o que o jukebox continua fazendo) mas nao da para consultas mais
ricas ("buscar por nome no acervo local", "quantas musicas ao todo") sem
escanear tudo de novo.

NESTA PASSADA
--------------
So o catalogo: caminho, genero, artista, nome do arquivo, tamanho e data de
modificacao. DE PROPOSITO sem leitura de ID3 e sem capa embutida -- cada uma
dessas coisas abre uma dependencia nova e um jeito novo de travar (arquivo de
audio corrompido emperrando a leitura da tag), e a prioridade agora e ter uma
base solida e comprovada RODANDO antes de empilhar mais em cima. O jukebox
principal continua navegando pelas pastas como sempre: este catalogo por
enquanto so e consultado pelo menu do operador (ACERVO), pronto para uma
proxima passada (busca local, "mais tocadas") ler sem escanear disco de novo.

ESCRITA ATOMICA
----------------
Mesmo principio do resto do projeto (creditos.py, config.json): o banco novo
e montado inteiro num arquivo TEMPORARIO e so substitui o catalogo antigo com
um rename, que e atomico no Linux. Uma queda de energia no meio da
reindexacao nunca deixa um catalogo pela metade -- na pior das hipoteses, o
catalogo antigo continua valendo ate a proxima reindexacao terminar.

USO
    python3 catalogo.py reindexar
"""

import os
import sqlite3
import time


SCHEMA = """
CREATE TABLE generos (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
);
CREATE TABLE artistas (
    id        INTEGER PRIMARY KEY,
    genero_id INTEGER NOT NULL REFERENCES generos(id) ON DELETE CASCADE,
    nome      TEXT NOT NULL,
    UNIQUE(genero_id, nome)
);
CREATE TABLE musicas (
    id           INTEGER PRIMARY KEY,
    artista_id   INTEGER NOT NULL REFERENCES artistas(id) ON DELETE CASCADE,
    nome_arquivo TEXT NOT NULL,
    caminho      TEXT NOT NULL UNIQUE,
    extensao     TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    tamanho      INTEGER NOT NULL,
    mtime        REAL NOT NULL
);
CREATE INDEX idx_artistas_genero ON artistas(genero_id);
CREATE INDEX idx_musicas_artista ON musicas(artista_id);
CREATE TABLE catalogo_info (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""


def _tipo_de(extensao, extensoes_link, extensao_busca, extensoes_playlist):
    if extensao == extensao_busca:
        return "busca"
    if extensao in extensoes_link:
        return "link"
    if extensao in extensoes_playlist:
        return "playlist"
    return "arquivo"


class Indexador:
    """extensoes: TODAS as extensoes que o jukebox reconhece (audio, video,
    link do YouTube, marcador de busca e .m3u) -- a mesma lista que o
    jukebox usa para listar musicas, para o catalogo nunca divergir do que
    aparece de verdade na tela."""

    def __init__(self, caminho_musicas, caminho_db, extensoes,
                 extensoes_link=(), extensao_busca=None,
                 extensoes_playlist=(".m3u", ".m3u8"), logger=None):
        self.caminho_musicas = caminho_musicas
        self.caminho_db = caminho_db
        self.extensoes = tuple(e.lower() for e in extensoes)
        self.extensoes_link = tuple(e.lower() for e in extensoes_link)
        self.extensao_busca = (extensao_busca or "").lower()
        self.extensoes_playlist = tuple(e.lower() for e in extensoes_playlist)
        self.log = logger

    def reindexar(self):
        """Varre o acervo inteiro e grava um catalogo novo. Retorna um
        dicionario com as contagens, para o operador ver o resultado."""
        inicio = time.time()
        temporario = self.caminho_db + ".tmp"
        if os.path.exists(temporario):
            os.remove(temporario)          # lixo de uma reindexacao anterior

        conexao = sqlite3.connect(temporario)
        try:
            conexao.executescript(SCHEMA)
            contagens = self._preencher(conexao)
            conexao.execute(
                "INSERT INTO catalogo_info (chave, valor) VALUES (?, ?)",
                ("gerado_em", time.strftime("%Y-%m-%d %H:%M:%S")))
            conexao.execute(
                "INSERT INTO catalogo_info (chave, valor) VALUES (?, ?)",
                ("origem", self.caminho_musicas))
            conexao.commit()
        finally:
            conexao.close()

        pasta = os.path.dirname(self.caminho_db)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        os.replace(temporario, self.caminho_db)   # atomico: nunca meio-pronto

        contagens["segundos"] = round(time.time() - inicio, 2)
        if self.log:
            self.log.info(
                "catalogo reindexado: %d genero(s), %d artista(s), "
                "%d musica(s) em %.2fs", contagens["generos"],
                contagens["artistas"], contagens["musicas"],
                contagens["segundos"])
        return contagens

    def _preencher(self, conexao):
        generos = artistas = musicas = 0
        try:
            nomes_genero = sorted(
                d for d in os.listdir(self.caminho_musicas)
                if os.path.isdir(os.path.join(self.caminho_musicas, d)))
        except OSError as erro:
            if self.log:
                self.log.error("nao consegui listar %s: %s",
                               self.caminho_musicas, erro)
            return {"generos": 0, "artistas": 0, "musicas": 0}

        for nome_genero in nomes_genero:
            pasta_genero = os.path.join(self.caminho_musicas, nome_genero)
            genero_id = conexao.execute(
                "INSERT INTO generos (nome) VALUES (?)",
                (nome_genero,)).lastrowid
            generos += 1

            try:
                nomes_artista = sorted(
                    d for d in os.listdir(pasta_genero)
                    if os.path.isdir(os.path.join(pasta_genero, d)))
            except OSError as erro:
                if self.log:
                    self.log.warning("nao consegui listar %s: %s",
                                     pasta_genero, erro)
                continue

            for nome_artista in nomes_artista:
                pasta_artista = os.path.join(pasta_genero, nome_artista)
                artista_id = conexao.execute(
                    "INSERT INTO artistas (genero_id, nome) VALUES (?, ?)",
                    (genero_id, nome_artista)).lastrowid
                artistas += 1

                try:
                    arquivos = os.listdir(pasta_artista)
                except OSError as erro:
                    if self.log:
                        self.log.warning("nao consegui listar %s: %s",
                                         pasta_artista, erro)
                    continue

                linhas = []
                for nome_arquivo in arquivos:
                    extensao = os.path.splitext(nome_arquivo)[1].lower()
                    if extensao not in self.extensoes:
                        continue
                    caminho = os.path.join(pasta_artista, nome_arquivo)
                    try:
                        st = os.stat(caminho)
                    except OSError:
                        continue
                    tipo = _tipo_de(extensao, self.extensoes_link,
                                    self.extensao_busca, self.extensoes_playlist)
                    linhas.append((artista_id, nome_arquivo, caminho, extensao,
                                   tipo, st.st_size, st.st_mtime))
                if linhas:
                    conexao.executemany(
                        "INSERT INTO musicas (artista_id, nome_arquivo, "
                        "caminho, extensao, tipo, tamanho, mtime) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)", linhas)
                    musicas += len(linhas)

        return {"generos": generos, "artistas": artistas, "musicas": musicas}


def resumo(caminho_db):
    """Leitura rapida e so-leitura para o menu do operador. Nunca lanca --
    banco ausente (primeira reindexacao ainda nao rodou) ou corrompido
    devolve None, e quem chama decide o que mostrar."""
    if not caminho_db or not os.path.exists(caminho_db):
        return None
    try:
        conexao = sqlite3.connect(caminho_db)
        try:
            linha = conexao.execute(
                "SELECT (SELECT COUNT(*) FROM generos), "
                "(SELECT COUNT(*) FROM artistas), "
                "(SELECT COUNT(*) FROM musicas), "
                "(SELECT valor FROM catalogo_info WHERE chave='gerado_em')"
            ).fetchone()
        finally:
            conexao.close()
    except sqlite3.Error:
        return None
    return {"generos": linha[0], "artistas": linha[1], "musicas": linha[2],
            "gerado_em": linha[3]}


# ----------------------------------------------------------------------
def _carregar_config(caminho):
    import json
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _indexador_da_config(cfg):
    import youtube
    extensoes_playlist = (".m3u", ".m3u8")
    extensoes = (tuple(cfg["audio"]["extensoes"]) + youtube.EXTENSOES_LINK
                + (youtube.EXTENSAO_BUSCA,) + extensoes_playlist)
    return Indexador(cfg["caminhos"]["musicas"], cfg["caminhos"]["catalogo"],
                     extensoes, extensoes_link=youtube.EXTENSOES_LINK,
                     extensao_busca=youtube.EXTENSAO_BUSCA,
                     extensoes_playlist=extensoes_playlist)


def main():
    import argparse
    import sys

    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    padrao = os.environ.get("JUKEBOX_CONFIG", os.path.join(base, "config.json"))
    ap = argparse.ArgumentParser(description="Catalogo do acervo (SQLite)")
    ap.add_argument("--config", default=padrao)
    sub = ap.add_subparsers(dest="acao", required=True)
    sub.add_parser("reindexar")
    sub.add_parser("resumo")
    args = ap.parse_args()

    cfg = _carregar_config(args.config)
    if args.acao == "reindexar":
        r = _indexador_da_config(cfg).reindexar()
        print("generos: %d  artistas: %d  musicas: %d  (%.2fs)"
             % (r["generos"], r["artistas"], r["musicas"], r["segundos"]))
    elif args.acao == "resumo":
        r = resumo(cfg["caminhos"]["catalogo"])
        print(r if r else "catalogo ainda nao foi gerado")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
