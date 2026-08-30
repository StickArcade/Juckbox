# Jukebox

Visão geral do projeto. Para o diário de uma investigação específica (bug de
foco após F1/YouTube), ver `README.md` — não confundir os dois: este arquivo
é a foto atual do projeto, aquele é o histórico de uma sessão de depuração.

## Arquivos

### Núcleo (rodam em produção)

| Arquivo | O que faz |
|---|---|
| `config.json` | Configuração de produção. Nada fica travado no código. |
| `config.dev.json` | Configuração para testar no desktop (`testar.sh` usa esta). Caminhos relativos, `fechar_tela_no_f1: true`, `recuperar_foco: false` — ver aviso sobre isso mais abaixo. |
| `jukebox` | Script principal: loop pygame, estados (menu de gênero/artista/música, tocando), fila, integra todos os módulos abaixo. ~2200 linhas. |
| `creditos.py` | Créditos com escrita atômica, lock entre processos e auditoria em JSONL. Também é CLI (`python3 creditos.py ...`). |
| `player.py` | mpv com IPC (`--input-ipc-server`): permite posição, volume e pausa sem matar o processo. Corrige o bug antigo do `stop()`. |
| `menu.py` | Menu de configuração do operador (F12), estilo EmulationStation: páginas empilháveis, PIN numérico, confirmação de ações irreversíveis, painel de texto para relatórios. |
| `busca.py` | Tela de busca do YouTube para o **cliente**: teclado virtual navegável só com setas, lista de resultados, marcação (checkbox) para playlist. |
| `carrossel.py` | Carrossel horizontal de cartões (gêneros/artistas): cartão em foco grande e nítido, vizinhos menores; cartões montados uma vez e cacheados. |
| `fundo.py` | Fundo que muda por gênero, com cache de miniaturas, transição suave (fade) e derivação automática a partir da logo quando não há `background.png` próprio. |
| `youtube.py` | Integração com `yt-dlp`: busca (`--flat-playlist`), resolução de link em vídeo+áudio, leitura de arquivos `.url`, separação artista/música do título. |
| `senha.py` | PIN do operador: hash PBKDF2 com sal, nunca texto puro. Também é CLI (`python3 senha.py definir/conferir/remover/estado`). |
| `catalogo.py` | Catálogo do acervo em SQLite: indexador que varre `musicas/` e grava gênero/artista/arquivo num banco, com escrita atômica (`tmp` + `rename`, igual ao resto do projeto). `jukebox` já importa este módulo direto e dispara a reindexação em thread separada — no boot (se o banco ainda não existir) e pelo F12 → ACERVO → REINDEXAR. **Só leitura para o operador por enquanto** — a navegação do cliente continua lendo as pastas direto, como sempre; é a base para busca local/relatórios de uma passada futura. Também é CLI (`python3 catalogo.py reindexar` / `resumo`). |

### Instalação / sistema (Batocera)

| Arquivo | O que faz |
|---|---|
| `iniciar.sh` | Decide entre subir o jukebox ou o EmulationStation no boot. Chamado de dentro do `/usr/bin/emulationstation-standalone` real do sistema (ver abaixo) — não por `batocera-services`. Ajusta o próprio `PATH` para enxergar `/userdata/system/.local/bin` (`yt-dlp`, `deno`), senão o mpv não resolve vídeo do YouTube. Duas proteções: arquivo `/userdata/system/.dev/modo-es` força EmulationStation (manutenção), e 3 quedas seguidas em menos de 20s também caem para o EmulationStation (a máquina nunca fica em tela preta sem saída). |
| `servico-jukebox` | Supervisor alternativo para `batocera-services` (Batocera não usa systemd), com backoff exponencial (2s → 60s) se o processo cair. **Não é o mecanismo usado pelo instalador atual** — hoje quem sobe e supervisiona o jukebox é só o `iniciar.sh` chamado pelo `emulationstation-standalone` patcheado (ver `instalador.sh`); os dois juntos rodariam dois jukebox ao mesmo tempo disputando o socket do mpv. Fica aqui como opção manual para quem preferir um serviço de verdade em vez do gancho no ES. |
| `emulationstation-standalone` | Cópia do script **original do Batocera** (não é código deste projeto), só de referência — o real fica em `/usr/bin/emulationstation-standalone` do sistema. O instalador insere uma linha marcada `[JUKEBOX]` perto do fim, trocando a chamada `emulationstation ${GAMELAUNCHOPT}...` por `iniciar.sh ${GAMELAUNCHOPT} ${CUSTOMESOPTIONS}` — é esse desvio que faz a máquina abrir o jukebox em vez do EmulationStation no boot. Não editar esta cópia à mão; ela é só o "antes" para comparação. |

