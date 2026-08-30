#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciamento de creditos do jukebox.

Por que este arquivo existe:
  A versao anterior fazia  open(...,"w").write(str(n))  direto no contador.
  Isso tem tres problemas graves numa maquina que fica ligada o dia todo:

  1. NAO E ATOMICO. Se a energia cair entre o truncate e o write, o arquivo
     fica vazio ou pela metade -> o cliente perde credito que pagou.
  2. NAO TEM LOCK. Se o script do moedeiro escrever ao mesmo tempo que o
     jukebox debita, uma das duas operacoes some (lost update).
  3. NAO TEM RASTRO. Cliente reclama que colocou 5 reais e so tocou 2 musicas
     e nao ha como verificar. Dono do ponto desconfia do acerto e nao ha como
     provar. Log de auditoria nao e luxo, e o que sustenta a operacao.

Uso pelo script do moedeiro (IMPORTANTE):
    python3 creditos.py adicionar 1 --origem moedeiro
  Nunca escreva no contador.txt direto. Sempre por aqui.
"""

import argparse
import fcntl
import json
import os
import sys
import time
from datetime import datetime


class GerenciadorCreditos:
    def __init__(self, caminho_contador, caminho_lock, caminho_auditoria,
                 max_bytes_auditoria=1_000_000, logger=None,
                 caminho_total=None):
        self.contador = caminho_contador
        self.lock = caminho_lock
        self.auditoria = caminho_auditoria
        self.max_bytes_auditoria = max_bytes_auditoria
        # Totalizador: contador de vida inteira, que SO SOBE. Nem consumo, nem
        # estorno, nem zeramento mexem nele. E a referencia para o acerto.
        self.total_arq = caminho_total or (
            os.path.join(os.path.dirname(caminho_contador), "total.txt"))
        self.log = logger
        for caminho in (self.contador, self.lock, self.auditoria):
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
        if not os.path.exists(self.contador):
            self._escrever_atomico(0)
        if not os.path.exists(self.total_arq):
            self._escrever_atomico(0, self.total_arq)

    # ------------------------------------------------------------------
    # Infra
    # ------------------------------------------------------------------
    def _escrever_atomico(self, valor, destino=None):
        """Grava via arquivo temporario + rename. O rename e atomico no Linux:
        ou o arquivo antigo esta la inteiro, ou o novo esta la inteiro.
        Nunca um estado pela metade, mesmo com queda de energia."""
        destino = destino or self.contador
        temporario = destino + ".tmp"
        with open(temporario, "w") as f:
            f.write(str(int(valor)))
            f.flush()
            os.fsync(f.fileno())          # forca gravacao no cartao/SSD
        os.replace(temporario, destino)
        # fsync do diretorio garante que o proprio rename foi persistido
        fd = os.open(os.path.dirname(destino) or ".", os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _ler_total(self):
        try:
            with open(self.total_arq, "r") as f:
                return max(0, int(f.read().strip() or 0))
        except (ValueError, OSError):
            return 0

    def total(self):
        """Total de creditos ja inseridos na vida da maquina."""
        with self._Trava(self.lock):
            return self._ler_total()

    def _ler_bruto(self):
        try:
            with open(self.contador, "r") as f:
                return max(0, int(f.read().strip() or 0))
        except (ValueError, OSError):
            # Arquivo corrompido: registra e assume zero em vez de derrubar o app
            self._registrar("contador_corrompido", 0, None, None,
                            "arquivo ilegivel, assumido 0")
            return 0

    def _registrar(self, evento, delta, antes, depois, detalhe=""):
        """Append-only em JSONL. Uma linha por evento, facil de somar depois."""
        try:
            if (os.path.exists(self.auditoria)
                    and os.path.getsize(self.auditoria) > self.max_bytes_auditoria):
                os.replace(self.auditoria, self.auditoria + ".1")
            linha = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "evento": evento,
                "delta": delta,
                "antes": antes,
                "depois": depois,
                "detalhe": detalhe,
            }
            with open(self.auditoria, "a") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as erro:
            if self.log:
                self.log.error("falha ao registrar auditoria: %s", erro)

    class _Trava:
        """Lock de arquivo entre processos. Segura o moedeiro e o jukebox."""
        def __init__(self, caminho):
            self.caminho = caminho
            self.fd = None

        def __enter__(self):
            self.fd = open(self.caminho, "w")
            fcntl.flock(self.fd, fcntl.LOCK_EX)
            return self

        def __exit__(self, *_):
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def ler(self):
        with self._Trava(self.lock):
            return self._ler_bruto()

    def adicionar(self, quantidade, origem="moedeiro"):
        quantidade = int(quantidade)
        if quantidade <= 0:
            return self.ler()
        with self._Trava(self.lock):
            antes = self._ler_bruto()
            depois = antes + quantidade
            self._escrever_atomico(depois)
            # o totalizador acompanha TODA entrada de credito
            self._escrever_atomico(self._ler_total() + quantidade,
                                   self.total_arq)
            self._registrar("credito_inserido", +quantidade, antes, depois, origem)
        if self.log:
            self.log.info("credito +%d (%s) saldo=%d", quantidade, origem, depois)
        return depois

    def consumir(self, quantidade=1, motivo=""):
        """Debita apenas se houver saldo. Retorna True se debitou.
        Ler e debitar acontecem dentro do MESMO lock -- e isso que evita
        tocar musica de graca quando duas coisas mexem no contador juntas."""
        quantidade = int(quantidade)
        with self._Trava(self.lock):
            antes = self._ler_bruto()
            if antes < quantidade:
                self._registrar("credito_insuficiente", 0, antes, antes, motivo)
                return False
            depois = antes - quantidade
            self._escrever_atomico(depois)
            self._registrar("credito_consumido", -quantidade, antes, depois, motivo)
        if self.log:
            self.log.info("credito -%d (%s) saldo=%d", quantidade, motivo, depois)
        return True

    def devolver(self, quantidade=1, motivo="falha na reproducao"):
        """Estorno. Se a musica foi debitada mas nao tocou (arquivo corrompido,
        mpv morreu, disco sumiu), o credito volta. Sem isso o cliente paga e
        nao ouve nada -- que e exatamente como se perde um ponto."""
        quantidade = int(quantidade)
        with self._Trava(self.lock):
            antes = self._ler_bruto()
            depois = antes + quantidade
            self._escrever_atomico(depois)
            self._registrar("credito_estornado", +quantidade, antes, depois, motivo)
        if self.log:
            self.log.warning("estorno +%d (%s) saldo=%d", quantidade, motivo, depois)
        return depois

    def zerar(self, motivo="zerado em teste", zerar_total=False):
        """Zera o saldo registrando um evento PROPRIO. Nao usa consumir() de
        proposito: se entrasse como consumo, o saldo zerado em teste viraria
        musica vendida no relatorio de acerto com o dono do ponto.

        zerar_total tambem apaga o totalizador. So passe True de proposito:
        num ponto em operacao o total e a referencia do acerto e nao deve
        voltar. Serve para preparar a maquina antes de instalar."""
        with self._Trava(self.lock):
            antes = self._ler_bruto()
            total_antes = self._ler_total()
            if antes:
                self._escrever_atomico(0)
                self._registrar("credito_zerado", -antes, antes, 0, motivo)
            if zerar_total and total_antes:
                self._escrever_atomico(0, self.total_arq)
                self._registrar("total_zerado", -total_antes, total_antes, 0,
                                motivo)
        if self.log and (antes or (zerar_total and total_antes)):
            self.log.info("zerado (%s): saldo -%d, total -%d", motivo, antes,
                          total_antes if zerar_total else 0)
        return 0

    def resumo_do_dia(self, dia=None):
        """Soma a auditoria do dia. Base do futuro relatorio de acerto."""
        dia = dia or datetime.now().strftime("%Y-%m-%d")
        inseridos = consumidos = estornados = zerados = 0
        por_origem = {}
        for arquivo in (self.auditoria, self.auditoria + ".1"):
            if not os.path.exists(arquivo):
                continue
            with open(arquivo, "r") as f:
                for linha in f:
                    try:
                        registro = json.loads(linha)
                    except ValueError:
                        continue
                    if not registro.get("ts", "").startswith(dia):
                        continue
                    if registro["evento"] == "credito_inserido":
                        inseridos += registro["delta"]
                        # separado por origem: com moedeiro, noteiro e pix
                        # juntos, o acerto precisa saber de onde veio cada um
                        origem = registro.get("detalhe") or "?"
                        por_origem[origem] = por_origem.get(origem, 0) + registro["delta"]
                    elif registro["evento"] == "credito_consumido":
                        consumidos += -registro["delta"]
                    elif registro["evento"] == "credito_estornado":
                        estornados += registro["delta"]
                    elif registro["evento"] == "credito_zerado":
                        zerados += -registro["delta"]
        return {"dia": dia, "inseridos": inseridos,
                "consumidos": consumidos, "estornados": estornados,
                "zerados": zerados, "saldo_atual": self.ler(),
                "total_acumulado": self.total(), "por_origem": por_origem}


    def exportar_csv(self, destino):
        """Despeja a auditoria inteira num CSV com ponto e virgula, que e o
        que o Excel em portugues abre sem reclamar. Devolve quantas linhas."""
        import csv
        linhas = 0
        with open(destino, "w", newline="", encoding="utf-8-sig") as saida:
            escritor = csv.writer(saida, delimiter=";")
            escritor.writerow(["data_hora", "evento", "delta", "antes",
                               "depois", "detalhe"])
            # o .1 e o arquivo rotacionado: vem primeiro por ser mais antigo
            for arquivo in (self.auditoria + ".1", self.auditoria):
                if not os.path.exists(arquivo):
                    continue
                with open(arquivo, encoding="utf-8") as entrada:
                    for linha in entrada:
                        try:
                            r = json.loads(linha)
                        except ValueError:
                            continue
                        escritor.writerow([
                            r.get("ts", ""), r.get("evento", ""),
                            r.get("delta", ""), r.get("antes", ""),
                            r.get("depois", ""), r.get("detalhe", "")])
                        linhas += 1
        if self.log:
            self.log.info("auditoria exportada: %s (%d linhas)", destino, linhas)
        return linhas


def _carregar_config(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    # Respeita JUKEBOX_CONFIG para a CLI usar a mesma config do app
    # (senao o "creditos.py adicionar" mexia no contador de producao enquanto
    # o jukebox de teste lia outro arquivo).
    padrao = os.environ.get(
        "JUKEBOX_CONFIG",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap = argparse.ArgumentParser(description="Creditos do jukebox")
    ap.add_argument("--config", default=padrao)
    sub = ap.add_subparsers(dest="acao", required=True)

    p = sub.add_parser("adicionar"); p.add_argument("quantidade", type=int)
    p.add_argument("--origem", default="manual")
    p = sub.add_parser("consumir"); p.add_argument("quantidade", type=int, nargs="?", default=1)
    p.add_argument("--motivo", default="manual")
    p = sub.add_parser("devolver"); p.add_argument("quantidade", type=int, nargs="?", default=1)
    sub.add_parser("ler")
    p = sub.add_parser("zerar")
    p.add_argument("--tudo", action="store_true",
                   help="zera tambem o totalizador")
    sub.add_parser("total")
    p = sub.add_parser("resumo"); p.add_argument("--dia", default=None)

    args = ap.parse_args()
    cfg = _carregar_config(args.config)["caminhos"]
    g = GerenciadorCreditos(cfg["contador"], cfg["lock"], cfg["auditoria"],
                            caminho_total=cfg.get("total"))

    if args.acao == "adicionar":
        print(g.adicionar(args.quantidade, args.origem))
    elif args.acao == "consumir":
        print("ok" if g.consumir(args.quantidade, args.motivo) else "sem saldo")
    elif args.acao == "devolver":
        print(g.devolver(args.quantidade))
    elif args.acao == "zerar":
        print(g.zerar("cli", zerar_total=args.tudo))
    elif args.acao == "total":
        print(g.total())
    elif args.acao == "ler":
        print(g.ler())
    elif args.acao == "resumo":
        print(json.dumps(g.resumo_do_dia(args.dia), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
