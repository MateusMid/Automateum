"use strict";

const LARGURAS = [230, 250, 250, 300, 320];  // largura dos cartões de cada coluna
const VAO = 150;                              // espaço entre colunas, onde correm os fios
const ENTRE = 16;                             // espaço vertical entre cartões
const SVG = "http://www.w3.org/2000/svg";

const palco = document.getElementById("palco");
const mundo = document.getElementById("mundo");
const fios = document.getElementById("fios");
const gaveta = document.getElementById("gaveta");
const gavetaCorpo = document.getElementById("gaveta-corpo");
const conexao = document.getElementById("conexao");

const cartoes = new Map();   // id do nó → elemento
let caixas = new Map();      // id do nó → {x, y, w, h}
let grafo = null;
let vista = { x: 0, y: 0, z: 1 };
let aberto = null;           // id do nó mostrado na gaveta
let emFoco = null;           // id do nó sob o mouse
const logsAbertos = new Set();

// Todo texto vindo da API (títulos de mensagens, nomes de notas) entra como textContent, nunca como HTML.
function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function svg(tag, atributos) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  return e;
}

// ---------- desenho do mapa

function preencherCartao(cartao, no) {
  cartao.className = `no estado-${no.estado}`;
  cartao.setAttribute("aria-label", `${no.titulo}: ${no.estado}`);
  const topo = el("div", "no-topo");
  topo.append(el("span", "ponto"), el("span", "no-titulo", no.titulo));
  if (no.etiqueta) topo.append(el("span", "no-etiqueta", no.etiqueta));
  cartao.replaceChildren(topo);
  no.linhas.forEach((texto, i) => {
    const linha = el("div", "no-linha cortada");
    if (no.raiz && i === no.linhas.length - 1) linha.append(el("span", "raiz", "RAIZ"));
    linha.append(texto);
    cartao.append(linha);
  });
}

function desenhar(g) {
  grafo = g;
  const vivos = new Set();
  mundo.querySelectorAll(".coluna-titulo").forEach((t) => t.remove());

  let x = 0;
  const colunas = g.colunas.map((coluna, i) => {
    const info = { x, w: LARGURAS[i] ?? 260, coluna };
    x += info.w + VAO;
    return info;
  });

  for (const { x: cx, w, coluna } of colunas) {
    for (const no of coluna.nos) {
      vivos.add(no.id);
      let cartao = cartoes.get(no.id);
      if (!cartao) {
        cartao = el("div");
        cartao.dataset.id = no.id;
        cartao.tabIndex = 0;
        cartao.setAttribute("role", "button");
        cartoes.set(no.id, cartao);
        mundo.append(cartao);
      }
      preencherCartao(cartao, no);
      cartao.style.width = `${w}px`;
      cartao.style.left = `${cx}px`;
    }
  }
  for (const [id, cartao] of cartoes) {
    if (!vivos.has(id)) { cartao.remove(); cartoes.delete(id); }
  }

  // Com a largura fixada, a altura de cada cartão já é conhecida: empilha cada coluna centrada no zero.
  caixas = new Map();
  colunas.forEach(({ x: cx, w, coluna }, i) => {
    const alturas = coluna.nos.map((no) => cartoes.get(no.id).offsetHeight);
    const total = alturas.reduce((a, b) => a + b, 0) + ENTRE * Math.max(0, alturas.length - 1);
    let y = -total / 2;
    coluna.nos.forEach((no, j) => {
      cartoes.get(no.id).style.top = `${y}px`;
      caixas.set(no.id, { x: cx, y, w, h: alturas[j] });
      y += alturas[j] + ENTRE;
    });
    const titulo = el("div", "coluna-titulo");
    titulo.append(el("b", "", `[${String(i + 1).padStart(2, "0")}]`), `  ${coluna.titulo}  ${coluna.nos.length}`);
    titulo.style.left = `${cx}px`;
    titulo.dataset.coluna = i;
    mundo.append(titulo);
  });
  const topo = Math.min(...[...caixas.values()].map((c) => c.y));
  mundo.querySelectorAll(".coluna-titulo").forEach((t) => { t.style.top = `${topo - 42}px`; });

  desenharFios(g.arestas);
  contar(g);
  if (emFoco) focar(emFoco);
}

