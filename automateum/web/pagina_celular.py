"""A página /celular: o QR code e o endereço para abrir o painel no celular. Só é servida no próprio computador."""
from __future__ import annotations

from html import escape

# As mesmas cores e a mesma fonte do mapa (index.html), para a página parecer parte dele.
_CSS = """
:root { --bg:#0c0c0b; --texto:#ecebe6; --mudo:#8d8b84; --linha:rgba(255,248,235,.09); --painel:#151514; --painel2:#1f1f1d;
  --bom:#74b08f; --atencao:#d9a440; --font:"Segoe UI Variable Text","Segoe UI",system-ui,sans-serif; color-scheme:dark; }
* { box-sizing:border-box; }
body { margin:0; min-height:100vh; display:grid; place-items:start center; padding:32px 16px 48px; background:var(--bg);
  color:var(--texto); font:15px/1.5 var(--font); }
main { width:100%; max-width:440px; }
.volta { display:inline-block; margin:0 0 18px; color:var(--mudo); font-size:13px; text-decoration:none; }
.volta:hover { color:var(--texto); }
h1 { margin:0 0 6px; font-size:22px; font-weight:600; letter-spacing:-.01em; }
.sub { margin:0 0 22px; color:var(--mudo); }
.cartao { background:var(--painel); border:1px solid var(--linha); border-radius:14px; padding:22px; }
.qr { display:grid; place-items:center; margin:0 auto 18px; width:max-content; max-width:100%; padding:14px; border-radius:12px; background:#fff; }
.qr svg { display:block; width:min(100%,232px); height:auto; }
.endereco { display:flex; gap:8px; align-items:stretch; }
.endereco code { flex:1; min-width:0; padding:9px 11px; border-radius:8px; background:var(--painel2); border:1px solid var(--linha);
  font:12.5px/1.4 ui-monospace,Consolas,monospace; word-break:break-all; color:var(--texto); }
button { padding:0 14px; border:1px solid var(--linha); border-radius:8px; background:var(--painel2); color:var(--texto); font:inherit;
  font-size:13px; cursor:pointer; }
button:hover { background:#292926; }
ol { margin:20px 0 0; padding:0; list-style:none; counter-reset:passo; display:grid; gap:10px; }
li { counter-increment:passo; display:flex; gap:12px; align-items:flex-start; color:#d6d4cd; font-size:14px; }
li::before { content:counter(passo); flex:none; width:22px; height:22px; margin-top:1px; border-radius:50%; display:grid; place-items:center;
  background:color-mix(in srgb,var(--bom) 22%,transparent); color:var(--bom); font-size:12px; font-weight:600; }
.selo { display:inline-block; margin:0 0 14px; padding:2px 9px; border-radius:999px; font-size:11.5px; letter-spacing:.04em;
  background:color-mix(in srgb,var(--bom) 18%,transparent); color:var(--bom); }
.aviso { margin:14px 0 0; padding:11px 13px; border-radius:10px; font-size:13px; color:var(--mudo); background:var(--painel);
  border:1px solid var(--linha); }
.aviso b { color:#d6d4cd; font-weight:600; }
details { margin:14px 0 0; font-size:13px; color:var(--mudo); }
summary { cursor:pointer; }
details code { display:block; margin:6px 0 0; font:12.5px ui-monospace,Consolas,monospace; word-break:break-all; color:var(--texto); }
.conectados { margin:14px 0 0; padding:0; list-style:none; display:grid; gap:6px; }
.conectados li { display:flex; justify-content:space-between; gap:10px; padding:9px 12px; border-radius:10px; background:var(--painel);
  border:1px solid var(--linha); font-size:13px; }
.conectados li::before { display:none; }
.conectados small { color:var(--mudo); }
.bom { color:var(--bom); }
.atencao { color:var(--atencao); }
@media (max-width:480px) { body { padding-top:20px; } .cartao { padding:16px; } }
"""

_ICONE = ("<link rel=icon href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' "
          "height='64' rx='14' fill='%23151514'/%3E%3Ccircle cx='32' cy='32' r='22' fill='%2374b08f'/%3E%3C/svg%3E\">")

_JS = """
document.querySelectorAll('[data-copiar]').forEach(function (b) {
  b.addEventListener('click', function () {
    var t = b.getAttribute('data-copiar');
    var fim = function () { var o = b.textContent; b.textContent = 'Copiado'; setTimeout(function () { b.textContent = o; }, 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(fim, function () {});
  });
});
"""


def _pagina(titulo: str, corpo: str, script: bool = False) -> str:
    return ("<!doctype html><html lang='pt-br'><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(titulo)}</title>{_ICONE}<style>{_CSS}</style><body><main>"
            "<a class='volta' href='/'>← voltar ao mapa</a>" + corpo + "</main>" + (f"<script>{_JS}</script>" if script else ""))


def desligado() -> str:
    return _pagina("Celular desligado", (
        "<h1>Painel no celular</h1><p class='sub'>O acesso pelo celular está desligado.</p>"
        "<div class='cartao'><span class='selo atencao'>desligado</span>"
        "<p style='margin:0'>No <code>config.local.toml</code>, ponha <code>celular = true</code> em <code>[painel]</code> "
        "e reinicie o Automateum.</p></div>"))


def principal(links: list[str], qr_svg: str, conectados: list[dict]) -> str:
    """`links[0]` é o endereço da placa em uso (o do QR); os demais são adaptadores que talvez o celular não alcance."""
    if not links:
        return _pagina("Painel no celular", (
            "<h1>Painel no celular</h1><p class='sub'>Não achei o endereço de rede deste computador.</p>"
            "<div class='cartao'><p style='margin:0'>Conecte o computador a uma rede e recarregue esta página.</p></div>"))
    corpo = ("<h1>Ver o painel no celular</h1><p class='sub'>Aponte a câmera do celular para o código abaixo.</p>"
             "<div class='cartao'><span class='selo'>só leitura</span>"
             + (f"<div class='qr'>{qr_svg}</div>" if qr_svg else "")
             + f"<div class='endereco'><code>{escape(links[0])}</code><button type='button' data-copiar='{escape(links[0], quote=True)}'>Copiar</button></div>"
             "<ol><li><span>O celular precisa estar no <b>mesmo Wi-Fi</b> (ou roteador) que este computador.</span></li>"
             "<li><span>Abra o endereço no navegador do celular. Na primeira vez a chave fica guardada nele.</span></li>"
             "<li><span>O computador precisa estar ligado. O celular só vê o mapa, não executa nada.</span></li></ol></div>")
    if conectados:
        corpo += "<ul class='conectados'>" + "".join(
            f"<li><span>{escape(c.get('nome', 'Celular'))}</span><small>{escape(c.get('ip', ''))}</small></li>" for c in conectados) + "</ul>"
    if len(links) > 1:
        corpo += ("<details><summary>O código não abre? Tente outro endereço</summary>"
                  "<p style='margin:8px 0 0'>Este computador tem mais de uma placa de rede; o celular só alcança uma delas.</p>"
                  + "".join(f"<code>{escape(l)}</code>" for l in links[1:]) + "</details>")
    corpo += ("<p class='aviso'><b>A chave</b> fica só neste computador (<code>dados/celular.chave</code>). Quem tiver o endereço lê o "
              "painel enquanto estiver na sua rede. Para invalidar, apague esse arquivo e reinicie o Automateum.</p>")
    return _pagina("Painel no celular", corpo, script=True)
