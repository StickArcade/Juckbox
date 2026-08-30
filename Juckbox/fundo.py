#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fundo que muda conforme o genero selecionado.

TRES PROBLEMAS QUE ESTE MODULO RESOLVE
--------------------------------------
1. TRAVAR A INTERFACE. Decodificar um PNG grande leva centenas de
   milissegundos. Se isso acontecesse a cada seta apertada, a navegacao
   engasgaria. Por isso quem chama so troca o fundo QUANDO O CARROSSEL PARA,
   e as ultimas imagens usadas ficam em cache.

2. ESTOURAR A MEMORIA. Cada fundo pronto ocupa a tela inteira em memoria
   (~8 MB em 1080p, ~33 MB em 4K). Guardar 17 generos encheria a RAM da
   placa. O cache guarda poucos e descarta o mais antigo.

3. TROCA BRUSCA. Fundo pulando de um para outro cansa a vista em 16 horas
   de operacao. A troca acontece por transicao suave.

ONDE COLOCAR AS IMAGENS:
    musicas/<GENERO>/background.png     <- fundo proprio do genero
    assets/background.png               <- fundo geral (usado quando falta)

SEM ARQUIVO PROPRIO, o fundo e DERIVADO DA LOGO do genero: a logo e reduzida,
ampliada de volta e escurecida, o que produz um borrao de cor no tom da arte.
Ou seja: colocando so as logos voce ja ganha fundo por genero de graca.
"""

import os
import pygame

EXTENSOES = (".png", ".jpg", ".jpeg", ".webp")


class FundoDinamico:
    def __init__(self, tela, superficie_padrao, alpha_escurecer=40,
                 logger=None, max_cache=5, duracao_fade=420):
        self.tela = tela
        self.tamanho = tela.get_size()
        self.alpha_escurecer = alpha_escurecer
        self.log = logger
        self.max_cache = max_cache
        self.duracao = duracao_fade

        # Miniaturas 40x24 ja escurecidas: 3 KB cada, entao cabem TODAS na
        # memoria. Com elas prontas, trocar de fundo vira so a ampliacao
        # (~20 ms, menos de um quadro) em vez de decodificar o PNG (~105 ms).
        self._miniaturas = {}
        self._cache = {"__padrao__": superficie_padrao}
        self._ordem = ["__padrao__"]
        self.chave_atual = "__padrao__"
        self._atual = superficie_padrao
        self._anterior = None
        self._inicio_fade = 0

    # ------------------------------------------------------------------
    @staticmethod
    def procurar(base):
        """Recebe um prefixo sem extensao e devolve o primeiro arquivo que
        existir."""
        for ext in EXTENSOES:
            if os.path.exists(base + ext):
                return base + ext
        return None

    # ------------------------------------------------------------------
    def _cobrir(self, imagem):
        """Preenche a tela mantendo a proporcao, cortando a sobra."""
        L, A = self.tamanho
        lo, ao = imagem.get_size()
        if not lo or not ao:
            return None
        fator = max(L / lo, A / ao)
        escalada = pygame.transform.smoothscale(
            imagem, (max(1, int(lo * fator)), max(1, int(ao * fator))))
        area = pygame.Surface(self.tamanho)
        area.blit(escalada, escalada.get_rect(center=(L // 2, A // 2)))
        return area

    def _borrar_da_logo(self, imagem, alpha):
        """Reduz a imagem a poucos pixels, ESCURECE AINDA PEQUENA e so entao
        amplia. Escurecer depois de ampliar custava 133 ms (2 milhoes de
        pixels); aqui sao 960 pixels e o custo some. O resultado e identico,
        porque a ampliacao e linear."""
        pequena = pygame.transform.smoothscale(imagem, (40, 24))
        veu = pygame.Surface((40, 24))
        veu.set_alpha(alpha)
        veu.fill((0, 0, 0))
        pequena.blit(veu, (0, 0))
        return pygame.transform.smoothscale(pequena, self.tamanho).convert()

    def _escurecer(self, superficie, alpha):
        """Para arte de verdade, que precisa continuar nitida: multiplicacao
        de canal, que usa caminho otimizado do SDL em vez de alpha por
        superficie."""
        if alpha <= 0:
            return superficie.convert()
        f = max(0, 255 - alpha)
        superficie.fill((f, f, f), special_flags=pygame.BLEND_RGB_MULT)
        return superficie.convert()

    def preparar_miniatura(self, chave, caminho_logo):
        """Decodifica a logo e guarda so a versao minuscula. Feito com a
        maquina ociosa, para que a troca de fundo nunca engasgue a navegacao."""
        if chave in self._miniaturas or not caminho_logo:
            return False
        try:
            imagem = pygame.image.load(caminho_logo).convert()
        except pygame.error as erro:
            if self.log:
                self.log.warning("miniatura de %s falhou: %s", chave, erro)
            self._miniaturas[chave] = None
            return False
        pequena = pygame.transform.smoothscale(imagem, (40, 24))
        veu = pygame.Surface((40, 24))
        veu.set_alpha(min(210, self.alpha_escurecer + 150))
        veu.fill((0, 0, 0))
        pequena.blit(veu, (0, 0))
        self._miniaturas[chave] = pequena
        return True

    def _compor(self, chave, caminho_fundo, caminho_logo):
        if chave in self._cache:
            return self._cache[chave]

        # caminho rapido: miniatura ja pronta e sem arte propria de fundo
        if not caminho_fundo and self._miniaturas.get(chave) is not None:
            pronta = pygame.transform.smoothscale(
                self._miniaturas[chave], self.tamanho).convert()
            self._guardar(chave, pronta)
            return pronta

        pronta = None
        try:
            if caminho_fundo:
                imagem = pygame.image.load(caminho_fundo).convert()
                pronta = self._cobrir(imagem)
                if pronta is not None:
                    pronta = self._escurecer(pronta, self.alpha_escurecer)
            elif caminho_logo:
                imagem = pygame.image.load(caminho_logo).convert()
                # derivado da logo vem mais claro e mais saturado que uma arte
                # feita para ser fundo, entao escurece bem mais
                pronta = self._borrar_da_logo(
                    imagem, min(210, self.alpha_escurecer + 150))
        except pygame.error as erro:
            if self.log:
                self.log.warning("fundo de %s falhou: %s", chave, erro)
            pronta = None

        if pronta is None:
            pronta = self._cache["__padrao__"]
        else:
            self._guardar(chave, pronta)
        return pronta

    def _guardar(self, chave, superficie):
        self._cache[chave] = superficie
        self._ordem.append(chave)
        while len(self._ordem) > self.max_cache:
            velha = self._ordem.pop(0)
            if velha == "__padrao__":          # o padrao nunca sai
                self._ordem.append(velha)
                continue
            self._cache.pop(velha, None)

    # ------------------------------------------------------------------
    def definir(self, chave, caminho_fundo=None, caminho_logo=None):
        """Inicia a troca. Chamar apenas quando a navegacao estiver parada."""
        if chave == self.chave_atual:
            return False
        nova = self._compor(chave, caminho_fundo, caminho_logo)
        if nova is self._atual:
            self.chave_atual = chave
            return False
        self._anterior = self._atual
        self._atual = nova
        self.chave_atual = chave
        self._inicio_fade = pygame.time.get_ticks()
        return True

    def em_transicao(self):
        if self._anterior is None:
            return False
        if pygame.time.get_ticks() - self._inicio_fade >= self.duracao:
            self._anterior = None
            return False
        return True

    def desenhar(self):
        if self._anterior is None:
            self.tela.blit(self._atual, (0, 0))
            return
        decorrido = pygame.time.get_ticks() - self._inicio_fade
        t = decorrido / float(self.duracao)
        if t >= 1.0:
            self._anterior = None
            self.tela.blit(self._atual, (0, 0))
            return
        self.tela.blit(self._anterior, (0, 0))
        entrando = self._atual.copy()
        entrando.set_alpha(int(255 * t))
        self.tela.blit(entrando, (0, 0))
