# Rotinas

Parte da [Documentação](README.md). Os horários e frequências podem ser personalizados na seção `[horarios]` do `config.toml`.

## Onde ver o resultado de cada rotina

- **No mapa:** clique na rotina. A seção **Resultado** da gaveta mostra o que a última rodada fez, o log e os itens que ela guarda, com um botão **Abrir no Obsidian**.
- **Rodar na hora:** o botão **Rodar agora** fica no topo da seção Resultado (e de novo no fim da gaveta). Ao terminar, o resultado se atualiza sozinho. Funciona em qualquer dia e hora, independente do horário agendado.
- **Todos os dias:** os horários padrão de algumas rotinas são só de segunda a sexta. Para rodar também no fim de semana, troque `mon-fri` por `*` em `[horarios]` do `config.local.toml`, por exemplo `resumo_mensagens = "cron: 0 9-18 * * *"`.
- **No cofre:** cada rotina mantém uma nota com o último resultado em `Automateum/Saídas/Rotinas/<rotina>.md` (a pasta vem de `[obsidian] pasta_automateum`). A nota traz estado, resumo, o texto gerado (briefing, fechamento, resumo de mensagens), os itens (tasks) e o log. Coletas de Slack e Gmail só registram quantas mensagens guardaram: o conteúdo delas não vai para o cofre.
- A nota só é reescrita quando o resultado muda, ou no máximo de hora em hora, para não agitar a sincronização do cofre. O `meu_dia` e o `dia_fechado` continuam escrevendo também o bloco na nota do dia.

## Projetos e prompts prontos no Orca

A rotina `prompts das tasks` (frente **Projetos**, a cada 15 min) prepara o começo de cada task: para cada **issue aberta atribuída a você** de um projeto **ativo**, ela cria no Orca uma **worktree** ligada à issue (`issue-<número>-<título>`), abre o Claude Code nela e **digita o prompt na caixa de entrada, sem enviar**. O prompt só vai embora quando você aperta **Enter** no Orca; é isso que autoriza.

- **Regra de segurança:** o Automateum nunca envia. O código só usa `orca terminal send --text` (sem `--enter`) e nunca usa `--agent` com `--prompt` (que enviaria sozinho). Há testes para isso. O texto passa por uma limpeza (sem caracteres de controle, no máximo 6000 caracteres).
- **As outras issues:** as que não são suas ficam listadas na gaveta ("Abertas, ainda sem prompt"). O botão **Começar** aceita a issue: a rotina roda na hora e prepara o prompt dela. Aceitas não gastam as vagas de `max_pendentes`.
- **Um cartão por projeto:** cada projeto aparece no mapa ligado à frente Projetos. A gaveta dele tem o botão Ativar/Desativar, as issues esperando e, em cada prompt pronto, o botão **Ver prompt**, que mostra o texto inteiro (o Claude Code esconde textos longos atrás de um cartão; `Ctrl+G` também abre no editor). O texto fica em `dados/prompts/` só neste computador e não é servido ao celular.
- **Digitar de novo:** cada prompt pronto tem o botão **Digitar de novo**. Se você fechou o terminal, ele abre outro Claude Code na mesma worktree (sem criar outra) e digita o prompt de novo, ainda sem enviar.
- **Revisão de PR:** a rotina `revisões de PR` (frente Projetos, 15 min) pega os PRs abertos do projeto ativo que **pedem a sua revisão**, busca o branch do PR (leitura, `git fetch`), cria uma worktree nele no Orca e deixa o prompt de revisão digitado, sem enviar. O prompt pede para ler o diff, apontar bugs, riscos e testes que faltam e propor correções **em texto**, sem alterar arquivo e sem comentar, aprovar ou pedir mudanças no GitHub. Aparecem na gaveta do projeto, com Ver prompt e Digitar de novo. Chaves do projeto: `revisar = false` desliga, `max_revisoes` (padrão 3), `modelo_revisao` (com `{numero}`, `{titulo}`, `{url}`, `{branch}`, `{base}`, `{corpo}`). PR vindo de fork é ignorado. **Chave "todos os PRs":** na gaveta do projeto, uma chave (Ligar/Desligar) faz a rotina procurar todo PR aberto, inclusive os seus (o GitHub não deixa pedir revisão ao próprio autor); desligada, só os que pedem a sua revisão. Também vale `revisar_quais = "todos"` no config como valor inicial.
- **Ativar e desativar:** no mapa, clique na rotina **prompts das tasks**; a seção **Projetos** da gaveta tem um botão por projeto. Projetos nascem desativados.
- **Config (`config.toml` ou `config.local.toml`):** `[projetos.<id>]` com `nome`, `github` (dono/repo, que também precisa estar no Orca), `rotulo` (opcional: só issues com essa etiqueta), `max_pendentes` (padrão 3: quantos prompts prontos ficam de uma vez; fechar a issue libera a vaga) e `modelo` (opcional, com `{numero}`, `{titulo}`, `{url}`, `{corpo}`). No máximo 2 worktrees novas por rodada (as aceitas com Começar: até 5).
- **Texto padrão:** título, link e corpo da issue, mais "leia o que for preciso e me proponha um plano antes de alterar qualquer arquivo; não faça commit, push nem abra PR sem eu pedir".
- **Precisa de:** o app do Orca aberto (o serviço **Orca** do mapa mostra isso), o token do GitHub e o `claude` instalado. As worktrees são criadas sem rodar os scripts de setup do repositório.
- O corpo das issues não vai para o cofre: a nota da rotina só lista número e título.

