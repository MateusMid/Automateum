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
- [ ] Configuração do token GitHub no `.env`
- [ ] Validação da rotina com dados reais

### Etapa 3 — Claude e Escrita no Obsidian
- [x] Cliente Claude Code headless (`claude -p`) sem tools
- [x] Rotinas `meu_dia` e `dia_fechado`
- [x] Testes de inserção e atualização atômica de blocos Markdown
- [ ] Validação contínua do briefing e fechamento no diário

### Etapa 4 — Slack
- [x] Implementação das rotinas `coletar_slack` e `resumo_mensagens`
- [ ] Configuração das credenciais do Slack no `.env`
- [ ] Validação de coleta e sumarização

### Etapa 5 — Gmail
- [x] Implementação da rotina `coletar_gmail`
- [ ] Configuração do cliente OAuth Google Cloud Desktop
- [ ] Execução do fluxo de autorização (`python -m automateum gmail-login`)
- [ ] Validação de coleta de mensagens

### Etapa 6 — Inicialização do Sistema
- [ ] Agendamento de inicialização automática no logon do Windows

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
1. Crie um app em [api.slack.com/apps](https://api.slack.com/apps) no seu workspace.
2. Em **OAuth & Permissions**, adicione os escopos de usuário (**User Token Scopes**):
   - `channels:history`, `groups:history`, `im:history`, `mpim:history`
   - `channels:read`, `groups:read`, `im:read`, `mpim:read`, `users:read`
3. Instale o app no workspace.
4. Adicione o token gerado (`xoxp-...`) ao `.env`:
   ```env
   SLACK_TOKEN=xoxp-...
   ```

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
- Temas para o painel com alternância entre modo claro e escuro
- Animação do fluxo de dados com controle de velocidade
- Suporte a monitoramento de nós remotos/múltiplas máquinas
- Integração com Google Agenda
- Automação de prompts e tarefas
