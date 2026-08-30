#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Links do YouTube como se fossem musicas do acervo.

COMO O OPERADOR CADASTRA
------------------------
Cria um arquivo de texto na arvore normal de musicas:

    musicas/YOUTUBE/Charlie Brown Jr/Zoio de Lula.url

com a URL dentro. So isso. O carrossel, as logos, o fundo por genero, a fila
e o estorno funcionam sem nenhuma mudanca, porque para o resto do programa
e apenas mais um arquivo.

DUAS COISAS QUE OS TESTES NA MAQUINA MOSTRARAM
----------------------------------------------
1. FORCAR H.264 (avc1) e obrigatorio. Sem isso o YouTube entrega AV1, que a
   GPU do i3 de 4a geracao nao decodifica -- cai para software, engasga e
   ainda chega a corromper o stream.

2. O yt-dlp devolve DUAS URLs (imagem e som separados). O mpv precisa das
   duas: a primeira como arquivo, a segunda em --audio-file.

E as URLs resolvidas EXPIRAM em poucas horas, entao nao adianta resolver
antes e guardar: tem de ser na hora de tocar.
"""

import os
import re
import subprocess

EXTENSOES_LINK = (".url", ".yt", ".youtube", ".link")

# Arquivo marcador que abre a tela de busca em vez de tocar. Mesmo truque do
# .url: o resto do programa nao precisa saber que existe uma tela de busca --
# para ele e so mais um arquivo na pasta.
EXTENSAO_BUSCA = ".buscar"


def eh_busca(caminho):
    return caminho.lower().endswith(EXTENSAO_BUSCA)

# altura maxima; 720p numa TV de bar e indistinguivel de 1080p e gasta bem
# menos banda e buffer
FORMATO = ("bestvideo[vcodec^=avc1][height<=%(a)d]+bestaudio/"
           "best[vcodec^=avc1][height<=%(a)d]/"
           "best[height<=%(a)d]")


def eh_link(caminho):
    return caminho.lower().endswith(EXTENSOES_LINK)


def disponivel():
    from shutil import which
    return which("yt-dlp") is not None


def ler_url(caminho):
    """Aceita o arquivo com a URL solta numa linha e tambem o formato de
    atalho do Windows ([InternetShortcut] / URL=...), que e o que sai quando
    se arrasta um link do navegador."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            conteudo = f.read()
    except OSError:
        return None
    achado = re.search(r"^\s*URL\s*=\s*(\S+)", conteudo,
                       re.IGNORECASE | re.MULTILINE)
    if achado:
        return achado.group(1).strip()
    for linha in conteudo.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "://" in linha:
            return linha
    return None


# Marcadores de "video oficial" que so poluem o nome da musica. Coisas como
# (Ao Vivo) ou (Acustico) NAO entram aqui: distinguem versoes de verdade.
_RUIDO = re.compile(
    r"\s*[\(\[]\s*(official\s*(music\s*)?video|video\s*oficial|"
    r"clipe\s*oficial|official\s*audio|lyric\s*video|hd|4k|"
    r"official\s*visualizer)\s*[\)\]]", re.IGNORECASE)


def _vazio(v):
    return not v or v.strip().upper() in ("NA", "NONE", "")


def separar_artista(titulo, canal, artista_meta="", faixa_meta=""):
    """Descobre (artista, musica) a partir do que o YouTube deu.

    Tres fontes, nesta ordem:
      1. artist/track do YouTube Music -- e o dado limpo, quando existe
      2. o titulo no formato "Artista - Musica", que e a convencao da maioria
      3. o canal, como ultimo recurso

    O canal fica por ultimo de proposito: ele costuma ser a GRAVADORA, nao o
    artista. "Oficina G3" publicado pelo canal "MK MUSIC" e o caso tipico."""
    titulo = (titulo or "").strip()
    if not _vazio(artista_meta) and not _vazio(faixa_meta):
        return artista_meta.strip(), _RUIDO.sub("", faixa_meta).strip()

    limpo = _RUIDO.sub("", titulo).strip()
    for separador in (" - ", " \u2013 ", " \u2014 ", " | "):
        if separador in limpo:
            esquerda, direita = limpo.split(separador, 1)
            esquerda, direita = esquerda.strip(), direita.strip()
            if esquerda and direita:
                return esquerda, direita
    return ((canal or "Encontrados").strip(), limpo or titulo)