function portas(arestas, lado) {
  // Distribui as pontas dos fios ao longo da lateral do cartão, na ordem em que os vizinhos aparecem.
  const meu = lado === "de" ? "de" : "para";
  const outro = lado === "de" ? "para" : "de";
  const centro = (id) => { const c = caixas.get(id); return c.y + c.h / 2; };
  const porNo = new Map();
  for (const a of arestas) {
    if (!porNo.has(a[meu])) porNo.set(a[meu], []);
    porNo.get(a[meu]).push(a);
  }
  const saida = new Map();
  for (const [id, lista] of porNo) {
    const c = caixas.get(id);
    lista.sort((a, b) => centro(a[outro]) - centro(b[outro]));
    const passo = Math.min(9, (c.h - 14) / Math.max(1, lista.length - 1));
    lista.forEach((a, i) => {
      saida.set(a, { x: lado === "de" ? c.x + c.w : c.x, y: c.y + c.h / 2 + (i - (lista.length - 1) / 2) * passo });
    });
  }
  return saida;
}

function desenharFios(todas) {
  const arestas = todas.filter((a) => caixas.has(a.de) && caixas.has(a.para));
  const saidas = portas(arestas, "de");
  const entradas = portas(arestas, "para");
  const novos = [];
  for (const a of arestas) {
    const p = saidas.get(a), q = entradas.get(a);
    const curva = Math.max(40, (q.x - p.x) / 2);
    const dados = { "data-de": a.de, "data-para": a.para };
    novos.push(svg("path", {
      class: `fio estado-${a.estado}`, ...dados,
      d: `M${p.x},${p.y} C${p.x + curva},${p.y} ${q.x - curva},${q.y} ${q.x},${q.y}`,
    }));
    for (const ponta of [p, q]) {
      novos.push(svg("circle", { class: `porta estado-${a.estado}`, ...dados, cx: ponta.x, cy: ponta.y, r: 2.6 }));
    }
  }
  fios.replaceChildren(...novos);
}

function contar(g) {
  const rotinas = g.colunas.flatMap((c) => c.nos).filter((n) => n.tipo === "rotina");
  const quantos = (estados) => rotinas.filter((n) => estados.includes(n.estado)).length;
  const partes = [
    ["ok", quantos(["ok"]), "ok"], ["rodando", quantos(["rodando"]), "rodando"],
    ["atencao", quantos(["atencao"]), "atenção"], ["falha", quantos(["falha"]), "falha"],
    ["parado", quantos(["parado", "espera"]), "paradas"],
  ].filter((p) => p[1] > 0);
  const contagem = document.getElementById("contagem");
  contagem.replaceChildren(`${rotinas.length} rotinas`);
  for (const [estado, n, nome] of partes) contagem.append(" · ", el("b", `estado-${estado}`, `${n} ${nome}`));
}

// ---------- foco ao passar o mouse

function focar(id) {
  emFoco = id;
  mundo.classList.add("foco");
  const ligados = new Set([id]);
  fios.querySelectorAll("[data-de]").forEach((f) => {
    const liga = f.dataset.de === id || f.dataset.para === id;
    f.classList.toggle("ligado", liga);
    if (liga) { ligados.add(f.dataset.de); ligados.add(f.dataset.para); }
  });
  for (const [nid, cartao] of cartoes) cartao.classList.toggle("ligado", ligados.has(nid));
}

function desfocar() {
  emFoco = null;
  mundo.classList.remove("foco");
}

mundo.addEventListener("mouseover", (e) => {
  const cartao = e.target.closest(".no");
  if (cartao && cartao.dataset.id !== emFoco) focar(cartao.dataset.id);
  else if (!cartao && emFoco) desfocar();
});
mundo.addEventListener("mouseleave", desfocar);

// ---------- mover e aproximar

function aplicarVista() {
  mundo.style.transform = `translate(${vista.x}px, ${vista.y}px) scale(${vista.z})`;
  palco.style.backgroundPosition = `${vista.x}px ${vista.y}px`;
  palco.style.backgroundSize = `${40 * vista.z}px ${40 * vista.z}px`;
}