### Utilitários avulsos (rodados manualmente, fora do jukebox)

| Arquivo | O que faz |
|---|---|
| `gerar_fundo.py` | Gera `assets/background.png` com degradê roxo escuro (ampliado de uma imagem minúscula via bicúbica — rápido e sem banding). |
| `conferir_logos.py` | Lista quais gêneros/artistas ainda não têm `logo.png`/`.jpg`/`.jpeg`/`.webp`. |
| `gerar_generos_squashfs.sh` | Regera `assets/generos.squashfs` a partir do `musicas/` real: para cada gênero, pega só `logo.*`/`background.*` (nunca de artista, nunca música) mais o placeholder `ADICIONE_ARTISTAS_AQUI` — e, caso especial, o gênero `YOUTUBE` leva a pasta `BUSCAR/*.buscar` que dispara a tela de busca ao ser navegada. Rodar depois de adicionar/trocar um logo de gênero; depois rodar `empacotar.sh` de novo para o pacote ir atualizado pra `dist/`/release. |
| `baixar_musicas.py` | Script solto para baixar áudio (mp3) de uma lista de links via `yt_dlp`. **Não integrado ao jukebox** — é uma ferramenta manual de povoamento do acervo. |
| `testar.sh` | Utilitário de teste no desktop: `deps` (confere dependências), `credito`/`saldo`, `rodar` (janela 1280×720), `fumaca` (teste automatizado sem tela, simula navegação e credita/consome), `log`, `limpar`. **Não usar em produção.** |

### Protótipo não usado

`ui/renderer.py`, `ui/components.py` e `themes/*/theme.json` são um sistema de
temas ainda **não ligado** ao jukebox — nenhum arquivo do projeto importa
`ui.renderer` ou `ui.components` hoje. `themes/neon/theme.json` está vazio
(seria a origem de um crash se o sistema de temas fosse ligado sem preencher).
Tratar como esqueleto para uma passada futura, não como código ativo.

### Cópias de segurança

`jukebox.bak`, `jukebox.bak2`, `busca.py.bak`, `youtube.py.bak` — versões
anteriores mantidas para comparar/reverter se algo quebrar. Não são
carregadas pelo programa.

## Instalação no Batocera

### Pelo instalador (jeito normal)

Numa imagem nova do Batocera, com internet:

```sh
wget -O instalador.sh https://github.com/<usuario>/<repo>/releases/latest/download/instalador.sh
sh instalador.sh
```

O `instalador.sh` baixa o `jukebox.squashfs` da mesma release (variável
`URL_SQUASHFS` no topo do script — ajustar para a release de verdade antes
de publicar), extrai em `/userdata/system/.dev/apps/Juckbox` e resolve
sozinho todo o resto: `.bashrc`, `PATH` para `/userdata/system/.local/bin`,
o binário do `yt-dlp` (embutido no squashfs, não depende de internet essa
parte), e o desvio no `/usr/bin/emulationstation-standalone` para chamar
`iniciar.sh` no lugar do EmulationStation. É idempotente — pode rodar de
novo numa máquina já instalada para atualizar o código sem perder
`musicas/`, `config.json` nem o catálogo. Ver `## Empacotamento e
instalador` mais abaixo para o que ele faz passo a passo, e como gerar o
`.squashfs` a partir deste repositório.

Acervo inicial: se `musicas/` não existir ou estiver sem nenhum gênero, o
próprio `jukebox` cria a prateleira de gêneros sozinho no primeiro boot —
ver `## Acervo inicial (primeiro boot)` abaixo. O instalador não mexe em
música nenhuma.

### Manual (sem o instalador, um arquivo de cada vez)

