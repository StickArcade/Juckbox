#!/bin/bash
# Decide o que sobe no lugar do EmulationStation.
#
# Chamado pelo emulationstation-standalone, que ja preparou resolucao,
# rotacao, teclado e dbus -- e que fica num laco reiniciando o que cair.
#
# DUAS PROTECOES, porque uma maquina que nao sobe no bar e prejuizo:
#
#  1. ARQUIVO DE MANUTENCAO. Se existir /userdata/system/.dev/modo-es, sobe o
#     EmulationStation normal. E como voce volta ao Batocera para mexer na
#     maquina, sem precisar desfazer a instalacao.
#
#  2. QUEDA RAPIDA. Se o jukebox morrer em menos de 20 s, e porque nao esta
#     conseguindo subir (dependencia faltando, config errado, tela). Depois de
#     3 quedas seguidas assim, ele desiste e chama o EmulationStation, para a
#     maquina nunca ficar numa tela preta sem saida.

# O jukebox nao roda dentro do venv, entao precisa enxergar as ferramentas
# instaladas em /userdata/system/.local/bin -- yt-dlp e deno, usados para
# tocar video do YouTube. Sem isso o mpv nao resolve as URLs.
export PATH="/userdata/system/.local/bin:$PATH"

JUKEBOX_DIR=/userdata/system/.dev/apps/Juckbox
FLAG_ES=/userdata/system/.dev/modo-es
CONTA_FALHAS=/var/run/jukebox-falhas
LOG=/userdata/system/.dev/arranque.log

registrar() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"
    if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 262144 ]; then
        mv -f "$LOG" "$LOG.1"
    fi
}

subir_es() {
    registrar "subindo EmulationStation"
    cd /userdata || exit 1
    exec emulationstation "$@" --exit-on-reboot-required --windowed
}

if [ -e "$FLAG_ES" ]; then
    registrar "modo-es presente: manutencao"
    subir_es "$@"
fi

if [ ! -f "$JUKEBOX_DIR/jukebox" ]; then
    registrar "ERRO: $JUKEBOX_DIR/jukebox nao encontrado"
    subir_es "$@"
fi

falhas=$(cat "$CONTA_FALHAS" 2>/dev/null || echo 0)
if [ "$falhas" -ge 3 ]; then
    registrar "3 quedas rapidas seguidas: caindo para o EmulationStation"
    rm -f "$CONTA_FALHAS"
    subir_es "$@"
fi

registrar "subindo o jukebox (falhas recentes: $falhas)"
inicio=$(date +%s)
cd "$JUKEBOX_DIR" || subir_es "$@"
python3 jukebox
codigo=$?
duracao=$(( $(date +%s) - inicio ))

if [ "$duracao" -lt 20 ]; then
    echo $(( falhas + 1 )) > "$CONTA_FALHAS"
    registrar "jukebox saiu em ${duracao}s (codigo $codigo) -- queda rapida $(( falhas + 1 ))/3"
    sleep 3
else
    rm -f "$CONTA_FALHAS"
    registrar "jukebox saiu apos ${duracao}s (codigo $codigo)"
fi

exit "$codigo"
