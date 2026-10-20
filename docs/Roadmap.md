# Roadmap

Parte da [Documentação](README.md).

Planejamento de etapas e guia para configuração de cada serviço.

---

## Etapas de Desenvolvimento

### Etapa 1 — Esqueleto e Painel Vivo
- [x] Registro de rotinas e serviços com metadata
- [x] Agendador com persistência de execuções
- [x] Banco de dados SQLite local
- [x] Rotina de saúde da máquina e conectividade dos serviços (`saude`)
- [x] Varredura de tarefas do Obsidian (`tasks_obsidian`)
- [x] API REST e streaming SSE do painel
- [x] Interface gráfica com mapa, nós interativos, zoom e pan
- [x] Painel lateral com log e trigger de execução manual

### Etapa 2 — GitHub
- [x] Implementação da rotina `tasks_github`
- [x] Configuração do token GitHub no `.env`
- [x] Validação da rotina com dados reais

### Etapa 3 — Claude e Escrita no Obsidian
- [x] Cliente Claude Code headless (`claude -p`) sem tools
- [x] Rotinas `meu_dia` e `dia_fechado`
- [x] Testes de inserção e atualização atômica de blocos Markdown
- [ ] Validação contínua do briefing e fechamento no diário

### Etapa 4 — Slack
- [x] Implementação das rotinas `coletar_slack` e `resumo_mensagens`
- [x] Slack pelo navegador (`[slack] modo = "navegador"`): login, coleta e resumo validados com conta real
- [x] Validação de coleta e sumarização (a segunda rodada devolve "nada novo", sem duplicar)
- [ ] Opcional: app com token (`modo = "app"` e `SLACK_TOKEN` no `.env`), para um workspace que aceite instalar o app

### Etapa 5 — Gmail
- [x] Implementação da rotina `coletar_gmail`
- [x] Configuração do cliente OAuth Google Cloud Desktop
- [x] Execução do fluxo de autorização (`python -m automateum gmail-login`)
- [x] Validação de coleta de mensagens (segunda rodada devolve "nada novo")
- [x] Mensagem clara no painel quando a autorização expira (modo Testing vence em 7 dias)

### Etapa 6 — Inicialização do Sistema
- [x] Agendamento de inicialização automática no logon do Windows

### Etapa 7 — Painel e celular
- [x] Resultado de cada rotina no cofre e na gaveta, com histórico por dia
- [x] Máquina no fechamento do dia (CPU, memória, discos) e gráfico de 24 horas no mapa
- [x] Seis estilos e seis organizações do mapa, sininho com os textos do dia e modo painel
- [x] Leitura pelo celular no mesmo Wi-Fi (opcional, só leitura, com chave)

### Etapa 8 — Projetos no Orca
- [x] Prompt de cada issue atribuída a você digitado numa worktree do Orca, nunca enviado (#26)
- [x] Começar, Ver prompt e Digitar de novo na gaveta do projeto
- [x] Revisão de PR com o prompt de revisão pronto, e a chave para todos os PRs
- [ ] Cadastrar outros projetos (`[projetos.<id>]` no `config.local.toml`)

### Etapa 9 — Motor dos resumos
- [x] Copilot CLI como reserva automática do Claude, com botão para trocar o principal

---

## Como Configurar as Credenciais

Enquanto uma credencial não estiver configurada, o respectivo serviço é exibido em cinza no painel e suas rotinas não serão disparadas.

### GitHub
1. Acesse **GitHub → Settings → Developer settings → Personal access tokens** (Fine-grained ou Classic).
2. Configure permissões de somente leitura para **Issues** e **Pull requests**.
3. Adicione ao `.env`:
   ```env
   GITHUB_TOKEN=ghp_...
   ```

### Slack
Há dois modos, escolhidos em `[slack] modo` no `config.local.toml`. Os dois só leem; nenhum envia mensagem.

**Modo `navegador`:** um coletor externo (fora do repositório) abre o Slack web num perfil próprio do Chrome, com a sua conta, e gera um texto com as mensagens. Não precisa instalar app no workspace. Precisa de Node, Python e Chrome.
1. Coloque a pasta do coletor num lugar fixo e rode o `logar.ps1` dela uma vez para entrar no Slack.
2. Configure `modo`, `kit` e, se quiser, `fora`, `time` e `meu_nome` (veja `config.local.example.toml`).
3. A colheita leva de 1 a 25 minutos: ponha um horário espaçado em `[horarios] coletar_slack`.
4. Rode `python -m automateum rodar coletar_slack` para validar. Use esse modo só se as normas do seu workspace permitirem a leitura automatizada.

**Modo `app` (padrão):**
1. Crie um app em [api.slack.com/apps](https://api.slack.com/apps) no seu workspace.
2. Em **OAuth & Permissions**, adicione os escopos de usuário (**User Token Scopes**):
   - `channels:history`, `groups:history`, `im:history`, `mpim:history`
   - `channels:read`, `groups:read`, `im:read`, `mpim:read`, `users:read`
3. Instale o app no workspace.
4. Adicione o token gerado (`xoxp-...`) ao `.env`:
   ```env
   SLACK_TOKEN=xoxp-...
   ```

### Orca
1. Instale e abra o app do Orca, e adicione nele o repositório do projeto.
2. Cadastre o projeto em `[projetos.<id>]` (`nome` e `github = "dono/repo"`) no `config.local.toml`.
3. No mapa, clique em **prompts das tasks** e use **Ativar** na seção Projetos.

### Copilot (opcional, reserva dos resumos)
1. Instale a CLI do GitHub Copilot (`copilot`) e faça o login uma vez no terminal.
2. O serviço Claude, no mapa, ganha a seção **Motor dos resumos** para escolher o principal.

### Gmail
1. Crie um projeto no [Google Cloud Console](https://console.cloud.google.com/) e habilite a **Gmail API**.
2. Configure a tela de consentimento OAuth e cadastre seu e-mail como usuário de teste.
3. Crie uma credencial de **OAuth Client ID** do tipo **Desktop App** e faça o download do JSON.
4. Salve o arquivo como `dados/gmail_credentials.json`.
5. Execute no terminal:
   ```bash
   python -m automateum gmail-login
   ```
   e conclua a autorização no navegador.

---

## Backlog de Melhorias
- Mostrar o outro PC no mapa (#22)
- Integração com Google Agenda (#23)
- Resumo das transcrições de reuniões (#24)
- Várias IAs gratuitas pelas automações, a definir (#27)
