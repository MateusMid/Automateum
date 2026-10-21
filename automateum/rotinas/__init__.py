"""Importar este pacote registra todas as rotinas, na ordem em que aparecem no painel."""
from . import saude, coletar_slack, coletar_gmail, resumo_mensagens  # noqa: F401, I001
from . import tasks_obsidian, tasks_github, meu_dia, dia_fechado, semana_fechada, preparar_prompts, preparar_revisoes  # noqa: F401, I001
