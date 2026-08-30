#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Player de audio via mpv.

O QUE MUDOU EM RELACAO A VERSAO ANTERIOR
----------------------------------------
1) BUG DO stop(): antes, ao apertar ESC durante uma playlist, o terminate()
   fazia o process.wait() retornar, a thread chamava on_finish e a proxima
   musica comecava a tocar mesmo o cliente tendo cancelado. Agora existe uma
   flag de parada intencional + um "token" de reproducao: callback so dispara
   se a musica terminou sozinha E ainda e a reproducao vigente.

2) IPC: mpv sobe com --input-ipc-server, entao da pra perguntar posicao e
   duracao, mudar volume e pausar SEM matar o processo. E o que permite ter
   barra de progresso, pausa e controle de volume no modo admin depois.

3) Encerramento em duas etapas: terminate(), espera curta, kill() se preciso.
   Sem isso, um mpv travado vira processo zumbi -- e em 16h de operacao isso
   acontece.
"""

import json
import os
import shutil
import socket
import subprocess
import threading
import time


# Extensoes tratadas como VIDEO. O mpv toca as duas coisas; o que muda e se
# ele abre janela de video ou roda so o audio.
EXTENSOES_VIDEO = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".ts")


def eh_video(caminho):
    return caminho.lower().endswith(EXTENSOES_VIDEO)


_OPCOES_MPV = None


def opcoes_mpv():
    """Le UMA vez as opcoes que ESTE mpv aceita. Builds diferentes aceitam
    coisas diferentes -- o do Batocera vem sem Lua, entao nao tem --no-osc. E
    o mpv nao ignora opcao desconhecida: sai com erro fatal."""
    global _OPCOES_MPV
    if _OPCOES_MPV is not None:
        return _OPCOES_MPV
    nomes = set()
    try:
        r = subprocess.run(["mpv", "--list-options"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=15)
        for linha in r.stdout.decode("utf-8", "ignore").splitlines():
            linha = linha.strip()
            if linha.startswith("--"):
                nomes.add(linha[2:].split()[0].split("=")[0])
    except Exception:
        pass
    _OPCOES_MPV = nomes
    return nomes


def filtrar_opcoes(flags, logger=None):
    """Devolve so as flags que este mpv reconhece."""
    conhecidas = opcoes_mpv()
    if not conhecidas:
        return [f for f in flags if f.split("=")[0] == "--fullscreen"]
    saida, descartadas = [], []
    for f in flags:
        base = f.lstrip("-").split("=")[0]
        if base.startswith("no-"):
            base = base[3:]
        (saida if base in conhecidas else descartadas).append(f)
    if descartadas and logger:
        logger.info("opcoes ignoradas (este mpv nao suporta): %s",
                    " ".join(descartadas))
    return saida


class MusicPlayer:
    # Abaixo deste tempo, uma saida com erro significa que a faixa nem chegou
    # a tocar -- entao vale estorno.
    LIMIAR_FALHA = 3.0

    def __init__(self, socket_mpv="/tmp/jukebox-mpv.sock", driver_saida="pulse",
                 volume=90, logger=None, janela_id=None, hwdec="auto"):
        self.socket_mpv = socket_mpv
        self.driver_saida = driver_saida
        self.volume = volume
        # Id da janela do pygame: com ele o mpv desenha DENTRO dessa janela em
        # vez de abrir a propria. Sem gerenciador de janelas, janela separada
        # rouba o teclado e nao devolve.
        self.janela_id = janela_id
        # Decodificacao por hardware: tira o video das costas da CPU.
        self.hwdec = hwdec
        self.log = logger

        self.processo = None
        self.tocando = False
        self.faixa_atual = None
        self.com_video = False        # a faixa atual esta abrindo janela de video
        self._conf_teclas = self._gravar_conf_teclas()

        self._parada_intencional = False
        self._token = 0                 # identifica a reproducao vigente
        self._trava = threading.Lock()

    # ------------------------------------------------------------------
    @staticmethod
    def _gravar_conf_teclas():
        """Enquanto o video toca, a janela do mpv fica na frente e recebe o
        teclado -- o pygame nao ve mais nada. Sem isto o cliente ficaria preso
        no clipe ate o fim. Aqui so ESC continua valendo, e ele encerra o mpv,
        o que o jukebox trata como fim da faixa e emenda a proxima da fila."""
        caminho = "/tmp/jukebox-mpv-input.conf"
        try:
            with open(caminho, "w") as f:
                f.write("ESC quit\n")
            return caminho
        except OSError:
            return None

    def disponivel(self):
        return shutil.which("mpv") is not None

    # ------------------------------------------------------------------
    def play(self, caminho, on_finish=None, loop=False, on_falha=None,
             audio_extra=None):
        """Toca um arquivo. Retorna True se conseguiu iniciar o processo.
        O retorno importa: quem chama usa isso para estornar o credito."""
        # link ja resolvido nao existe em disco: vem como URL
        eh_url = caminho.startswith("http://") or caminho.startswith("https://")
        if not eh_url and not os.path.exists(caminho):
            if self.log:
                self.log.error("arquivo inexistente: %s", caminho)
            return False
        if not self.disponivel():
            if self.log:
                self.log.error("mpv nao encontrado no sistema")
            return False

        self.stop()  # garante que nada anterior esta rodando

        with self._trava:
            self._token += 1
            token = self._token
            self._parada_intencional = False
            self.tocando = True
            self.faixa_atual = caminho

        if os.path.exists(self.socket_mpv):
            try:
                os.remove(self.socket_mpv)
            except OSError:
                pass

        self.com_video = eh_video(caminho) or bool(audio_extra) or eh_url

        comando = [
            "mpv",
            "--no-terminal",
            "--really-quiet",
            "--audio-display=no",
            "--volume=%d" % self.volume,
            "--input-ipc-server=" + self.socket_mpv,
        ]
        if self.com_video:
            if self.janela_id:
                # embutido: sem janela propria, sem disputa de foco.
                # O teclado continua no pygame, entao o ESC segue funcionando.
                desejadas = ["--wid=%d" % self.janela_id, "--osd-level=0",
                             "--no-input-default-bindings"]
            else:
                desejadas = ["--fullscreen", "--ontop", "--no-osc",
                             "--osd-level=0", "--no-input-default-bindings"]
                if self._conf_teclas:
                    desejadas.append("--input-conf=" + self._conf_teclas)
            if self.hwdec and self.hwdec != "no":
                desejadas.append("--hwdec=" + self.hwdec)
            comando += filtrar_opcoes(desejadas, self.log)

        # O YouTube entrega imagem e som em URLs separadas; sem isto o clipe
        # toca mudo.
        if audio_extra:
            comando.append("--audio-file=" + audio_extra)
        else:
            comando.append("--no-video")

        # "auto" (ou vazio) deixa o mpv escolher. No Batocera use "pulse";
        # num desktop com pipewire/alsa o auto costuma ser mais seguro.
        if self.driver_saida and self.driver_saida != "auto":
            comando.append("--ao=" + self.driver_saida)
        if loop:
            comando.append("--loop")
        comando.append(caminho)

        ambiente = os.environ.copy()
        ambiente["XDG_RUNTIME_DIR"] = "/run/user/%d" % os.getuid()

        try:
            self.processo = subprocess.Popen(
                comando, env=ambiente,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as erro:
            if self.log:
                self.log.error("falha ao iniciar mpv: %s", erro)
            with self._trava:
                self.tocando = False
            return False

        threading.Thread(target=self._monitorar,
                         args=(token, on_finish, on_falha, time.time()),
                         daemon=True).start()
        if self.log:
            rotulo = caminho if eh_url else os.path.basename(caminho)
            self.log.info("tocando%s: %s", " [video]" if self.com_video else "",
                          rotulo[:70])
        return True

    def _monitorar(self, token, on_finish, on_falha=None, inicio=None):
        processo = self.processo
        try:
            codigo = processo.wait()
        except Exception:
            codigo = -1
        duracao = time.time() - inicio if inicio else 999.0

        with self._trava:
            # Se o token mudou, outra musica ja comecou: este callback e velho.
            if token != self._token:
                return
            parada_manual = self._parada_intencional
            self.tocando = False
            self.faixa_atual = None
            self.com_video = False

        if parada_manual:
            if self.log:
                self.log.info("reproducao interrompida pelo usuario")
            return
        # [FIX] Falha logo no comeco = a musica nao tocou. Sem isto o credito
        # ja foi debitado e nada e estornado, porque o processo chegou a
        # INICIAR. No bar isso e o cliente pagando e nao ouvindo.
        if codigo not in (0, None) and duracao < self.LIMIAR_FALHA:
            if self.log:
                self.log.error("mpv falhou em %.1fs (codigo %s) - faixa nao tocou",
                               duracao, codigo)
            if on_falha:
                try:
                    on_falha()
                except Exception as erro:
                    if self.log:
                        self.log.exception("erro no callback de falha: %s", erro)
                return

        if codigo not in (0, None) and self.log:
            self.log.warning("mpv terminou com codigo %s", codigo)
        if on_finish:
            try:
                on_finish()
            except Exception as erro:
                if self.log:
                    self.log.exception("erro no callback de fim: %s", erro)

    # ------------------------------------------------------------------
    def stop(self):
        """Parada intencional: NAO dispara o on_finish."""
        with self._trava:
            if not self.processo:
                self.tocando = False
                return
            self._parada_intencional = True
            self._token += 1
            processo = self.processo

        try:
            processo.terminate()
            try:
                processo.wait(timeout=2)
            except subprocess.TimeoutExpired:
                processo.kill()          # nao deixa zumbi
                processo.wait(timeout=2)
        except Exception:
            pass

        with self._trava:
            self.processo = None
            self.tocando = False
            self.faixa_atual = None
            self.com_video = False

    def esta_tocando(self):
        with self._trava:
            return self.tocando and self.processo and self.processo.poll() is None

    # ------------------------------------------------------------------
    # IPC com o mpv
    # ------------------------------------------------------------------
    def _comando_ipc(self, comando, timeout=0.4):
        if not os.path.exists(self.socket_mpv):
            return None
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(self.socket_mpv)
            s.send((json.dumps({"command": comando}) + "\n").encode("utf-8"))
            resposta = s.recv(4096).decode("utf-8", "ignore")
            s.close()
            for linha in resposta.splitlines():
                try:
                    dados = json.loads(linha)
                except ValueError:
                    continue
                if "data" in dados or dados.get("error") == "success":
                    return dados.get("data")
        except (OSError, socket.timeout):
            return None
        return None

    def posicao(self):
        """(segundos_tocados, duracao_total) ou (None, None)."""
        return (self._comando_ipc(["get_property", "time-pos"]),
                self._comando_ipc(["get_property", "duration"]))

    def definir_volume(self, valor):
        self.volume = max(0, min(130, int(valor)))
        self._comando_ipc(["set_property", "volume", self.volume])
        return self.volume

    def alternar_pausa(self):
        pausado = self._comando_ipc(["get_property", "pause"])
        novo = not bool(pausado)
        self._comando_ipc(["set_property", "pause", novo])
        return novo