```sh
# 1. Renomear a pasta de músicas para sem acento, se vier de um ZIP antigo
#    (o acento já causou problema de encoding)
mv "/userdata/músicas" /userdata/musicas 2>/dev/null

# 2. Copiar os arquivos para o mesmo lugar que .bashrc/iniciar.sh esperam
JUKEBOX_DIR=/userdata/system/.dev/apps/Juckbox
mkdir -p "$JUKEBOX_DIR"
cp config.json creditos.py player.py menu.py busca.py carrossel.py fundo.py \
   youtube.py senha.py catalogo.py jukebox iniciar.sh servico-jukebox \
   "$JUKEBOX_DIR"/
cp -r assets themes ui "$JUKEBOX_DIR"/     # se ainda não existirem lá
chmod +x "$JUKEBOX_DIR"/jukebox "$JUKEBOX_DIR"/iniciar.sh

# 3. yt-dlp precisa estar no PATH que o iniciar.sh usa
mkdir -p /userdata/system/.local/bin
cp yt-dlp /userdata/system/.local/bin/     # baixar de github.com/yt-dlp/yt-dlp se não tiver
chmod +x /userdata/system/.local/bin/yt-dlp

# 4. Fazer o EmulationStation real chamar o iniciar.sh no boot
#    (o instalador faz isso com sed de forma idempotente; à mão, adicionar
#    perto do fim do /usr/bin/emulationstation-standalone, substituindo a
#    linha "emulationstation ${GAMELAUNCHOPT} ... ${CUSTOMESOPTIONS}"):
#      /userdata/system/.dev/apps/Juckbox/iniciar.sh ${GAMELAUNCHOPT} ${CUSTOMESOPTIONS}

# 5. Verificar
tail -f /userdata/system/.dev/arranque.log /userdata/system/.dev/jukebox.log
```

`servico-jukebox`/`batocera-services` é uma alternativa que existe no
repositório mas **não é o caminho usado pelo instalador** — ver a tabela de
arquivos acima.

## Acervo inicial (primeiro boot)

`jukebox` chama `inicializar_acervo()` uma vez, antes de subir a tela: se
`musicas/` não existe ou existe mas está sem NENHUM gênero (pasta trocada,
cartão novo, imagem restaurada sem o acervo junto), ele monta a prateleira
sozinho, sem depender do dono lembrar de nada:

1. Se `assets/generos.squashfs` existir, extrai (`unsquashfs`) direto para
   `musicas/` — é a árvore real de gêneros/artistas com `logo.png`/
   `background.*` já prontos por gênero, sem nenhuma música dentro. Esse
   pacote é gerado uma vez com `mksquashfs` a partir de um acervo já
   povoado (ver `## Empacotamento e instalador`) e é o mesmo arquivo que
   viaja dentro do `jukebox.squashfs` da release.
2. Se o pacote não existir, ou a extração falhar (`unsquashfs` ausente,
   arquivo corrompido), cai no fallback: cria ~30 gêneros populares de
   bar/jukebox vazios (`GENEROS_PADRAO` no código — sertanejo, pagode,
   funk, rock, mpb, etc.) mais o gênero `YOUTUBE` (onde `guardar_busca()`
   grava o que o cliente encontrar na busca).
3. Cada gênero novo, de qualquer uma das duas formas, ganha uma subpasta
   marcadora `ADICIONE_ARTISTAS_AQUI` — sem ela, `ocultar_vazios` faria o
   gênero recém-criado sumir do carrossel por não ter nenhum artista
   ainda. `limpar_placeholders_de_artista()` roda a cada boot e apaga essa
   pasta sozinha assim que um artista de verdade aparecer ao lado dela; o
   dono do bar não precisa lembrar de limpar nada.

Se já existe qualquer gênero em `musicas/` (mesmo um só), `inicializar_acervo()`
não toca em nada — isto é só para máquina nova ou acervo perdido, nunca
mexe num acervo que já está em uso.

## Regra nova e obrigatória: o moedeiro

O script do aceitador de moedas **não pode mais** escrever no `contador.txt`
direto. Sempre por aqui:

```sh
python3 /userdata/jukebox/creditos.py adicionar 1 --origem moedeiro
```

É isso que garante o lock, a gravação atômica e o registro na auditoria.
Se escrever direto no arquivo, o crédito volta a se perder.

## Comandos úteis

```sh
creditos.py ler                        # saldo atual
creditos.py adicionar 5 --origem teste # crédito de teste
creditos.py total                      # total acumulado (vida inteira, nunca cai)
creditos.py resumo                     # fechamento do dia
creditos.py resumo --dia 2026-08-01    # fechamento de um dia específico
creditos.py zerar --tudo               # zera saldo E totalizador (só antes de instalar!)

senha.py definir 1234                  # define o PIN do menu do operador (3-8 dígitos)
senha.py conferir 1234
senha.py remover                       # menu volta a abrir sem senha
senha.py estado
```

