"use strict";
(function () {
  const modal = document.getElementById("agenda-modal");
  const content = document.getElementById("agenda-conteudo");
  const detail = document.getElementById("agenda-detalhe");
  const period = document.getElementById("agenda-periodo");
  let selected = new Date();
  let opener = null;
  let rangeStart = null, rangeEnd = null;
  const weekdays = ["seg", "ter", "qua", "qui", "sex"];

  function localDate(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }
  function monday(d) {
    const x = localDate(d);
    x.setDate(x.getDate() - (x.getDay() + 6) % 7);
    return x;
  }
  function localIso(d) {
    const offset = -d.getTimezoneOffset();
    const sign = offset >= 0 ? "+" : "-";
    const zone = sign + String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0") + ":" + String(Math.abs(offset) % 60).padStart(2, "0");
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + "T" + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + ":00" + zone;
  }
  function dateOnly(value) {
    const [y, m, d] = value.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  function eventDate(value, allDay) {
    return allDay ? dateOnly(value) : new Date(value);
  }
  function safe(text) {
    return String(text || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function hm(d) {
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }
  function fmt(d, options) {
    return new Intl.DateTimeFormat("pt-BR", options).format(d);
  }
  function periodText(start) {
    const end = new Date(start); end.setDate(end.getDate() + 4);
    period.textContent = start.getMonth() === end.getMonth()
      ? fmt(start, { day: "numeric" }) + "–" + fmt(end, { day: "numeric", month: "long", year: "numeric" })
      : fmt(start, { day: "numeric", month: "short" }) + " – " + fmt(end, { day: "numeric", month: "short", year: "numeric" });
  }
  async function carregar() {
    const start = monday(selected), end = new Date(start); end.setDate(end.getDate() + 5);
    rangeStart = start; rangeEnd = end;
    periodText(start);
    content.innerHTML = '<div class="agenda-status">Carregando agenda…</div>';
    try {
      const url = "/api/agenda?inicio=" + encodeURIComponent(localIso(start)) + "&fim=" + encodeURIComponent(localIso(end));
      const response = await fetch(url);
      const data = await response.json();
      if (!response.ok) throw new Error(data.erro || data.detail || "Não foi possível carregar a agenda.");
      const events = (data.eventos || []).filter((ev) => ev.status !== "cancelled").sort((a, b) => eventDate(a.inicio, a.dia_inteiro) - eventDate(b.inicio, b.dia_inteiro));
      desenhar(start, events);
    } catch (error) {
      content.innerHTML = '<div class="agenda-status">' + safe(error.message || "Não foi possível carregar a agenda.") + "</div>";
    }
  }
  function desenhar(start, events) {
    const days = Array.from({ length: 5 }, (_, i) => { const d = new Date(start); d.setDate(d.getDate() + i); return d; });
    const end = new Date(start); end.setDate(end.getDate() + 5);
    const today = localDate(new Date()).getTime();
    const timed = Array.from({ length: 5 }, () => []), allDay = Array.from({ length: 5 }, () => []);
    events.forEach((ev) => {
      if (!ev.inicio) return;
      const d = eventDate(ev.inicio, ev.dia_inteiro);
      if (d < start || d >= end) return;
      const index = Math.floor((localDate(d) - start) / 86400000);
      if (index < 0 || index >= 5) return;
      (ev.dia_inteiro ? allDay : timed)[index].push(ev);
    });
    let html = '<div class="agenda-week"><div class="agenda-canto" style="grid-column:1;grid-row:1"></div>';
    days.forEach((d, i) => html += '<div class="agenda-dia' + (d.getTime() === today ? ' agenda-dia-atual' : '') + '" style="grid-column:' + (i + 2) + ';grid-row:1">' + weekdays[i] + '<b>' + d.getDate() + '</b></div>');
    html += '<div class="agenda-allday-label" style="grid-column:1;grid-row:2">dia todo</div>';
    allDay.forEach((list, i) => html += '<div class="agenda-all-day" style="grid-column:' + (i + 2) + ';grid-row:2">' + list.map((ev) => '<button type="button" class="agenda-all-event" data-event-id="' + safe(ev.id) + '" data-account="' + safe(ev.conta) + '" title="' + safe(ev.titulo) + '">' + safe(ev.titulo) + '</button>').join("") + '</div>');
    timed.forEach((list) => {
      list.sort((a, b) => eventDate(a.inicio, false) - eventDate(b.inicio, false));
      let cluster = [], clusterEnd = -Infinity;
      const layoutCluster = () => {
        const laneEnds = [];
        cluster.forEach((ev) => {
          const begin = eventDate(ev.inicio, false).getTime(), finish = eventDate(ev.fim || ev.inicio, false).getTime();
          let lane = laneEnds.findIndex((until) => until <= begin);
          if (lane < 0) lane = laneEnds.length;
          laneEnds[lane] = finish;
          ev._agendaLane = lane;
        });
        cluster.forEach((ev) => { ev._agendaLanes = laneEnds.length; });
        cluster = [];
      };
      list.forEach((ev) => {
        const begin = eventDate(ev.inicio, false).getTime(), finish = eventDate(ev.fim || ev.inicio, false).getTime();
        if (cluster.length && begin >= clusterEnd) layoutCluster();
        cluster.push(ev); clusterEnd = Math.max(clusterEnd, finish);
      });
      if (cluster.length) layoutCluster();
    });
    for (let hour = 7; hour < 22; hour++) {
      const row = hour - 7 + 3;
      html += '<div class="agenda-hora" style="grid-column:1;grid-row:' + row + '">' + String(hour).padStart(2, "0") + ':00</div>';
      days.forEach((d, i) => {
        const items = timed[i].filter((ev) => {
          const s = eventDate(ev.inicio, false), e = eventDate(ev.fim || ev.inicio, false);
          return s.getHours() <= hour && (e.getHours() > hour || (e.getHours() === hour && e.getMinutes() > 0));
        });
        html += '<div class="agenda-slot" style="grid-column:' + (i + 2) + ';grid-row:' + row + '">';
        items.forEach((ev) => {
          const s = eventDate(ev.inicio, false), e = eventDate(ev.fim || ev.inicio, false);
          const startMinutes = Math.max(7 * 60, s.getHours() * 60 + s.getMinutes());
          const endMinutes = Math.min(22 * 60, Math.max(startMinutes, e.getHours() * 60 + e.getMinutes()));
          const top = (startMinutes - hour * 60) * 64 / 60;
          if (top < 0 || top >= 64) return;
          const duration = Math.max(0, endMinutes - startMinutes);
          const height = duration * 64 / 60;
          const compact = duration < 35;
          const tiny = duration <= 5;
          const lanes = ev._agendaLanes || 1, lane = ev._agendaLane || 0;
          const tag = "button";
          const link = ' type="button" data-event-id="' + safe(ev.id) + '" data-account="' + safe(ev.conta) + '"';
          const left = 'calc(' + (lane * 100 / lanes).toFixed(3) + '% + 3px)';
          const right = 'calc(' + ((lanes - lane - 1) * 100 / lanes).toFixed(3) + '% + 3px)';
          html += '<' + tag + ' class="agenda-event agenda-event-button' + (ev.transcricao ? ' transcrito' : '') + (compact ? ' compact' : '') + (tiny ? ' tiny' : '') + '"' + link + ' style="top:' + top + 'px;height:' + Math.min(height, 960 - (hour - 7) * 64 - top) + 'px;left:' + left + ';right:' + right + '" title="' + safe(ev.titulo + ' · ' + hm(s) + '–' + hm(e) + (ev.transcricao ? ' · transcrição vinculada' : '') + (ev.descricao ? " · " + ev.descricao : "")) + '"><strong>' + safe(ev.titulo) + '</strong><span>' + hm(s) + '–' + hm(e) + '</span></' + tag + '>';
        });
        html += '</div>';
      });
    }
    html += '</div>';
    if (!events.length) html = '<div class="agenda-status">Nenhuma reunião nesta semana.</div>';
    content.innerHTML = html;
  }
  async function abrirDetalhe(button) {
    const params = new URLSearchParams({ evento_id: button.dataset.eventId, conta: button.dataset.account,
      inicio: localIso(rangeStart), fim: localIso(rangeEnd) });
    detail.hidden = false;
    detail.innerHTML = '<div class="agenda-status">Carregando detalhes…</div>';
    try {
      const response = await fetch('/api/agenda/detalhe?' + params.toString());
      const ev = await response.json();
      if (!response.ok) throw new Error(ev.detail || ev.erro || 'Não foi possível carregar os detalhes.');
      const start = eventDate(ev.inicio, ev.dia_inteiro), end = eventDate(ev.fim || ev.inicio, ev.dia_inteiro);
      const when = ev.dia_inteiro ? fmt(start, { weekday:'long', day:'numeric', month:'long', year:'numeric' })
        : fmt(start, { weekday:'long', day:'numeric', month:'long', year:'numeric' }) + ' · ' + hm(start) + '–' + hm(end);
      const t = ev.transcricao;
      detail.innerHTML = '<button type="button" class="agenda-detail-close" id="agenda-detalhe-voltar">← Voltar à agenda</button>' +
        '<h3>' + safe(ev.titulo) + '</h3><div class="agenda-detail-meta">' + safe(when) + '</div>' +
        (ev.participantes && ev.participantes.length ? '<h4>Participantes</h4><p>' + safe(ev.participantes.join(', ')) + '</p>' : '') +
        (ev.meet_url ? '<p><a href="' + safe(ev.meet_url) + '" target="_blank" rel="noopener noreferrer">Abrir Google Meet</a></p>' : '') +
        (ev.html_link ? '<p><a href="' + safe(ev.html_link) + '" target="_blank" rel="noopener noreferrer">Abrir no Google Agenda</a></p>' : '') +
        (ev.descricao ? '<h4>Descrição</h4><p>' + safe(ev.descricao) + '</p>' : '') +
        (t ? '<h4>Transcrição Gutenberg · ' + safe(t.titulo) + '</h4>' + (t.resumo ? '<h4>Resumo</h4><pre>' + safe(t.resumo) + '</pre>' : '<p>Transcrição localizada; ainda não há resumo salvo no Obsidian.</p>') +
          (t.nota ? '<p>Nota no Obsidian: ' + safe(t.nota) + '</p>' : '') + '<details><summary>Transcrição completa (' + safe(t.falas) + ' falas)</summary><pre>' + safe(t.texto || 'Transcrição indisponível.') + '</pre></details>' :
          '<h4>Transcrição</h4><p>Não encontrei uma transcrição do Gutenberg compatível com esta reunião (mesmo dia e início em até 15 minutos).</p>');
      document.getElementById('agenda-detalhe-voltar').addEventListener('click', () => { detail.hidden = true; button.focus(); });
    } catch (error) {
      detail.innerHTML = '<button type="button" class="agenda-detail-close" id="agenda-detalhe-voltar">← Voltar à agenda</button><div class="agenda-status">' + safe(error.message) + '</div>';
      document.getElementById('agenda-detalhe-voltar').addEventListener('click', () => { detail.hidden = true; button.focus(); });
    }
  }
  function abrir(origem) {
    if (modal.open) return;
    opener = origem || document.activeElement;
    selected = new Date(); modal.showModal(); carregar();
  }
  document.getElementById("agenda-fechar").addEventListener("click", () => modal.close());
  document.getElementById("agenda-hoje").addEventListener("click", () => { selected = new Date(); carregar(); });
  document.getElementById("agenda-anterior").addEventListener("click", () => { selected.setDate(selected.getDate() - 7); carregar(); });
  document.getElementById("agenda-proxima").addEventListener("click", () => { selected.setDate(selected.getDate() + 7); carregar(); });
  content.addEventListener('click', (event) => { const button = event.target.closest('[data-event-id]'); if (button) abrirDetalhe(button); });
  modal.addEventListener("click", (event) => { if (event.target === modal) modal.close(); });
  modal.addEventListener("close", () => { if (opener && opener.isConnected) opener.focus(); });
  window.AgendaUI = { abrir };
})();
