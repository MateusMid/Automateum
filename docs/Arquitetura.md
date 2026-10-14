# Arquitetura

Parte da [Documentação](README.md).

Um único processo Python local faz tudo: agenda as rotinas, guarda o estado e serve o painel.

```
python -m automateum
   ├── agendador  → dispara cada rotina no horário dela (APScheduler)
   ├── estado     → SQLite com execuções, checagens, itens coletados e avisos
   ├── API        → rotas FastAPI entregando o mapa e detalhes
   └── painel     → HTML/CSS/JS que desenha o mapa e escuta eventos via SSE
```

## As cinco colunas do mapa

| Coluna | O que é | Exemplos |
|---|---|---|
| Máquina | O computador onde tudo roda | CPU, memória, disco, IP |
| Serviços | De onde vêm e para onde vão os dados | Slack, Gmail, GitHub, Obsidian, Claude |
| Frentes | Agrupamento das rotinas por assunto | Sistema, Mensagens, Tasks, Notas |
| Rotinas | O trabalho em si | ver [Rotinas](Rotinas.md) |
| Com você | Onde o resultado chega | Diário, notas do Automateum, avisos |

## Estrutura do código

```
automateum/
  __main__.py     entrada: sobe o painel, roda uma rotina avulsa, login do Gmail
  config.py       lê config.toml, config.local.toml e .env
  nucleo/
    registro.py   catálogo de serviços e rotinas (@rotina)
    agendador.py  agenda e executa as rotinas
    estado.py     armazenamento SQLite
    eventos.py    barramento SSE para avisar o painel em tempo real
    grafo.py      monta nós e arestas do mapa do painel
  servicos/       clientes de integração (slack, gmail, github, obsidian, claude, maquina)
  rotinas/        implementação de cada rotina
  web/            API FastAPI e estáticos do painel (HTML, CSS, JS)
config.toml       horários, canais e preferências padrão
config.local.toml sobreposições locais da máquina (fora do git)
.env              tokens e credenciais (fora do git)
dados/            banco SQLite e token do Gmail (fora do git)
```

## Como nasce uma rotina

Uma rotina é uma função decorada com `@rotina` que especifica frente, dependências de serviços e periodicidade. O mapa do painel é construído dinamicamente a partir desse registro:

```python
@rotina(id="tasks_obsidian", nome="tasks do cofre", frente="Tasks",
        quando="cada 30m", usa=["obsidian"])
def rodar(ctx):
    """Varre o cofre atrás de checkboxes abertos."""
    tasks = obsidian.tasks_abertas(ctx.config)
    ctx.estado.substituir_itens("obsidian", tasks)
    return f"{len(tasks)} abertas"
```

- `quando` aceita `"cada 15m"`, `"cron: 30 8 * * mon-fri"` ou `"nunca"`.
- O retorno textual vira o resumo exibido no cartão do painel.
- Se a função levanta exceção, a execução é gravada como falha e gera um aviso no painel.
- Se falta credencial de um serviço em `usa`, a rotina fica cinza e não roda.

## Estados do Painel

| Cor | Estado | Significado |
|---|---|---|
| Ciano | ok | Rodou com sucesso |
| Âmbar | atenção | Rodou, mas requer atenção |
| Vermelho | falha | Quebrou. A etiqueta `RAIZ` marca a origem da falha |
| Cinza | parado | Sem credencial ou rotina desligada |

## Comandos

```bash
python -m automateum                 # sobe o painel e o agendador
python -m automateum rodar <id>      # roda uma rotina avulsa uma vez
python -m automateum gmail-login     # autoriza a API do Gmail
python -m pytest -q tests            # executa a suíte de testes
```
