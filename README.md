# ⚡ Automateum

O **Automateum** é um assistente de produtividade e automação pessoal que centraliza notificações, pendências e
comunicações (Slack, Gmail, GitHub e notas do Obsidian) e gera resumos inteligentes com IA (Claude) direto na sua
rotina diária.

Com uma interface web/painel local construído em FastAPI e agendamento de tarefas via APScheduler, o Automateum
organiza seu dia e mantém seu cofre do Obsidian atualizado com suas tarefas e resumos diários.

---

## 🚀 Funcionalidades

- **📥 Centralização de Mensagens & Comunicações:**
  - **Slack:** Leitura e consolidação de canais públicos, privados e mensagens diretas, por um app com token ou por um coletor que lê o Slack web com a sua conta (modo `navegador`).
  - **Gmail:** Filtro e captura inteligente de e-mails prioritários e não lidos.
  - **GitHub:** Rastreamento de issues e pull requests atribuídos a você.
- **🧠 Resumos Inteligentes com Claude:**
  - Briefing da manhã, resumo das mensagens de hora em hora e fechamento do dia, pelo Claude Code (`claude -p`).
    Se ele falhar, o Copilot (CLI `copilot`) responde no lugar; um botão no mapa troca qual é o principal.
- **📝 Integração Nativa com Obsidian:**
  - Extração de tarefas e escrita direta nas notas diárias do seu cofre (`vault`).
  - Uma nota por rotina com o último resultado e um arquivo por dia com o histórico dos textos gerados.
- **🧑‍💻 Projetos no Orca:**
  - Cada issue atribuída a você ganha uma worktree no Orca com o Claude Code aberto e o prompt **digitado, sem
    enviar**; as outras esperam o botão Começar. Os PRs que pedem a sua revisão ganham um prompt de revisão do
    mesmo jeito. Nada sai até você apertar Enter no Orca.
- **⏰ Rotinas Automatizadas:**
  - Agendamento flexível de rotinas em horários configuráveis (estilo cron) via APScheduler.
