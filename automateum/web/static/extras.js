/* Extras do mapa: faixa "Hoje", gráfico da máquina, título e ícone vivos, densidade e tamanho do texto,
   modo painel de parede e a lista para o celular. Só lê o que o servidor já entrega: o estado.js (window.MAPA)
   e, na mesma origem, /api/hoje e /api/maquina/historico (o conteúdo das mensagens nunca vai no estado.js). */
(function () {
  'use strict';
  var DENS = [{nome: 'compacto', f: .8}, {nome: 'normal', f: 1}, {nome: 'espaçado', f: 1.25}];
  var TEXTO = [.9, 1, 1.15, 1.3];
  var PROBLEMA = {ruim: 1, duvida: 1, atencao: 1};
  var GRAV = {ruim: 5, duvida: 4, atencao: 3, dele: 2, bom: 1, desligado: 0, construcao: 0};
  var NOME = {ruim: 'quebrado', duvida: 'dúvida', atencao: 'atenção', dele: 'com você', bom: 'em dia', desligado: 'desligado', construcao: 'em construção'};
  var raiz = document.documentElement;
  var dens = 1, ft = 1, parede = false, hoje = null, painelAberto = '';

  function $(s, r) { return (r || document).querySelector(s); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function hm(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  function guardar(k, v) { try { localStorage.setItem(k, String(v)); } catch (e) { /* sem armazenamento */ } }
  function ler(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function mapa() { return window.MAPA && window.MAPA.nos ? window.MAPA : null; }
  function refazer() { if (window.MapaTela) window.MapaTela.medir(); }

  // ------------------------------------------------------------ estado geral --
  // O que pesa no título e no ícone: rotinas, serviços de fora e a máquina (as frentes só repetem o que elas contêm).
  function resumo() {
    var m = mapa(), r = {n: 0, pior: 'bom', parado: false};
    if (!m) return r;
    m.nos.forEach(function (x) {
      if (x.tipo !== 'rotina' && x.tipo !== 'externo' && x.id !== 'mesa') return;
      var e = GRAV[x.estado] != null ? x.estado : 'construcao';
      if (PROBLEMA[e]) r.n++;
      if (GRAV[e] > GRAV[r.pior]) r.pior = e;
    });
    // o motor regrava o estado a cada poucos minutos; se parou, a tela é de antes
    if (m.gerado_ms && Date.now() - m.gerado_ms > 15 * 6e4) { r.parado = true; r.pior = 'ruim'; }
    return r;
  }
  function cor(e) {
    var v = getComputedStyle(raiz).getPropertyValue('--' + (e === 'construcao' ? 'desligado' : e)).trim();
    return v || '#74b08f';
  }

  // ------------------------------------------------------- título e ícone vivos --
  function icone(r) {
    var c = document.createElement('canvas'), x;
    c.width = c.height = 64;
    x = c.getContext('2d');
    if (!x) return;
    x.fillStyle = '#151514'; x.beginPath();
    if (x.roundRect) x.roundRect(0, 0, 64, 64, 14); else x.rect(0, 0, 64, 64);
    x.fill();
    x.fillStyle = cor(r.pior); x.beginPath(); x.arc(32, 32, 22, 0, Math.PI * 2); x.fill();
    if (r.n > 0) {
      x.fillStyle = '#0c0c0b'; x.font = '700 28px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(r.n > 9 ? '9+' : String(r.n), 32, 34);
    }
    var l = $('link[rel="icon"]');
    if (!l) { l = document.createElement('link'); l.rel = 'icon'; document.head.appendChild(l); }
    l.type = 'image/png'; l.href = c.toDataURL('image/png');
  }
  function titulo(r) {
    document.title = r.parado ? 'Automateum (mapa parado)'
      : r.n ? 'Automateum (' + r.n + (r.n === 1 ? ' problema)' : ' problemas)') : 'Automateum';
  }

  // ------------------------------------------------------------ gráficos --
  var hist = {t: 0, p: null};
  function historico() {
    if (hist.p && Date.now() - hist.t < 60000) return hist.p;
    hist.t = Date.now();
    hist.p = fetch('/api/maquina/historico?horas=24', {headers: {'Accept': 'application/json'}})
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .catch(function () { hist.p = null; return null; });
    return hist.p;
  }
  // Eixo do tempo de verdade: um buraco (PC desligado) aparece como buraco, em vez de ser espremido.
  function linhas(d, w, h, pad2) {
    var med = (d && d.medidas) || [], fim = Date.now(), ini = fim - 24 * 36e5;
    function xy(t, v) { return [(pad2 + (t - ini) / (fim - ini) * (w - 2 * pad2)).toFixed(1), (h - pad2 - v / 100 * (h - 2 * pad2)).toFixed(1)]; }
    function trilha(campo) {
      var partes = [], atual = [], antes = 0;
      med.forEach(function (m) {
        var t = Date.parse(m.quando);
        if (isNaN(t) || t < ini) return;
        if (atual.length && t - antes > 15 * 6e4) { partes.push(atual); atual = []; }
        atual.push(xy(t, Math.max(0, Math.min(100, m[campo])))); antes = t;
      });
      if (atual.length) partes.push(atual);
      return partes.map(function (p) {
        if (p.length === 1) return '<circle cx="' + p[0][0] + '" cy="' + p[0][1] + '" r="1.2"/>';
        return '<polyline points="' + p.map(function (q) { return q.join(','); }).join(' ') + '"/>';
      }).join('');
    }
    return {cpu: trilha('cpu'), mem: trilha('memoria'), n: med.length};
  }
  function spark(d) {
    var l = linhas(d, 240, 28, 1.5);
    if (!l.n) return '<svg class="spk" viewBox="0 0 240 28" preserveAspectRatio="none" aria-hidden="true"></svg>';
    return '<svg class="spk" viewBox="0 0 240 28" preserveAspectRatio="none" role="img" aria-label="CPU e memória nas últimas 24 horas">' +
      '<g class="spk-mem">' + l.mem + '</g><g class="spk-cpu">' + l.cpu + '</g></svg>';
  }
  function grafico(d) {
    var w = 400, h = 120, l = linhas(d, w, h, 4);
    if (!l.n) return '<p class="gv-nota">Ainda não há medições nas últimas 24 horas.</p>';
    var grade = [0, 50, 100].map(function (v) {
      var y = (h - 4 - v / 100 * (h - 8)).toFixed(1);
      return '<line x1="4" x2="' + (w - 4) + '" y1="' + y + '" y2="' + y + '"/><text x="6" y="' + (+y + 9) + '">' + v + '%</text>';
    }).join('');
    var fim = new Date(), ini = new Date(Date.now() - 24 * 36e5);
    return '<svg class="grf" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="CPU e memória nas últimas 24 horas">' +
      '<g class="grf-grade">' + grade + '</g><g class="spk-mem">' + l.mem + '</g><g class="spk-cpu">' + l.cpu + '</g></svg>' +
      '<div class="grf-eixo"><span>' + hm(ini) + '</span><span>agora ' + hm(fim) + '</span></div>' +
      '<div class="grf-leg"><span class="spk-cpu"><i></i>CPU (pico de cada faixa)</span><span class="spk-mem"><i></i>memória</span></div>';
  }
  function preencherSparks() {
    var alvos = document.querySelectorAll('[data-spark]');
    if (!alvos.length) return;
    historico().then(function (d) {
      if (!d) return;
      document.querySelectorAll('[data-spark]').forEach(function (el) { el.innerHTML = spark(d); });
    });
  }
  // a gaveta pede o gráfico grande da máquina por aqui
  function preencherGrafico(el) {
    historico().then(function (d) {
      if (!el.isConnected) return;
      el.innerHTML = d ? grafico(d) : '<p class="gv-nota">Não consegui ler o histórico da máquina no servidor.</p>';
    });
  }

  // ------------------------------------------------------------ faixa "Hoje" --
  var textos = [], hojeT = 0;
  function dia(iso) {
    var d = new Date(iso), h = new Date();
    if (isNaN(d)) return '';
    var k = Math.round((new Date(h.getFullYear(), h.getMonth(), h.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    return (k === 0 ? '' : k === 1 ? 'ontem ' : pad(d.getDate()) + '/' + pad(d.getMonth() + 1) + ' ') + hm(d);
  }
  function primeiraLinha(txt) {
    var ls = String(txt || '').split('\n').map(function (l) { return l.trim(); }).filter(Boolean);
    var boa = ls.filter(function (l) { return !/^(#+\s|\*\*[^*]+\*\*:?$)/.test(l); })[0] || ls[0] || '';
    return boa.replace(/^[-*•]\s+/, '').replace(/\*\*|__|`/g, '');
  }
  // Markdown mínimo (títulos, negrito, listas), sempre escapado antes.
  function md(txt) {
    var out = [], lista = false;
    function fecha() { if (lista) { out.push('</ul>'); lista = false; } }
    String(txt || '').split('\n').forEach(function (bruta) {
      var l = esc(bruta.trim()).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
      if (!l) { fecha(); return; }
      var t = /^#{1,4}\s+(.*)$/.exec(l), li = /^[-*•]\s+(.*)$/.exec(l);
      if (t) { fecha(); out.push('<h4>' + t[1] + '</h4>'); }
      else if (li) { if (!lista) { out.push('<ul>'); lista = true; } out.push('<li>' + li[1] + '</li>'); }
      else { fecha(); out.push('<p>' + l + '</p>'); }
    });
    fecha();
    return out.join('');
  }
  function desenharHoje() {
    if (!hoje) return;
    var r = resumo(), m = mapa();
    var estado = r.parado ? 'o mapa parou de atualizar' : r.n ? r.n + (r.n === 1 ? ' pede atenção' : ' pedem atenção') : 'tudo em dia';
    var dele = m ? m.nos.filter(function (x) { return x.estado === 'dele'; }).length : 0;
    var h = '<div class="hoje-cab"><span class="hoje-estado e-' + r.pior + '"><i></i>' + esc(estado) + '</span>';
    if (dele) h += '<span class="hoje-dele">' + dele + ' esperando você</span>';
    textos.forEach(function (t) {
      h += '<button type="button" class="hoje-chip' + (painelAberto === t.id ? ' on' : '') + '" data-hoje="' + esc(t.id) + '" aria-expanded="' + (painelAberto === t.id) + '">' +
        '<b>' + esc(t.titulo) + ' <small>' + esc(dia(t.quando)) + '</small></b><span>' + esc(primeiraLinha(t.conteudo)) + '</span></button>';
    });
    h += '<span class="hoje-relogio" id="relogio"></span></div>';
    var aberto = textos.filter(function (t) { return t.id === painelAberto; })[0];
    h += '<div class="hoje-painel"' + (aberto ? '' : ' hidden') + '>' +
      (aberto ? '<button type="button" class="hoje-x" data-hoje-fechar aria-label="Fechar">×</button><h3>' + esc(aberto.titulo) + ' <small>' + esc(dia(aberto.quando)) + '</small></h3>' + md(aberto.conteudo) : '') + '</div>';
    hoje.innerHTML = h;
    relogio();
  }
  function carregarHoje(forca) {
    if (!forca && Date.now() - hojeT < 60000) return;
    hojeT = Date.now();
    fetch('/api/hoje', {headers: {'Accept': 'application/json'}})
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) { textos = (d && d.textos) || []; desenharHoje(); })
      .catch(function () { /* a faixa fica só com o contador */ });
  }
  function relogio() {
    var el = $('#relogio'), d = new Date();
    if (el) el.textContent = hm(d) + ' · ' + ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'][d.getDay()] + ' ' + pad(d.getDate()) + '/' + pad(d.getMonth() + 1);
  }

  // ------------------------------------------------- densidade e tamanho do texto --
  function aplicarTamanho() {
    raiz.style.setProperty('--ft', String(ft));
    raiz.style.setProperty('--dp', String(dens));
    raiz.classList.toggle('ft', ft !== 1);
    var b = $('[data-x="dens"]'), t = $('[data-x="ft"]');
    if (b) b.textContent = 'Cartões: ' + (DENS.filter(function (d) { return d.f === dens; })[0] || DENS[1]).nome;
    if (t) t.textContent = 'Texto ' + Math.round(ft * 100) + '%';
  }
  function mudarDens() {
    var i = DENS.map(function (d) { return d.f; }).indexOf(dens);
    dens = DENS[(i + 1) % DENS.length].f; guardar('fluxo.dens', dens); aplicarTamanho(); refazer();
  }
  function mudarTexto(passo) {
    var i = TEXTO.indexOf(ft);
    i = Math.max(0, Math.min(TEXTO.length - 1, (i < 0 ? 1 : i) + passo));
    ft = TEXTO[i]; guardar('fluxo.ft', ft); aplicarTamanho(); refazer();
  }

  // ------------------------------------------------------------ modo painel --
  var trava = null;
  function entrarParede(on) {
    parede = on;
    document.body.classList.toggle('parede', on);
    if (window.Gaveta && Gaveta.fechar) { try { Gaveta.fechar(); } catch (e) { /* gaveta ainda não abriu */ } }
    try {
      if (on && navigator.wakeLock) navigator.wakeLock.request('screen').then(function (s) { trava = s; }, function () {});
      else if (!on && trava) { trava.release(); trava = null; }
    } catch (e) { /* sem wake lock */ }
    try {
      if (on && !document.fullscreenElement && raiz.requestFullscreen) raiz.requestFullscreen().catch(function () {});
      else if (!on && document.fullscreenElement) document.exitFullscreen();
    } catch (e) { /* sem tela cheia */ }
    var u = new URL(location.href);
    if (on) u.searchParams.set('parede', '1'); else u.searchParams.delete('parede');
    history.replaceState(null, '', u);
    relogio(); setTimeout(refazer, 60);
  }

  // ------------------------------------------------------ lista para o celular --
  function lista() {
    var el = $('#celular'), m = mapa();
    if (!el || !m) return;
    var porPai = {};
    m.nos.forEach(function (x) { if (x.pai) (porPai[x.pai] = porPai[x.pai] || []).push(x); });
    function linha(x) {
      var e = GRAV[x.estado] != null ? x.estado : 'construcao';
      return '<button type="button" class="cl-item e-' + e + '" data-no="' + esc(x.id) + '"><i></i><span><b>' + esc(x.rotulo || x.id) + '</b>' +
        '<small>' + esc(x.frase || NOME[e]) + '</small></span></button>';
    }
    var problemas = m.nos.filter(function (x) { return (x.tipo === 'rotina' || x.tipo === 'externo' || x.id === 'mesa') && (PROBLEMA[x.estado] || x.estado === 'dele'); })
      .sort(function (a, b) { return GRAV[b.estado] - GRAV[a.estado]; });
    var h = '';
    h += '<h2>Precisa de você</h2>' + (problemas.length ? problemas.map(linha).join('') : '<p class="cl-ok">Nada pedindo atenção agora.</p>');
    var mesa = m.nos.filter(function (x) { return x.id === 'mesa'; })[0];
    if (mesa) h += '<h2>Máquina</h2>' + linha(mesa) + '<div class="cl-spark" data-spark></div>';
    var grupos = m.nos.filter(function (x) { return x.tipo === 'grupo'; });
    if (grupos.length) {
      h += '<h2>Frentes</h2>' + grupos.map(function (g) {
        var filhos = (porPai[g.id] || []).filter(function (x) { return x.tipo === 'rotina'; });
        return '<details class="cl-grupo"><summary class="e-' + (GRAV[g.estado] != null ? g.estado : 'construcao') + '"><i></i><b>' + esc(g.rotulo || g.id) + '</b>' +
          '<small>' + filhos.length + (filhos.length === 1 ? ' rotina' : ' rotinas') + '</small></summary>' + linha(g) + filhos.map(linha).join('') + '</details>';
      }).join('');
    }
    var fora = m.nos.filter(function (x) { return x.tipo === 'externo'; });
    if (fora.length) h += '<h2>Serviços de fora</h2>' + fora.map(linha).join('');
    h += '<p class="cl-nota">Só leitura: para rodar ou ligar rotinas, use o painel no computador.</p>';
    el.innerHTML = h;
    preencherSparks();
  }

  // ---------------------------------------------------------------- ligação --
  function atualizou() {
    var r = resumo();
    titulo(r); icone(r);
    desenharHoje(); carregarHoje(false);
    preencherSparks(); lista();
  }
  function iniciar() {
    var s = parseFloat(ler('fluxo.dens')), t = parseFloat(ler('fluxo.ft'));
    if (DENS.some(function (d) { return d.f === s; })) dens = s;
    if (TEXTO.indexOf(t) >= 0) ft = t;
    hoje = $('#hoje');
    var zoom = $('#zoom');
    if (zoom) {
      zoom.insertAdjacentHTML('beforeend',
        '<button type="button" data-x="ft-" aria-label="Diminuir o texto">A−</button><button type="button" data-x="ft" disabled></button>' +
        '<button type="button" data-x="ft+" aria-label="Aumentar o texto">A+</button><button type="button" data-x="dens"></button>' +
        '<button type="button" data-x="parede" title="Modo painel (P)">Painel</button>');
      zoom.addEventListener('click', function (ev) {
        var b = ev.target.closest('[data-x]');
        if (!b) return;
        var a = b.getAttribute('data-x');
        if (a === 'dens') mudarDens(); else if (a === 'ft-') mudarTexto(-1); else if (a === 'ft+') mudarTexto(1);
        else if (a === 'parede') entrarParede(true);
      });
    }
    aplicarTamanho();
    if (hoje) {
      hoje.addEventListener('click', function (ev) {
        if (ev.target.closest('[data-hoje-fechar]')) { painelAberto = ''; desenharHoje(); return; }
        var c = ev.target.closest('[data-hoje]');
        if (c) { painelAberto = painelAberto === c.getAttribute('data-hoje') ? '' : c.getAttribute('data-hoje'); desenharHoje(); }
      });
    }
    var cel = $('#celular');
    if (cel) cel.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-no]');
      if (b && window.Gaveta) Gaveta.abrir(b.getAttribute('data-no'));
    });
    var sair = $('#sair-parede');
    if (sair) sair.addEventListener('click', function () { entrarParede(false); });
    document.addEventListener('keydown', function (ev) {
      if (ev.ctrlKey || ev.altKey || ev.metaKey || (ev.target && ev.target.closest && ev.target.closest('input, textarea'))) return;
      var k = String(ev.key).toLowerCase();
      if (k === 'p') entrarParede(!parede);
      else if (k === 'd') mudarDens();
      else if (k === '[') mudarTexto(-1);
      else if (k === ']') mudarTexto(1);
      else if (k === 'escape' && painelAberto) { painelAberto = ''; desenharHoje(); }
      else if (k === 'escape' && parede) entrarParede(false);
    });
    document.addEventListener('fullscreenchange', function () { if (parede && !document.fullscreenElement) entrarParede(false); });
    atualizou();
    setInterval(relogio, 15000);
    setInterval(function () { if (mapa()) { desenharHoje(); carregarHoje(false); } }, 60000);
    if (new URLSearchParams(location.search).get('parede') === '1') {
      parede = true; document.body.classList.add('parede'); relogio();
    }
  }

  // o mapa avisa durante o carregamento da página, antes do DOMContentLoaded: o ouvinte tem de existir já
  document.addEventListener('mapa:atualizado', function () { if (hoje) atualizou(); });
  window.Extras = {fator: function () { return {dens: dens, ft: ft}; }, preencherGrafico: preencherGrafico, spark: spark, md: md};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
