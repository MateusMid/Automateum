import json
from datetime import date

from ..nucleo.registro import rotina
from ..servicos import ia, obsidian, reunioes

_PEDIDO = (
    "Resuma esta reunião para as minhas notas com até quatro partes curtas, cada uma com um título em negrito: "
    "**Assunto** (uma ou duas linhas), **Decisões**, **Próximos passos** (quem faz o quê e o prazo, se foi dito) "
    "e **Em aberto**. \"Eu\" na transcrição sou eu. Omita a parte que não tiver nada. A transcrição vem da legenda "
    "automática e tem palavras erradas: corrija pelo contexto quando for óbvio e não invente o que não foi dito."
)
_MIN_FALAS = 3        # menos que isso é teste de microfone, não reunião
_POR_RODADA = 3       # cada resumo leva alguns minutos no Claude
_LIMITE = 150_000     # caracteres da transcrição que vão para o Claude
_CURSOR = "reunioes:resumidas"


def _nome(t: dict, dados: dict) -> str:
    hora = dados["inicio"].replace(":", "h") if dados["inicio"] else ""
    return " ".join(p for p in (t["dia"], hora, t["chave"].rsplit("/", 1)[-1]) if p)


def _bloco_do_dia(ctx, dia: str, nome: str, conteudo: str) -> None:
    """O bloco "reunioes" do diário daquele dia tem uma seção por reunião, guardadas no cursor do dia."""
    chave = f"reunioes:dia:{dia}"
    secoes = json.loads(ctx.estado.cursor(chave) or "{}")
    secoes[nome] = conteudo
    ctx.estado.definir_cursor(chave, json.dumps(secoes, ensure_ascii=False))
    texto = "## Reuniões\n\n" + "\n\n".join(secoes[n] for n in sorted(secoes))
    obsidian.escrever_bloco_diario(ctx.config, "reunioes", texto, date.fromisoformat(dia))


@rotina(id="resumir_reunioes", nome="resumo de reuniões", frente="Notas", quando="cada 15m",
        usa=["reunioes", "claude", "obsidian"], entrega=["diario", "notas"])
def rodar(ctx):
    """Traz as transcrições do Gutenberg de Downloads para a pasta fixa e resume cada reunião nova no cofre e no diário."""
    cfg = ctx.config
    movidas = reunioes.trazer(cfg)
    for m in movidas:
        ctx.log(f"trazida: {m.name}")
    feitas = json.loads(ctx.estado.cursor(_CURSOR) or "{}")
    novas = [t for t in reunioes.transcricoes(cfg, parada_ha=60) if feitas.get(t["chave"]) != t["tamanho"]]
    pasta_propria = cfg.secao("obsidian").get("pasta_automateum", "Automateum")
    resumidas, curtas, textos = 0, 0, []
    for t in novas:
        dados = reunioes.ler(t["arquivo"])
        if dados["falas"] < _MIN_FALAS:
            curtas += 1
            feitas[t["chave"]] = t["tamanho"]   # se crescer (outra cópia maior), volta a ser avaliada
            continue
        if resumidas == _POR_RODADA:
            break
        resumo = ia.perguntar(ctx, _PEDIDO, f"### {dados['titulo']}\n{dados['texto'][:_LIMITE]}")
        nome = _nome(t, dados)
        cabeca = (f"{dados['falas']} falas · {', '.join(dados['quem'])}"
                  f" · transcrição em `{t['arquivo']}`")
        caminho = obsidian.escrever_proprio(cfg, f"Reuniões/{nome}.md", f"# {dados['titulo']}\n\n{cabeca}\n\n{resumo}")
        _bloco_do_dia(ctx, t["dia"], nome, f"### [[{pasta_propria}/Reuniões/{nome}|{dados['titulo']}]]\n\n{resumo}")
        feitas[t["chave"]] = t["tamanho"]
        ctx.estado.definir_cursor(_CURSOR, json.dumps(feitas, ensure_ascii=False))
        ctx.log(f"resumida: {caminho.name}")
        textos.append(f"**{dados['titulo']}**\n\n{resumo}")
        resumidas += 1
    ctx.estado.definir_cursor(_CURSOR, json.dumps(feitas, ensure_ascii=False))
    ctx.texto = "\n\n".join(textos)
    partes = [f"{len(movidas)} trazidas de Downloads" if movidas else "",
              f"{resumidas} reuniões resumidas" if resumidas else "",
              f"{curtas} curtas demais (menos de {_MIN_FALAS} falas)" if curtas else ""]
    return " · ".join(p for p in partes if p) or "nenhuma reunião nova"