O `resumo` é a base do relatório de acerto com o dono do ponto: soma
inseridos, consumidos, estornados e zerados a partir da auditoria, com
detalhamento por origem (moedeiro, manual, teste etc). O menu do operador
(F12 → RELATÓRIOS → FECHAMENTO DO DIA) mostra a mesma coisa na tela, e
EXPORTAR AUDITORIA gera um `.csv` completo.

## O que a máquina faz hoje (visão funcional)

- **Navegação**: carrossel de gêneros → carrossel de artistas → lista de
  músicas. Gêneros/artistas sem conteúdo ficam ocultos (`ocultar_vazios`).
- **Fila e playlist automática**: com mais de 1 crédito na máquina, o cliente
  já entra "montando fila" sem precisar achar um botão — escolhe várias
  músicas, e quando a fila enche (limitada pelo saldo e por `max_fila`) ela
  toca sozinha depois de uma contagem regressiva (`segundos_auto_play`).
- **Busca no YouTube**: um arquivo marcador `.buscar` dentro de uma pasta
  abre a tela de teclado virtual (`busca.py`) em vez de tocar. O cliente
  digita, vê resultados com duração e canal. ENTER sem marcar nada toca a
  música em destaque na hora (cobrando 1 crédito) pelo mesmo caminho de
  qualquer música — com estorno automático se o vídeo falhar. DIREITA marca
  (checkbox) uma ou mais músicas da lista; ENTER com marcações manda **todas
  direto para a fila** (1, 2, 3, 4... quantas o crédito disponível cobrir),
  tocando normalmente pela fila — **nunca vira arquivo `.m3u`** nessa tela.
  Toda escolha (marcada ou avulsa) vira um `.url` salvo em
  `musicas/YOUTUBE/<artista>/`, então a máquina "aprende": a próxima busca
  pela mesma música já é instantânea, sem rede.
- **Playlists (.m3u) tocam direto pelo cliente**: um `.m3u`/`.m3u8` dentro de
  uma pasta aparece na lista de músicas como qualquer arquivo (`eh_playlist()`
  em `jukebox`). Escolher toca a primeira faixa cobrando 1 crédito normal e
  empilha o resto na fila (`ler_playlist()` lê caminhos relativos à pasta do
  `.m3u` e links `http(s)` direto, com `#EXTINF` opcional só para o nome);
  se a máquina já está "montando fila", todas entram na fila de uma vez,
  respeitando `max_fila`.
- **Criar uma playlist — exclusivo do menu do operador**: a mesma tela de
  busca é reaproveitada por F12 → ACERVO → BUSCAR PARA PLAYLIST
  (`modo_playlist=True` em `TelaBusca.abrir`, mais resultados por busca —
  `resultados_busca_playlist`, padrão 20 — do que a busca comum do cliente).
  Nesse modo, marcar e confirmar **exporta** em vez de enfileirar: grava um
  `.url` por música e um `.m3u` na pasta do gênero escolhido (nomeada pelo
  termo pesquisado; se a pasta já existir, pergunta antes de mesclar em vez
  de sobrescrever). Na tela do cliente, ENTER com marcações sempre enfileira
  — nunca exporta. ESQUERDA com pelo menos uma música marcada, em **qualquer**
  uma das duas telas, pula direto para a escolha de pasta e pede o PIN do
  operador se houver um definido (a menos que o PIN já tenha sido digitado
  há pouco — ver `segundos_validade_senha` abaixo) — é um atalho a mais para
  o operador exportar sem passar pelo F12 → ACERVO primeiro, não uma porta
  aberta para o cliente: sem PIN configurado ela abre igual, então **definir
  o PIN antes de expor a máquina continua obrigatório** (ver `## Antes de
  instalar em ponto real`).
- **Menu do operador (F12)**: sobreposto, sem pausar a reprodução. Protegido
  por PIN (`senha.py`) com bloqueio de 30s após 3 tentativas erradas. O PIN
  digitado certo fica válido por `segundos_validade_senha` (padrão 300s) —
  reabrir o menu ou exportar uma playlist logo em seguida não pergunta de
  novo. Páginas: SOM (volumes, aplicados na hora), CRÉDITOS E PREÇO, ACERVO
  (reindexar sem reiniciar, ver resumo do catálogo SQLite, buscar/criar
  playlist), APARÊNCIA, RELATÓRIOS (fechamento do dia, exportar CSV),
  SISTEMA (reiniciar/desligar com confirmação obrigatória "NÃO" por padrão).
