# Sessão 2026-08-29 — foco não volta após F1 / fim de vídeo do YouTube

Registro da investigação para quem continuar a partir daqui (humano ou outra
sessão do Claude Code). Não confundir com `LEIA-ME.md`, que é a visão geral
do projeto — este arquivo é o diário desta sessão específica.

## Sintoma

Depois de fechar o pcmanfm (aberto por F1) ou depois que um vídeo do YouTube
terminava, a janela do jukebox ficava atrás de tudo. O processo continuava
vivo, 0% de CPU, e o log registrava o fechamento normalmente — só não
recuperava o foco sozinho. Só voltava com Alt+F4 ou Alt+Tab manual.

## Causa raiz confirmada

O `/etc/openbox/rc.xml` deste Batocera tem uma regra global:

```xml
<application type="normal">
  <fullscreen>yes</fullscreen>
  <decor>no</decor>
</application>
```

Isso força **qualquer** janela "normal" — jukebox, pcmanfm, mpv — a virar
fullscreen sem borda. Quando a janela da frente fecha (pcmanfm ou mpv), o
Openbox roda a própria lógica interna de "para quem devolver o foco" **em
paralelo** ao nosso `xdotool windowactivate`. Às vezes essa lógica interna
termina *depois* do nosso pedido e desfaz o foco silenciosamente — o log
dizia "foco devolvido ao jukebox" e a janela ficava atrás mesmo assim. É uma
corrida (race), não uma falha do comando: reproduzi ao vivo o caso em que uma
`windowactivate` isolada "colava" e o caso em que não colava, variando só o
tempo entre o fechamento da janela anterior e a nossa chamada.

Confirmado com o processo rodando (pid ao vivo), sem alterar nada:
`xdotool getactivewindow` continuava apontando para outra janela mesmo
segundos depois do log de sucesso — a prova de que o log estava otimista e o
pedido realmente não tinha colado.

## Correção aplicada

Arquivo `jukebox`, função `recuperar_foco()`: em vez de uma tentativa única
via `Popen` (fire-and-forget), agora insiste em `xdotool windowactivate` por
~1.5 s (tentativas em 0, 0.15, 0.35, 0.6, 1.0 e 1.5 s), numa thread daemon
separada. A última tentativa, feita depois que a "poeira" do fechamento já
baixou, vence a disputa contra a lógica interna do Openbox. A thread só chama
`xdotool` — não toca em fila, estado ou tela — então não precisa passar pelo
loop principal para agir com segurança (mesmo princípio já usado no
`_monitorar` do `player.py`).

Como os dois sintomas (F1 e fim do vídeo) passam pela mesma função
`recuperar_foco()` (chamada em `encerrar_reproducao()` e no retorno do
gerenciador de arquivos), a correção cobre os dois com uma mudança só.

Mudança é 100% reversível: só a função Python, nenhum arquivo de sistema
tocado. Cópias antigas em `jukebox.bak` e `jukebox.bak2` se precisar
comparar/reverter.

## Validação feita

- Reiniciei o processo supervisionado (`servico-jukebox`/`iniciar.sh` já
  reinicia sozinho quando o processo morre — cuidado ao matar o pid para
  testar, ele volta em ~1s automaticamente e é fácil acabar com dois
  processos rodando ao mesmo tempo disputando a mesma janela X/socket do
  mpv; sempre conferir com `ps aux | grep "python3 jukebox"` depois).
- Enviei F1 de verdade para a janela do jukebox (`xdotool key --window <id>
  F1`), esperei o pcmanfm abrir, fechei como um cliente fecharia
  (`wmctrl -c`), e **sem chamar xdotool manualmente depois**, o foco voltou
  sozinho ao jukebox. Repeti duas vezes, funcionou nas duas.

## Não testado ainda

- **Fim de vídeo do YouTube ao vivo** (precisa de rede + `yt-dlp` resolvendo
  um link real e o mpv tocando até o fim). O mecanismo é idêntico ao do F1
  (mesma função `recuperar_foco()`), então a expectativa é que funcione, mas
  não foi observado ponta a ponta nesta sessão. Vale confirmar na próxima,
  ou quando a máquina tocar um vídeo de verdade.

## Bug latente (não é a causa do problema atual, mas fica registrado)

`config.json` desta instância tem `fechar_tela_no_f1: false`. **Se algum dia
esse valor voltar para `true`**, existe um bug separado: `JANELA_ID` é
capturado uma única vez no boot (linha ~181) e nunca é atualizado depois que
`pygame.display.quit()` + `pygame.display.set_mode()` recriam a janela no
retorno do F1 — a partir daí `JANELA_ID` aponta para uma janela X que já não
existe, e toda recuperação de foco subsequente (não só a do F1) fica muda.
Se for reativar `fechar_tela_no_f1`, é preciso capturar de novo o
`pygame.display.get_wm_info()["window"]` logo após o `set_mode()` de
recriação (por volta da linha 1565 do arquivo `jukebox`) e só chamar
`recuperar_foco()` depois disso, não antes.

## O que já foi tentado e descartado (não repetir)

- `xdotool windowunmap` — derrubou o Openbox com sinal 11, levou o X junto.
- `wmctrl -b add,skip_taskbar` — travou a sessão gráfica.
- `xdotool windowactivate` sem repetição, com e sem `--sync` — inconsistente
  por causa da corrida descrita acima (`--sync` bloqueia o laço principal,
  por isso a versão nova continua sem `--sync`, só que repetida).
- Destruir/recriar a tela no F1 (`fechar_tela_no_f1: true`) — funciona, mas
  introduz o bug latente do `JANELA_ID` descrito acima; por isso está `false`
  no config atual.
- Repintar periódico de 3 s — não resolve, porque o problema é foco/stacking
  da janela, não desenho.
- `video_embutido: true` (mpv com `--wid`) — derrubava o Openbox ao terminar
  o vídeo. Manter `false`.
- Alterar o `--startup` do Openbox — não fazer. Já quebrou o boot gráfico
  desta máquina uma vez (precisou formatar). `/etc/X11/xinit/xinitrc`
  também está fora dos limites.

## Diagnóstico útil para a próxima vez

Com `"diagnostico_janelas": true` no `config.json`, o log grava
`[JANELAS ...]` com a lista de janelas visíveis a cada F1. Repare que a
própria janela do jukebox **nunca aparece nessa lista** — não é bug, é só
que ela não tem `WM_NAME`/`_NET_WM_NAME` definido (`wmctrl -lx` mostra
`N/A` no título), e o `registrar_janelas()` busca por nome
(`xdotool search --name .`). Para ver a janela do jukebox de verdade, usar
`wmctrl -lx` (lista por classe, `jukebox.jukebox`) em vez de `xdotool
search --name`.
