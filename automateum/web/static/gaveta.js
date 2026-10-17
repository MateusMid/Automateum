/*
  gaveta.js - o detalhe de uma peca do mapa, igual em todas as visoes.

  Sem ela a pagina mostra o desenho e mais nada: da para olhar, e nao para conferir nem agir.

  A pagina chama:
    Gaveta.iniciar({encolher: '#palco', ancora: '#palco', aoAbrir: function (id) {}, aoFechar: function () {}})
                             encolher: quem cede a largura para a gaveta nao cobrir o desenho
                             ancora:   a gaveta comeca na altura do topo deste elemento, e a barra
                                       de cima da pagina continua inteira e clicavel
    Gaveta.receber(M)        a cada leitura nova do dados/estado.js
    Gaveta.abrir(id)         id de um no ou de uma ligacao; '@mapa' abre a saude do proprio mapa
    Gaveta.fechar()
    Gaveta.aberto()          o id aberto, ou null
    Gaveta.chip()            o html do botao "o mapa esta certo?" para o topo da pagina

  Tudo aqui leva o prefixo gv- e data-gv-, para nao esbarrar no que a pagina ja tem.

  A REGRA DOS BOTOES: a pagina nao executa nada. Quem executa e o acoes.py, em
  127.0.0.1, e so a lista fechada dele. A chave vem de dados/acoes.js, lida do disco. Sem servidor
  no ar o botao aparece desligado e diz por que.
*/
(function () {
  'use strict';

  var EST = {
    ruim: {nome: 'quebrado', grav: 5}, duvida: {nome: 'dúvida', grav: 4}, atencao: {nome: 'atenção', grav: 3},
    dele: {nome: 'com você', grav: 2}, bom: {nome: 'em dia', grav: 1}, desligado: {nome: 'parado', grav: 0},
    construcao: {nome: 'em construção', grav: 0}
  };
  var LETRA = {b: 'bom', a: 'atencao', r: 'ruim', d: 'dele', q: 'duvida', o: 'desligado', c: 'construcao'};
  var GL = {'-': -1, o: 0, c: 0, b: 1, d: 2, a: 3, q: 4, r: 5};
  var PASSO = {desligada: 'pausada no Agendador', rodando: 'rodando agora', propria: 'fez esta leitura', perdeu: 'perdeu a hora',
               nunca: 'ainda não rodou', gatilho: 'gatilho que o mapa não lê', sumiu: 'não está no Agendador'};
  var NO_CODIGO = {bom: 'em dia', atencao: 'rodou com ressalva', ruim: 'falhou', dele: 'parou esperando você',
                   duvida: 'saída que o mapa não conhece'};
  var ATRASO_MAX = 12 * 60 * 1000;
  var MAPA_ID = '@mapa';

  var M = null, I = null, aberto = null, raiz = null, opts = {}, rolagem = 0;
  var servidor = {token: null, porta: 8765, vivo: false, visto: false};
  var acoes = {};
  var armado = {};      // desligar:<id> esperando o segundo clique

  // ------------------------------------------------------------- apoio --
  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function est(e) { return EST[e] ? e : 'construcao'; }
  function gl(e) { e = est(e); return '<span class="gv-gl gv-e-' + e + ' gv-' + e + '" aria-hidden="true"></span>'; }
  function nomeEst(e) { return EST[e] ? EST[e].nome : e; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function data(iso) { return iso ? new Date(iso) : null; }
  function hm(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  function hms(d) { return hm(d) + ':' + pad(d.getSeconds()); }
  function dias(d) {
    var h = new Date();
    return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(h.getFullYear(), h.getMonth(), h.getDate())) / 864e5);
  }
  function longo(iso) {
    var d = data(iso); if (!d || isNaN(d)) return 'nunca';
    var k = dias(d);
    return (k === 0 ? 'hoje' : k === -1 ? 'ontem' : k === 1 ? 'amanhã' : pad(d.getDate()) + '/' + pad(d.getMonth() + 1)) + ' às ' + hm(d);
  }
  function falta(ms) {
    if (ms <= 30000) return 'agora';
    var m = Math.round(ms / 60000);
    if (m < 60) return 'em ' + m + ' min';
    var h = Math.floor(m / 60), r = m % 60;
    if (h < 24) return 'em ' + h + ' h' + (r ? ' ' + pad(r) : '');
    var d = Math.round(h / 24);
    return 'em ' + d + (d === 1 ? ' dia' : ' dias');
  }
  function ha(ms) {
    if (ms < 60000) return 'há menos de 1 min';
    var m = Math.round(ms / 60000);
    if (m < 60) return 'há ' + m + ' min';
    var h = Math.floor(m / 60);
    return h < 24 ? 'há ' + h + ' h' + (m % 60 ? ' ' + pad(m % 60) : '') : 'há ' + Math.round(h / 24) + ' dia(s)';
  }
  function mmss(ms) { var s = Math.max(0, Math.round(ms / 1000)); return Math.floor(s / 60) + ':' + pad(s % 60); }
  function plural(n, um, varios) { return n + ' ' + (n === 1 ? um : varios); }
  function outro(l, id) { return l.de === id ? l.para : l.de; }
  function maiuscula(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }

  // ----------------------------------------------------------- indice --
  function indexar(m) {
    var X = {no: {}, itens: {}, filhos: {}, ligDe: {}, lig: {}};
    (m.nos || []).forEach(function (n) {
      X.no[n.id] = X.itens[n.id] = n;
      if (n.pai) (X.filhos[n.pai] = X.filhos[n.pai] || []).push(n);
    });
    (m.ligacoes || []).forEach(function (l) {
      X.lig[l.id] = X.itens[l.id] = l;
      (X.ligDe[l.de] = X.ligDe[l.de] || []).push(l);
      (X.ligDe[l.para] = X.ligDe[l.para] || []).push(l);
    });
    return X;
  }
  function rotuloDe(x) {
    if (!x) return '';
    if (x.tipo === 'ligacao') {
      var a = I.no[x.de], b = I.no[x.para];
      return (a ? a.rotulo : x.de) + ' → ' + (b ? b.rotulo : x.para);
    }
    return x.rotulo || x.id;
  }
  function areaDe(x) {
    if (x.tipo === 'rotina' || x.tipo === 'parado') { var p = I.no[x.pai]; return p ? p.rotulo : ''; }
    return '';
  }
  function subtitulo(x) {
    if (x.tipo === 'rotina') return 'rotina' + (areaDe(x) ? ' · ' + areaDe(x) : '');
    if (x.tipo === 'parado') return 'parado por decisão' + (areaDe(x) ? ' · ' + areaDe(x) : '');
    if (x.tipo === 'grupo') {
      var z = I.no[x.zona], dom = x.dominio ? (M.dominios || {})[x.dominio] : '';
      // sem artigo: o nome da maquina vem do catalogo, e "da Meu PC" nao e portugues
      return 'área · ' + (z ? z.rotulo : 'máquina') + (dom ? ' · ' + dom : '');
    }
    if (x.tipo === 'externo') return 'serviço de fora' + (x.sub ? ' · ' + x.sub : '');
    if (x.tipo === 'zona') return x.sub || '';
    if (x.tipo === 'ligacao') return 'ligação' + (x.rotulo ? ' · ' + x.rotulo : '');
    return '';
  }
  function situacao(x) {
    if (x.tipo !== 'rotina') return '';
    if (x.passo === 'codigo') return NO_CODIGO[x.estado] || '';
    return PASSO[x.passo] || '';
  }
  // onde a peca mora: maquina > frente > rotina. E o "por onde comeca" de cada item.
  function trilha(x) {
    var p = [], z, g;
    if (x.tipo === 'ligacao') return '';
    if (x.tipo === 'rotina' || x.tipo === 'parado') { g = I.no[x.pai]; z = I.no[(g && g.zona) || x.zona]; }
    else if (x.tipo === 'grupo') z = I.no[x.zona];
    else if (x.tipo === 'externo') z = I.no.internet;
    if (z && z !== x) p.push(z);
    if (g && g !== z && g !== x) p.push(g);
    if (!p.length) return '';
    return '<nav class="gv-trilha" aria-label="Onde fica">' + p.map(function (n) {
      return '<button type="button" data-gv-abrir="' + esc(n.id) + '">' + esc(n.rotulo) + '</button>';
    }).join('<i aria-hidden="true">›</i>') + '<i aria-hidden="true">›</i><span>' + esc(rotuloDe(x)) + '</span></nav>';
  }
  function cadeia(x) {
    var out = [], vistos = {}, c = x.causa;
    while (c && !vistos[c] && I.itens[c]) { vistos[c] = 1; out.push(I.itens[c]); c = I.itens[c].causa; }
    return out;
  }
  function afetados(id) {
    var r = (M.raizes || []).filter(function (z) { return z.id === id; })[0];
    return r ? r.afeta.map(function (k) { return I.itens[k]; }).filter(Boolean) : [];
  }
  function ligacoesDe(x) {
    if (x.tipo === 'rotina' || x.tipo === 'parado') return I.ligDe[x.pai] || [];
    if (x.tipo === 'zona' && x.id === 'internet') return [I.lig['mesa~internet']].filter(Boolean);
    if (x.tipo === 'ligacao') return [];
    return I.ligDe[x.id] || [];
  }

  // ---------------------------------------------------------- pedacos --
  function secao(t, corpo, n) {
    return '<section class="gv-sec"><h4>' + esc(t) + (n != null ? ' <span>' + n + '</span>' : '') + '</h4>' + corpo + '</section>';
  }
  function ref(x) {
    if (!x) return '';
    return '<li class="gv-e-' + est(x.estado) + '" data-gv-abrir="' + esc(x.id) + '" tabindex="0">' + gl(x.estado) + '<span>' + esc(rotuloDe(x)) +
      '</span><small>' + esc(x.frase || '') + '</small></li>';
  }
  function refs(l) { return '<ul class="gv-ref">' + l.map(ref).join('') + '</ul>'; }
  function parte(p) {
    return '<li class="gv-e-' + est(p.estado) + ' gv-fixo">' + gl(p.estado) + '<span>' + esc(p.rotulo || p.id) + '</span><small>' + esc(p.frase || '') + '</small></li>';
  }
  function fatos(x) {
    var h = '';
    function f(t, v) { if (v) h += '<dt>' + esc(t) + '</dt><dd>' + v + '</dd>'; }
    if (x.tipo === 'rotina') {
      f('Última rodada', x.rodando ? 'rodando agora' : esc(longo(x.ultima)));
      if (x.ligada === false) f('Próxima', 'não roda: está desligada');
      else if (x.proxima) f('Próxima', esc(longo(x.proxima)) + ' · <span data-gv-ate="' + esc(x.proxima) + '">' + esc(falta(data(x.proxima).getTime() - Date.now())) + '</span>');
      if (x.repete_min) f('Repete', 'a cada ' + (x.repete_min >= 60 ? String(x.repete_min / 60).replace('.', ',') + ' h' : x.repete_min + ' min'));
      if (x.resultado != null && x.ultima) {
        f('Código de saída', '<code>0x' + (x.resultado >>> 0).toString(16).toUpperCase() + '</code>' +
          (x.codigo_frase && x.codigo_frase !== x.frase ? ' · ' + esc(x.codigo_frase) : ''));
      }
      if (x.caminho) f('No Agendador', '<code>' + esc(x.caminho) + '</code>');
    }
    if (x.ms != null) f('Resposta', x.ms + ' ms');
    if (x.tipo === 'ligacao' && x.rotulo) f('Para quê', esc(x.rotulo));
    return h ? secao('Detalhes', '<dl class="gv-fatos">' + h + '</dl>') : '';
  }
  // A ficha da rotina (13/10/2026): o que cada codigo de saida quer dizer nela, de onde vem a cor
  // desta leitura, o prazo do que a rodada escreve e o que o codigo 0 nao prova.
  function comoJulga(x) {
    var f = x.ficha || {};
    if (x.passo === 'propria') return 'É a própria leitura do mapa: se esta tela está em dia, ela rodou.';
    if (x.passo === 'desligada') return 'Está desligada no Agendador: não há rodada para julgar.';
    if (x.rodando && f.janela == null) return 'Fica no ar: enquanto o Agendador diz que está rodando, está de pé.';
    if (!f.sonda) return 'Só pelo código de saída: a rotina terminou sem quebrar. O mapa não confere o que ela escreveu.';
    if (x.codigo_frase) return 'Pelo que a última rodada escreveu (log ou arquivo), além do código de saída.';
    return 'Tem sonda do que a rodada escreve, mas a última rodada não deixou nada que ela lesse: valeu o código de saída.';
  }
  function ficha(x) {
    var f = x.ficha;
    if (x.tipo !== 'rotina' || !f) return '';
    var cods = (f.codigos || []).slice();
    if (!cods.some(function (c) { return c[0] === 0; })) cods.unshift([0, 'bom', 'terminou bem']);
    var atual = x.resultado != null && x.ultima && !x.rodando ? x.resultado : null;
    var h = '<ul class="gv-cods">' + cods.map(function (c) {
      return '<li class="gv-e-' + est(c[1]) + (c[0] === atual ? ' gv-cod-atual' : '') + '">' + gl(c[1]) + '<code>' + c[0] + '</code><span>' + esc(c[2]) +
        (c[0] === atual ? ' <i>última rodada</i>' : '') + '</span></li>';
    }).join('') + '</ul>';
    h += '<p class="gv-nota">Código fora desta lista vira dúvida: o mapa não chuta. Os do próprio Agendador (morta pelo teto de tempo, PC reiniciou no meio) valem para toda rotina.</p>';
    var d = '<dt>Como o mapa julga</dt><dd>' + esc(comoJulga(x)) + '</dd>';
    if (f.janela != null && f.sonda) d += '<dt>Prazo do que ela escreve</dt><dd>' + f.janela + ' min depois do disparo</dd>';
    else if (f.sem_janela) d += '<dt>Prazo do que ela escreve</dt><dd>' + esc(f.sem_janela) + '</dd>';
    if (f.ressalva) d += '<dt>O que o 0 não prova</dt><dd>' + esc(f.ressalva) + '</dd>';
    return secao('Ficha', h + '<dl class="gv-fatos gv-ficha">' + d + '</dl>');
  }
  function batimento(id) {
    var s = (M.historico || {})[id];
    if (!s) return '<p class="gv-nota">Ainda sem histórico: o mapa começa a contar quando vê o item pela primeira vez.</p>';
    var n = 96, por = s.length / n, fs = M.fatia_s * 1000, base = (M.fatia - s.length + 1) * fs, h = '<div class="gv-bat">';
    for (var i = 0; i < n; i++) {
      var p = '-', a = Math.floor(i * por), b = Math.floor((i + 1) * por);
      for (var j = a; j < b; j++) if (GL[s[j]] > GL[p]) p = s[j];
      h += '<b class="' + (p === '-' ? 'gv-nada' : 'gv-e-' + LETRA[p]) + '" title="' + hm(new Date(base + a * fs)) + ' a ' + hm(new Date(base + b * fs)) + ': ' +
        (p === '-' ? 'sem medida' : nomeEst(LETRA[p])) + '"></b>';
    }
    return h + '</div><div class="gv-bat-eixo"><span>24 h atrás</span><span>12 h atrás</span><span>agora</span></div>';
  }
  // SMART: o que, de que frente, ate quando, quando conta como feito, e de onde veio
  function cartaoEspera(w) {
    var h = '<article class="gv-esp gv-e-' + est(w.estado) + '"><div class="gv-esp-o">' + gl(w.estado) + '<b>' + esc(w.texto) + '</b></div><dl>' +
      (w.frente ? '<dt>Frente</dt><dd>' + esc(w.frente) + '</dd>' : '') +
      '<dt>Prazo</dt><dd>' + esc(w.prazo || 'sem prazo') + '</dd>' +
      (w.feito_quando ? '<dt>Feito quando</dt><dd>' + esc(w.feito_quando) + '</dd>' : '') + '</dl>';
    if (w.acao) h += botaoAcao(w.acao);
    return h + '</article>';
  }

  // DO COMECO AO FIM (14/10/2026). Pedido dele sobre o Fluxo e a Rede: "falta informacoes tipo saber
  // onde e o inicio e final de uma rotina ao clicar em algo". Comeca: a maquina do Agendador e a hora,
  // tirada da primeira frase do "oque" (o catalogo escreve a hora antes dos dois-pontos). Termina: o
  // campo fim, escrito no catalogo lendo cada script. So aparece na tela que pede (opts.percurso):
  // as do Fluxo e da Rede que ele usa ficam como estao ate ele ver as copias.
  var HORA_NA_FRASE = /\d|logon|boot|cada|segunda|domingo|último dia/i;
  function quandoDe(x) {
    var m = /^(.{3,90}?)[:.](\s|$)/.exec(x.oque || ''), t = m ? m[1] : '';
    if (t && HORA_NA_FRASE.test(t)) return t.charAt(0).toLowerCase() + t.slice(1);
    if (x.repete_min) return 'a cada ' + (x.repete_min >= 60 ? String(x.repete_min / 60).replace('.', ',') + ' h' : x.repete_min + ' min');
    if (x.proxima) { var d = data(x.proxima); return 'às ' + hm(d) + ' de ' + pad(d.getDate()) + '/' + pad(d.getMonth() + 1); }
    return '';
  }
  function percurso(x) {
    if (!opts.percurso || x.tipo !== 'rotina') return '';
    var mesa = I.no.mesa, q = quandoDe(x);
    var comeca = esc((mesa ? mesa.rotulo : 'Este PC') + ', pelo Agendador do Windows') + (q ? ': ' + esc(q) : '');
    var termina = x.fim ? esc(maiuscula(x.fim)) : '<span class="gv-nota">O mapa ainda não sabe: falta a linha desta rotina em FIM, no catalogo.py.</span>';
    return secao('Do começo ao fim', '<dl class="gv-fatos gv-percurso"><dt>Começa</dt><dd>' + comeca + '</dd><dt>Termina</dt><dd>' + termina + '</dd></dl>');
  }

  // ------------------------------------------- o resultado da rotina --
  // O que a rotina fez na última rodada, o log, os itens que ela guarda e o link da nota dela no
  // Obsidian. Vem do servidor (/api/no/rotina/<id>) e não do estado.js: o estado.js pode ser lido
  // por qualquer página aberta no navegador, e o resultado tem conteúdo de mensagens e tasks.
  var resultados = {};  // rotina -> {t: quando buscou, d: resposta do servidor}
  var logAberto = false;
  var ESTADO_DA_RODADA = {ok: 'bom', falha: 'ruim', atencao: 'atencao', rodando: 'duvida'};
  // Só o que os textos gerados usam: **negrito** e quebra de linha, sobre texto já escapado.
  function mdSimples(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>'); }
  function htmlResultado(d) {
    var ex = (d.execucoes || [])[0], h = '', itens = d.itens || [];
    var texto = d.texto && d.texto.conteudo
      ? '<div class="gv-texto"><small>Último texto gerado · ' + esc(longo(d.texto.quando)) + '</small><div>' + mdSimples(d.texto.conteudo) + '</div></div>'
      : '';
    if (ex) {
      var e = ESTADO_DA_RODADA[ex.status] || 'construcao';
      h += '<div class="gv-res-topo gv-e-' + e + '">' + gl(e) + '<b>' + esc(ex.resumo || nomeEst(e)) + '</b><small>' +
        esc(longo(ex.fim || ex.inicio)) + '</small></div>';
      h += texto;
      if (ex.log && ex.log.trim()) {
        h += '<details class="gv-det gv-log"' + (logAberto ? ' open' : '') + '><summary>Log da última rodada</summary><pre class="gv-pre">' +
          esc(ex.log.trim()) + '</pre></details>';
      }
    } else {
      h += '<p class="gv-nota">Ainda não há resultado guardado desta rotina.</p>' + texto;
    }
    if (itens.length) {
      h += '<ul class="gv-itens">' + itens.slice(0, 12).map(function (i) {
        var t = esc((i.titulo || '').slice(0, 160));
        var link = /^https?:\/\//.test(i.url || '') ? '<a href="' + esc(i.url) + '" target="_blank" rel="noopener noreferrer">' + t + '</a>' : t;
        var det = [i.origem, (i.quando || '').slice(0, 10)].filter(Boolean).join(' · ');
        return '<li>' + link + (det ? '<small>' + esc(det) + '</small>' : '') + '</li>';
      }).join('') + '</ul>';
      if (itens.length > 12) h += '<p class="gv-nota">e mais ' + (itens.length - 12) + ' itens guardados.</p>';
    }
    if (d.nota && /^obsidian:\/\/open\?/.test(d.nota.obsidian || '')) {
      h += '<a class="gv-obs" href="' + esc(d.nota.obsidian) + '">Abrir no Obsidian</a>' +
        '<p class="gv-nota">' + esc(d.nota.arquivo) + '</p>';
    }
    return h;
  }
  function preencherResultado() {
    var el = raiz && raiz.querySelector('[data-gv-res]');
    if (!el) return;
    var rid = el.getAttribute('data-gv-res'), c = resultados[rid];
    if (!/^[\w-]+$/.test(rid)) { el.innerHTML = ''; return; }
    if (c) el.innerHTML = htmlResultado(c.d);
    if (c && Date.now() - c.t < 15000) return;
    fetch('/api/no/rotina/' + encodeURIComponent(rid), {headers: {'Accept': 'application/json'}})
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (d) {
        resultados[rid] = {t: Date.now(), d: d};
        var vivo = raiz && raiz.querySelector('[data-gv-res="' + rid + '"]');
        if (vivo) vivo.innerHTML = htmlResultado(d);
      })
      .catch(function () {
        if (!resultados[rid] && el.isConnected) el.innerHTML = '<p class="gv-nota">Não consegui ler o resultado desta rotina no servidor.</p>';
      });
  }

  // ----------------------------------------------------------- a peca --
  function corpoDaPeca(id) {
    var x = I.itens[id], e = est(x.estado), sit = situacao(x);
    var h = '<header class="gv-cab gv-e-' + e + '">' + gl(e) + '<div class="gv-t"><h3>' + esc(rotuloDe(x)) + '</h3><small>' + esc(subtitulo(x)) + '</small></div>' +
      '<button class="gv-x" type="button" data-gv-fechar title="Fechar (Esc)" aria-label="Fechar">×</button></header><div class="gv-corpo">';
    h += trilha(x);
    h += '<div class="gv-est gv-e-' + e + '"><span class="gv-estn">' + gl(e) + esc(nomeEst(e)) + '</span>' + (sit ? '<span class="gv-passo">· ' + esc(sit) + '</span>' : '') + '</div>';
    if (x.frase) h += '<p class="gv-frase">' + esc(x.frase) + '</p>';
    h += motor(x);
    if (x.tipo === 'rotina') {
      // o botão de rodar também fica aqui, junto do resultado que ele atualiza (o do fim da gaveta continua)
      var rodarAqui = x.rodar_ok && x.ligada !== false
        ? '<div class="gv-acoes gv-e-' + e + ' gv-acao-topo">' + botaoAcao('rodar:' + x.id) + '</div>' : '';
      h += secao('Resultado', rodarAqui + '<div data-gv-res="' + esc(String(x.id).replace(/^rot-/, '')) + '"><p class="gv-nota">Carregando…</p></div>');
    }
    h += percurso(x);
    var linhas = (x.linhas || []).slice();
    if (x.sonda && x.sonda.frase) linhas.unshift('sonda da área: ' + x.sonda.frase);
    if (linhas.length) h += '<ul class="gv-linhas" title="O que o mapa mediu nesta peça">' + linhas.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ul>';
    var esp = (M.esperando || []).filter(function (w) { return w.de === id; });
    if (esp.length) h += secao('Esperando você', esp.map(cartaoEspera).join(''));
    var c = cadeia(x);
    if (c.length) h += secao('Por causa de', refs(c));
    var af = afetados(id);
    if (af.length) h += secao('Afeta', refs(af), af.length);
    h += fatos(x);
    h += secao('Últimas 24 horas', batimento(id));
    if (x.id === 'mesa' && window.Extras) h += secao('CPU e memória · 24 horas', '<div data-gv-hist><p class="gv-nota">Carregando…</p></div>');
    if (x.partes && x.partes.length) {
      var ps = x.partes.slice().sort(function (a, b) { return (EST[est(b.estado)].grav - EST[est(a.estado)].grav) || String(a.rotulo).localeCompare(String(b.rotulo), 'pt-BR'); });
      h += secao(x.id === 'lojas' ? 'Lojas' : 'Partes', '<ul class="gv-ref">' + ps.map(parte).join('') + '</ul>', ps.length);
    }
    if (x.oque) h += secao('O que é', '<p class="gv-oque">' + esc(x.oque) + '</p>');
    h += ficha(x);
    var fs = I.filhos[id] || [], ja = {};
    af.forEach(function (a) { ja[a.id] = 1; });
    if (fs.length && !fs.every(function (f) { return ja[f.id]; })) {
      fs = fs.slice().sort(function (a, b) { return EST[est(b.estado)].grav - EST[est(a.estado)].grav; });
      h += secao(x.tipo === 'zona' ? 'Rotinas nesta máquina' : x.id === 'parados' ? 'Parados' : 'Rotinas', refs(fs), fs.length);
    }
    var ls = ligacoesDe(x);
    if (ls.length) h += secao(x.tipo === 'rotina' ? 'O que a área dela usa' : 'Ligações', refs(ls), ls.length);
    if (x.tipo === 'ligacao') h += secao('Pontas', refs([I.no[x.de], I.no[x.para]]));
    if (x.tipo === 'rotina') {
      // desligada nao roda nem pelo botao: quem oferece o proximo passo e a chave, logo abaixo
      if (x.ligada !== false) {
        h += '<div class="gv-acoes gv-e-' + e + '">' + (x.rodar_ok ? botaoAcao('rodar:' + x.id)
          : '<p class="gv-nota">Sem botão de rodar: esta rotina gasta token, avisa gente ou mexe em algo que não se repete sem estrago. Ela roda na hora dela.</p>') + '</div>';
      }
      h += chave(x);
    }
    return h + '</div>';
  }

  // ------------------------------------------------- a saude do mapa --
  function saude() {
    var agora = Date.now(), idade = agora - M.gerado_ms, c = M.contagem || {}, erros = M.erros_motor || [], p = M.prova || null;
    var e = idade > ATRASO_MAX ? 'ruim' : erros.length || (p && p.saida !== 0) ? 'atencao' : 'bom';
    var frase = idade > ATRASO_MAX ? 'O mapa parou de atualizar: o que está na tela é de ' + hm(new Date(M.gerado_ms)) + '.'
      : erros.length ? 'O mapa está medindo, mas ' + plural(erros.length, 'leitura falhou', 'leituras falharam') + ' na última rodada.'
      : 'O mapa está medindo: cada cor desta tela saiu de uma leitura feita ' + ha(idade) + '.';
    return {estado: e, frase: frase};
  }
  function corpoDoMapa() {
    var agora = Date.now(), s = saude(), c = M.contagem || {}, erros = M.erros_motor || [], p = M.prova || null;
    var prox = M.gerado_ms + (M.intervalo_s || 300) * 1000 - agora;
    var nRot = (M.nos || []).filter(function (n) { return n.tipo === 'rotina'; }).length;
    var nExt = (M.nos || []).filter(function (n) { return n.tipo === 'externo'; }).length;
    var h = '<header class="gv-cab gv-e-' + s.estado + '">' + gl(s.estado) + '<div class="gv-t"><h3>O mapa está certo?</h3><small>o que garante o que você vê nesta tela</small></div>' +
      '<button class="gv-x" type="button" data-gv-fechar title="Fechar (Esc)" aria-label="Fechar">×</button></header><div class="gv-corpo">';
    h += '<div class="gv-est gv-e-' + s.estado + '"><span class="gv-estn">' + gl(s.estado) + esc(s.estado === 'bom' ? 'medindo' : nomeEst(s.estado)) + '</span></div>';
    h += '<p class="gv-frase">' + esc(s.frase) + '</p>';
    if (erros.length) h += '<ul class="gv-linhas">' + erros.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ul>';
    var f = '';
    function d(t, v) { f += '<dt>' + esc(t) + '</dt><dd>' + v + '</dd>'; }
    d('Última leitura', esc(hms(new Date(M.gerado_ms))) + ' · <span data-gv-ha="' + M.gerado_ms + '">' + esc(ha(agora - M.gerado_ms)) + '</span>');
    d('Próxima', '<span data-gv-em="' + (M.gerado_ms + (M.intervalo_s || 300) * 1000) + '">' + (prox > 0 ? 'em ' + mmss(prox) : 'lendo de novo') + '</span>');
    d('Levou', (M.duracao_ms / 1000).toFixed(1).replace('.', ',') + ' s');
    d('Mediu', plural(c.total || 0, 'item', 'itens') + ': ' + plural(nRot, 'rotina', 'rotinas') + ', ' + plural(nExt, 'serviço de fora', 'serviços de fora') +
      ' e ' + plural((M.ligacoes || []).length, 'ligação', 'ligações'));
    if (M.boot) d('Ligada desde', esc(longo(M.boot)));
    d('Botões', servidor.vivo ? 'no ar' : 'fora do ar: nenhum botão responde');
    h += secao('A leitura', '<dl class="gv-fatos">' + f + '</dl>');

    // o limite do mapa, dito por ele mesmo: rotina sem sonda do que escreve fica verde so por ter terminado
    var soCod = (M.nos || []).filter(function (n) {
      return n.tipo === 'rotina' && n.ficha && !n.ficha.sonda && n.passo !== 'propria' && !(n.rodando && n.ficha.janela == null);
    });
    if (soCod.length) {
      h += secao('Julgadas só pelo código de saída', '<p class="gv-oque">' + esc(soCod.length + ' de ' + plural(nRot, 'rotina', 'rotinas') +
        '. Nestas o verde quer dizer que a rodada terminou sem quebrar. O mapa não lê o que elas escreveram, e a ficha de cada uma diz o que o código 0 não prova.') +
        '</p>' + refs(soCod), soCod.length);
    }

    var pv = '';
    if (!p) pv = '<p class="gv-nota">A prova ainda não foi rodada desde que este registro existe.</p>';
    else {
      pv = '<div class="gv-est gv-e-' + (p.saida === 0 ? 'bom' : 'ruim') + '"><span class="gv-estn">' + gl(p.saida === 0 ? 'bom' : 'ruim') +
        esc(p.saida === 0 ? 'passou' : 'reprovou') + '</span><span class="gv-passo">· ' + esc(longo(p.quando)) + '</span></div>' +
        '<p class="gv-oque">' + esc(plural(p.conferencias || 0, 'conferência', 'conferências') + ' e ' + plural(p.mutantes || 0, 'defeito plantado', 'defeitos plantados') +
        (p.escaparam ? ', ' + p.escaparam + ' sem ser pego' : ', todos pegos') + '.') + '</p>';
    }
    pv += '<p class="gv-nota">A prova planta de propósito cada defeito que este mapa já teve e confere que ele acusa. Passar quer dizer que as regras de cor continuam funcionando.</p>';
    h += secao('A prova', pv);

    h += secao('Como conferir uma peça', '<ol class="gv-passos"><li>Clique na peça. O bloco em letra de máquina é o que o mapa mediu, sem interpretação.</li>' +
      '<li>Compare "Última rodada" e "Código de saída" com o Agendador do Windows: o caminho da tarefa está logo abaixo.</li>' +
      '<li>Se a rotina tiver "Rodar agora", rode e veja a faixa das 24 horas ganhar um ponto novo.</li></ol>');
    h += '<div class="gv-acoes gv-e-bom">' + botaoAcao('medir-agora') + botaoAcao('provar-mapa') + '</div>';
    if (!servidor.vivo) h += '<p class="gv-nota">Os botões sobem no logon, pela tarefa Mapa - botoes. Sem ela no ar o mapa segue medindo, só não executa.</p>';
    return h + '</div>';
  }

  // ---------------------------------------------------------- botoes --
  function urlServidor(p) { return 'http://127.0.0.1:' + servidor.porta + p; }
  function rotAcao(a) {
    var p = a.split(':'), d = p[1] && /^\d{4}-\d\d-\d\d$/.test(p[1]) ? p[1].slice(8, 10) + '/' + p[1].slice(5, 7) : '';
    if (p[0] === 'rodar') return 'Rodar agora';
    if (p[0] === 'motor') return 'Usar o ' + (p[1] === 'copilot' ? 'Copilot' : 'Claude') + ' como principal';
    if (p[0] === 'ligar') return 'Ligar esta rotina';
    if (p[0] === 'desligar') return armado[a] ? 'Confirmar: desligar' : 'Desligar esta rotina';
    if (a === 'medir-agora') return 'Medir agora';
    if (a === 'provar-mapa') return 'Rodar a prova';
    return a;
  }
  // Qual IA escreve os resumos: o botao inverte principal e reserva (o servidor guarda a escolha)
  function motor(x) {
    var m = x.motor, u = m && m.ultimo;
    if (!m) return '';
    var h = '<p class="gv-oque">Em uso: <b>' + esc(m.ativo_nome) + '</b>. Se ele falhar, o texto é feito pelo ' + esc(m.reserva_nome) +
      (m.reserva_pronta ? '.' : ' (que não está instalado neste computador, então não vai adiantar).') + '</p>';
    if (u && u.reserva) h += '<p class="gv-nota">Na última vez o ' + esc(m.ativo_nome) + ' não respondeu e o texto saiu pelo ' + esc(m.reserva_nome) +
      ' (' + hm(new Date(u.quando)) + '): ' + esc(u.motivo) + '</p>';
    h += '<div class="gv-acoes gv-e-bom">' + botaoAcao('motor:' + m.reserva) + '</div>';
    return secao('Motor dos resumos', h);
  }
  // A chave da rotina (13/10/2026): ligar e desligar no Agendador, com a decisao anotada pelo servidor
  function chave(x) {
    if (x.tipo !== 'rotina' || !x.ficha || x.passo === 'sumiu') return '';
    var f = x.ficha, h;
    if (x.ligada === false) {
      h = '<p class="gv-oque">Desligada no Agendador: não roda até você ligar.</p><div class="gv-acoes gv-e-bom">' + botaoAcao('ligar:' + x.id) + '</div>';
    } else if (f.sem_chave) {
      h = '<p class="gv-oque">Ligada.</p><p class="gv-nota">Não se desliga por aqui: ' + esc(f.sem_chave) + '.</p>';
    } else {
      h = '<p class="gv-oque">Ligada: roda na hora dela.</p><div class="gv-acoes gv-e-desligado">' + botaoAcao('desligar:' + x.id) + '</div>' +
        '<p class="gv-nota">Desligar não interrompe a rodada em andamento e fica anotado como decisão sua, com a data. Volta com um clique.</p>';
    }
    return secao('Chave', h);
  }
  function botaoAcao(acao) {
    var st = acoes[acao], pronto = !!(servidor.token && servidor.vivo);
    var ocupado = st && (st.estado === 'enviando' || st.estado === 'rodando');
    return '<button type="button" class="gv-acao' + (st ? ' gv-' + st.estado : '') + '" data-gv-acao="' + esc(acao) + '"' + (!pronto || ocupado ? ' disabled' : '') +
      (pronto ? '' : ' title="O servidor dos botões não está no ar."') + '>' + esc(st ? st.texto : rotAcao(acao)) + '</button>';
  }
  // os botoes tambem vivem fora da gaveta (a coluna "Precisa de voce" da Triagem), por Gaveta.botao
  function repintarBotoes(acao) {
    if (!raiz) return;
    [].forEach.call(document.querySelectorAll('[data-gv-acao]'), function (b) {
      var a = b.getAttribute('data-gv-acao');
      if (!acao || a === acao) b.outerHTML = botaoAcao(a);
    });
  }
  function marcarAcao(acao, estado, texto) {
    if (estado) acoes[acao] = {estado: estado, texto: texto}; else delete acoes[acao];
    repintarBotoes(acao);
  }
  function agir(acao) {
    if (!servidor.token || !servidor.vivo) return;
    var st = acoes[acao];
    if (st && (st.estado === 'enviando' || st.estado === 'rodando')) return;
    // desligar pede o segundo clique: o primeiro arma o botao por 6 s
    if (/^desligar:/.test(acao) && !armado[acao]) {
      armado[acao] = true;
      repintarBotoes(acao);
      setTimeout(function () { if (armado[acao]) { delete armado[acao]; repintarBotoes(acao); } }, 6000);
      return;
    }
    delete armado[acao];
    marcarAcao(acao, 'enviando', 'Enviando…');
    fetch(urlServidor('/acao'), {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Mapa-Token': servidor.token}, body: JSON.stringify({acao: acao})})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || ('HTTP ' + r.status)); return j; }); })
      .then(function (j) { marcarAcao(acao, 'rodando', 'Rodando…'); acompanhar(acao, j.id, Date.now()); })
      .catch(function (e) { fimAcao(acao, 'erro', 'Não foi: ' + e.message); });
  }
  function acompanhar(acao, id, t0) {
    fetch(urlServidor('/estado/' + encodeURIComponent(id)), {headers: {'X-Mapa-Token': servidor.token}})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        // -1 e o teto da pagina, nao falha: o processo segue rodando e o mapa conta o fim depois
        if (j.fim) fimAcao(acao, j.codigo === 0 ? 'ok' : j.codigo === -1 ? 'aviso' : 'erro',
                           maiuscula(j.texto) || (j.codigo === 0 ? 'Feito' : 'Saiu com o código ' + j.codigo));
        else if (Date.now() - t0 < 40 * 60000) setTimeout(function () { acompanhar(acao, id, t0); }, 2000);
        else fimAcao(acao, 'erro', 'Passou de 40 min sem terminar');
      })
      .catch(function () { setTimeout(function () { acompanhar(acao, id, t0); }, 4000); });
  }
  function fimAcao(acao, estado, texto) {
    marcarAcao(acao, estado, texto);
    // a rodada acabou: o resultado guardado ficou velho, então busca de novo e redesenha a gaveta aberta
    if (/^rodar:/.test(acao)) {
      delete resultados[acao.slice(6).replace(/^rot-/, '')];
      if (aberto) desenhar();
    }
    // a chave mudou no Agendador: uma leitura agora, para a tela nao esperar os 5 min
    if (estado === 'ok' && /^(ligar|desligar):/.test(acao)) agir('medir-agora');
    if (opts.aoAgir) { try { opts.aoAgir(acao, estado); } catch (e) { /* a pagina que se vire */ } }
    setTimeout(function () { if (acoes[acao] && acoes[acao].texto === texto) marcarAcao(acao, null); }, 20000);
  }
  // A chave dos botoes vem do disco, nunca do HTTP. Com ela em maos, o /vivo diz se o servidor
  // esta de pe; os botoes so ligam com as duas coisas.
  function carregarChave() {
    var s = document.createElement('script');
    s.src = '/dados/acoes.js?t=' + Date.now();
    s.onload = function () {
      s.remove();
      var a = window.MAPA_ACOES; window.MAPA_ACOES = undefined;
      if (a && a.token) { servidor.token = a.token; servidor.porta = a.porta || 8765; sondarServidor(); }
      else mudarServidor(null, false);
    };
    s.onerror = function () { s.remove(); mudarServidor(null, false); };
    document.head.appendChild(s);
  }
  function sondarServidor() {
    var ctl = window.AbortController ? new AbortController() : null;
    var t = ctl && setTimeout(function () { ctl.abort(); }, 1500);
    fetch(urlServidor('/vivo'), ctl ? {signal: ctl.signal} : {})
      .then(function (r) { return r.json(); })
      .then(function (j) { mudarServidor(servidor.token, !!(j && j.ok)); })
      .catch(function () { mudarServidor(servidor.token, false); })
      .then(function () { if (t) clearTimeout(t); });
  }
  function mudarServidor(token, vivo) {
    var antes = servidor.token + '|' + servidor.vivo + '|' + servidor.visto;
    servidor.token = token; servidor.vivo = vivo; servidor.visto = true;
    if (antes === token + '|' + vivo + '|true') return;
    if (aberto === MAPA_ID) desenhar();
    repintarBotoes();              // os de fora da gaveta tambem dependem do servidor
    pintarChip();
  }

  // ------------------------------------------------------------- tela --
  function montar() {
    if (raiz) return;
    var st = document.createElement('style');
    st.setAttribute('data-gv', '');
    st.textContent = CSS;
    document.head.appendChild(st);
    raiz = document.createElement('aside');
    raiz.className = 'gv';
    raiz.id = 'gv';
    raiz.setAttribute('aria-hidden', 'true');
    raiz.setAttribute('aria-label', 'Detalhe da peça');
    document.body.appendChild(raiz);
    raiz.addEventListener('click', function (ev) {
      var t = ev.target, b;
      if (!t || !t.closest) return;
      if (t.closest('[data-gv-fechar]')) { fechar(); return; }
      if ((b = t.closest('[data-gv-acao]'))) { if (!b.disabled) agir(b.getAttribute('data-gv-acao')); return; }
      if ((b = t.closest('[data-gv-abrir]'))) abrir(b.getAttribute('data-gv-abrir'));
    });
    raiz.addEventListener('keydown', function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest('li[data-gv-abrir]') : null;
      if (b && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrir(b.getAttribute('data-gv-abrir')); }
    });
    // a roda dentro da gaveta rola a gaveta, e nao o zoom do palco que esta embaixo
    raiz.addEventListener('wheel', function (ev) { ev.stopPropagation(); }, {passive: true});
    ['pointerdown', 'mousedown', 'dblclick'].forEach(function (k) { raiz.addEventListener(k, function (ev) { ev.stopPropagation(); }); });
    document.addEventListener('click', function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest('[data-gv-saude]') : null;
      if (b) { ev.preventDefault(); if (aberto === MAPA_ID) fechar(); else abrir(MAPA_ID); }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && aberto) fechar();
    });
    setInterval(tique, 1000);
    carregarChave();
    setInterval(carregarChave, 30000);
  }
  function largura() { return raiz ? raiz.offsetWidth : 440; }
  function ancorar() {
    if (!raiz) return;
    var el = opts.ancora ? document.querySelector(opts.ancora) : null;
    var t = el ? Math.max(0, Math.round(el.getBoundingClientRect().top)) + 'px' : '0px';
    if (raiz.style.top !== t) raiz.style.top = t;
    raiz.classList.toggle('gv-ancorada', !!el);
  }
  function encolher(liga) {
    if (!opts.encolher) return;
    var el = document.querySelector(opts.encolher);
    if (!el) return;
    // em janela estreita a gaveta fica por cima: espremer o desenho para caber nao ajuda ninguem
    var v = liga && window.innerWidth >= 1180 ? largura() + 'px' : '';
    if (el.style.marginRight !== v) el.style.marginRight = v;
  }
  function desenhar() {
    if (!raiz || !aberto || !M) return;
    var c = raiz.querySelector('.gv-corpo');
    rolagem = c ? c.scrollTop : 0;
    // a gaveta é redesenhada a cada leitura nova: lembra se o log estava aberto
    if (raiz.querySelector('.gv-log')) logAberto = !!raiz.querySelector('.gv-log[open]');
    raiz.innerHTML = aberto === MAPA_ID ? corpoDoMapa() : corpoDaPeca(aberto);
    c = raiz.querySelector('.gv-corpo');
    if (c) c.scrollTop = rolagem;
    preencherResultado();
    var hist = raiz.querySelector('[data-gv-hist]');
    if (hist && window.Extras) Extras.preencherGrafico(hist);
  }
  function abrir(id) {
    montar();
    if (!M || !I) return false;
    if (id !== MAPA_ID && !I.itens[id]) return false;
    var mudou = aberto !== id;
    if (mudou) logAberto = false;
    aberto = id;
    if (mudou) { var c = raiz.querySelector('.gv-corpo'); if (c) c.scrollTop = 0; }
    desenhar();
    if (mudou) { var c2 = raiz.querySelector('.gv-corpo'); if (c2) c2.scrollTop = 0; }
    ancorar();
    raiz.classList.add('gv-on');
    raiz.setAttribute('aria-hidden', 'false');
    document.body.classList.add('gv-aberta');
    encolher(true);
    pintarChip();
    if (mudou && opts.aoAbrir) { try { opts.aoAbrir(id === MAPA_ID ? null : id); } catch (e) { /* a pagina que se vire */ } }
    return true;
  }
  function fechar(calado) {
    if (!aberto) return;
    aberto = null;
    if (raiz) { raiz.classList.remove('gv-on'); raiz.setAttribute('aria-hidden', 'true'); }
    document.body.classList.remove('gv-aberta');
    encolher(false);
    pintarChip();
    if (!calado && opts.aoFechar) { try { opts.aoFechar(); } catch (e) { /* a pagina que se vire */ } }
  }
  function receber(m) {
    if (!m || !m.nos) return;
    M = m; I = indexar(m);
    if (aberto && aberto !== MAPA_ID && !I.itens[aberto]) fechar();
    else desenhar();
    pintarChip();
  }
  function tique() {
    if (!M) return;
    var agora = Date.now();
    pintarChip();
    if (!raiz || !aberto) return;
    [].forEach.call(raiz.querySelectorAll('[data-gv-ate]'), function (el) { el.textContent = falta(data(el.getAttribute('data-gv-ate')).getTime() - agora); });
    [].forEach.call(raiz.querySelectorAll('[data-gv-ha]'), function (el) { el.textContent = ha(agora - +el.getAttribute('data-gv-ha')); });
    [].forEach.call(raiz.querySelectorAll('[data-gv-em]'), function (el) {
      var f = +el.getAttribute('data-gv-em') - agora;
      el.textContent = f > 0 ? 'em ' + mmss(f) : 'lendo de novo';
    });
  }
  // O botao do topo: diz de quando e a leitura e abre a saude do mapa. Fica vermelho sozinho
  // quando a leitura envelhece, que e a unica forma de um mapa parado nao parecer um mapa em dia.
  function chip() { return '<button type="button" class="gv-chip" data-gv-saude title="O mapa está certo? Clique para conferir."></button>'; }
  function pintarChip() {
    var els = document.querySelectorAll('[data-gv-saude]');
    if (!els.length) return;
    var txt, e;
    if (!M) { txt = 'sem dados'; e = 'ruim'; }
    else {
      var s = saude(), idade = Date.now() - M.gerado_ms;
      e = s.estado;
      txt = hm(new Date(M.gerado_ms)) + ' · ' + ha(idade) + (servidor.visto && !servidor.vivo ? ' · botões fora do ar' : '');
    }
    [].forEach.call(els, function (el) {
      var h = '<i class="gv-e-' + e + '"></i><span>' + esc(txt) + '</span><b>conferir</b>';
      if (el.innerHTML !== h) el.innerHTML = h;
      el.title = 'Leitura das ' + (M ? hm(new Date(M.gerado_ms)) : '?') + '. O mapa está certo? Clique para conferir.';
      el.classList.toggle('gv-chip-on', aberto === MAPA_ID);
      el.classList.toggle('gv-chip-ruim', e === 'ruim');
    });
  }
  function iniciar(o) {
    opts = o || {};
    montar();
    pintarChip();
    window.addEventListener('resize', function () { if (aberto) { ancorar(); encolher(true); } });
  }

  // -------------------------------------------------------------- css --
  // As cores vem da pele da pagina quando ela as define (--texto, --mudo, --linha, --bom...), e
  // caem na paleta padrao quando nao define.
  var CSS = [
    // .gv-fora: o involucro de um botao de acao posto na pagina, fora da gaveta
    '.gv, .gv-chip, .gv-fora {',
    '  --gv-texto: var(--texto, #ecebe6);',
    '  --gv-mudo: var(--mudo, #8d8b84);',
    '  --gv-texto2: var(--texto2, color-mix(in srgb, var(--gv-texto) 76%, var(--gv-mudo)));',
    '  --gv-linha: var(--linha, rgba(255, 248, 235, .09));',
    '  --gv-linha2: var(--linha2, color-mix(in srgb, var(--gv-mudo) 34%, transparent));',
    '  --gv-bg: var(--ficha-bg, var(--zona, #121211));',
    '  --gv-borda: var(--ficha-borda, var(--gv-linha2));',
    '  --gv-fundo: var(--bg, #0c0c0b);',
    '  --gv-vazio: var(--vazio, color-mix(in srgb, var(--gv-mudo) 20%, transparent));',
    '  --gv-font: var(--font, var(--sans, "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif));',
    '  --gv-fontT: var(--fontT, var(--din, Bahnschrift, "Segoe UI", sans-serif));',
    '  --gv-mono: Consolas, "Cascadia Mono", monospace;',
    '  --gv-c: var(--gv-mudo);',
    '}',
    '.gv { position: fixed; top: 0; right: 0; bottom: 0; width: min(440px, 94vw); z-index: 90; display: flex; flex-direction: column; box-sizing: border-box;',
    '  background: var(--gv-bg); color: var(--gv-texto); border-left: 1px solid var(--gv-borda); box-shadow: -30px 0 60px rgba(0, 0, 0, .32);',
    '  -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); font: 13px/1.45 var(--gv-font); letter-spacing: normal; text-transform: none; text-align: left;',
    '  transform: translateX(104%); visibility: hidden; transition: transform .24s cubic-bezier(.2, .7, .2, 1), visibility 0s linear .24s; cursor: auto; user-select: text; }',
    '.gv.gv-on { transform: none; visibility: visible; transition: transform .24s cubic-bezier(.2, .7, .2, 1); }',
    '.gv.gv-ancorada { border-top: 1px solid var(--gv-linha); box-shadow: -24px 12px 50px rgba(0, 0, 0, .28); }',
    '.gv *, .gv *::before, .gv *::after { box-sizing: border-box; }',
    '.gv-e-bom { --gv-c: var(--bom, #74b08f); } .gv-e-atencao { --gv-c: var(--atencao, #d9a440); } .gv-e-ruim { --gv-c: var(--ruim, #e5534b); }',
    '.gv-e-dele { --gv-c: var(--dele, #a593f2); } .gv-e-duvida { --gv-c: var(--duvida, #63a6d8); }',
    '.gv-e-desligado { --gv-c: var(--desligado, #6d6b65); } .gv-e-construcao { --gv-c: var(--construcao, #5f5d57); }',
    '.gv-gl { display: inline-block; flex: none; width: 7px; height: 7px; background: var(--gv-c); }',
    '.gv-gl.gv-bom { border-radius: 50%; } .gv-gl.gv-ruim { border-radius: 1px; }',
    '.gv-gl.gv-atencao { width: 8px; clip-path: polygon(50% 0, 100% 100%, 0 100%); }',
    '.gv-gl.gv-dele { border-radius: 1px; transform: rotate(45deg) scale(.84); }',
    '.gv-gl.gv-duvida { background: none; height: auto; color: var(--gv-c); font: 700 11px/7px var(--gv-fontT); text-align: center; }',
    '.gv-gl.gv-duvida::before { content: "?"; }',
    '.gv-gl.gv-desligado { background: none; border: 1.3px solid var(--gv-c); border-radius: 50%; }',
    '.gv-gl.gv-construcao { background: none; border: 1.3px dashed var(--gv-c); border-radius: 50%; }',
    '.gv-cab { display: flex; align-items: flex-start; gap: 12px; padding: 18px 18px 14px; border-bottom: 1px solid var(--gv-linha); }',
    '.gv-cab > .gv-gl { width: 9px; height: 9px; margin-top: 8px; }',
    '.gv-t { min-width: 0; flex: 1; }',
    '.gv-t h3 { margin: 0 0 2px; font: 600 18px/1.3 var(--gv-font); letter-spacing: -.01em; overflow-wrap: anywhere; }',
    '.gv-t small { color: var(--gv-mudo); font-size: 12px; }',
    '.gv-x { flex: none; background: none; border: 1px solid var(--gv-linha2); border-radius: 7px; width: 28px; height: 28px; cursor: pointer; color: var(--gv-mudo); font-size: 17px; line-height: 1; padding: 0; }',
    '.gv-x:hover { color: var(--gv-texto); border-color: var(--gv-mudo); }',
    '.gv-corpo { padding: 14px 18px 28px; overflow-y: auto; flex: 1; scrollbar-width: thin; scrollbar-color: var(--gv-linha2) transparent; }',
    '.gv-trilha { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 6px; margin: 0 0 12px; font-size: 11.5px; color: var(--gv-mudo); }',
    '.gv-trilha button { padding: 2px 7px; margin-left: -7px; border: 0; border-radius: 5px; background: none; color: var(--gv-mudo); font: inherit; cursor: pointer; }',
    '.gv-trilha button:hover { color: var(--gv-texto); background: color-mix(in srgb, var(--gv-mudo) 14%, transparent); }',
    '.gv-trilha i { font-style: normal; opacity: .6; } .gv-trilha span { color: var(--gv-texto2); }',
    '.gv-est { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 12.5px; }',
    '.gv-estn { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; color: color-mix(in srgb, var(--gv-c) 80%, var(--gv-texto)); }',
    '.gv-est.gv-e-bom .gv-estn { color: var(--gv-texto); }',
    '.gv-passo { color: var(--gv-mudo); font-size: 12px; }',
    '.gv-frase { margin: 0 0 12px; font-size: 14px; line-height: 1.5; }',
    '.gv-linhas { margin: 0 0 6px; padding: 9px 11px; list-style: none; background: var(--gv-fundo); border: 1px solid var(--gv-linha); border-radius: 7px; font: 11.5px/1.55 var(--gv-mono); color: var(--gv-texto2); overflow-wrap: anywhere; }',
    '.gv-linhas li + li { margin-top: 3px; }',
    '.gv-acao-topo { margin: 0 0 10px; }',
    '.gv-res-topo { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; column-gap: 10px; align-items: baseline; font-size: 13px; }',
    '.gv-res-topo small { color: var(--gv-mudo); font-size: 11.5px; white-space: nowrap; }',
    '.gv-texto { margin-top: 10px; padding: 10px 12px; max-height: 320px; overflow: auto; background: var(--gv-fundo); border: 1px solid var(--gv-linha); border-radius: 7px; font-size: 12.5px; line-height: 1.55; color: var(--gv-texto2); overflow-wrap: anywhere; }',
    '.gv-texto small { display: block; margin-bottom: 6px; color: var(--gv-mudo); font-size: 11px; }',
    '.gv-det { margin-top: 10px; } .gv-det summary { cursor: pointer; color: var(--gv-mudo); font-size: 12px; }',
    '.gv-pre { margin: 8px 0 0; padding: 9px 11px; max-height: 220px; overflow: auto; background: var(--gv-fundo); border: 1px solid var(--gv-linha); border-radius: 7px; font: 11.5px/1.55 var(--gv-mono); color: var(--gv-texto2); white-space: pre-wrap; overflow-wrap: anywhere; }',
    '.gv-itens { list-style: none; margin: 10px 0 0; padding: 0; font-size: 12.5px; } .gv-itens li { padding: 5px 0; } .gv-itens li + li { border-top: 1px solid var(--gv-linha); }',
    '.gv-itens a { color: var(--gv-texto); text-decoration: none; } .gv-itens a:hover { text-decoration: underline; }',
    '.gv-itens small { display: block; color: var(--gv-mudo); font-size: 11.5px; overflow-wrap: anywhere; }',
    '.gv-obs { display: inline-block; margin-top: 12px; padding: 6px 12px; border: 1px solid var(--gv-linha); border-radius: 7px; color: var(--gv-texto); text-decoration: none; font-size: 12.5px; }',
    '.gv-obs:hover, .gv-obs:focus-visible { background: color-mix(in srgb, var(--gv-mudo) 14%, transparent); outline: none; }',
    '.gv-sec { margin-top: 20px; }',
    '.gv-sec h4 { margin: 0 0 8px; font: 600 9.5px/1.2 var(--gv-fontT); letter-spacing: .12em; text-transform: uppercase; color: var(--gv-mudo); }',
    '.gv-sec h4 span { margin-left: 4px; font-variant-numeric: tabular-nums; opacity: .8; }',
    '.gv-ref { list-style: none; margin: 0; padding: 0; }',
    '.gv-ref li { display: grid; grid-template-columns: 8px minmax(0, 1fr); column-gap: 10px; align-items: center; padding: 5px 8px; margin: 0 -8px; border-radius: 6px; cursor: pointer; }',
    '.gv-ref li.gv-fixo { cursor: default; }',
    '.gv-ref li:not(.gv-fixo):hover, .gv-ref li:focus-visible { background: color-mix(in srgb, var(--gv-mudo) 12%, transparent); outline: none; }',
    '.gv-ref li small { grid-column: 2; color: var(--gv-mudo); font-size: 11.5px; line-height: 1.38; }',
    '.gv-fatos { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 16px; margin: 0; font-size: 12.5px; }',
    '.gv-fatos dt { color: var(--gv-mudo); } .gv-fatos dd { margin: 0; color: var(--gv-texto2); overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }',
    '.gv-fatos code { font: 11.5px var(--gv-mono); color: var(--gv-texto2); }',
    '.gv-ficha { margin-top: 12px; grid-template-columns: minmax(0, 1fr); gap: 2px 0; } .gv-ficha dt { margin-top: 8px; } .gv-ficha dd { line-height: 1.5; font-variant-numeric: normal; }',
    '.gv-cods { list-style: none; margin: 0; padding: 0; font-size: 12.5px; }',
    '.gv-cods li { display: grid; grid-template-columns: 8px 22px minmax(0, 1fr); column-gap: 10px; align-items: baseline; padding: 4px 0; color: var(--gv-texto2); }',
    '.gv-cods li + li { border-top: 1px solid var(--gv-linha); }',
    '.gv-cods .gv-gl { position: relative; top: -1px; } .gv-cods code { font: 11.5px var(--gv-mono); color: var(--gv-mudo); text-align: right; }',
    '.gv-cods li.gv-cod-atual { color: var(--gv-texto); } .gv-cods li.gv-cod-atual code { color: var(--gv-texto); }',
    '.gv-cods i { font-style: normal; margin-left: 6px; padding: 1px 7px; border-radius: 999px; font-size: 10.5px; color: var(--gv-mudo); background: color-mix(in srgb, var(--gv-mudo) 14%, transparent); white-space: nowrap; }',
    '.gv-bat { display: flex; gap: 1px; height: 22px; }',
    '.gv-bat b { flex: 1; background: var(--gv-c); border-radius: 1px; }',
    '.gv-bat b.gv-e-bom { background: color-mix(in srgb, var(--gv-c) 46%, var(--gv-vazio)); }',
    '.gv-bat b.gv-e-desligado, .gv-bat b.gv-e-construcao { background: color-mix(in srgb, var(--gv-mudo) 40%, var(--gv-vazio)); }',
    '.gv-bat b.gv-nada { background: var(--gv-vazio); }',
    '.gv-bat-eixo { display: flex; justify-content: space-between; color: var(--gv-mudo); font-size: 10.5px; margin-top: 5px; font-variant-numeric: tabular-nums; }',
    '.gv-oque { margin: 0; color: var(--gv-texto2); line-height: 1.55; }',
    '.gv-nota { margin: 6px 0 0; color: var(--gv-mudo); font-size: 11.5px; line-height: 1.45; }',
    '.gv-passos { margin: 0; padding-left: 18px; color: var(--gv-texto2); font-size: 12.5px; line-height: 1.5; } .gv-passos li + li { margin-top: 5px; }',
    '.gv-esp { padding: 10px 12px; border: 1px solid color-mix(in srgb, var(--gv-c) 34%, var(--gv-linha)); border-radius: 8px; background: color-mix(in srgb, var(--gv-c) 7%, transparent); }',
    '.gv-esp + .gv-esp { margin-top: 8px; }',
    '.gv-esp-o { display: flex; align-items: baseline; gap: 9px; } .gv-esp-o .gv-gl { position: relative; top: -1px; } .gv-esp-o b { font-weight: 600; }',
    '.gv-esp dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 3px 12px; margin: 8px 0 0 16px; font-size: 12px; }',
    '.gv-esp dt { color: var(--gv-mudo); } .gv-esp dd { margin: 0; color: var(--gv-texto2); }',
    '.gv-esp .gv-acao { margin: 10px 0 0 16px; }',
    '.gv-acoes { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }',
    '.gv-sec .gv-acoes { margin-top: 10px; }',
    '.gv-acao { padding: 6px 13px; border-radius: 6px; border: 1px solid color-mix(in srgb, var(--gv-c) 48%, var(--gv-linha2)); background: color-mix(in srgb, var(--gv-c) 13%, transparent);',
    '  color: var(--gv-texto); cursor: pointer; font: 600 12px/1.3 var(--gv-font); transition: background-color .15s; }',
    '.gv-acao:hover:not([disabled]) { background: color-mix(in srgb, var(--gv-c) 26%, transparent); }',
    '.gv-acao[disabled] { opacity: .5; cursor: not-allowed; }',
    '.gv-acao.gv-ok { --gv-c: var(--bom, #74b08f); } .gv-acao.gv-erro { --gv-c: var(--ruim, #e5534b); } .gv-acao.gv-aviso { --gv-c: var(--atencao, #d9a440); }',
    '.gv-chip { flex: none; margin-left: auto; display: inline-flex; align-items: center; gap: 8px; padding: 4px 6px 4px 10px; border: 1px solid var(--gv-linha2); border-radius: 999px; background: none;',
    '  color: var(--gv-mudo); font: 11.5px/1.3 var(--gv-font); letter-spacing: normal; text-transform: none; white-space: nowrap; cursor: pointer; font-variant-numeric: tabular-nums; }',
    '.gv-chip i { width: 7px; height: 7px; border-radius: 50%; background: var(--gv-c); }',
    '.gv-chip b { padding: 2px 8px; border-radius: 999px; background: color-mix(in srgb, var(--gv-mudo) 16%, transparent); color: var(--gv-texto); font-weight: 600; }',
    '.gv-chip:hover, .gv-chip.gv-chip-on { color: var(--gv-texto); border-color: var(--gv-mudo); }',
    '.gv-chip.gv-chip-ruim { border-color: var(--ruim, #e5534b); color: var(--gv-texto); }',
    '@media (max-width: 1500px) { .gv-chip span { display: none; } .gv-chip { padding-left: 8px; } }',
    '@media (prefers-reduced-motion: reduce) { .gv, .gv.gv-on { transition: none; } }'
  ].join('\n');

  // clique num botao de acao posto fora da gaveta por Gaveta.botao: age sem abrir o detalhe da peca
  document.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest('[data-gv-acao]') : null;
    if (!b || (raiz && raiz.contains(b))) return;
    ev.stopPropagation();
    if (!b.disabled) agir(b.getAttribute('data-gv-acao'));
  }, true);

  window.Gaveta = {iniciar: iniciar, receber: receber, abrir: abrir, fechar: fechar, aberto: function () { return aberto; }, chip: chip, MAPA: MAPA_ID,
    botao: botaoAcao, agir: agir};
})();