def buscar(termo, quantos=8, timeout=25, logger=None,
           maximo_segundos=600):
    """Procura no YouTube e devolve uma lista de dicionarios.

    Usa --flat-playlist de proposito: sem ele o yt-dlp abriria cada video para
    extrair detalhes, e oito videos levariam mais de meio minuto. Assim a
    busca inteira sai em poucos segundos, e a resolucao pesada acontece so no
    video que o cliente escolher."""
    if not termo.strip():
        return []
    # artist/track vem do YouTube Music quando o video e musical -- e a fonte
    # mais confiavel. Nem sempre existe, dai o titulo serve de reserva.
    modelo = ("%(title)s\t%(duration)s\t%(id)s\t%(uploader)s"
              "\t%(artist)s\t%(track)s")
    # Pede o dobro: o filtro de duracao vai descartar DVDs e coletaneas, e
    # sem folga a lista chegaria curta ao cliente.
    comando = ["yt-dlp", "ytsearch%d:%s" % (quantos * 3, termo),
               "--flat-playlist", "--no-warnings", "--print", modelo]
    try:
        r = subprocess.run(comando, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp nao instalado")
    except subprocess.TimeoutExpired:
        raise RuntimeError("busca demorou demais")

    achados = []
    for linha in r.stdout.decode("utf-8", "ignore").splitlines():
        partes = linha.split("\t")
        if len(partes) < 3 or not partes[2].strip():
            continue
        titulo, duracao, ident = partes[0], partes[1], partes[2].strip()
        canal = partes[3] if len(partes) > 3 else ""
        artista_meta = partes[4] if len(partes) > 4 else ""
        faixa_meta = partes[5] if len(partes) > 5 else ""
        try:
            segundos = int(float(duracao))
        except (ValueError, TypeError):
            segundos = 0
        # Numa jukebox, "DVD Completo" de 80 minutos prende a maquina por uma
        # hora com um credito so. Duracao desconhecida (0) tambem cai fora:
        # costuma ser transmissao ao vivo, que nao tem fim.
        if maximo_segundos and (segundos <= 0 or segundos > maximo_segundos):
            continue
        artista, musica = separar_artista(titulo, canal, artista_meta,
                                         faixa_meta)
        achados.append({
            "titulo": titulo.strip() or "(sem titulo)",
            "artista": artista,
            "musica": musica,
            "canal": (canal or "").strip(),
            "segundos": segundos,
            "duracao": "%d:%02d" % (segundos // 60, segundos % 60) if segundos else "",
            "url": "https://www.youtube.com/watch?v=" + ident,
        })
    achados = achados[:quantos]
    if logger:
        logger.info("busca '%s': %d resultado(s) ate %ds",
                    termo[:40], len(achados), maximo_segundos)
    return achados


def resolver(url, altura=720, timeout=30, logger=None):
    """Devolve (url_video, url_audio) -- a segunda pode ser None quando o
    formato ja vem com som junto. Levanta RuntimeError se nao conseguir."""
    comando = ["yt-dlp", "-f", FORMATO % {"a": altura}, "-g",
               "--no-playlist", "--no-warnings", url]
    try:
        r = subprocess.run(comando, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp nao instalado")
    except subprocess.TimeoutExpired:
        raise RuntimeError("tempo esgotado ao resolver o link")

    linhas = [l.strip() for l in r.stdout.decode("utf-8", "ignore").splitlines()
              if l.strip()]
    if r.returncode != 0 or not linhas:
        erro = r.stderr.decode("utf-8", "ignore").strip().splitlines()
        detalhe = erro[-1] if erro else "sem detalhe"
        if logger:
            logger.error("yt-dlp falhou: %s", detalhe)
        raise RuntimeError(detalhe[:80])

    if logger:
        logger.info("link resolvido em %d stream(s)", len(linhas))
    return (linhas[0], linhas[1] if len(linhas) > 1 else None)
