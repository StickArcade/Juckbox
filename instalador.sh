#!/bin/sh
# Instalador do Jukebox para Batocera.
#
# Uso numa maquina nova (com internet):
#   wget -O instalador.sh https://github.com/StickArcade/Juckbox/releases/latest/download/instalador.sh
#   sh instalador.sh
#
# Ou apontando pra outro squashfs/release (ex.: testar uma versao antiga):
#   sh instalador.sh https://.../jukebox.squashfs
#
# Se "jukebox.squashfs" ja estiver do lado deste script (baixado a mao, ou
# extraido de um pendrive), o instalador usa ele direto e nao baixa nada.
#
# E IDEMPOTENTE: rodar de novo numa maquina ja instalada atualiza o codigo
# sem mexer em musicas/, config.json ou no estado (creditos, fila, log,
# catalogo) -- serve tanto pra instalar quanto pra atualizar.
#
# O que ele faz, nesta ordem:
#   1. Garante o squashfs do jukebox (local ou "wget").
#   2. Extrai e copia o codigo/assets para JUKEBOX_DIR (musicas/ e
#      config.json existentes nunca sao sobrescritos).
#   3. Coloca o yt-dlp (vem dentro do squashfs) em /userdata/system/.local/bin.
#   4. Instala o(s) Python via AppImage (+ venv) em PYTHON_APPS_DIR, para
#      bibliotecas que o python3 de fabrica do Batocera nao roda -- so na
#      primeira vez, nunca mexe se a pasta ja existir (nao perder pacotes
#      ja instalados). O jukebox em si NAO usa isto, continua rodando no
#      python3 do sistema -- ver comentario em iniciar.sh.
#   5. Acrescenta PATH e atalhos no .bashrc (bloco marcado, idempotente),
#      incluindo o alias "activate" para essa venv.
#   6. Faz o /usr/bin/emulationstation-standalone chamar o iniciar.sh do
#      jukebox no lugar do EmulationStation, guardando uma copia do
#      original antes de mexer.
#
# Musica nao faz parte disto -- o proprio jukebox monta uma prateleira de
# generos vazia sozinho no primeiro boot (ver LEIA-ME.md, "Acervo inicial").

set -eu

URL_SQUASHFS="${1:-https://github.com/StickArcade/Juckbox/releases/latest/download/jukebox.squashfs}"
# As quatro variaveis abaixo aceitam override por ambiente -- serve pra
# testar o instalador contra um destino falso (JUKEBOX_DIR=/tmp/fake ... sh
# instalador.sh), nunca precisa mexer nisso pra instalar de verdade.
JUKEBOX_DIR="${JUKEBOX_DIR:-/userdata/system/.dev/apps/Juckbox}"
LOCAL_BIN="${LOCAL_BIN:-/userdata/system/.local/bin}"
BASHRC="${BASHRC:-/userdata/system/.bashrc}"
ES_STANDALONE="${ES_STANDALONE:-/usr/bin/emulationstation-standalone}"
PYTHON_APPS_DIR="${PYTHON_APPS_DIR:-/userdata/system/.dev/apps/python}"
MARCA_BASHRC_INICIO="# ---- jukebox: inicio (gerado por instalador.sh) ----"
MARCA_BASHRC_FIM="# ---- jukebox: fim ----"
MARCA_ES="[JUKEBOX]"

