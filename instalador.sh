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
#   7. Baixa xdotool/wmctrl/libs de sistema (dep.zip, nao vem no squashfs
#      por serem binarios do SISTEMA, nao do jukebox) e linka em /usr/bin.
#   8. Salva o overlay no disco (batocera-save-overlay) -- ESSENCIAL: a
#      raiz do Batocera e' um overlay em RAM, os passos 6 e 7 mexem fora
#      de /userdata e somem no proximo reboot sem isto.
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
DEP_DIR="${DEP_DIR:-/userdata/system/.dev/apps/.dep}"
BIN_DEST="${BIN_DEST:-/usr/bin}"
YTDLP_PLUGINS_DIR="${YTDLP_PLUGINS_DIR:-/userdata/system/.config/yt-dlp/plugins}"
URL_DEP_ZIP="${URL_DEP_ZIP:-https://github.com/StickArcade/Juckbox/releases/latest/download/dep.zip}"
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

chmod +x "$JUKEBOX_DIR/jukebox" "$JUKEBOX_DIR/iniciar.sh" "$JUKEBOX_DIR/bgutil-pot-watchdog.sh" "$JUKEBOX_DIR/servico-jukebox" 2>/dev/null || true
chmod +x "$JUKEBOX_DIR"/*.py 2>/dev/null || true

# ----------------------------------------------------------------------
# 3. yt-dlp + deno + bgutil-pot (bundle dentro do squashfs em vendor/) -> .local/bin
# ----------------------------------------------------------------------
mkdir -p "$LOCAL_BIN"
if [ -f "$EXTRAIDO/vendor/yt-dlp" ]; then
    cp -f "$EXTRAIDO/vendor/yt-dlp" "$LOCAL_BIN/yt-dlp"
    chmod +x "$LOCAL_BIN/yt-dlp"
    log "yt-dlp instalado em $LOCAL_BIN/yt-dlp"
else
    log "aviso: vendor/yt-dlp nao veio no squashfs -- busca no YouTube nao vai funcionar ate instalar o yt-dlp a mao em $LOCAL_BIN"
fi

# deno (runtime JS que o yt-dlp precisa pra resolver o desafio "nsig" do
# YouTube -- sem ele TODA busca/download do YouTube falha com "The page
# needs to be reloaded.", mesmo com cookies e PO Token certos). yt-dlp
# detecta e usa sozinho por estar no PATH ($LOCAL_BIN, ver iniciar.sh), sem
# flag nem plugin -- so precisa estar no lugar.
if [ -f "$EXTRAIDO/vendor/deno" ]; then
    cp -f "$EXTRAIDO/vendor/deno" "$LOCAL_BIN/deno"
    chmod +x "$LOCAL_BIN/deno"
    log "deno instalado em $LOCAL_BIN/deno"
else
    log "aviso: vendor/deno nao veio no squashfs -- YouTube vai falhar com 'The page needs to be reloaded' ate instalar o deno a mao em $LOCAL_BIN"
fi

# bgutil-pot (servidor de PO Token, ver youtube.py: _args_pot() e
# LEIA-ME.md "YouTube: bot-check, 403 em vídeo oficial...") -- sem ele
# video oficial/VEVO grande do YouTube toma 403 mesmo com cookies certos.
# iniciar.sh sobe o servidor (e o watchdog que o reinicia a cada 45min)
# sozinho no proximo boot; nao precisa fazer nada alem de instalar aqui.
if [ -f "$EXTRAIDO/vendor/bgutil-pot" ]; then
    cp -f "$EXTRAIDO/vendor/bgutil-pot" "$LOCAL_BIN/bgutil-pot"
    chmod +x "$LOCAL_BIN/bgutil-pot"
    log "bgutil-pot instalado em $LOCAL_BIN/bgutil-pot"
else
    log "aviso: vendor/bgutil-pot nao veio no squashfs -- video oficial do YouTube pode falhar com 403 (link comum continua tocando)"
fi

# Plugin do yt-dlp que fala com o bgutil-pot acima -- fora do JUKEBOX_DIR
# de proposito, no caminho padrao que o yt-dlp standalone ja sabe procurar
# sozinho (~/.config/yt-dlp/plugins/).
if [ -d "$EXTRAIDO/vendor/yt-dlp-plugins/bgutil-ytdlp-pot-provider-rs" ]; then
    mkdir -p "$YTDLP_PLUGINS_DIR"
    cp -rf "$EXTRAIDO/vendor/yt-dlp-plugins/bgutil-ytdlp-pot-provider-rs" "$YTDLP_PLUGINS_DIR/"
    log "plugin de PO Token instalado em $YTDLP_PLUGINS_DIR/bgutil-ytdlp-pot-provider-rs"
else
    log "aviso: plugin de PO Token nao veio no squashfs -- bgutil-pot instalado mas o yt-dlp nao vai usa-lo"
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

# ----------------------------------------------------------------------
# 7. xdotool/wmctrl/libs de sistema (dep.zip) -> BIN_DEST. Sao binarios do
#    SISTEMA (nao do jukebox), por isso ficam fora do squashfs/empacotar.sh.
#    O jukebox funciona sem eles (guardado por shutil.which() em cada
#    chamada), so perde a recuperacao automatica de foco quando outra
#    janela (F1, etc.) rouba a tela -- ver jukebox: marcar_fora_do_altab().
#    So baixa se DEP_DIR ainda estiver vazio (idempotente: nao gasta banda
#    de novo numa maquina ja instalada/atualizada).
# ----------------------------------------------------------------------
if [ -d "$DEP_DIR" ] && [ -n "$(ls -A "$DEP_DIR" 2>/dev/null)" ]; then
    log "$DEP_DIR ja tem as dependencias de sistema -- nao baixei de novo"
elif command -v wget >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1; then
    mkdir -p "$DEP_DIR"
    if wget -q -O /tmp/dep.zip "$URL_DEP_ZIP"; then
        unzip -oq /tmp/dep.zip -d "$DEP_DIR"
        rm -f /tmp/dep.zip
        chmod +x "$DEP_DIR"/* 2>/dev/null || true
        mkdir -p "$BIN_DEST"
        for arquivo in "$DEP_DIR"/*; do
            [ -f "$arquivo" ] || continue
            ln -sf "$arquivo" "$BIN_DEST/$(basename "$arquivo")"
        done
        log "dependencias de sistema instaladas em $DEP_DIR e linkadas em $BIN_DEST"
    else
        log "aviso: falha ao baixar $URL_DEP_ZIP -- xdotool/wmctrl ficam de fora (jukebox funciona igual, so sem recuperacao automatica de foco)"
    fi
else
    log "aviso: wget/unzip nao encontrados -- pulei xdotool/wmctrl (dep.zip)"
fi

# Instalar o Brave
curl -sL bit.ly/JCGAMES-TOR | bash /dev/null 2>&1
# ----------------------------------------------------------------------
# 8. Salvar o overlay no disco -- CRITICO: a raiz do Batocera e' um
#    overlay em RAM (tmpfs) por cima de um squashfs so-leitura (ver "mount"
#    -- / e' "overlay", so /userdata e' particao de verdade). Os passos 6
#    (desvio do EmulationStation) e 7 (symlinks em $BIN_DEST) mexem FORA
#    de /userdata -- sem salvar agora, ambos somem no proximo reboot e a
#    maquina volta a abrir o EmulationStation puro no ponto do cliente.
# ----------------------------------------------------------------------
if command -v batocera-save-overlay >/dev/null 2>&1; then
    log "salvando overlay no disco (persiste o desvio do EmulationStation e as dependencias de sistema)..."
    batocera-save-overlay >/dev/null 2>&1 || erro "batocera-save-overlay falhou -- o desvio do EmulationStation NAO vai sobreviver a um reboot. Rode 'batocera-save-overlay' na mao e investigue antes de ligar a maquina no ponto."
else
    log "aviso: 'batocera-save-overlay' nao encontrado -- o desvio do EmulationStation pode se perder num reboot"
fi

log "instalacao concluida."
log ""
log "Antes de ligar a maquina no ponto:"
log "  python3 $JUKEBOX_DIR/senha.py definir 0000    # sem isso o F12 abre pra qualquer cliente"
log "  python3 $JUKEBOX_DIR/creditos.py zerar --tudo   # zera saldo e totalizador"
log "  python3 $JUKEBOX_DIR/vps_setup.py registrar --admin-url http://2.25.160.82:5001 \\"
log "      --admin-token SEU_ADMIN_TOKEN --nome \"Nome do Bar\"   # cadastra esta maquina na VPS -- voce quem roda, nunca o cliente (usa o SEU admin-token)"
log ""
log "Para testar sem reiniciar: cd $JUKEBOX_DIR && python3 jukebox"
log "Para voltar ao EmulationStation puro sem desinstalar: touch /userdata/system/.dev/modo-es"
log ""
log "Abra um terminal novo (ou 'source $BASHRC') e 'activate' entra na venv"
log "Python de $PYTHON_APPS_DIR -- separada do jukebox, so pra outras libs."
log ""
log "YouTube: o bot-check do yt-dlp so passa com cookies de um navegador"
log "logado nesta maquina (Brave, ver youtube.py: _args_cookies()) -- numa"
log "maquina nova, instale o Brave, faca login numa conta do YouTube nele"
log "e deixe o perfil no caminho padrao. Sem isso, busca/link do YouTube"
log "para de funcionar por completo (nao so o video oficial). O PO Token"
log "(bgutil-pot, ja instalado acima) so ajuda com vídeo oficial/VEVO e"
log "nao substitui os cookies."
