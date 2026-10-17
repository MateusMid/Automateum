"""python -m automateum              sobe o painel e o agendador
python -m automateum rodar <id>    roda uma rotina uma vez e mostra o resultado
python -m automateum gmail-login   autoriza a leitura do Gmail (abre o navegador)
"""
import argparse
import sys

from . import config as cfg
from .nucleo import log


def main() -> int:
    parser = argparse.ArgumentParser(prog="automateum", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("gmail-login")
    sub.add_parser("rodar").add_argument("rotina")
    args = parser.parse_args()
    config = cfg.carregar()
    logger = log.configurar(config.pasta_dados)

    if args.comando == "gmail-login":
        from .servicos import gmail
        gmail.login(config)
        print("Gmail autorizado.")
        return 0

    from .web.api import criar_app
    app = criar_app(config)

    if args.comando == "rodar":
        from .nucleo.registro import ROTINAS
        ag, estado = app.state.agendador, app.state.estado
        if args.rotina not in ROTINAS:
            print(f"rotina desconhecida. Existem: {', '.join(ROTINAS)}")
            return 2
        if motivo := ag.motivo_parada(ROTINAS[args.rotina]):
            print(f"não dá para rodar: {motivo}")
            return 1
        ag.executar(args.rotina, manual=True)
        e = estado.execucoes(args.rotina, 1)[0]
        print(f"[{e['status']}] {e['resumo']}\n{e['log']}", end="")
        return 0 if e["status"] != "falha" else 1

    import uvicorn
    painel = config.secao("painel")
    host, porta = painel.get("host", "127.0.0.1"), painel.get("porta", 8765)
    if painel.get("celular"):
        host = "0.0.0.0"  # o painel só deixa passar leitura, de rede privada, com a chave do celular (web/celular.py)
    if not log.porta_livre("127.0.0.1" if host == "0.0.0.0" else host, porta):
        logger.error("a porta %s já está em uso: o Automateum provavelmente já está rodando em http://%s:%s",
                     porta, host, porta)
        if log.tem_console():
            print(f"A porta {porta} já está em uso. O Automateum provavelmente já está rodando em http://{host}:{porta}")
        return 1
    logger.info("Automateum em http://%s:%s", host, porta)
    if log.tem_console():
        print(f"Automateum em http://{host}:{porta}")
    uvicorn.run(app, host=host, port=porta, log_config=log.config_uvicorn(config.pasta_dados))
    return 0


def _iniciar() -> int:
    if sys.stdout is not None:  # sem console (pythonw.exe) o stdout não existe
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return main()
    except Exception:
        import logging
        logging.getLogger("automateum").exception("falha ao subir o Automateum")
        raise


if __name__ == "__main__":
    sys.exit(_iniciar())
