#!/bin/sh
# Gera os dois arquivos da release (jukebox.squashfs + instalador.sh) em
# dist/, prontos para subir como assets de uma release no GitHub.
#
# Uso: sh empacotar.sh
#
# So roda no proprio Batocera (ou em qualquer Linux com mksquashfs): usa o
# mksquashfs do sistema, nao baixa nada.

set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIST_DIR="$REPO_DIR/dist"
PAYLOAD=$(mktemp -d)
trap 'rm -rf "$PAYLOAD"' EXIT

log() { echo "[empacotar] $*"; }

command -v mksquashfs >/dev/null 2>&1 || { echo "mksquashfs nao encontrado" >&2; exit 1; }

# ----------------------------------------------------------------------
# Codigo + assets que rodam em producao (ver LEIA-ME.md, tabela "Nucleo" e
# "Instalacao/sistema"). NAO entra: musicas/, musicas.bkp/, .dev/,
# __pycache__/, *.bak*, config.dev.json, testar.sh, .git -- nada disso e
# codigo de producao nem faz sentido numa maquina nova.
# ----------------------------------------------------------------------
log "montando payload em $PAYLOAD"
cp "$REPO_DIR"/config.json \
   "$REPO_DIR"/creditos.py \
   "$REPO_DIR"/player.py \
   "$REPO_DIR"/menu.py \
   "$REPO_DIR"/busca.py \
   "$REPO_DIR"/carrossel.py \
   "$REPO_DIR"/fundo.py \
   "$REPO_DIR"/youtube.py \
   "$REPO_DIR"/senha.py \
   "$REPO_DIR"/catalogo.py \
   "$REPO_DIR"/jukebox \
   "$REPO_DIR"/iniciar.sh \
   "$REPO_DIR"/servico-jukebox \
   "$REPO_DIR"/emulationstation-standalone \
   "$REPO_DIR"/LEIA-ME.md \
   "$PAYLOAD/"
cp -r "$REPO_DIR"/assets "$REPO_DIR"/themes "$REPO_DIR"/ui "$PAYLOAD/"

# config.json de producao tem o PIN (sal+resumo) desta maquina -- uma
# instalacao nova nao pode herdar o PIN de outra. Zera os dois campos; o
# resto (caminhos, audio, interface, operacao) e generico e serve de
# template legitimo.
python3 - "$PAYLOAD/config.json" <<'PYEOF'
import json, sys
caminho = sys.argv[1]
with open(caminho, encoding="utf-8") as f:
    cfg = json.load(f)
cfg["operacao"]["senha_sal"] = None
cfg["operacao"]["senha_resumo"] = None
with open(caminho, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF

# yt-dlp bundlado (binario standalone, PATH="/userdata/system/.local/bin")
# -- sem ele a busca no YouTube nao funciona numa maquina sem internet
# franca pra baixar na hora da instalacao.
mkdir -p "$PAYLOAD/vendor"
if command -v yt-dlp >/dev/null 2>&1; then
    cp "$(command -v yt-dlp)" "$PAYLOAD/vendor/yt-dlp"
    log "yt-dlp $($PAYLOAD/vendor/yt-dlp --version 2>/dev/null || echo '?') incluido no pacote"
else
    log "aviso: yt-dlp nao encontrado neste sistema -- pacote vai sem ele (instalador avisa na hora)"
fi

chmod +x "$PAYLOAD"/jukebox "$PAYLOAD"/iniciar.sh "$PAYLOAD"/servico-jukebox "$PAYLOAD"/*.py 2>/dev/null || true
[ -f "$PAYLOAD/vendor/yt-dlp" ] && chmod +x "$PAYLOAD/vendor/yt-dlp"

# ----------------------------------------------------------------------
# Squashfs
# ----------------------------------------------------------------------
mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR/jukebox.squashfs"
mksquashfs "$PAYLOAD" "$DIST_DIR/jukebox.squashfs" -comp xz -noappend >/dev/null
cp "$REPO_DIR/instalador.sh" "$DIST_DIR/instalador.sh"

( cd "$DIST_DIR" && sha256sum jukebox.squashfs instalador.sh > SHA256SUMS 2>/dev/null || true )

log "pronto:"
ls -lh "$DIST_DIR"
log ""
log "sobe jukebox.squashfs, instalador.sh (e SHA256SUMS, opcional) como"
log "assets de uma release no GitHub. Antes de publicar, edite a URL"
log "padrao (URL_SQUASHFS) no topo de instalador.sh para apontar pra essa"
log "release."