- **Gerenciador de arquivos (F1)**: abre `pcmanfm` por cima, sem derrubar a
  janela do jukebox nem parar a música. Foco volta sozinho ao fechar (ver
  `recuperar_foco()` e o diário em `README.md`).
- **Vídeo do YouTube e de arquivos locais**: mpv decide sozinho se abre janela
  própria ou toca só o áudio, conforme a extensão/URL. Se a fila emenda de
  uma faixa com vídeo (janela própria do mpv) para uma local (sem janela), o
  foco volta sozinho pro jukebox no meio da fila, não só quando ela acaba.
- **Joystick/botões de arcade**: mesmo mapeamento lógico do teclado
  (cima/baixo/esquerda/direita/ok/voltar); botão START (número configurável
  em `operacao.botao_start_joystick`, padrão 7) também marca para playlist,
  mesma ação da seta DIREITA.
- **Som de moeda**: toca ao creditar (moedeiro, manual ou estorno) — nunca ao
  debitar, senão viraria alarme a cada música iniciada.
- **Saída de manutenção**: `Ctrl+Shift+Q`.

## Regra nova e obrigatória: o moedeiro

(ver seção acima)

## O que mudou (marcado com `[FIX]` no código de `jukebox`, `player.py`, `menu.py`, `busca.py`)

**Desempenho — o que importa para 16 h ligado**

1. `pygame.Surface` de tela cheia deixou de ser alocada a cada frame. Era o
   maior desperdício do código: ~8 MB alocados 60×/s em 1080p. Fundo e overlay
   agora são combinados uma única vez no boot.
2. Fontes e textos são criados uma vez e reaproveitados. Antes, `SysFont` era
   instanciada a cada frame e cada item de menu rasterizado 60×/s sem mudar.
3. A tela só é redesenhada quando algo muda (`precisa_desenhar`). Menu parado
   não consome CPU; ainda assim há um repintar periódico de segurança
   (`repintar_a_cada`) e tratamento dos eventos `WINDOWEXPOSED`/etc contra
   tela preta após Alt+Tab.
4. O `contador.txt` era lido do disco a cada frame. Agora, 2×/s.
5. Listagem de diretório com cache de 30 s (`segundos_cache_diretorio`), em
   vez de `os.listdir` a cada navegação.
6. Carrossel: cartão completo montado uma vez por item e cacheado; o
   redimensionamento por escala também é cacheado (degraus de 0,05, descarte
   do mais antigo ao encher). Sem logo, a cor do cartão vem de um hash
   (`crc32`) do nome, então gêneros com nomes parecidos não saem parecidos.
7. Fundo dinâmico: miniaturas 40×24 já escurecidas ficam todas em memória;
   trocar de fundo é só ampliar (~20 ms) em vez de decodificar o PNG de novo.
   Preparo das miniaturas acontece em segundo plano, um gênero por vez, só
   quando a máquina está ociosa.

**Confiabilidade**

8. Crédito atômico (`tmp` + `fsync` + `rename`) com lock `flock`. Testado com
   20 threads disputando 10 créditos: exatamente 10 débitos, saldo zero, nenhum
   crédito duplicado ou perdido.
9. Auditoria em JSONL com rotação: cada crédito inserido, consumido, estornado
   e zerado fica registrado com horário, delta e origem/motivo.
10. **Estorno automático.** Se o crédito foi debitado e a música não tocou
    (arquivo sumiu, mpv falhou, link do YouTube não resolveu), o crédito volta
    sozinho — vale para música avulsa, fila, playlist e busca.
11. `stop()` não dispara mais o `on_finish` — o ESC durante a playlist agora
    cancela de verdade, em vez de emendar a próxima faixa (token de
    reprodução + flag de parada intencional em `player.py`).
12. `terminate()` com `kill()` de reserva: mpv travado não vira zumbi.
13. Fila gravada em disco e retomada após reinício. O cliente não perde o que
    pagou se faltar energia.
