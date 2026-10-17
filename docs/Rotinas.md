# Rotinas

Parte da [Documentação](README.md). Os horários e frequências podem ser personalizados na seção `[horarios]` do `config.toml`.

## Onde ver o resultado de cada rotina

- **No mapa:** clique na rotina. A seção **Resultado** da gaveta mostra o que a última rodada fez, o log e os itens que ela guarda, com um botão **Abrir no Obsidian**.
- **No cofre:** cada rotina mantém uma nota com o último resultado em `Automateum/Saídas/Rotinas/<rotina>.md` (a pasta vem de `[obsidian] pasta_automateum`). A nota traz estado, resumo, o texto gerado (briefing, fechamento, resumo de mensagens), os itens (tasks) e o log. Coletas de Slack e Gmail só registram quantas mensagens guardaram: o conteúdo delas não vai para o cofre.
- A nota só é reescrita quando o resultado muda, ou no máximo de hora em hora, para não agitar a sincronização do cofre. O `meu_dia` e o `dia_fechado` continuam escrevendo também o bloco na nota do dia.

## Sistema

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `saude` | a cada 2 min | Máquina | Checa a integridade da máquina (CPU, memória, disco) e de cada serviço configurado. Atualiza o status da coluna de serviços. Mede todos os discos fixos (ou só os de `[maquina] discos`, por exemplo `["C:", "D:"]`) e guarda uma medição por rodada (7 dias) para o fechamento do dia. |

## Mensagens

| Rotina | Quando | Depende de | O que faz |
|---|---|---|---|
| `coletar_slack` | a cada 15 min | Slack | Guarda as mensagens novas das conversas configuradas desde a última coleta. Na primeira execução busca as últimas 24h. |
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

- Visualização do painel no celular direto pelo navegador (HTML responsivo / rede local)
- Preparação de pautas automatizadas para reuniões a partir de notas de reuniões recentes
- Sinalização visual no cofre para tasks com mais de N dias sem movimentação
- Resumo executivo semanal

