#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Menu de configuracao em sobreposicao, no estilo do EmulationStation.

Desenha por cima da tela atual, sem interromper nada: a fila continua andando
e a musica tocando enquanto o operador mexe aqui.

MODELO DE PAGINAS
-----------------
Uma pagina e uma lista de itens. Cada item e um dicionario:

    {"rotulo": "VOLUME",             # o que aparece a esquerda
     "valor": "90%",                 # texto a direita (ou funcao que devolve)
     "acao": "som"}                  # nome de outra pagina, funcao, ou None

Se "acao" for o nome de outra pagina, entrar nela empilha; ESC desempilha.
Se for uma funcao, ela e chamada. Se for None, o item so mostra informacao.

O valor pode ser uma funcao sem argumentos: assim numeros vivos (saldo, total,
memoria) aparecem sempre atualizados, sem precisar reconstruir a pagina.
"""

import pygame


class Menu:
    def __init__(self, tela, px, fonte, texto, ui, logger=None):
        self.tela = tela
        self.px = px
        self.fonte = fonte
        self.texto = texto          # funcao de texto com cache do jukebox
        self.ui = ui
        self.log = logger

        self.paginas = {}
        self.pilha = []             # [[nome_da_pagina, indice_selecionado]]
        self.aviso = ""             # mensagem temporaria no rodape
        self.aviso_ate = 0.0
        self.inicial = "principal"

        # --- pedido de senha ---
        self.modo = None            # None ou "senha"
        self.pin = ""
        self.verificador = None
        self.indice_tecla = 0
        self.tentativas = 0
        self.bloqueado_ate = 0
        self.TECLAS = list("0123456789") + ["APAGAR", "OK"]
        self.MAX_TENTATIVAS = 3
        self.BLOQUEIO_MS = 30000

        # --- painel de texto (relatorios) ---
        self.texto_titulo = ""
        self.texto_linhas = []

        # --- confirmacao de acao irreversivel ---
        self.pergunta = ""
        self.ao_confirmar = None
        self.escolha_sim = False

    # ------------------------------------------------------------------
    def definir_paginas(self, paginas, inicial="principal"):
        self.paginas = paginas
        self.inicial = inicial

    def abrir(self):
        self.modo = None
        self.pin = ""
        self.pilha = [[self.inicial, 0]]
        if self.log:
            self.log.info("menu de configuracao aberto")

    def pedir_senha(self, verificador):
        """Entra no modo de digitacao. verificador(pin) devolve True/False."""
        self.verificador = verificador
        self.modo = "senha"
        self.pin = ""
        self.indice_tecla = 0
        self.pilha = [[self.inicial, 0]]     # so para o menu contar como ativo
        if self.log:
            self.log.info("senha do operador solicitada")

    def fechar(self):
        self.modo = None
        self.pin = ""
        self.pilha = []
        if self.log:
            self.log.info("menu de configuracao fechado")

    def ativo(self):
        return bool(self.pilha)

    def mostrar_aviso(self, mensagem, segundos=2.5):
        self.aviso = mensagem
        self.aviso_ate = pygame.time.get_ticks() + segundos * 1000

    # ------------------------------------------------------------------
    def mostrar_texto(self, titulo, linhas):
        """Painel so de leitura, para relatorios. Qualquer tecla fecha."""
        self.modo = "texto"
        self.texto_titulo = titulo
        self.texto_linhas = list(linhas)

    def _processar_texto(self, acao):
        self.modo = None
        return True

    def pedir_confirmacao(self, pergunta, ao_confirmar):
        """Usado nas acoes que nao tem volta. Comeca em NAO de proposito: um
        ENTER dado sem querer nao pode desligar a maquina no meio do bar."""
        self.modo = "confirmar"
        self.pergunta = pergunta
        self.ao_confirmar = ao_confirmar
        self.escolha_sim = False

    def _processar_confirmacao(self, acao):
        if acao in ("esquerda", "direita"):
            self.escolha_sim = not self.escolha_sim
        elif acao == "voltar":
            self.modo = None
        elif acao == "ok":
            confirmou = self.escolha_sim
            self.modo = None
            if confirmou and self.ao_confirmar:
                try:
                    resposta = self.ao_confirmar()
                    if isinstance(resposta, str):
                        self.mostrar_aviso(resposta)
                except Exception as erro:
                    if self.log:
                        self.log.exception("erro na acao confirmada: %s", erro)
                    self.mostrar_aviso("erro ao executar")
        return True

    def bloqueado(self):
        return pygame.time.get_ticks() < self.bloqueado_ate

    def digitar(self, caractere):
        """Atalho pelo teclado numerico. A tela tambem funciona so com setas,
        porque numa cabine pode nao haver teclado."""
        if self.modo != "senha" or self.bloqueado():
            return
        if caractere.isdigit() and len(self.pin) < 8:
            self.pin += caractere

    def _confirmar_senha(self):
        if not self.verificador or not self.pin:
            return
        if self.verificador(self.pin):
            self.tentativas = 0
            self.modo = None
            self.pin = ""
            if self.log:
                self.log.info("senha aceita")
        else:
            self.tentativas += 1
            self.pin = ""
            if self.log:
                self.log.warning("senha incorreta (%d/%d)",
                                 self.tentativas, self.MAX_TENTATIVAS)
            if self.tentativas >= self.MAX_TENTATIVAS:
                self.bloqueado_ate = pygame.time.get_ticks() + self.BLOQUEIO_MS
                self.tentativas = 0
                self.mostrar_aviso("bloqueado por %ds" % (self.BLOQUEIO_MS // 1000), 4)
            else:
                self.mostrar_aviso("senha incorreta", 2)

    def _processar_senha(self, acao):
        if self.bloqueado():
            if acao == "voltar":
                self.fechar()
            return True
        if acao == "voltar":
            if self.pin:
                self.pin = self.pin[:-1]
            else:
                self.fechar()
            return True
        if acao in ("esquerda", "direita"):
            passo = -1 if acao == "esquerda" else 1
            self.indice_tecla = (self.indice_tecla + passo) % len(self.TECLAS)
            return True
        if acao == "ok":
            escolha = self.TECLAS[self.indice_tecla]
            if escolha == "OK":
                self._confirmar_senha()
            elif escolha == "APAGAR":
                self.pin = self.pin[:-1]
            elif len(self.pin) < 8:
                self.pin += escolha
            return True
        return True

    def _pagina_atual(self):
        nome, indice = self.pilha[-1]
        itens = self.paginas.get(nome, {}).get("itens", [])
        return nome, itens, indice

    def processar(self, acao):
        """Recebe as mesmas acoes logicas do resto do app. Devolve True se
        consumiu a acao (o jukebox entao nao deve trata-la)."""
        if not self.ativo():
            return False
        if self.modo == "senha":
            return self._processar_senha(acao)
        if self.modo == "confirmar":
            return self._processar_confirmacao(acao)
        if self.modo == "texto":
            return self._processar_texto(acao)
        nome, itens, indice = self._pagina_atual()

        if acao == "voltar":
            self.pilha.pop()
            if not self.pilha:
                self.fechar()
            return True

        if not itens:
            return True

        if acao in ("cima", "baixo"):
            passo = -1 if acao == "cima" else 1
            self.pilha[-1][1] = (indice + passo) % len(itens)
            return True

        if acao == "ok":
            alvo = itens[indice].get("acao")
            if isinstance(alvo, str) and alvo in self.paginas:
                self.pilha.append([alvo, 0])
            elif callable(alvo):
                try:
                    resposta = alvo()
                    if isinstance(resposta, str):
                        self.mostrar_aviso(resposta)
                except Exception as erro:
                    if self.log:
                        self.log.exception("erro no item do menu: %s", erro)
                    self.mostrar_aviso("erro ao executar")
            else:
                self.mostrar_aviso("ainda nao implementado")
            return True

        if acao in ("esquerda", "direita"):
            ajustar = itens[indice].get("ajustar")
            if callable(ajustar):
                try:
                    mensagem = ajustar(-1 if acao == "esquerda" else 1)
                    if mensagem:
                        self.mostrar_aviso(mensagem, 1.6)
                except Exception as erro:
                    if self.log:
                        self.log.exception("erro ao ajustar: %s", erro)
            return True

        return True         # o menu consome tudo para nao vazar para o fundo

    # ------------------------------------------------------------------
    def _desenhar_senha(self):
        px = self.px
        LARG, ALT = self.tela.get_size()
        veu = pygame.Surface((LARG, ALT))
        veu.set_alpha(200)
        veu.fill((0, 0, 0))
        self.tela.blit(veu, (0, 0))

        pl, pa = px(760), px(400)
        painel = pygame.Surface((pl, pa), pygame.SRCALPHA)
        pygame.draw.rect(painel, (18, 18, 26, 248), (0, 0, pl, pa),
                         border_radius=px(20))
        pygame.draw.rect(painel, (167, 139, 250, 190), (0, 0, pl, pa),
                         width=max(2, px(3)), border_radius=px(20))

        f_tit = self.fonte(px(40))
        titulo = f_tit.render("SENHA DO OPERADOR", True, (255, 214, 0))
        painel.blit(titulo, ((pl - titulo.get_width()) // 2, px(30)))

        if self.bloqueado():
            resta = (self.bloqueado_ate - pygame.time.get_ticks()) // 1000 + 1
            f = self.fonte(px(40))
            aviso = f.render("BLOQUEADO - aguarde %ds" % resta, True, (255, 90, 90))
            painel.blit(aviso, ((pl - aviso.get_width()) // 2, pa // 2 - px(20)))
            self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))
            return

        # Bolinhas do PIN, DESENHADAS em vez de escritas: a fonte do sistema
        # nao tem o glifo de circulo cheio e ele saia como quadradinho.
        raio = px(11)
        passo = px(42)
        quantos = max(1, len(self.pin))
        largura = passo * quantos - (passo - raio * 2)
        cx = (pl - largura) // 2 + raio
        cy = px(120)
        if self.pin:
            for i in range(len(self.pin)):
                pygame.draw.circle(painel, (255, 255, 255),
                                   (cx + i * passo, cy), raio)
        else:
            pygame.draw.line(painel, (110, 110, 135),
                             (pl // 2 - px(20), cy), (pl // 2 + px(20), cy),
                             max(2, px(3)))

        # tira de teclas: funciona so com as setas, sem teclado
        f_t = self.fonte(px(34))
        y = px(190)
        larguras = [f_t.size(t)[0] + px(28) for t in self.TECLAS]
        total = sum(larguras) + px(8) * (len(self.TECLAS) - 1)
        x = (pl - total) // 2
        for i, t in enumerate(self.TECLAS):
            w = larguras[i]
            if i == self.indice_tecla:
                realce = pygame.Surface((w, px(52)), pygame.SRCALPHA)
                pygame.draw.rect(realce, (124, 58, 237, 190), (0, 0, w, px(52)),
                                 border_radius=px(10))
                painel.blit(realce, (x, y))
            cor = (255, 255, 255) if i == self.indice_tecla else (150, 150, 170)
            r = f_t.render(t, True, cor)
            painel.blit(r, (x + (w - r.get_width()) // 2, y + px(10)))
            x += w + px(8)

        f_pe = self.fonte(px(26))
        if self.aviso and pygame.time.get_ticks() < self.aviso_ate:
            pe = f_pe.render(self.aviso, True, (255, 120, 90))
        else:
            pe = f_pe.render("LADOS escolher   ENTER confirmar   ESC apagar/sair",
                             True, (120, 120, 145))
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(56)))
        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))

    def _desenhar_texto(self):
        px = self.px
        LARG, ALT = self.tela.get_size()
        veu = pygame.Surface((LARG, ALT))
        veu.set_alpha(200)
        veu.fill((0, 0, 0))
        self.tela.blit(veu, (0, 0))

        f_tit = self.fonte(px(42))
        f_l = self.fonte(px(34))
        linha_h = px(48)
        pl = px(860)
        pa = px(150) + linha_h * max(1, len(self.texto_linhas)) + px(70)

        painel = pygame.Surface((pl, pa), pygame.SRCALPHA)
        pygame.draw.rect(painel, (18, 18, 26, 248), (0, 0, pl, pa),
                         border_radius=px(20))
        pygame.draw.rect(painel, (167, 139, 250, 190), (0, 0, pl, pa),
                         width=max(2, px(3)), border_radius=px(20))

        titulo = f_tit.render(self.texto_titulo, True, (255, 214, 0))
        painel.blit(titulo, ((pl - titulo.get_width()) // 2, px(32)))
        pygame.draw.line(painel, (90, 80, 130),
                         (px(40), px(100)), (pl - px(40), px(100)), max(1, px(2)))

        y = px(130)
        for linha in self.texto_linhas:
            if isinstance(linha, (tuple, list)):
                # (rotulo, valor): rotulo a esquerda, valor a direita
                esq = f_l.render(str(linha[0]), True, (200, 200, 215))
                dir_ = f_l.render(str(linha[1]), True, (255, 255, 255))
                painel.blit(esq, (px(48), y))
                painel.blit(dir_, (pl - px(48) - dir_.get_width(), y))
            elif linha == "-":
                pygame.draw.line(painel, (70, 65, 95),
                                 (px(48), y + px(16)), (pl - px(48), y + px(16)),
                                 max(1, px(2)))
            else:
                painel.blit(f_l.render(str(linha), True, (150, 150, 175)),
                            (px(48), y))
            y += linha_h

        f_pe = self.fonte(px(26))
        pe = f_pe.render("qualquer tecla para voltar", True, (120, 120, 145))
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(50)))
        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))

    def _desenhar_confirmacao(self):
        px = self.px
        LARG, ALT = self.tela.get_size()
        veu = pygame.Surface((LARG, ALT))
        veu.set_alpha(200)
        veu.fill((0, 0, 0))
        self.tela.blit(veu, (0, 0))

        pl, pa = px(720), px(300)
        painel = pygame.Surface((pl, pa), pygame.SRCALPHA)
        pygame.draw.rect(painel, (18, 18, 26, 248), (0, 0, pl, pa),
                         border_radius=px(20))
        pygame.draw.rect(painel, (255, 140, 90, 200), (0, 0, pl, pa),
                         width=max(2, px(3)), border_radius=px(20))

        f = self.fonte(px(38))
        pergunta = f.render(self.pergunta, True, (255, 255, 255))
        painel.blit(pergunta, ((pl - pergunta.get_width()) // 2, px(60)))

        f_b = self.fonte(px(36))
        y = px(160)
        for i, rotulo in enumerate(("NAO", "SIM")):
            selecionado = (i == 1) == self.escolha_sim
            w, h = px(200), px(64)
            x = pl // 2 + (px(20) if i else -px(20) - w)
            if selecionado:
                realce = pygame.Surface((w, h), pygame.SRCALPHA)
                cor = (200, 60, 60, 200) if i else (124, 58, 237, 190)
                pygame.draw.rect(realce, cor, (0, 0, w, h), border_radius=px(12))
                painel.blit(realce, (x, y))
            r = f_b.render(rotulo, True,
                           (255, 255, 255) if selecionado else (150, 150, 170))
            painel.blit(r, (x + (w - r.get_width()) // 2, y + px(14)))

        f_pe = self.fonte(px(26))
        pe = f_pe.render("LADOS escolher   ENTER confirmar   ESC cancelar",
                         True, (120, 120, 145))
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(50)))
        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))

    def desenhar(self):
        if not self.ativo():
            return
        if self.modo == "texto":
            self._desenhar_texto()
            return
        if self.modo == "confirmar":
            self._desenhar_confirmacao()
            return
        if self.modo == "senha":
            self._desenhar_senha()
            return
        px = self.px
        LARG, ALT = self.tela.get_size()
        nome, itens, indice = self._pagina_atual()
        pagina = self.paginas.get(nome, {})

        # escurece o fundo para o menu ficar legivel sobre qualquer tela
        veu = pygame.Surface((LARG, ALT))
        veu.set_alpha(180)
        veu.fill((0, 0, 0))
        self.tela.blit(veu, (0, 0))

        # painel
        pl, pa = px(900), px(720)
        painel = pygame.Surface((pl, pa), pygame.SRCALPHA)
        pygame.draw.rect(painel, (18, 18, 26, 245), (0, 0, pl, pa),
                         border_radius=px(20))
        pygame.draw.rect(painel, (167, 139, 250, 190), (0, 0, pl, pa),
                         width=max(2, px(3)), border_radius=px(20))

        # titulo
        f_tit = self.fonte(px(46))
        titulo = f_tit.render(pagina.get("titulo", "CONFIGURA\u00c7\u00d5ES"),
                              True, (255, 214, 0))
        painel.blit(titulo, ((pl - titulo.get_width()) // 2, px(34)))
        pygame.draw.line(painel, (90, 80, 130),
                         (px(40), px(104)), (pl - px(40), px(104)),
                         max(1, px(2)))

        # itens
        f_item = self.fonte(px(38))
        f_valor = self.fonte(px(32))
        linha_h = px(62)
        topo = px(132)
        visiveis = max(3, (pa - topo - px(90)) // linha_h)
        inicio = max(0, min(indice - visiveis // 2, len(itens) - visiveis))

        for i, item in enumerate(itens[inicio:inicio + visiveis]):
            real = inicio + i
            y = topo + i * linha_h
            selecionado = real == indice
            if selecionado:
                # [FIX] desenhar direto no painel com alfa FURAVA o painel:
                # draw.rect substitui os pixels em vez de mesclar, entao o
                # realce virava um buraco por onde se via a tela de tras.
                # Numa superficie propria + blit, a mescla acontece certo.
                rl, rh = pl - px(48), linha_h - px(6)
                realce = pygame.Surface((rl, rh), pygame.SRCALPHA)
                pygame.draw.rect(realce, (124, 58, 237, 150), (0, 0, rl, rh),
                                 border_radius=px(10))
                painel.blit(realce, (px(24), y - px(6)))
            cor = (255, 255, 255) if selecionado else (185, 185, 200)
            painel.blit(f_item.render(item["rotulo"], True, cor), (px(48), y))

            valor = item.get("valor")
            if callable(valor):
                try:
                    valor = valor()
                except Exception:
                    valor = "?"
            if valor:
                # item ajustavel e selecionado ganha as setas, para o operador
                # saber que da para mexer sem precisar adivinhar
                if selecionado and callable(item.get("ajustar")):
                    valor = "\u2039  %s  \u203a" % valor
                render = f_valor.render(str(valor), True,
                                        (196, 181, 253) if selecionado
                                        else (130, 130, 155))
                painel.blit(render, (pl - px(48) - render.get_width(), y + px(6)))
            elif isinstance(item.get("acao"), str):
                seta = f_valor.render("\u203a", True,
                                      (196, 181, 253) if selecionado
                                      else (110, 110, 135))
                painel.blit(seta, (pl - px(56) - seta.get_width(), y + px(2)))

        # rodape: aviso temporario ou as teclas
        f_pe = self.fonte(px(28))
        if self.aviso and pygame.time.get_ticks() < self.aviso_ate:
            pe = f_pe.render(self.aviso, True, (255, 180, 90))
        else:
            # sem setas unicode: a fonte do sistema nao tem esses glifos e
            # eles saiam como quadradinhos
            pe = f_pe.render(
                "CIMA/BAIXO navegar   LADOS ajustar   ENTER entrar   ESC voltar",
                True, (120, 120, 145))
        painel.blit(pe, ((pl - pe.get_width()) // 2, pa - px(56)))

        self.tela.blit(painel, painel.get_rect(center=(LARG // 2, ALT // 2)))