14. `try/except` no loop principal e log rotativo. Um nome de arquivo estranho
    não derruba mais a tela para o terminal do Batocera; depois de 60 falhas
    seguidas, sai com código 1 para o supervisor reiniciar.
15. Supervisor com backoff: se o processo cair, volta sozinho, sem loop de
    reinício a 100 % de CPU (`servico-jukebox`); `iniciar.sh` cobre a queda
    logo no boot com um caminho separado (3 quedas rápidas → EmulationStation).
16. Recuperação de foco após F1/fim de vídeo insiste por ~1,5s numa thread à
    parte, em vez de uma tentativa única — corrige uma corrida contra a
    lógica interna do Openbox. Ver investigação completa em `README.md`.
17. Foco também volta sozinho ao emendar, no meio da fila, de uma faixa com
    vídeo (janela própria do mpv) para uma faixa local sem janela — antes só
    `encerrar_reproducao()` chamava `recuperar_foco()`, e ela só roda quando
    a fila inteira acaba, não a cada faixa; o jukebox continuava tocando
    (áudio normal, log sem erro), só que atrás da janela do vídeo anterior.
18. Laço principal parava de fato enquanto o gerenciador de arquivos (F1)
    estava aberto, em vez de só ignorar a navegação: `pygame.event.get()`
    bloqueava com a janela do jukebox coberta, e o laço nunca voltava a
    checar se o `pcmanfm` tinha fechado. Trocado por `time.sleep(0.25)`, que
    não depende do SDL para nada enquanto a outra janela está na frente.

**Funcional**

19. Suporte a `.flac`, `.m4a`, `.ogg`, `.wav`, `.opus`, além de `.mp3`, e a
    vídeo (`.mp4`, `.mkv`, `.webm`, `.avi`, `.mov`, `.m4v`).
20. Suporte a joystick/botões de arcade com o mesmo mapeamento do teclado.
21. Rolagem da lista corrigida: o item selecionado fica centralizado em vez de
    colado no rodapé.
22. Busca no YouTube, playlists `.m3u`, menu do operador com senha e
    totalizador de vida inteira — tudo descrito na seção funcional acima.
23. Playlists `.m3u`/`.m3u8` agora tocam direto pela navegação normal do
    cliente (antes só existiam como saída do menu do operador) — ver
    `## O que a máquina faz hoje` acima.
24. Acervo inicial autossuficiente: máquina nova ou cartão trocado ganha a
    prateleira de gêneros sozinha no primeiro boot, do pacote
    `assets/generos.squashfs` ou de uma lista de gêneros padrão vazios — ver
    `## Acervo inicial (primeiro boot)`.
25. Catálogo SQLite (`catalogo.py`) passou a ser construído pelo próprio
    `jukebox` em segundo plano no primeiro boot (se o banco ainda não
    existe), sem depender do operador rodar `catalogo.py` ou abrir o F12
    manualmente uma vez antes.

## Empacotamento e instalador

Dois scripts na raiz, pensados para uma release no GitHub:

- **`empacotar.sh`** — roda neste repositório (ou em qualquer clone com
  `mksquashfs`) e gera `dist/jukebox.squashfs` + `dist/instalador.sh`
  (cópia) + `dist/SHA256SUMS`. O squashfs leva só o que roda em produção —
  os módulos `.py`, `jukebox`, `iniciar.sh`, `servico-jukebox`,
  `emulationstation-standalone` (cópia de referência), `assets/`,
  `themes/`, `ui/`, `LEIA-ME.md` e o binário standalone do `yt-dlp`
  (`vendor/yt-dlp`, copiado do que estiver no `PATH` de quem empacota).
  **Nunca** `musicas/`, `musicas.bkp/`, `.dev/`, `__pycache__/`, `*.bak*`,
  `config.dev.json` nem `testar.sh` — não é código de produção nem faz
  sentido numa máquina nova. O `config.json` empacotado tem `senha_sal` e
  `senha_resumo` zerados antes de entrar no squashfs — o PIN de uma máquina
  nunca deve viajar para outra dentro da release.