function encaixar() {
  if (!caixas.size) return;
  const cs = [...caixas.values()];
  const x0 = Math.min(...cs.map((c) => c.x)), x1 = Math.max(...cs.map((c) => c.x + c.w));
  const y0 = Math.min(...cs.map((c) => c.y)) - 50, y1 = Math.max(...cs.map((c) => c.y + c.h));
  const largura = palco.clientWidth - (gaveta.hidden ? 0 : gaveta.offsetWidth) - 60;
  const altura = palco.clientHeight - 110;
  const z = Math.max(0.2, Math.min(largura / (x1 - x0), altura / (y1 - y0), 1.15));
  vista = { z, x: 30 + (largura - (x1 - x0) * z) / 2 - x0 * z, y: 44 + (altura - (y1 - y0) * z) / 2 - y0 * z };
  aplicarVista();
}

function aproximar(fator, px = palco.clientWidth / 2, py = palco.clientHeight / 2) {
  const z = Math.max(0.2, Math.min(2.5, vista.z * fator));
  vista.x = px - (px - vista.x) * (z / vista.z);
  vista.y = py - (py - vista.y) * (z / vista.z);
  vista.z = z;
  aplicarVista();
}

palco.addEventListener("wheel", (e) => {
  e.preventDefault();
  aproximar(Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
}, { passive: false });

let arrasto = null;
palco.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  arrasto = { x: e.clientX, y: e.clientY, vx: vista.x, vy: vista.y, moveu: false,
              alvo: e.target.closest(".no")?.dataset.id ?? null };
  palco.setPointerCapture(e.pointerId);
});
palco.addEventListener("pointermove", (e) => {
  if (!arrasto) return;
  const dx = e.clientX - arrasto.x, dy = e.clientY - arrasto.y;
  if (!arrasto.moveu && Math.hypot(dx, dy) < 4) return;
  arrasto.moveu = true;
  palco.classList.add("arrastando");
  vista.x = arrasto.vx + dx;
  vista.y = arrasto.vy + dy;
  aplicarVista();
});
function soltar() {
  if (!arrasto) return;
  // Soltar sem ter movido é um clique: abre o cartão que estava debaixo do ponteiro.
  if (!arrasto.moveu && arrasto.alvo) abrir(arrasto.alvo);
  arrasto = null;
  palco.classList.remove("arrastando");
}
palco.addEventListener("pointerup", soltar);
palco.addEventListener("pointercancel", () => { arrasto = null; palco.classList.remove("arrastando"); });

mundo.addEventListener("keydown", (e) => {
  const cartao = e.target.closest(".no");
  if (cartao && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); abrir(cartao.dataset.id); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fechar(); });
document.getElementById("mais").addEventListener("click", () => aproximar(1.25));
document.getElementById("menos").addEventListener("click", () => aproximar(0.8));
document.getElementById("encaixar").addEventListener("click", encaixar);
document.getElementById("fechar").addEventListener("click", fechar);

// ---------- gaveta de detalhes

const NOMES_TIPO = { rotina: "rotina", servico: "serviço", frente: "frente", maquina: "máquina", destino: "com você" };
const NOMES_ESTADO = { ok: "ok", atencao: "atenção", falha: "falha", rodando: "rodando", parado: "parado" };

function hora(iso) {
  if (!iso) return "";
  const hoje = new Date().toLocaleDateString("sv");  // "sv" dá AAAA-MM-DD no fuso local
  return iso.slice(0, 10) === hoje ? iso.slice(11, 19) : `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}`;
}

function caminhoDoNo(id) {
  const corte = id.indexOf(":");
  const [tipo, nid] = corte === -1 ? [id, "local"] : [id.slice(0, corte), id.slice(corte + 1)];
  return `/api/no/${tipo}/${encodeURIComponent(nid)}`;
}

async function abrir(id) {
  aberto = id;
  logsAbertos.clear();
  const estavaFechada = gaveta.hidden;
  gaveta.hidden = false;
  await carregarGaveta();
  if (estavaFechada) encaixar();
}

function fechar() {
  if (gaveta.hidden) return;
  aberto = null;
  gaveta.hidden = true;
  encaixar();
}

async function carregarGaveta() {
  if (!aberto) return;
  const id = aberto;
  const resposta = await fetch(caminhoDoNo(id));
  if (!resposta.ok || aberto !== id) return;
  mostrarGaveta(await resposta.json());
}