- **🖥️ Painel Local:**
  - Mapa ao vivo da máquina, dos serviços e das rotinas, com seis estilos e seis organizações, gaveta de detalhes,
    botões de rodar, ligar e desligar, sininho com os textos do dia e gráfico de CPU e memória.
  - Opcional: leitura pelo celular no mesmo Wi-Fi, com QR code e chave (só leitura).

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem:** Python 3.11+
- **API / Web:** [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **Agendamento:** [APScheduler](https://apscheduler.readthedocs.io/)
- **Integrações:**
  - [Slack SDK](https://github.com/slackapi/python-slack-sdk)
  - [Google API Client](https://github.com/googleapis/google-api-python-client)
  - GitHub REST API
  - Claude (Claude Code CLI, `claude -p`) e GitHub Copilot CLI (`copilot`), de reserva
  - Orca (CLI `orca`), para as worktrees e os prompts das tasks
- **Configurações & Armazenamento:** TOML (`tomllib`), SQLite, arquivo `.env`
- **Painel:** HTML, CSS e JavaScript puros, sem etapa de build; [segno](https://github.com/heuer/segno) para o QR do celular

---

## 📋 Pré-requisitos

- Python 3.11 ou superior instalado
- [Claude Code](https://claude.com/claude-code) instalado e logado, para os resumos
- Tokens de acesso para as integrações que desejar usar (GitHub, Slack, Google/Gmail)
- Opcionais: a CLI do GitHub Copilot (`copilot`, motor de reserva dos resumos), o app do Orca aberto (para os
  prompts das tasks) e Node com Chrome (para o Slack pelo modo `navegador`)

---

## ⚙️ Instalação e Configuração

### 1. Clonar o repositório

```bash
git clone https://github.com/MateusMid/Automateum.git
cd Automateum
```

### 2. Criar e ativar o ambiente virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente e arquivo TOML

Copie o template de ambiente e o template de configuração local:

```bash
cp .env.example .env
cp config.local.example.toml config.local.toml
```

Preencha os tokens no `.env`:

```
GITHUB_TOKEN=github_pat_...
SLACK_TOKEN=xoxp-...
```

Configure o caminho do seu cofre do Obsidian em `config.local.toml`:

```toml
[obsidian]
cofre = 'C:\Users\seu_usuario\Documents\SeuCofre'
```

Para ler o Slack sem criar um app (modo `navegador`), aponte para a pasta do coletor, que fica fora do repositório. Ele precisa de Node, Python e Chrome, e o login é feito uma vez pelo `logar.ps1` do próprio coletor:

```toml
[slack]
modo = "navegador"
kit = 'C:\Users\seu_usuario\.automateum\kit-slack'
meu_nome = "Seu Nome"   # suas próprias mensagens não entram no resumo

# a colheita leva de 1 a 25 minutos: use um horário espaçado
[horarios]
coletar_slack = "cron: 30 8-18 * * mon-fri"
```

Sem `modo`, vale o padrão `app`, que usa o `SLACK_TOKEN` do `.env`. Use o modo `navegador` só se as normas do seu workspace permitirem essa leitura automatizada.

O `config.local.toml` é ignorado pelo git e sobrepõe apenas as configurações específicas da sua máquina. Ajuste preferências gerais e horários em `config.toml`.

Para o Gmail, salve o cliente OAuth do tipo "Desktop" do Google Cloud em `dados/gmail_credentials.json` e rode
`python -m automateum gmail-login` uma vez.

Sem a credencial de um serviço, ele aparece cinza no painel e as rotinas que dependem dele não rodam.

---

## 🏃 Como Executar

```bash
python -m automateum
```

O painel abre em <http://127.0.0.1:8765>.

### Iniciar junto com o Windows

```powershell
scripts\instalar-inicio.ps1      # registra a tarefa "Automateum" no logon e sobe agora (-SemIniciar só registra)
scripts\desinstalar-inicio.ps1   # para e remove a tarefa
```

A tarefa roda `.venv\Scripts\pythonw.exe -m automateum` sem janela. Sem terminal, tudo vai para
`dados/automateum.log` (rotação de 1 MB, 3 arquivos); é lá que aparece um erro de subida. Para parar sem remover:
`Stop-ScheduledTask -TaskName Automateum`. O comando `claude` precisa estar no PATH do usuário, não só do terminal.

Outros comandos:

```bash
python -m automateum rodar tasks_obsidian   # roda uma rotina uma vez e mostra o resultado
python -m automateum gmail-login            # autoriza a leitura do Gmail
python -m pytest -q tests                   # testes
```

---

## 🧩 Criar uma Rotina

Um arquivo em `automateum/rotinas/`, importado em `automateum/rotinas/__init__.py`. O painel é desenhado a partir
desse registro, então a rotina nova aparece no mapa sem mexer no HTML.

```python
from ..nucleo.registro import rotina

@rotina(id="exemplo", nome="exemplo", frente="Tasks", quando="cada 30m", usa=["obsidian"])
def rodar(ctx):
    """A primeira linha vira a descrição no painel."""
    ctx.log("aparece no log da execução")
    return "vira o resumo no cartão"
```

`quando` aceita `"cada 15m"`, `"cron: 30 8 * * mon-fri"` (dias da semana por nome) ou `"nunca"`.

---

## 📚 Documentação Completa

A documentação detalhada de escopo, arquitetura e rotinas está disponível na pasta [`docs/`](docs/README.md):

- [Escopo](docs/Escopo.md) — Objetivos, o que entra, limites e regras de segurança.
- [Arquitetura](docs/Arquitetura.md) — As 5 colunas do mapa, estrutura do código e ciclo de vida.
- [Rotinas](docs/Rotinas.md) — Catálogo de rotinas, horários e formato dos briefings.
- [Painel](docs/Painel.md) — Referência visual e guia de navegação no mapa.
- [Roadmap](docs/Roadmap.md) — Etapas, setup de credenciais (Slack, Gmail, GitHub) e backlog.

---

## 🔒 O que as Rotinas Podem Escrever

No cofre, só em `Automateum/Saídas/` e em blocos `%% automateum:<nome>:inicio %%` … `%% automateum:<nome>:fim %%`
na nota do diário do dia. O que estiver fora do bloco nunca é alterado.

Slack, Gmail e GitHub são só leitura.

