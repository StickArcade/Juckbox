#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tela de busca do YouTube: teclado virtual e lista de resultados.

POR QUE UM MODULO SEPARADO DO MENU
----------------------------------
O menu e do OPERADOR e vive atras de senha. Esta tela e do CLIENTE, no meio
do bar. Misturar as duas faria a tela do cliente herdar o comportamento do
painel de manutencao, que e o contrario do que se quer.

TUDO FUNCIONA SO COM AS SETAS
-----------------------------
Numa cabine com botoes de arcade nao ha teclado. Entao o teclado virtual e
navegavel em duas dimensoes e ENTER escolhe. Quem tiver teclado de verdade
pode digitar direto -- o metodo digitar() aceita as teclas.
"""

import math

import pygame

LINHAS_TECLADO = [
    list("ABCDEFGHIJ"),
    list("KLMNOPQRST"),
    list("UVWXYZ0123"),
    list("456789 '-"),
    ["ESPACO", "APAGAR", "BUSCAR"],
]


class TelaBusca:
    def __init__(self, tela, px, fonte, ui, logger=None):
        self.tela = tela
        self.px = px
        self.fonte = fonte
        self.ui = ui
        self.log = logger

        self.ativa = False
        self.estado = "teclado"      # teclado | buscando | resultados
        self.termo = ""
        self.linha = 0
        self.coluna = 0
        self.resultados = []
        self.indice = 0
        self.aviso = ""
        self.ao_escolher = None      # callback(item) -- uma so, toca/enfileira
        self.ao_escolher_varios = None  # callback([item,...]) -- direto pra fila
        self.ao_buscar = None        # callback(termo) -- dispara a thread
        self.ao_exportar = None      # callback() -- abre o menu do sistema
        self.modo_playlist = False   # True so no atalho do operador (F12)

        # Musicas marcadas (checkbox). Dois usos, dependendo de modo_playlist:
        #  - modo cliente (padrao): marcar 2, 3, 4 musicas e confirmar manda
        #    todas direto pra fila, pelo credito que houver -- nunca vira
        #    arquivo de playlist.
        #  - modo playlist (F12 -> ACERVO -> BUSCAR PARA PLAYLIST): confirmar
        #    exporta um .m3u, e so o operador chega nesse modo.
        # Fica de PROPOSITO fora do abrir()/fechar(): no modo playlist o
        # operador pode buscar varias vezes ("blink 182", depois "sum 41"...)
        # marcando aos poucos, e so decide a pasta e finaliza quando quiser.
        # Guardado por URL (nao por indice) porque o indice muda a cada
        # busca nova -- a URL e o unico jeito de saber se "e a mesma musica"
        # entre uma lista de resultados e outra.
        self.marcados = {}           # url -> item completo (titulo/artista/url/...)

    def abrir(self, ao_buscar, ao_escolher, ao_exportar=None,
              ao_escolher_varios=None, modo_playlist=False):
        self.ativa = True
        self.estado = "teclado"
        self.termo = ""
        self.linha = self.coluna = 0
        self.resultados = []
        self.indice = 0
        self.aviso = ""
        self.ao_buscar = ao_buscar
        self.ao_escolher = ao_escolher
        self.ao_exportar = ao_exportar
        self.ao_escolher_varios = ao_escolher_varios
        # modo_playlist=True SO no atalho do operador (F12 -> ACERVO ->
        # BUSCAR PARA PLAYLIST): la, marcar + confirmar grava um .m3u. No
        # uso normal do cliente (arquivo .buscar dentro do acervo), marcar
        # + confirmar manda tudo direto pra fila -- ninguem precisa de senha
        # nem cria playlist so pra ouvir umas musicas.
        self.modo_playlist = modo_playlist
        if self.log:
            self.log.info("tela de busca aberta (%s)",
                          "playlist" if modo_playlist else "cliente")

    def fechar(self):
        self.ativa = False
        self.estado = "teclado"
        self.termo = ""
        self.resultados = []

    def digitar(self, caractere):
        """Atalho para quem tem teclado de verdade."""
        if not self.ativa or self.estado != "teclado":
            return
        if caractere.isalnum() or caractere in " '-":
            if len(self.termo) < 40:
                self.termo += caractere.upper()

    def apagar(self):
        self.termo = self.termo[:-1]

    def receber_resultados(self, achados, erro=None):
        if erro:
            self.estado = "teclado"
            self.aviso = str(erro)[:50]
            return
        self.resultados = achados
        self.indice = 0
        self.estado = "resultados" if achados else "teclado"
        if not achados:
            self.aviso = "nada encontrado"

    def _tecla_atual(self):
        linha = LINHAS_TECLADO[self.linha]
        return linha[min(self.coluna, len(linha) - 1)]

    def _exportar(self):
        """So faz sentido com algo marcado. Captura o termo ANTES de
        fechar -- fechar() zera self.termo, e o .m3u usa esse nome."""
        if self.marcados and self.ao_exportar:
            termo = self.termo
            self.fechar()
            self.ao_exportar(termo)

    def processar(self, acao):
        """Devolve True se consumiu a acao."""
        if not self.ativa:
            return False

        if self.estado == "buscando":
            return True

        if self.estado == "resultados":
            if acao == "voltar":
                self.estado = "teclado"
            elif acao == "cima":
                self.indice = (self.indice - 1) % len(self.resultados)
            elif acao == "baixo":
                self.indice = (self.indice + 1) % len(self.resultados)
            elif acao == "direita":
                # Marca/desmarca. No modo playlist (operador) vira musica do
                # futuro .m3u; no modo cliente vira mais uma musica pra
                # entrar direto na fila quando confirmar com ENTER -- quem
                # so quer UMA musica nem precisa marcar, ENTER sozinho ja
                # toca a musica em destaque na hora.
                item = self.resultados[self.indice]
                url = item["url"]
                if url in self.marcados:
                    del self.marcados[url]
                else:
                    self.marcados[url] = item
            elif acao == "esquerda":
                # EXPORTAR pra .m3u: existe SO no modo playlist (atalho do
                # operador pra nao precisar navegar F12 -> ACERVO -> CRIAR
                # PLAYLIST). No modo cliente nao faz nada -- criar playlist e
                # coisa do menu de gerenciamento, nunca da tela do cliente.
                if self.modo_playlist:
                    self._exportar()
                return True
            elif acao == "ok":
                if self.marcados:
                    if self.modo_playlist:
                        # [FIX] com algo marcado, ENTER tocava so a musica
                        # destacada e fechava a busca -- as marcadas sumiam
                        # sem aviso nenhum. Agora, no modo playlist, ENTER
                        # com marcacao pendente tambem exporta (igual
                        # ESQUERDA).
                        self._exportar()
                    else:
                        # Modo cliente: tudo que foi marcado vai direto pra
                        # fila, na hora -- nunca vira playlist/m3u. Quantas
                        # vao realmente tocar depende so do credito que
                        # houver (mesma regra do resto da fila).
                        itens = list(self.marcados.values())
                        self.marcados.clear()
                        self.fechar()
                        if self.ao_escolher_varios:
                            self.ao_escolher_varios(itens)
                else:
                    escolhido = self.resultados[self.indice]
                    self.fechar()
                    if self.ao_escolher:
                        self.ao_escolher(escolhido)
            return True

        if acao == "voltar":
            if self.termo:
                self.apagar()
            else:
                self.fechar()
            return True
        if acao == "cima":
            self.linha = (self.linha - 1) % len(LINHAS_TECLADO)
        elif acao == "baixo":
            self.linha = (self.linha + 1) % len(LINHAS_TECLADO)
        elif acao == "esquerda":
            self.coluna = (self.coluna - 1) % len(LINHAS_TECLADO[self.linha])
        elif acao == "direita":
            self.coluna = (self.coluna + 1) % len(LINHAS_TECLADO[self.linha])
        elif acao == "ok":
            tecla = self._tecla_atual()
            if tecla == "BUSCAR":
                if self.termo.strip():
                    self.estado = "buscando"
                    self.aviso = ""
                    if self.ao_buscar:
                        self.ao_buscar(self.termo)
            elif tecla == "APAGAR":
                self.apagar()
            elif tecla == "ESPACO":
                if len(self.termo) < 40:
                    self.termo += " "
            elif len(self.termo) < 40:
                self.termo += tecla
        self.coluna = min(self.coluna, len(LINHAS_TECLADO[self.linha]) - 1)
        return True

    def _coracao_pulsando(self, tamanho):
        """Coracao pulsando no lugar do selo de play, para a musica atual da
        lista de resultados chamar mais atencao que as outras. A pulsacao
        vem do relogio do pygame, entao continua batendo sozinha enquanto a
        tela ficar redesenhando (tela_busca.ativa ja forca isso no laco
        principal -- ver comentario la em cima do `if menu.ativo() or
        tela_busca.ativa`)."""
        pulso = 0.75 + 0.25 * math.sin(pygame.time.get_ticks() / 170.0)
        lado = max(4, int(tamanho * pulso))
        surf = pygame.Surface((tamanho, tamanho), pygame.SRCALPHA)
        cx, cy = tamanho // 2, tamanho // 2
        r = max(2, lado // 4)
        cor = (255, 60, 100, 255)
        pygame.draw.circle(surf, cor, (cx - r, cy - r // 2), r)
        pygame.draw.circle(surf, cor, (cx + r, cy - r // 2), r)
        pontos = [(cx - lado // 2, cy - r // 3),
                 (cx + lado // 2, cy - r // 3),
                 (cx, cy + lado // 2)]
        pygame.draw.polygon(surf, cor, pontos)
        return surf

    def _checkbox(self, lado, marcado):
        """Desenhado igual ao selo de play (retangulo + linhas), nao um
        glifo de fonte -- a fonte de fallback do sistema pode nao ter
        checkbox/emoji, e um quadrado vazio/cheio funciona em qualquer
        fonte."""
        surf = pygame.Surface((lado, lado), pygame.SRCALPHA)
        cor_borda = (167, 139, 250, 255) if marcado else (110, 110, 135, 200)
        pygame.draw.rect(surf, cor_borda, (0, 0, lado, lado),
                         width=max(2, self.px(3)), border_radius=self.px(6))
        if marcado:
            pygame.draw.rect(surf, (124, 58, 237, 255),
                             (self.px(4), self.px(4),
                              lado - self.px(8), lado - self.px(8)),
                             border_radius=self.px(4))
            p = lado * 0.2
            pygame.draw.lines(surf, (255, 255, 255), False, [
                (p, lado * 0.55), (lado * 0.42, lado - p), (lado - p, p)],
                max(2, self.px(3)))
        return surf

    def _painel(self, largura, altura):
        px = self.px
        p = pygame.Surface((largura, altura), pygame.SRCALPHA)
        pygame.draw.rect(p, (18, 18, 26, 248), (0, 0, largura, altura),
                         border_radius=px(20))
        pygame.draw.rect(p, (167, 139, 250, 190), (0, 0, largura, altura),
                         width=max(2, px(3)), border_radius=px(20))
        return p

    def desenhar(self):
        if not self.ativa:
            return
        LARG, ALT = self.tela.get_size()
        veu = pygame.Surface((LARG, ALT))
        veu.set_alpha(210)
        veu.fill((0, 0, 0))
        self.tela.blit(veu, (0, 0))

        if self.estado == "resultados":
            self._desenhar_resultados(LARG, ALT)
        else:
            self._desenhar_teclado(LARG, ALT)

    def _desenhar_teclado(self, LARG, ALT):
        px = self.px
        pl, pa = px(1000), px(620)
        painel = self._painel(pl, pa)

        f_tit = self.fonte(px(40))
        titulo = f_tit.render("BUSCAR NO YOUTUBE", True, (255, 214, 0))
        painel.blit(titulo, ((pl - titulo.get_width()) // 2, px(28)))

        caixa = pygame.Surface((pl - px(96), px(64)), pygame.SRCALPHA)
        pygame.draw.rect(caixa, (40, 40, 56, 255), caixa.get_rect(),
                         border_radius=px(10))
        painel.blit(caixa, (px(48), px(92)))
        f_termo = self.fonte(px(38))
        mostrado = self.termo + ("_" if self.estado == "teclado" else "")
        painel.blit(f_termo.render(mostrado or "digite...", True,
                                   (255, 255, 255) if self.termo
                                   else (110, 110, 135)),
                    (px(66), px(104)))

        if self.estado == "buscando":
            f = self.fonte(px(44))
            r = f.render("BUSCANDO...", True, (120, 255, 120))
            painel.blit(r, ((pl - r.get_width()) // 2, px(300)))
            self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))
            return

        topo = px(190)
        alt_t = px(64)
        for li, linha in enumerate(LINHAS_TECLADO):
            larguras = [max(px(64), self.fonte(px(32)).size(t)[0] + px(34))
                        for t in linha]
            total = sum(larguras) + px(10) * (len(linha) - 1)
            x = (pl - total) // 2
            y = topo + li * (alt_t + px(12))
            for ci, tecla in enumerate(linha):
                w = larguras[ci]
                escolhida = (li == self.linha and
                             ci == min(self.coluna, len(linha) - 1))
                if escolhida:
                    realce = pygame.Surface((w, alt_t), pygame.SRCALPHA)
                    cor = ((60, 190, 90, 210) if tecla == "BUSCAR"
                           else (124, 58, 237, 200))
                    pygame.draw.rect(realce, cor, (0, 0, w, alt_t),
                                     border_radius=px(10))
                    painel.blit(realce, (x, y))
                f_t = self.fonte(px(32))
                cor_txt = ((255, 255, 255) if escolhida else
                           (150, 255, 150) if tecla == "BUSCAR" else
                           (185, 185, 200))
                r = f_t.render(tecla, True, cor_txt)
                painel.blit(r, (x + (w - r.get_width()) // 2,
                                y + (alt_t - r.get_height()) // 2))
                x += w + px(10)

        f_pe = self.fonte(px(26))
        texto_pe = self.aviso if self.aviso else \
            "SETAS mover   ENTER escolher   ESC apagar/sair"
        cor_pe = (255, 120, 90) if self.aviso else (120, 120, 145)
        pe = f_pe.render(texto_pe, True, cor_pe)
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(46)))
        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))

    def _desenhar_resultados(self, LARG, ALT):
        px = self.px
        linha_h = px(70)
        visiveis = min(len(self.resultados), 7)
        pl = px(1200)
        pa = px(150) + linha_h * visiveis + px(60)
        painel = self._painel(pl, pa)

        f_tit = self.fonte(px(36))
        texto_titulo = 'RESULTADOS: "%s"' % self.termo[:28]
        if self.marcados:
            sufixo = "p/ playlist" if self.modo_playlist else "marcada(s)"
            texto_titulo += "  (%d %s)" % (len(self.marcados), sufixo)
        titulo = f_tit.render(texto_titulo, True, (255, 214, 0))
        painel.blit(titulo, ((pl - titulo.get_width()) // 2, px(28)))
        pygame.draw.line(painel, (90, 80, 130), (px(40), px(96)),
                         (pl - px(40), px(96)), max(1, px(2)))

        inicio = max(0, min(self.indice - visiveis // 2,
                            len(self.resultados) - visiveis))
        f_n = self.fonte(px(32))
        f_s = self.fonte(px(24))
        y = px(120)
        for i in range(inicio, inicio + visiveis):
            r = self.resultados[i]
            escolhido = i == self.indice
            if escolhido:
                realce = pygame.Surface((pl - px(48), linha_h - px(8)),
                                        pygame.SRCALPHA)
                pygame.draw.rect(realce, (124, 58, 237, 160),
                                 realce.get_rect(), border_radius=px(10))
                painel.blit(realce, (px(24), y - px(4)))
            cor = (255, 255, 255) if escolhido else (190, 190, 205)

            # Marcador de video: quadrado arredondado com um play dentro.
            # Desenhado, nao baixado -- nao custa rede nem espera, e a lista
            # aparece completa desde o primeiro quadro. A musica selecionada
            # ganha um coracao pulsando no lugar, pra chamar mais atencao.
            # Checkbox de playlist, ANTES do selo de video -- e uma marca
            # do operador (quem vai criar o m3u depois), independente de
            # qual linha o cursor esta em cima agora.
            cx_lado = px(30)
            cx_box = self._checkbox(cx_lado, r["url"] in self.marcados)
            painel.blit(cx_box, (px(48), y + px(8)))

            mx, my, lado = px(48) + cx_lado + px(14), y + px(4), px(38)
            if escolhido:
                selo = self._coracao_pulsando(lado)
            else:
                selo = pygame.Surface((lado, lado), pygame.SRCALPHA)
                pygame.draw.rect(selo, (150, 45, 45, 220),
                                 (0, 0, lado, lado), border_radius=px(8))
                m = lado * 0.30
                pygame.draw.polygon(selo, (255, 255, 255), [
                    (m, m), (m, lado - m), (lado - m * 0.9, lado / 2)])
            painel.blit(selo, (mx, my))

            texto_x = mx + lado + px(16)
            titulo_v = r["titulo"]
            while (f_n.size(titulo_v)[0] > pl - texto_x - px(140)
                   and len(titulo_v) > 8):
                titulo_v = titulo_v[:-2]
            painel.blit(f_n.render(titulo_v, True, cor), (texto_x, y))
            sub = r["canal"][:38]
            painel.blit(f_s.render(sub, True, (130, 130, 155)),
                        (texto_x, y + px(36)))
            if r["duracao"]:
                d = f_s.render(r["duracao"], True,
                               (196, 181, 253) if escolhido else (130, 130, 155))
                painel.blit(d, (pl - px(48) - d.get_width(), y + px(12)))
            y += linha_h

        f_pe = self.fonte(px(24))
        # a dica muda com o estado, senao o rodape mente sobre o que a tecla
        # faz -- no modo playlist ENTER/ESQUERDA exportam; no modo cliente
        # ENTER manda as marcadas direto pra fila (nao existe exportar aqui)
        if self.marcados and self.modo_playlist:
            dica_enter = "ENTER/ESQUERDA exportar"
        elif self.marcados:
            dica_enter = "ENTER tocar marcadas"
        else:
            dica_enter = "ENTER tocar"
        pe = f_pe.render(
            "CIMA/BAIXO escolher   %s   DIREITA marcar   ESC voltar"
            % dica_enter, True, (120, 120, 145))
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(44)))
        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))