- **`instalador.sh`** — o que o dono do bar roda numa máquina nova (ou para
  atualizar uma já instalada): `wget` do `instalador.sh` da release,
  `sh instalador.sh`. Ele baixa o `jukebox.squashfs` (mesma release —
  `URL_SQUASHFS` no topo do script) ou usa um que já esteja do lado dele,
  extrai, copia o código/assets para `/userdata/system/.dev/apps/Juckbox`
  **sem sobrescrever `config.json` nem `musicas/` já existentes**, instala
  o `yt-dlp` embutido em `/userdata/system/.local/bin`, injeta um bloco
  marcado no `.bashrc` (PATH + atalhos `jk`/`juckebox`/`jklog`/`jkcred`) e
  desvia o `/usr/bin/emulationstation-standalone` real do sistema para
  chamar o `iniciar.sh` do jukebox (guardando o original em
  `emulationstation-standalone.orig` antes de mexer). É seguro rodar de
  novo: cada passo confere se já foi feito antes de repetir.

Publicar a release: gerar os arquivos com `empacotar.sh`, editar a URL
padrão no topo de `instalador.sh` para apontar para a release de verdade
(`https://github.com/<usuario>/<repo>/releases/latest/download/jukebox.squashfs`),
e subir `jukebox.squashfs` + `instalador.sh` (+ `SHA256SUMS`, opcional) como
assets dessa release no GitHub. Isso é feito fora deste repositório/sessão
— publicar uma release é uma ação visível publicamente, então fica a
critério de quem tem acesso ao GitHub do projeto.

**`assets/generos.squashfs` não é versionado** (`.gitignore`): tem ~75MB,
acima do limite de 25MB por arquivo do upload manual pelo site do GitHub
("Add file → Upload files"). Ele é reproduzível a qualquer momento com
`gerar_generos_squashfs.sh` a partir de `musicas/`, e já viaja embutido
dentro do `jukebox.squashfs` da release (que sim, sobe — assets de Release
aceitam até 2GB, é upload por outro caminho, não passa por esse limite).
Quem clonar/baixar só o código-fonte do repositório e quiser esse arquivo
localmente roda `gerar_generos_squashfs.sh` (precisa de `musicas/` povoada)
ou baixa e extrai o `jukebox.squashfs` da última release.

## Aviso sobre `config.dev.json`

Esta config tem `fechar_tela_no_f1: true` e `recuperar_foco: false` de
propósito para teste no desktop. **Não copiar esses dois valores para
produção**: existe um bug latente documentado em `README.md` — se
`fechar_tela_no_f1` voltar a `true` em produção, `JANELA_ID` fica apontando
para uma janela que não existe mais depois que a tela é recriada, e toda
recuperação de foco subsequente fica muda. Em produção (`config.json`) é
`false`/`true`, respectivamente — não inverter.

## Antes de instalar em ponto real

- Testar o ciclo completo do moedeiro pelo CLI.
- Definir o PIN do operador (`senha.py definir <pin>`) antes de expor a
  máquina — sem PIN o menu F12 abre direto para qualquer cliente curioso.
- Deixar rodando um fim de semana e conferir `jukebox.log` e `supervisor.log`.
- Conferir consumo de memória depois de 12 h (`ps aux | grep jukebox`).
- Rodar `conferir_logos.py` e preencher os `logo.png` que faltarem por gênero
  (opcional para artista).
- `themes/neon/theme.json` está vazio e `ui/renderer.py`/`ui/components.py`
  não são usados: ignorar essa pasta até decidir ligar o sistema de temas.
- `creditos.py zerar --tudo` antes de entregar a máquina no ponto, para o
  totalizador começar do zero.

## Catálogo SQLite (passada em andamento)

`catalogo.py` indexa `musicas/` (gênero → artista → arquivo, com tamanho e
data de modificação) num banco SQLite, com o mesmo padrão de escrita atômica
do resto do projeto (arquivo temporário + `rename`). É reconstruído do zero
a cada chamada — sem indexação incremental de propósito: mais simples, e
para o tamanho de acervo esperado leva frações de segundo (191 músicas em
~0,15s neste ambiente de teste).

**Escopo desta passada, de propósito reduzido para não arriscar a operação
ao vivo**: só o catálogo (caminho/gênero/artista/nome). Sem ID3, sem capa
embutida, sem contagem de execuções — cada uma dessas coisas é mais uma
dependência e mais um jeito de travar num arquivo corrompido. A navegação do
cliente **continua** lendo as pastas direto (`listar_pastas`/`listar_musicas`
em `jukebox`), exatamente como antes; o catálogo por enquanto só é lido pelo
menu do operador (F12 → ACERVO → CATÁLOGO (SQLITE), somente leitura).

