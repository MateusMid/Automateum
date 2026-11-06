"""Lembretes pessoais persistidos no banco local do Automateum."""
from datetime import datetime


ADIAR_MINUTOS = {5, 15, 30}


def _horario_local(valor: str) -> str:
    try:
        horario = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ValueError("informe uma data e hora válidas") from None
    if horario.tzinfo is None:
        horario = horario.astimezone()
    else:
        horario = horario.astimezone()
    return horario.isoformat(timespec="seconds")


def criar(estado, titulo: str, quando: str) -> dict:
    titulo = str(titulo or "").strip()
    if not titulo:
        raise ValueError("escreva o que você quer lembrar")
    if len(titulo) > 200:
        raise ValueError("o lembrete pode ter até 200 caracteres")
    return estado.criar_lembrete(titulo, _horario_local(quando))


def adiar(estado, ident: str, minutos: int) -> bool:
    if minutos not in ADIAR_MINUTOS:
        raise ValueError("escolha adiar por 5, 15 ou 30 minutos")
    return estado.adiar_lembrete(ident, minutos)


def notificacoes(estado) -> list[dict]:
    """Lembretes ativos, futuros ou vencidos. Os vencidos continuam aparecendo até concluir/adiar."""
    agora = datetime.now().astimezone()
    resultado = []
    for item in estado.lembretes():
        try:
            quando = datetime.fromisoformat(item["quando"])
            if quando.tzinfo is None:
                quando = quando.astimezone()
        except (KeyError, TypeError, ValueError):
            continue
        vencido = quando <= agora
        resultado.append({
            "id": f"lembrete:{item['id']}",
            "tipo": "lembrete",
            "lembrete_id": item["id"],
            "vencido": vencido,
            "titulo": item["titulo"],
            "quando": quando.isoformat(timespec="seconds"),
            "conteudo": "Está na hora." if vencido else "Lembrete agendado.",
        })
    return resultado
