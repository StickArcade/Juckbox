#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carrossel horizontal do jukebox.

Conceito: cartao central grande e nitido, vizinhos menores e esmaecidos,
setas nas bordas -- igual ao painel de downloads.

DECISOES QUE IMPORTAM PARA UMA MAQUINA LIGADA 16h/DIA
-----------------------------------------------------
1. O cartao completo (fundo + logo + textos) e montado UMA VEZ por item e
   guardado em cache no tamanho maximo. Redimensionar e barato perto de
   recompor tudo a cada quadro.
2. Esse redimensionamento so acontece enquanto o carrossel esta em movimento.
   Parado, o loop principal nem redesenha -- entao o custo e zero na maior
   parte do tempo, que e como a maquina fica na pratica.
3. Sem logo, o cartao gera um fundo colorido com a inicial. A cor sai do
   proprio nome, entao cada genero fica sempre com a mesma cor, sem precisar
   cadastrar nada.

ONDE COLOCAR AS LOGOS (a primeira que existir vence):
    musicas/<GENERO>/logo.png            <- recomendado: junto do conteudo
    assets/logos/<GENERO>.png
Mesma logica para artista, dentro da pasta do artista.
Formatos aceitos: .png .jpg .jpeg .webp
"""

import math
import os
import zlib

import pygame

EXTENSOES_LOGO = (".png", ".jpg", ".jpeg", ".webp")

# Paleta usada quando o item nao tem logo. Tons que combinam com fundo escuro.
# Doze matizes bem espalhados pelo circulo de cores. A paleta antiga tinha
# dois rosas e dois laranjas quase iguais, e cartoes vizinhos acabavam
# saindo da mesma cor.
PALETA = [
    (124, 58, 237),   # roxo
    (236, 72, 153),   # rosa
    (37, 99, 235),    # azul
    (16, 185, 129),   # verde
    (234, 88, 12),    # laranja
    (6, 182, 212),    # ciano
    (220, 38, 38),    # vermelho
    (79, 70, 229),    # indigo
    (132, 204, 22),   # lima
    (245, 158, 11),   # ambar
    (13, 148, 136),   # teal
    (192, 38, 211),   # fucsia
]


class Carrossel:
    def __init__(self, tela, px, fonte, ui, logger=None):
        """px e fonte vem do script principal para o carrossel herdar a mesma
        escala e o mesmo cache de fontes -- nada de criar fonte por conta."""
        self.tela = tela
        self.px = px
        self.fonte = fonte
        self.ui = ui
        self.log = logger
        self._cache = {}          # chave -> superficie do cartao pronto
        self._cache_escala = {}   # (chave, escala) -> superficie redimensionada
        self.MAX_ESCALAS = int(ui.get("max_cache_escalas", 260))
        self.rapido = bool(ui.get("escala_rapida", False))

        # Area da imagem QUADRADA (1:1). A logo do projeto e quadrada, entao
        # 1:1 encaixa sem cortar nada. Para mudar a proporcao depois, mexa
        # so em ALTURA_IMAGEM e some o mesmo tanto em ALTURA_CARTAO.
        self.LARGURA_CARTAO = px(420)
        self.ALTURA_IMAGEM = px(420)
        self.ALTURA_CARTAO = self.ALTURA_IMAGEM + px(170)   # 170 = etiqueta + titulo
        self.ESPACAMENTO = px(480)

    # ------------------------------------------------------------------
    # Localizacao e carga das logos
    # ------------------------------------------------------------------
    @staticmethod
    def procurar_logo(pastas):
        """Recebe uma lista de pastas/prefixos e devolve o primeiro arquivo de
        logo que existir."""
        for base in pastas:
            for ext in EXTENSOES_LOGO:
                caminho = base + ext
                if os.path.exists(caminho):
                    return caminho
        return None

    def _carregar_logo(self, caminho, largura, altura):
        """Carrega e recorta a logo para preencher a area sem deformar."""
        try:
            imagem = pygame.image.load(caminho).convert_alpha()
        except pygame.error as erro:
            if self.log:
                self.log.warning("logo invalida %s: %s", caminho, erro)
            return None
        lo, ao = imagem.get_size()
        if not lo or not ao:
            return None
        fator = max(largura / lo, altura / ao)
        imagem = pygame.transform.smoothscale(
            imagem, (max(1, int(lo * fator)), max(1, int(ao * fator))))
        area = pygame.Surface((largura, altura), pygame.SRCALPHA)
        area.blit(imagem, imagem.get_rect(center=(largura // 2, altura // 2)))
        return area

    def _placeholder(self, nome, largura, altura):
        """Sem logo: bloco colorido com a inicial. A cor vem do nome, entao e
        estavel entre reinicios."""
        area = pygame.Surface((largura, altura), pygame.SRCALPHA)
        # crc32 em vez da soma dos bytes: a soma dava cores quase iguais para
        # nomes parecidos (ROCK CLASSICO x ROCK NACIONAL), que sao exatamente
        # os que ficam lado a lado na lista ordenada.
        cor = PALETA[zlib.crc32(nome.encode("utf-8")) % len(PALETA)]
        area.fill(cor)
        # leve degrade para nao ficar chapado
        sombra = pygame.Surface((largura, altura), pygame.SRCALPHA)
        for i in range(altura):
            a = int(90 * i / max(1, altura))
            pygame.draw.line(sombra, (0, 0, 0, a), (0, i), (largura, i))
        area.blit(sombra, (0, 0))
        f = self.fonte(int(altura * 0.5))
        inicial = f.render(nome[:1].upper(), True, (255, 255, 255))
        area.blit(inicial, inicial.get_rect(center=(largura // 2, altura // 2)))
        return area

    # ------------------------------------------------------------------
    # Montagem do cartao
    # ------------------------------------------------------------------
    def montar_cartao(self, chave, titulo, subtitulo, caminho_logo):
        if chave in self._cache:
            return self._cache[chave]

        px = self.px
        L, A = self.LARGURA_CARTAO, self.ALTURA_CARTAO
        cartao = pygame.Surface((L, A), pygame.SRCALPHA)

        raio = px(24)
        pygame.draw.rect(cartao, (18, 18, 24, 235), (0, 0, L, A), border_radius=raio)

        # area da imagem, com o topo arredondado acompanhando o cartao
        imagem = None
        if caminho_logo:
            imagem = self._carregar_logo(caminho_logo, L, self.ALTURA_IMAGEM)
        if imagem is None:
            imagem = self._placeholder(titulo, L, self.ALTURA_IMAGEM)
        mascara = pygame.Surface((L, self.ALTURA_IMAGEM), pygame.SRCALPHA)
        pygame.draw.rect(mascara, (255, 255, 255, 255),
                         (0, 0, L, self.ALTURA_IMAGEM), border_radius=raio)
        pygame.draw.rect(mascara, (255, 255, 255, 255),
                         (0, self.ALTURA_IMAGEM - raio, L, raio))
        imagem.blit(mascara, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        cartao.blit(imagem, (0, 0))

        y = self.ALTURA_IMAGEM + px(28)

        # etiqueta (ex: "12 ARTISTAS")
        if subtitulo:
            f = self.fonte(px(26))
            texto = f.render(subtitulo.upper(), True, (196, 181, 253))
            pad = px(16)
            larg = texto.get_width() + pad * 2
            alt = texto.get_height() + px(10)
            etiqueta = pygame.Surface((larg, alt), pygame.SRCALPHA)
            pygame.draw.rect(etiqueta, (76, 29, 149, 170), (0, 0, larg, alt),
                             border_radius=alt // 2)
            etiqueta.blit(texto, (pad, px(5)))
            cartao.blit(etiqueta, ((L - larg) // 2, y))
            y += alt + px(18)

        # titulo, quebrando em duas linhas se nao couber
        f = self.fonte(px(40))
        for linha in self._quebrar(titulo, f, L - px(40))[:2]:
            render = f.render(linha, True, (255, 255, 255))
            cartao.blit(render, ((L - render.get_width()) // 2, y))
            y += render.get_height() + px(4)

        self._cache[chave] = cartao
        return cartao

    @staticmethod
    def _quebrar(texto, fonte, largura_max):
        palavras, linhas, atual = texto.split(), [], ""
        for p in palavras:
            teste = (atual + " " + p).strip()
            if fonte.size(teste)[0] <= largura_max or not atual:
                atual = teste
            else:
                linhas.append(atual)
                atual = p
        if atual:
            linhas.append(atual)
        return linhas or [texto]

    # ------------------------------------------------------------------
    # Desenho
    # ------------------------------------------------------------------
    def _escalado(self, chave, cartao, escala):
        """Cache por (item, escala arredondada): durante a animacao varios
        cartoes passam pelas mesmas escalas e a conta nao se repete."""
        # Tres decisoes pensadas em maquina fraca:
        # 1. Degraus de 0,05 e nao 0,01. Com 0,01 eram 61 variantes por item --
        #    1159 combinacoes com 19 generos, muito acima do limite do cache.
        #    Com 0,05 sao 13, e tudo cabe sem nunca precisar limpar.
        # 2. Quando enche, descarta a MAIS ANTIGA em vez de apagar tudo. O
        #    .clear() jogava fora 400 superficies de uma vez e obrigava a
        #    recompor todas -- travadinha periodica sem explicacao.
        # 3. escala_rapida troca smoothscale por scale: menos suave, bem
        #    mais barato.
        passo = round(escala * 20) / 20.0
        ck = (chave, passo)
        if ck not in self._cache_escala:
            while len(self._cache_escala) >= self.MAX_ESCALAS:
                self._cache_escala.pop(next(iter(self._cache_escala)))
            L = max(1, int(cartao.get_width() * passo))
            A = max(1, int(cartao.get_height() * passo))
            metodo = (pygame.transform.scale if self.rapido
                      else pygame.transform.smoothscale)
            self._cache_escala[ck] = metodo(cartao, (L, A))
        return self._cache_escala[ck]

    def _pulso_creditos(self):
        """Fase unica do respiro do cartao em foco com credito na maquina --
        halo e cartao usam a MESMA conta pra pulsar juntos, sincronizados."""
        return 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 420.0)

    def _halo_neon(self, halo, px, pulso):
        """Contorno neon pulsando -- so entra em cena com credito na
        maquina, pra puxar o olho do cliente pro cartao que ele vai
        escolher. A COR precisa ser bem diferente do lilas parado --
        [FIX] a primeira versao era roxo saturado (mesma familia do lilas),
        depois magenta -- agora verde neon, a pedido."""
        alpha_base = 195 + int(60 * pulso)
        cor = (60, 255, 110)
        # camada externa, mais larga e mais fraca: da o "brilho" do neon
        pygame.draw.rect(halo, cor + (int(alpha_base * 0.45),),
                         halo.get_rect(), width=max(4, px(12)),
                         border_radius=px(28))
        pygame.draw.rect(halo, cor + (alpha_base,),
                         halo.get_rect(), width=max(2, px(5)),
                         border_radius=px(28))

    def desenhar(self, itens, posicao, montar, centro_y=None, mostrar_setas=True,
                com_creditos=False):
        """itens: lista de nomes. posicao: indice em float (permite animacao).
        montar: funcao(indice) -> (chave, titulo, subtitulo, caminho_logo).
        com_creditos: True enquanto o cliente tiver saldo -- troca o
        contorno lilas parado do cartao em foco por um neon pulsando."""
        if not itens:
            return
        px = self.px
        LARG, ALT = self.tela.get_size()
        cx = LARG // 2
        cy = centro_y if centro_y is not None else ALT // 2

        base = int(round(posicao))
        # de fora para dentro, para o cartao central ficar por cima
        ordem = sorted(range(base - 3, base + 4),
                       key=lambda k: -abs(k - posicao))
        for k in ordem:
            distancia = k - posicao
            if abs(distancia) > 3.2:
                continue
            indice = k % len(itens)
            chave, titulo, subtitulo, logo = montar(indice)
            cartao = self.montar_cartao(chave, titulo, subtitulo, logo)

            proximidade = min(abs(distancia), 3.0)
            escala = 1.0 - proximidade * 0.20
            alpha = int(255 - proximidade * 78)
            if alpha <= 8:
                continue

            desenho = self._escalado(chave, cartao, escala)
            em_foco_com_credito = proximidade < 0.35 and com_creditos
            if em_foco_com_credito:
                # o cartao respira (5%, bem sutil pra nao "saltar" em cima
                # dos vizinhos) ANTES do halo ser montado, pra folga entre
                # os dois ficar sempre igual -- senao no pico do pulso o
                # cartao cresce mais que a margem do halo antigo e aperta.
                pulso = self._pulso_creditos()
                fator = 1.0 + 0.05 * pulso
                desenho = pygame.transform.smoothscale(
                    desenho, (max(1, int(desenho.get_width() * fator)),
                             max(1, int(desenho.get_height() * fator))))
            if proximidade < 0.35:
                # halo no cartao em foco: e o que diz ao cliente onde ele esta
                halo = pygame.Surface(
                    (desenho.get_width() + px(16), desenho.get_height() + px(16)),
                    pygame.SRCALPHA)
                if em_foco_com_credito:
                    self._halo_neon(halo, px, pulso)
                else:
                    pygame.draw.rect(halo, (167, 139, 250, 150),
                                     halo.get_rect(), width=max(2, px(4)),
                                     border_radius=px(28))
                self.tela.blit(halo, halo.get_rect(
                    center=(int(cx + distancia * self.ESPACAMENTO), cy)))
            if alpha < 255:
                desenho = desenho.copy()
                desenho.fill((255, 255, 255, alpha),
                             special_flags=pygame.BLEND_RGBA_MULT)
            x = cx + distancia * self.ESPACAMENTO
            self.tela.blit(desenho, desenho.get_rect(center=(int(x), cy)))

        if mostrar_setas:
            self._seta(px(90), cy, -1)
            self._seta(LARG - px(90), cy, 1)

    def _seta(self, x, y, sentido):
        raio = self.px(38)
        circulo = pygame.Surface((raio * 2, raio * 2), pygame.SRCALPHA)
        pygame.draw.circle(circulo, (30, 27, 46, 200), (raio, raio), raio)
        pygame.draw.circle(circulo, (150, 120, 240, 220), (raio, raio), raio,
                           max(1, self.px(3)))
        d = raio // 3
        # sentido -1 desenha "<" (voltar) e +1 desenha ">" (avancar)
        pontos = [(raio - sentido * d // 2, raio - d),
                  (raio + sentido * d // 2, raio),
                  (raio - sentido * d // 2, raio + d)]
        pygame.draw.lines(circulo, (235, 230, 255), False, pontos,
                          max(2, self.px(5)))
        self.tela.blit(circulo, circulo.get_rect(center=(int(x), int(y))))
