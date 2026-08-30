#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera um fundo escuro em degrade para o jukebox.

Por que gerar em vez de baixar uma imagem: o fundo precisa ser ESCURO e de
baixo contraste. Ele nao e a estrela da tela -- os cartoes sao. Fundo claro
ou muito detalhado faz os cartoes sumirem, que e exatamente o que acontece
com a folha de partitura bege.

Uso:
    python3 gerar_fundo.py                 # 3840x2160 (recomendado)
    python3 gerar_fundo.py 1920 1080       # outra resolucao
    python3 gerar_fundo.py 1080 1920       # TV em pe

Truque: o degrade e desenhado numa imagem minuscula e depois ampliado com
interpolacao bicubica. Sai perfeitamente suave e leva menos de um segundo,
em vez de calcular milhoes de pixels um a um.
"""

import math
import os
import sys

from PIL import Image, ImageFilter

SAIDA = os.path.join("assets", "background.png")

# Tons da paleta roxa, do centro para as bordas.
CENTRO = (46, 26, 74)      # roxo do brilho central
MEIO = (24, 16, 40)        # roxo profundo
BORDA = (8, 6, 14)         # quase preto nos cantos


def misturar(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gerar(largura, altura):
    # 1) degrade radial numa imagem pequena
    pl, pa = 96, 54
    pequena = Image.new("RGB", (pl, pa))
    pixels = pequena.load()
    # brilho um pouco acima do centro: deixa a parte de baixo mais calma,
    # que e onde ficam os titulos dos cartoes
    fx, fy = pl / 2.0, pa * 0.42
    maior = math.hypot(max(fx, pl - fx), max(fy, pa - fy))
    for y in range(pa):
        for x in range(pl):
            d = math.hypot(x - fx, y - fy) / maior
            if d < 0.55:
                cor = misturar(CENTRO, MEIO, d / 0.55)
            else:
                cor = misturar(MEIO, BORDA, (d - 0.55) / 0.45)
            pixels[x, y] = cor

    fundo = pequena.resize((largura, altura), Image.BICUBIC)

    # 2) vinheta extra nos cantos, para o conteudo central respirar
    mascara = Image.new("L", (pl, pa))
    mp = mascara.load()
    for y in range(pa):
        for x in range(pl):
            d = math.hypot((x - pl / 2.0) / (pl / 2.0),
                           (y - pa / 2.0) / (pa / 2.0))
            mp[x, y] = int(max(0, min(255, (d - 0.55) * 300)))
    mascara = mascara.resize((largura, altura), Image.BICUBIC)
    fundo = Image.composite(Image.new("RGB", (largura, altura), (4, 3, 8)),
                            fundo, mascara)

    # 3) leve suavizacao para eliminar qualquer banda do degrade
    return fundo.filter(ImageFilter.GaussianBlur(radius=max(1, largura // 900)))


def main():
    largura = int(sys.argv[1]) if len(sys.argv) > 2 else 3840
    altura = int(sys.argv[2]) if len(sys.argv) > 2 else 2160

    os.makedirs("assets", exist_ok=True)
    if os.path.exists(SAIDA):
        reserva = SAIDA.replace(".png", "-anterior.png")
        os.replace(SAIDA, reserva)
        print("fundo anterior guardado em", reserva)

    gerar(largura, altura).save(SAIDA)
    print("gerado: %s (%dx%d)" % (SAIDA, largura, altura))
    print()
    print("Com fundo escuro, o escurecimento por cima vira excesso.")
    print('Em config.json e config.dev.json, baixe "alpha_overlay" de 140 para 40.')


if __name__ == "__main__":
    main()
