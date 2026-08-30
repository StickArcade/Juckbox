#!/bin/sh
# Regera assets/generos.squashfs a partir do acervo real em musicas/.
#
# Roda sempre que um logo/background de GENERO for adicionado ou trocado
# (ver conferir_logos.py para saber quais generos ainda faltam). So pega
# logo.*/background.* de cada pasta de genero -- NUNCA de artista, NUNCA
# musica/playlist -- entao e seguro rodar com o acervo de verdade do bar
# do lado, sem risco de vazar nome de artista ou faixa no pacote que vai
# pra release.
#
# Uso: sh gerar_generos_squashfs.sh

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
MUSIC_DIR="$REPO_DIR/musicas"
DESTINO="$REPO_DIR/assets/generos.squashfs"
EXTENSOES="png jpg jpeg webp"
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT

log() { echo "[gerar_generos_squashfs] $*"; }

[ -d "$MUSIC_DIR" ] || { echo "musicas/ nao existe em $MUSIC_DIR" >&2; exit 1; }
command -v mksquashfs >/dev/null 2>&1 || { echo "mksquashfs nao encontrado" >&2; exit 1; }

total=0
com_logo=0
com_bg=0
for pasta in "$MUSIC_DIR"/*/; do
    [ -d "$pasta" ] || continue
    genero=$(basename "$pasta")
    total=$((total + 1))

    if [ "$genero" = "YOUTUBE" ]; then
        # Genero especial: a pasta BUSCAR/*.buscar e o que abre a tela de
        # busca do YouTube ao navegar ate ela (ver EXTENSAO_BUSCA em
        # youtube.py) -- sem ela o cliente nao tem como disparar a busca
        # pela navegacao normal. Copia do acervo se existir; senao cria
        # uma vazia (so a extensao importa, o conteudo nao e lido).
        mkdir -p "$STAGING/$genero/BUSCAR"
        if [ -d "$pasta/BUSCAR" ] && [ -n "$(find "$pasta/BUSCAR" -iname '*.buscar' -print -quit)" ]; then
            cp "$pasta"/BUSCAR/*.buscar "$STAGING/$genero/BUSCAR/"
        else
            : > "$STAGING/$genero/BUSCAR/Buscar no YouTube.buscar"
        fi
    else
        mkdir -p "$STAGING/$genero/ADICIONE_ARTISTAS_AQUI"
    fi

    for ext in $EXTENSOES; do
        if [ -f "$pasta/logo.$ext" ]; then
            cp "$pasta/logo.$ext" "$STAGING/$genero/"
            com_logo=$((com_logo + 1))
            break
        fi
    done
    for ext in $EXTENSOES; do
        if [ -f "$pasta/background.$ext" ]; then
            cp "$pasta/background.$ext" "$STAGING/$genero/"
            com_bg=$((com_bg + 1))
            break
        fi
    done
done

rm -f "$DESTINO"
mksquashfs "$STAGING" "$DESTINO" -comp xz -noappend >/dev/null

log "gerado $DESTINO"
log "$total genero(s): $com_logo com logo, $com_bg com background"
log "lembrar de rodar empacotar.sh de novo para levar isso pra dist/ e pra release"