function mostrarGaveta(d) {
  const partes = [el("div", "tipo", NOMES_TIPO[d.tipo] ?? d.tipo), el("h2", "", d.titulo)];
  if (d.descricao) partes.push(el("p", "", d.descricao));

  if (d.campos?.length) {
    const dl = el("dl", "campos");
    for (const [rotulo, valor] of d.campos) dl.append(el("dt", "", rotulo), el("dd", "", valor));
    partes.push(dl);
  }

  if (d.rodar) {
    const botao = el("button", "botao", d.rodando ? "rodando…" : "rodar agora");
    botao.disabled = Boolean(d.motivo) || d.rodando;
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      botao.textContent = "rodando…";
      const r = await fetch(`/api/rotinas/${encodeURIComponent(d.rodar)}/rodar`, { method: "POST" });
      if (!r.ok) botao.after(el("div", "motivo", (await r.json()).detail ?? "não foi possível rodar"));
    });
    partes.push(botao);
    if (d.motivo) partes.push(el("div", "motivo", `parada: ${d.motivo}`));
  }

  if (d.execucoes) {
    partes.push(el("h3", "", "ÚLTIMAS EXECUÇÕES"));
    const lista = el("ul", "lista");
    for (const e of d.execucoes) {
      const li = el("li", `estado-${e.status}`);
      const topo = el("div", "exec-topo");
      topo.append(el("span", "status", NOMES_ESTADO[e.status] ?? e.status), el("span", "hora", hora(e.inicio)),
                  el("span", "", e.resumo || ""));
      li.append(topo);
      if (e.log) {
        const det = el("details");
        det.open = logsAbertos.has(e.id);
        det.addEventListener("toggle", () => (det.open ? logsAbertos.add(e.id) : logsAbertos.delete(e.id)));
        det.append(el("summary", "", "log"), el("pre", "", e.log));
        li.append(det);
      }
      lista.append(li);
    }
    if (!d.execucoes.length) lista.append(el("li", "sub", "ainda não rodou"));
    partes.push(lista);
  }

  if (d.itens?.length) {
    partes.push(el("h3", "", `ITENS COLETADOS · ${d.itens.length}`));
    const lista = el("ul", "lista");
    for (const i of d.itens) {
      const li = el("li");
      if (/^https:\/\//.test(i.url)) {
        const a = el("a", "", i.titulo);
        a.href = i.url; a.target = "_blank"; a.rel = "noopener noreferrer";
        li.append(a);
      } else {
        li.append(i.titulo);
      }
      li.append(el("div", "sub", [i.origem, i.corpo, i.quando].filter(Boolean).join(" · ")));
      lista.append(li);
    }
    partes.push(lista);
  }

  if (d.avisos) {
    partes.push(el("h3", "", "AVISOS"));
    const lista = el("ul", "lista");
    for (const a of d.avisos) {
      const li = el("li", `estado-${a.nivel}`);
      li.append(a.texto, el("div", "sub", `${hora(a.quando)} · ${a.rotina}`));
      lista.append(li);
    }
    if (!d.avisos.length) lista.append(el("li", "sub", "nenhum aviso"));
    partes.push(lista);
  }

  const rolagem = gaveta.scrollTop;
  gavetaCorpo.replaceChildren(...partes);
  gaveta.scrollTop = rolagem;
}

// ---------- dados ao vivo

let primeira = true;
let pendente = null;

async function atualizar() {
  try {
    const resposta = await fetch("/api/grafo");
    if (!resposta.ok) return;
    desenhar(await resposta.json());
    if (primeira) { primeira = false; encaixar(); }
    carregarGaveta();
  } catch { /* servidor fora do ar: o EventSource já mostra "reconectando" */ }
}

function agendarAtualizacao() {
  clearTimeout(pendente);
  pendente = setTimeout(atualizar, 120);
}

function marcarConexao(estado, texto) {
  conexao.className = `estado-${estado}`;
  conexao.textContent = texto;
}

const eventos = new EventSource("/api/eventos");
eventos.onopen = () => { marcarConexao("ok", "ao vivo"); agendarAtualizacao(); };
eventos.onerror = () => marcarConexao("falha", "sem conexão, tentando de novo…");
eventos.onmessage = agendarAtualizacao;

setInterval(atualizar, 30000);  // rede de segurança caso algum evento se perca
window.addEventListener("resize", encaixar);
atualizar();