## Qual IA escreve os resumos

`meu_dia`, `dia_fechado` e `resumo_mensagens` usam o **Claude** (`claude -p`) e, se ele falhar ou não estiver instalado, o **Copilot** (`copilot`, a CLI do GitHub Copilot). Quando o texto sai pelo motor de reserva, o log da rodada diz por quê.

- **Botão:** no mapa, clique no serviço **Claude** e, na seção **Motor dos resumos**, use **Usar o Copilot como principal** (ou o contrário). O motor escolhido passa a ser o principal e o outro vira a reserva. A escolha fica guardada.
- **Config (opcional):** `[ia] motor = "copilot"` define o inicial; `[copilot] modelo = "..."` e `timeout_segundos` ajustam a CLI.
- **Copilot:** precisa da CLI instalada e logada (`copilot`, com o login feito uma vez no terminal). O Automateum não libera nenhuma ferramenta para ele: só manda o texto e lê a resposta.
- **Privacidade:** o texto vai para o motor que responder. Com o Copilot, vai para o GitHub/Microsoft.

## Sistema

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `saude` | a cada 2 min | Máquina | Checa a integridade da máquina (CPU, memória, disco) e de cada serviço configurado. Atualiza o status da coluna de serviços. Mede todos os discos fixos (ou só os de `[maquina] discos`, por exemplo `["C:", "D:"]`) e guarda uma medição por rodada (7 dias) para o fechamento do dia. |

## Mensagens

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `coletar_slack` | a cada 15 min | Slack | Guarda as mensagens novas das conversas configuradas desde a última coleta. Na primeira execução busca as últimas 24h. **Só alguns canais:** `[slack] canais = ["geral", "dev"]` (nome sem `#`, vale nos dois modos) mantém só esses canais; vazio = todos. No modo `navegador`, DMs e suas anotações seguem entrando; `dms = false` deixa só os canais. `canais_marcados = ["canal-movimentado"]` (modo `navegador`) guarda de um canal **só o que cita você** (`@seu nome`, vindo de `meu_nome` ou de `marcas`) e apenas o trecho em volta da citação (~160 caracteres antes e ~240 depois). O que já estava guardado de um canal que saiu da lista, ou de um canal marcado sem citar você, é apagado na próxima coleta. |
| `coletar_gmail` | a cada 15 min | Gmail | Captura e-mails não lidos da caixa de entrada ainda não processados. |
| `resumo_mensagens` | de hora em hora, 9h às 18h, seg a sex | Claude, Obsidian | Resume as comunicações recebidas no período e registra em `Automateum/Saídas/Mensagens/AAAA-MM-DD.md`. |

## Tasks

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `tasks_obsidian` | a cada 30 min | Obsidian | Varre o cofre do Obsidian por checkboxes abertos (`- [ ]`) e armazena a lista com referência de nota e linha. |
| `tasks_github` | a cada 30 min | GitHub | Busca issues e PRs atribuídos e PRs aguardando revisão. |

## Notas

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `meu_dia` | 08:30, seg a sex | Obsidian, Claude | Agrega tarefas abertas, mensagens recentes, notas dos últimos diários e notas de contexto recentes, escrevendo o briefing matinal no diário de hoje. |
| `dia_fechado` | 19:00, seg a sex | Obsidian, Claude | Lê as anotações do dia, resumos de mensagens e tarefas concluídas/pendentes, registrando o fechamento no diário. Termina com uma linha da máquina (média e pico de CPU e memória, o disco livre de cada disco, desde quando está ligada), calculada pelas medições e não escrita pelo Claude. A temperatura não entra: o Windows não a expõe sem um programa de monitoramento à parte. |

## Estrutura dos Briefings

### Meu dia
- **Prioridades:** até 5 itens ordenados por urgência e impacto, com referência da nota ou repositório
- **Envelhecendo:** pendências antigas demandando ação (executar, delegar ou descartar)
- **Responder:** mensagens e e-mails que requerem retorno

### Dia fechado
- **Andou:** realizações e tarefas finalizadas ou avançadas
- **Ficou aberto:** o que foi previsto mas não pôde ser concluído
- **Amanhã:** primeiros passos recomendados para o dia seguinte

## Ideias e Próximos Passos

- Acesso ao painel pelo celular fora do Wi-Fi (hoje só pela rede local; ver docs/Painel.md)
- Preparação de pautas automatizadas para reuniões a partir de notas de reuniões recentes
- Sinalização visual no cofre para tasks com mais de N dias sem movimentação
- Resumo executivo semanal