Reindexação roda em thread separada (nunca trava a tela) e é disparada em
dois momentos: no boot, se o arquivo do catálogo ainda não existir; e sob
comando, no F12 → ACERVO → REINDEXAR (que já limpava os caches em memória —
agora também manda atualizar o catálogo). Testável isoladamente com
`python3 catalogo.py reindexar` / `resumo`, ou `./testar.sh catalogo`.

## Validação feita nesta passada

Testado num desktop com tela real (X de verdade, 1920×1080 — não o driver
`dummy` do SDL, que só serve para o smoke test automatizado e não sobe a
janela de fato). Fluxo confirmado ao vivo, com busca de verdade no YouTube:

- **App sobe limpo** na resolução real, sem os erros de vídeo que aparecem
  no smoke test headless (`jukebox iniciado - 1920x1080`, carrossel e fundo
  renderizando normalmente).
- **Busca → fila, nunca `.m3u`, nunca senha**: busquei "ART POPULAR" de
  verdade, marquei 3 resultados e confirmei. Log confirma cada passo —
  `tela de busca aberta (cliente)` → `busca 'ART POPULAR': 8 resultado(s)` →
  três linhas `busca guardada no acervo: .../Art Popular/*.url` →
  `fila completa (3) - tocando em 10s` — e nenhuma linha de senha ou
  exportação apareceu. As 3 músicas tocaram de verdade uma a uma
  (vídeo do YouTube resolvido e embutido na janela), debitando 1 crédito
  cada, exatamente como qualquer outra música da fila.
- **Catálogo no menu**: F12 → ACERVO → CATÁLOGO (SQLITE) mostrou
  `191 musica(s) (2026-08-30 12:15:06)`, o resumo real do banco gerado por
  `catalogo.py`. REINDEXAR disparou a atualização em segundo plano e o
  aviso `Catálogo: 194 música(s), 106 artista(s), 21 gênero(s)` apareceu
  pouco depois — a contagem já refletindo as 3 músicas novas que a busca
  tinha acabado de salvar no acervo, prova de que o indexador lê o disco de
  verdade a cada chamada.

**Achado durante o teste, fora do escopo desta passada:** com
`video_embutido: true` (valor só de `config.dev.json`, para teste local —
em produção é `false`), enquanto um vídeo está tocando embutido o F12 não
chega ao jukebox; o teclado parece ficar preso na janela filha do mpv
embutida. Não é regressão desta passada (não mexemos em `player.py` nem na
lógica de vídeo embutido) e não afeta produção, que usa `video_embutido:
false` — mpv abre janela própria nesse caso, caminho já coberto por
`recuperar_foco()`. Fica registrado para investigar numa passada futura se
o modo embutido continuar sendo usado em teste.

## Próxima passada

Ler o catálogo SQLite (em vez das pastas) para dar busca por teclado no
acervo local — hoje a busca só existe para o YouTube — e, com o catálogo já
provado em produção, avaliar ID3, capas e contagem de execuções
("mais tocadas") como pontos separados. Ligar (ou remover de vez) o
protótipo de temas em `ui/` também fica pendente. Investigar o F12 travado
durante vídeo embutido (achado acima), se o modo continuar em uso.

**Bug conhecido, ainda não corrigido**: o fallback de `inicializar_acervo()`
(quando `assets/generos.squashfs` não existe ou falha ao extrair — ver
`## Acervo inicial (primeiro boot)`) cria a pasta `YOUTUBE` vazia, mas
**sem** a subpasta `BUSCAR/*.buscar` que `gerar_generos_squashfs.sh` coloca
no pacote. Sem essa pasta, o cliente não tem como abrir a tela de busca do
YouTube pela navegação normal (só funciona quem chegar pelo F12 → ACERVO →
BUSCAR PARA PLAYLIST). Na prática não afeta a release, porque o
`jukebox.squashfs` sempre carrega o `generos.squashfs` de verdade — só
morde numa instalação que caia no fallback puro (squashfs ausente/corrompido
no boot). Correção: em `inicializar_acervo()` (arquivo `jukebox`), no ramo
que cria `GENEROS_PADRAO`, criar também
`os.path.join(MUSIC_PATH, GENERO_BUSCA, "BUSCAR", "Buscar no YouTube.buscar")`
(arquivo vazio) em vez de só `os.makedirs(... GENERO_BUSCA ...)`.
