# ⚡ Automateum

  O **Automateum** é um assistente de produtividade e automação pessoal que centraliza notificações, pendências e
comunicações (Slack, Gmail, GitHub e notas do Obsidian) e gera resumos inteligentes com IA (Claude) direto na sua
rotina diária.

  Com uma interface web/painel local construído em FastAPI e agendamento de tarefas via APScheduler, o Automateum
organiza seu dia e mantém seu cofre do Obsidian atualizado com suas tarefas e resumos diários.

  ---

  ## 🚀 Funcionalidades

  - **📥 Centralização de Mensagens & Comunicações:**
    - **Slack:** Leitura e consolidação de canais públicos, privados e mensagens diretas.
    - **Gmail:** Filtro e captura inteligente de e-mails prioritários e não lidos.
    - **GitHub:** Rastreamento de issues e pull requests atribuídos a você.
  - **🧠 Resumos Inteligentes com Claude:**
    - Geração de resumos periódicos e digest do seu dia com modelos Claude (Sonnet).
  - **📝 Integração Nativa com Obsidian:**
    - Extração de tarefas e escrita direta nas notas diárias do seu cofre (`vault`).
  - **⏰ Rotinas Automatizadas:**
    - Agendamento flexível de rotinas em horários configuráveis (estilo cron) via APScheduler.
  - **🖥️ Painel Local:**
    - Interface web leve servida via FastAPI/Uvicorn para monitoramento e controle.

  ---

  ## 🛠️ Tecnologias Utilizadas

  - **Linguagem:** Python 3.11+
  - **API / Web:** [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
  - **Agendamento:** [APScheduler](https://apscheduler.readthedocs.io/)
  - **Integrações:**
    - [Slack SDK](https://github.com/slackapi/python-slack-sdk)
    - [Google API Client](https://github.com/googleapis/google-api-python-client)
    - GitHub REST API
    - Claude (Anthropic / Claude Code CLI)
  - **Configurações & Armazenamento:** TOML (`tomllib`), SQLite, `python-dotenv`

  ---

  ## 📋 Pré-requisitos

  - Python 3.11 ou superior instalado
  - Tokens de acesso para as integrações que desejar usar (GitHub, Slack, Google/Gmail)

  ---

  ## ⚙️ Instalação e Configuração

  ### 1. Clonar o repositório
  ```bash
  git clone https://github.com/seu-usuario/automateum.git
  cd automateum

### 2. Criar e ativar o ambiente virtual

  # Windows
  python -m venv .venv
  .venv\Scripts\activate

  # Linux / macOS
  python -m venv .venv
  source .venv/bin/activate

### 3. Instalar as dependências

  pip install -r requirements.txt

### 4. Configurar variáveis de ambiente e arquivo TOML

Copie o template de ambiente:

  cp .env.example .env

Preencha os tokens no .env:

  GITHUB_TOKEN=ghp_...
  SLACK_TOKEN=xoxp-...

Ajuste as preferências no arquivo config.toml (como caminho do seu cofre do Obsidian, canais do Slack, consultas do
Gmail e horários das rotinas).
──────
## 🏃 Como Executar

(Adicione aqui o comando de entrada quando implementar o entrypoint principal, ex.: python -m automateum ou uvicorn
automateum.main:app --reload)
