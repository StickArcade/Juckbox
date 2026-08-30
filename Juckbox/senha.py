#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Senha do operador (PIN numerico).

POR QUE NAO GUARDAR EM TEXTO
----------------------------
O F1 abre o gerenciador de arquivos e o config.json fica ali, legivel. Senha
em texto seria enfeite. Aqui vai o resumo criptografico com sal: mesmo com o
arquivo na mao, nao da para ler o PIN de volta.

Nao e cofre -- quem tiver acesso ao arquivo pode APAGAR a senha e entrar. A
protecao real e contra o cliente curioso no bar, nao contra voce mesmo.

USO
    python3 senha.py definir 1234
    python3 senha.py conferir 1234
    python3 senha.py remover
    python3 senha.py estado
"""

import argparse
import collections
import hashlib
import hmac
import io
import json
import os
import secrets
import sys

ITERACOES = 120_000        # custo proposital: torna tentativa e erro lenta


def _resumo(pin, sal):
    return hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"),
                               bytes.fromhex(sal), ITERACOES).hex()


def gerar(pin):
    """Devolve (sal, resumo) para guardar no config."""
    sal = secrets.token_hex(16)
    return sal, _resumo(pin, sal)


def conferir(pin, sal, resumo):
    """Comparacao em tempo constante, para nao vazar o PIN pelo tempo de
    resposta."""
    if not sal or not resumo:
        return False
    try:
        return hmac.compare_digest(_resumo(pin, sal), resumo)
    except (ValueError, TypeError):
        return False


def definida(cfg):
    op = cfg.get("operacao", {})
    return bool(op.get("senha_sal") and op.get("senha_resumo"))


# ----------------------------------------------------------------------
def _carregar(caminho):
    return json.load(io.open(caminho, encoding="utf-8"),
                     object_pairs_hook=collections.OrderedDict)


def _gravar(caminho, cfg):
    """Atomico, igual ao resto do projeto: temporario + fsync + rename."""
    temporario = caminho + ".tmp"
    with io.open(temporario, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporario, caminho)


def main():
    padrao = os.environ.get(
        "JUKEBOX_CONFIG",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap = argparse.ArgumentParser(description="Senha do operador")
    ap.add_argument("--config", default=padrao)
    sub = ap.add_subparsers(dest="acao", required=True)
    p = sub.add_parser("definir"); p.add_argument("pin")
    p = sub.add_parser("conferir"); p.add_argument("pin")
    sub.add_parser("remover")
    sub.add_parser("estado")

    args = ap.parse_args()
    cfg = _carregar(args.config)
    op = cfg.setdefault("operacao", collections.OrderedDict())

    if args.acao == "definir":
        if not str(args.pin).isdigit() or not (3 <= len(str(args.pin)) <= 8):
            print("O PIN deve ter de 3 a 8 digitos.")
            return 1
        op["senha_sal"], op["senha_resumo"] = gerar(args.pin)
        _gravar(args.config, cfg)
        print("senha definida (%d digitos)" % len(str(args.pin)))
    elif args.acao == "conferir":
        ok = conferir(args.pin, op.get("senha_sal"), op.get("senha_resumo"))
        print("confere" if ok else "NAO confere")
        return 0 if ok else 1
    elif args.acao == "remover":
        op.pop("senha_sal", None)
        op.pop("senha_resumo", None)
        _gravar(args.config, cfg)
        print("senha removida - o menu volta a abrir sem pedir nada")
    elif args.acao == "estado":
        print("definida" if definida(cfg) else "nao definida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
