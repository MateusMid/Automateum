from ..nucleo.registro import FALHA, OK, SERVICOS, rotina
from ..servicos import maquina


@rotina(id="saude", nome="saúde", frente="Sistema", quando="cada 2m")
def rodar(ctx):
    """Checa a máquina e cada serviço configurado; é o que pinta a coluna de serviços."""
    ctx.estado.salvar_checagem("maquina", maquina.ler())
    ok, falhas, parados = 0, [], 0
    for s in SERVICOS.values():
        if s.configurado(ctx.config):
            parados += 1
            continue
        c = s.checar(ctx.config)
        ctx.estado.salvar_checagem(s.id, c)
        ctx.log(f"{s.nome}: {c.estado} · {c.detalhe}")
        if c.estado == FALHA:
            falhas.append(s.nome)
        elif c.estado == OK:
            ok += 1
    partes = [f"{ok} ok"]
    if falhas:
        partes.append("com falha: " + ", ".join(falhas))
    if parados:
        partes.append(f"{parados} sem credencial")
    return " · ".join(partes)