log() { echo "[instalador] $*"; }
erro() { echo "[instalador] ERRO: $*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || erro "rode como root (e assim que o Batocera roda por padrao)."

# ----------------------------------------------------------------------
# 1. Squashfs do jukebox: usa o que estiver do lado do script, senao baixa
# ----------------------------------------------------------------------
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SQUASHFS="$SCRIPT_DIR/jukebox.squashfs"

if [ -f "$SQUASHFS" ]; then
    log "usando $SQUASHFS (ja esta local, nao baixei nada)"
else
    command -v wget >/dev/null 2>&1 || erro "wget nao encontrado e jukebox.squashfs nao esta ao lado do script."
    SQUASHFS=/tmp/jukebox.squashfs
    log "baixando $URL_SQUASHFS"
    wget -O "$SQUASHFS" "$URL_SQUASHFS" || erro "falha ao baixar o squashfs."
fi

command -v unsquashfs >/dev/null 2>&1 || erro "unsquashfs nao encontrado (deveria vir de fabrica no Batocera)."

# ----------------------------------------------------------------------
# 2. Extrair e copiar para JUKEBOX_DIR, sem tocar em musicas/ nem config.json
#    ja existentes (isso e o que faz o instalador servir pra atualizar tambem)
# ----------------------------------------------------------------------
EXTRAIDO=/tmp/jukebox-extraido
rm -rf "$EXTRAIDO"
log "extraindo squashfs..."
unsquashfs -f -d "$EXTRAIDO" "$SQUASHFS" >/dev/null

mkdir -p "$JUKEBOX_DIR"

log "copiando codigo e assets para $JUKEBOX_DIR"
for item in "$EXTRAIDO"/*; do
    nome=$(basename "$item")
    case "$nome" in
        config.json)
            if [ -f "$JUKEBOX_DIR/config.json" ]; then
                log "config.json ja existe -- mantendo o da maquina (nao sobrescrevo PIN/config feita no local)"
                continue
            fi
            ;;
        musicas)
            # o pacote nao deveria trazer isto, mas por seguranca nunca
            # sobrescrever um acervo que ja exista
            continue
            ;;
    esac
    cp -rf "$item" "$JUKEBOX_DIR/"
done

chmod +x "$JUKEBOX_DIR/jukebox" "$JUKEBOX_DIR/iniciar.sh" "$JUKEBOX_DIR/servico-jukebox" 2>/dev/null || true
chmod +x "$JUKEBOX_DIR"/*.py 2>/dev/null || true

# ----------------------------------------------------------------------
# 3. yt-dlp (bundle dentro do squashfs em vendor/) -> .local/bin
# ----------------------------------------------------------------------
mkdir -p "$LOCAL_BIN"
if [ -f "$EXTRAIDO/vendor/yt-dlp" ]; then
    cp -f "$EXTRAIDO/vendor/yt-dlp" "$LOCAL_BIN/yt-dlp"
    chmod +x "$LOCAL_BIN/yt-dlp"
    log "yt-dlp instalado em $LOCAL_BIN/yt-dlp"
else
    log "aviso: vendor/yt-dlp nao veio no squashfs -- busca no YouTube nao vai funcionar ate instalar o yt-dlp a mao em $LOCAL_BIN"
fi

# ----------------------------------------------------------------------
# 4. Python(s) via AppImage + venv, para bibliotecas futuras que o
#    python3 de fabrica do Batocera nao roda. O JUKEBOX EM SI NAO USA
#    ISTO -- continua no python3 do sistema (ver comentario em
#    iniciar.sh). So copia na primeira vez: se PYTHON_APPS_DIR ja existe,
#    nao mexe, pra nao perder pacotes que ja tiverem sido instalados nessa
#    venv depois da instalacao.
# ----------------------------------------------------------------------
if [ -d "$EXTRAIDO/python-apps" ]; then
    if [ -d "$PYTHON_APPS_DIR" ]; then
        log "$PYTHON_APPS_DIR ja existe -- mantendo (nao mexo pra nao perder pacotes ja instalados)"
    else
        mkdir -p "$(dirname "$PYTHON_APPS_DIR")"
        cp -rf "$EXTRAIDO/python-apps" "$PYTHON_APPS_DIR"
        chmod +x "$PYTHON_APPS_DIR"/*.AppImage 2>/dev/null || true
        log "python(s) AppImage instalado(s) em $PYTHON_APPS_DIR"
    fi
else
    log "aviso: python-apps nao veio no squashfs -- pulei esse passo"
fi

rm -rf "$EXTRAIDO"

# ----------------------------------------------------------------------
# 5. .bashrc -- PATH + atalhos, num bloco marcado (idempotente: apaga o
#    bloco antigo antes de escrever, nunca duplica)
# ----------------------------------------------------------------------
touch "$BASHRC"
if grep -qF "$MARCA_BASHRC_INICIO" "$BASHRC" 2>/dev/null; then
    log ".bashrc: atualizando bloco do jukebox"
    TMP_BASHRC=$(mktemp)
    awk -v ini="$MARCA_BASHRC_INICIO" -v fim="$MARCA_BASHRC_FIM" '
        $0==ini {pular=1}
        !pular {print}
        $0==fim {pular=0}
    ' "$BASHRC" > "$TMP_BASHRC"
    mv "$TMP_BASHRC" "$BASHRC"
else
    log ".bashrc: adicionando bloco do jukebox"
fi
cat >> "$BASHRC" <<EOF
$MARCA_BASHRC_INICIO
export PATH="$LOCAL_BIN:\$PATH"
export JUKEBOX_DIR=$JUKEBOX_DIR
alias jk='cd \$JUKEBOX_DIR'
alias juckebox='cd \$JUKEBOX_DIR && { batocera-es-swissknife --emukill; sleep 2; python3 jukebox; }'
alias jklog='tail -f /userdata/system/.dev/jukebox.log'
alias jkcred='python3 \$JUKEBOX_DIR/creditos.py --config \$JUKEBOX_DIR/config.json'
alias activate='source $PYTHON_APPS_DIR/venv/bin/activate'
$MARCA_BASHRC_FIM
EOF

# ----------------------------------------------------------------------
# 6. emulationstation-standalone: desviar para o iniciar.sh do jukebox
# ----------------------------------------------------------------------
if [ -f "$ES_STANDALONE" ]; then
    if grep -qF "$MARCA_ES" "$ES_STANDALONE"; then
        log "emulationstation-standalone: ja aponta pro jukebox (nada a fazer)"
    else
        [ -f "$ES_STANDALONE.orig" ] || cp -f "$ES_STANDALONE" "$ES_STANDALONE.orig"
        python3 - "$ES_STANDALONE" "$JUKEBOX_DIR" "$MARCA_ES" <<'PYEOF'
import sys
caminho, jukebox_dir, marca = sys.argv[1:4]
with open(caminho, "r", encoding="utf-8") as f:
    conteudo = f.read()
alvo = "emulationstation ${GAMELAUNCHOPT} --exit-on-reboot-required --windowed ${CUSTOMESOPTIONS}"
if alvo not in conteudo:
    sys.exit("linha esperada nao encontrada em " + caminho + " -- versao do Batocera pode ser diferente da testada; edite a mao.")
substituto = (
    "# %s quem decide o que sobe e o iniciar.sh. Ele volta para o\n"
    "     # EmulationStation se houver o arquivo modo-es ou se o jukebox falhar.\n"
    "     %s/iniciar.sh ${GAMELAUNCHOPT} ${CUSTOMESOPTIONS}"
) % (marca, jukebox_dir)
conteudo = conteudo.replace(alvo, substituto, 1)
with open(caminho, "w", encoding="utf-8") as f:
    f.write(conteudo)
PYEOF
        chmod +x "$ES_STANDALONE"
        log "emulationstation-standalone: desviado para $JUKEBOX_DIR/iniciar.sh (original em $ES_STANDALONE.orig)"
    fi
else
    log "aviso: $ES_STANDALONE nao encontrado -- desvio nao aplicado, precisa fazer a mao (ver LEIA-ME.md)"
fi

log "instalacao concluida."
log ""
log "Antes de ligar a maquina no ponto:"
log "  python3 $JUKEBOX_DIR/senha.py definir <PIN>     # sem isso o F12 abre pra qualquer cliente"
log "  python3 $JUKEBOX_DIR/creditos.py zerar --tudo   # zera saldo e totalizador"
log ""
log "Para testar sem reiniciar: cd $JUKEBOX_DIR && python3 jukebox"
log "Para voltar ao EmulationStation puro sem desinstalar: touch /userdata/system/.dev/modo-es"
log ""
log "Abra um terminal novo (ou 'source $BASHRC') e 'activate' entra na venv"
log "Python de $PYTHON_APPS_DIR -- separada do jukebox, so pra outras libs."
