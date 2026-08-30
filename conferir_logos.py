#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lista quais generos e artistas ainda estao sem logo."""
import io, json, os

EXT = (".png", ".jpg", ".jpeg", ".webp")
cfg = json.load(io.open("config.json", encoding="utf-8"))
RAIZ = cfg["caminhos"]["musicas"]
if not os.path.isdir(RAIZ):
    RAIZ = "./músicas"


def tem_logo(pasta):
    for e in EXT:
        if os.path.exists(os.path.join(pasta, "logo" + e)):
            return True
    return False


def subpastas(p):
    try:
        return sorted(d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d)))
    except OSError:
        return []


generos = subpastas(RAIZ)
com, sem, vazios = [], [], []

for g in generos:
    caminho = os.path.join(RAIZ, g)
    artistas = subpastas(caminho)
    if not artistas:
        vazios.append(g)
        continue
    (com if tem_logo(caminho) else sem).append(g)

print("=" * 58)
print("GENEROS COM LOGO (%d)" % len(com))
for g in com:
    print("   ok  %s" % g)

print()
print("GENEROS SEM LOGO (%d)  <- faltam estas" % len(sem))
for g in sem:
    print("   --  %s/logo.png" % os.path.join(RAIZ, g))

if vazios:
    print()
    print("PASTAS VAZIAS (%d) - nao aparecem na tela, nao precisam de logo" % len(vazios))
    for g in vazios:
        print("       %s" % g)

# artistas
falta_art = []
for g in com + sem:
    for a in subpastas(os.path.join(RAIZ, g)):
        p = os.path.join(RAIZ, g, a)
        if not tem_logo(p):
            falta_art.append(os.path.join(p, "logo.png"))

print()
print("=" * 58)
print("ARTISTAS SEM LOGO: %d (opcional)" % len(falta_art))
for p in falta_art[:15]:
    print("   --  %s" % p)
if len(falta_art) > 15:
    print("   ... e mais %d" % (len(falta_art) - 15))
print()
print("Total a desenhar: %d logo(s) de genero" % len(sem))
