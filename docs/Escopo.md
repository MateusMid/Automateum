# Escopo

Parte da [Documentação](README.md).

## Objetivo

Automatizar o fluxo de trabalho diário: em vez de abrir Slack, Gmail, GitHub e o Obsidian para descobrir o que mudou e o que tenho que fazer, um conjunto de rotinas coleta isso sozinho, resume e deixa anotado. Um painel mostra o que está rodando, o que falhou e por quê.

A inspiração é o painel de referência (imagem em [Painel](Painel.md)).

## O que entra na primeira versão

**Mensagens**
- Slack: mensagens novas dos canais e DMs configuradas
- Gmail: e-mails não lidos da caixa de entrada
- Resumo de hora em hora do que chegou, com o que pede resposta prioritária primeiro

**Tasks**
- Obsidian: todos os checkboxes abertos (`- [ ]`) do cofre configurado, com nota e linha
- GitHub: issues e PRs atribuídos e PRs esperando revisão

**Notas no Obsidian**
- Briefing de manhã ("Meu dia") escrito na nota do diário
- Fechamento à noite ("Dia fechado") na mesma nota
- Resumos de mensagens em `Automateum/Saídas/Mensagens/`

**Painel**
- Mapa em HTML com máquina → serviços → frentes → rotinas → avisos
- Estado ao vivo, histórico de execuções, log e botão para rodar na hora

## O que fica de fora

- **Enviar qualquer coisa.** Nenhuma rotina manda mensagem, responde e-mail ou mexe em issue. Slack, Gmail e GitHub são só leitura.
- **WhatsApp e Telegram.** Não entraram nesta versão.
- **Notion, ClickUp e outros gestores de tarefa externos.**
- **Aviso no celular.** Os avisos aparecem só no painel por enquanto.
- **Acesso de fora da rede local.** O painel escuta só na máquina local (`127.0.0.1`).
- **Mexer nas notas pessoais.** As rotinas não editam, movem nem apagam nada além das saídas e blocos controlados.

## Decisões

| Decisão | Escolha | Motivo |
|---|---|---|
| Fontes de mensagem | Slack e Gmail | Onde chega a maior parte das comunicações de trabalho |
| Fontes de task | Obsidian e GitHub | Onde as tarefas e pendências de desenvolvimento residem |
| Cofre | Obsidian local | Controle total dos dados em Markdown local |
| Resumos | Claude Code headless (`claude -p`) | Uso direto do modelo sem necessidade de API key adicional |
| GitHub | API REST com token / gh | Acesso seguro e somente leitura |
| Banco | SQLite local | Leve, embutido e sem necessidade de infraestrutura extra |
| Painel | HTML, JS e SVG puros | Leve, sem necessidade de etapa de build (Node/npm) |

## Regras de segurança

1. **Escrita no cofre só em dois lugares:** a pasta `Automateum/Saídas/` e blocos delimitados no fim da nota do diário (`%% automateum:meu_dia:inicio %%` … `%% automateum:meu_dia:fim %%`). O que está fora do bloco nunca é tocado.
2. **Gravação atômica:** escreve num arquivo temporário e renomeia, para plugins de sincronização nunca sincronizarem um arquivo pela metade.
3. **O Claude roda sem ferramentas.** O conteúdo de mensagens e e-mails é tratado estritamente como dado a resumir; não dispara nenhuma ação no sistema.
4. **Tokens só no `.env` e configurações locais em `config.local.toml`,** fora do controle de versão git.

## Critérios de Sucesso

- Abrir o painel de manhã e saber imediatamente o que chegou e o que priorizar.
- A nota do diário já conter o briefing consolidado para o início do dia de trabalho.
- Se qualquer rotina quebrar, o painel indicar precisamente qual, por quê e qual serviço falhou.
