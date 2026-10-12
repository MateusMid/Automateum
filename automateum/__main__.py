"""python -m automateum              sobe o painel e o agendador
python -m automateum rodar <id>    roda uma rotina uma vez e mostra o resultado
python -m automateum gmail-login   autoriza a leitura do Gmail (abre o navegador)
"""
import argparse
import sys

from . import config as cfg


def main() -> int:
    parser = argparse.ArgumentParser(prog="automateum", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("gmail-login")
    sub.add_parser("rodar").add_argument("rotina")
    args = parser.parse_args()
    config = cfg.carregar()

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
    print(f"Automateum em http://{host}:{porta}")
    uvicorn.run(app, host=host, port=porta, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
