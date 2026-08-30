#!/bin/bash
# Utilitário de teste do jukebox no desktop (NÃO usar em produção).
#
#   ./testar.sh deps       -> confere e instala o que falta
#   ./testar.sh credito 5  -> insere 5 créditos de teste
#   ./testar.sh saldo      -> mostra o saldo
#   ./testar.sh rodar      -> abre em janela 1280x720
#   ./testar.sh fumaca     -> teste automático sem abrir tela
#   ./testar.sh log        -> acompanha o log
#   ./testar.sh catalogo   -> reindexa o catálogo SQLite e mostra o resumo
#   ./testar.sh limpar     -> zera créditos, fila e logs de teste

cd "$(dirname "$0")" || exit 1
export JUKEBOX_CONFIG=config.dev.json
export PYGAME_HIDE_SUPPORT_PROMPT=1
mkdir -p .dev

verde()    { echo -e "\033[32m$*\033[0m"; }
vermelho() { echo -e "\033[31m$*\033[0m"; }

checar_deps() {
    local faltando=()
    echo "Conferindo dependências..."

    if command -v python3 >/dev/null; then
        verde "  ok  python3 $(python3 -V 2>&1 | cut -d' ' -f2)"
    else
        vermelho "  -- python3 AUSENTE"; faltando+=("python3")
    fi

    if python3 -c "import pygame" 2>/dev/null; then
        verde "  ok  pygame $(python3 -c 'import pygame;print(pygame.version.ver)' 2>/dev/null)"
    else
        vermelho "  -- pygame AUSENTE"; faltando+=("python3-pygame")
    fi

    if python3 -c "import PIL" 2>/dev/null; then
        verde "  ok  pillow (necessário só para o GIF de 'tocando')"
    else
        vermelho "  -- pillow AUSENTE"; faltando+=("python3-pil")
    fi

    if command -v mpv >/dev/null; then
        verde "  ok  mpv $(mpv --version 2>/dev/null | head -1 | cut -d' ' -f2)"
    else
        vermelho "  -- mpv AUSENTE  <-- sem isso NENHUMA música toca"; faltando+=("mpv")
    fi

    # A pasta de músicas é a fonte de tudo; se estiver errada, a tela abre vazia
    local pasta
    pasta=$(python3 -c "import json;print(json.load(open('config.dev.json'))['caminhos']['musicas'])")
    if [ -d "$pasta" ]; then
        verde "  ok  pasta de músicas: $pasta ($(find "$pasta" -maxdepth 1 -type d | tail -n +2 | wc -l) gêneros)"
    else
        vermelho "  -- pasta de músicas não encontrada: $pasta"
    fi

    if [ ${#faltando[@]} -gt 0 ]; then
        echo
        echo "Instale com:"
        echo "  sudo apt update && sudo apt install -y ${faltando[*]}"
        return 1
    fi
    echo; verde "Tudo pronto."
}

case "${1:-deps}" in
    deps)
        checar_deps
        ;;
    credito)
        python3 creditos.py adicionar "${2:-5}" --origem teste-manual
        echo "saldo: $(python3 creditos.py ler)"
        ;;
    saldo)
        echo "saldo: $(python3 creditos.py ler)"
        python3 creditos.py resumo
        ;;
    rodar)
        checar_deps || { vermelho "Resolva as dependências antes."; exit 1; }
        chmod +x jukebox 2>/dev/null
        echo
        echo "Abrindo em janela. Setas navegam, ENTER seleciona, ESC volta."
        echo "Para sair: Ctrl+Shift+Q (ou feche a janela)."
        echo
        python3 ./jukebox
        ;;
    fumaca)
        # Sobe sem tela, simula navegação e conferre o ciclo de crédito.
        SDL_VIDEODRIVER=dummy python3 - <<'PY'
import os, sys, time, threading, runpy
os.environ["JUKEBOX_CONFIG"] = "config.dev.json"
import pygame
sys.path.insert(0, ".")
from creditos import GerenciadorCreditos

g = GerenciadorCreditos("./.dev/contador.txt", "./.dev/contador.lock",
                        "./.dev/creditos.jsonl")
g.adicionar(3, "fumaca")
print(">>> saldo inicial:", g.ler())

def tecla(k):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0))

def roteiro():
    time.sleep(1.5)
    for descricao, k in [("navegar", pygame.K_DOWN),
                         ("entrar no genero", pygame.K_RETURN),
                         ("entrar no artista", pygame.K_RETURN),
                         ("tocar", pygame.K_RETURN)]:
        print(">>>", descricao); tecla(k); time.sleep(0.6)
    time.sleep(1.5)
    print(">>> saldo apos tocar:", g.ler())
    tecla(pygame.K_ESCAPE); time.sleep(0.5)
    pygame.event.post(pygame.event.Event(pygame.QUIT))

threading.Thread(target=roteiro, daemon=True).start()
runpy.run_path("jukebox", run_name="__main__")
print(">>> saldo final:", g.ler())
PY
        echo
        echo "=== auditoria ==="
        tail -6 .dev/creditos.jsonl
        ;;
    log)
        tail -f .dev/jukebox.log
        ;;
    catalogo)
        python3 catalogo.py reindexar
        python3 catalogo.py resumo
        ;;
    limpar)
        rm -rf .dev
        echo "estado de teste apagado"
        ;;
    *)
        grep '^#   ' "$0" | sed 's/^#   //'
        ;;
esac
