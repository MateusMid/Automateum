# Documentação do Automateum

Sistema pessoal que roda rotinas em Python (buscar mensagens, resumir, ver tasks, ler e anotar no cofre do Obsidian) e mostra tudo num painel em HTML, com o fluxo rodando ao vivo.

- **Painel:** `http://127.0.0.1:8765` (com `python -m automateum` rodando)

---

## Índice da Documentação

- [Escopo](Escopo.md) — o que o projeto faz, o que fica de fora e as decisões tomadas
- [Arquitetura](Arquitetura.md) — como as peças se encaixam e como criar uma rotina nova
- [Rotinas](Rotinas.md) — cada rotina, quando roda e o que faz
- [Painel](Painel.md) — o desenho do mapa e a referência visual
- [Roadmap](Roadmap.md) — etapas, andamento e como configurar cada credencial

---

## Pastas do Projeto

- `docs/anexos/` — imagens e referências visuais
- `dados/` — banco SQLite e credenciais locais (fora do git)
- `automateum/` — código fonte da aplicação
- `tests/` — suíte de testes com `pytest`
