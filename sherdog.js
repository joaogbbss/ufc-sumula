/* =====================================================================
   SÚMULA UFC — Módulo "Compartilhar no Sherdog"
   ---------------------------------------------------------------------
   Gera um card em PNG com o evento inteiro (lutas, lutadores, OVR,
   cartel e probabilidades) em dois formatos: FILEIRA (largo, 2 colunas)
   ou VERTICAL (estreito, uma luta por linha). Também monta o BBCode
   pronto para colar no fórum do Sherdog.

   Instalação: 1 linha no index.html, logo ANTES de </body>:
       <script src="sherdog.js"></script>
   O módulo se registra sozinho no roteador (window.XT / window.XV),
   exatamente como o bloco do Raio-X. Remover a linha desfaz tudo.
   ===================================================================== */
(function () {
  'use strict';

  const BASE = 1500, GOLD = '#f5c518', BLUE = '#6c8cff', BG = '#090a0d',
        MUT = '#8b94a5', TXT = '#eef1f6', LINE = '#2a2e38',
        FD = '"Big Shoulders Display",Impact,"Arial Narrow",sans-serif',
        FB = 'Archivo,Arial,Helvetica,sans-serif';

  // estado do módulo
  const Q = { up: null, an: null, cd: null, dec: null, live: null, loaded: false, mode: 'event', ev: 0, lay: 'row',
              fev: '', fid: '', pid: '', pq: '', busy: false, note: '' };

  const F = id => S.F.get(mid(id)) || null;
  const an = id => Q.an && Q.an.fighters[mid(id)] || null;
  const cd = id => Q.cd && Q.cd.cards && Q.cd.cards[mid(id)] || null;
  // estimativa pré-UFC (cards.json "est"): [ovr, V, D, E, nota-base]
  const est = id => Q.cd && Q.cd.est && Q.cd.est[mid(id)] || null;
  // OVR exibível: card estatístico (com * se provisório) ou estimativa pré-UFC (EST)
  const ovrOf = id => {
    const c = cd(id); if (c) return { v: c[0], tag: c[8] != null && c[8] < 4 ? '*' : '', c };
    const e = est(id); return e ? { v: e[0], tag: 'EST', c: null } : null;
  };
  const nm = x => (F(x.id) || {}).name || x.name || x.id;
  const pct = v => Math.round(v * 100) + '%';
  const last = n => String(n || '').trim().split(/\s+/).pop();

  /* ---------- carga dos dados (cada arquivo é opcional) ---------- */
  async function grab(file) {
    try {
      const r = await fetch('data/' + file, { cache: 'no-cache' });
      return r.ok ? await r.json() : null;
    } catch { return null; }
  }
  async function load() {
    if (Q.loaded) return;
    const [a, c] = await Promise.all([grab('analytics.json'), grab('cards.json')]);
    Q.an = a; Q.cd = c;
    // o app já carrega upcoming.json no boot; só busca de novo se faltar
    const u = (S.up && S.up.length) ? { events: S.up } : await grab('upcoming.json');
    Q.up = u && u.events && u.events.length ? u : null;
    Q.loaded = true;
  }
  // auditoria de decisões e probabilidade ao vivo: só quando o modo "luta realizada" é usado
  async function loadFightExtras() {
    if (Q.dec !== null && Q.live !== null) return;
    const [d, l] = await Promise.all([grab('decisions.json'), grab('live.json')]);
    Q.dec = d || false; Q.live = l || false;
  }

  /* ---------- probabilidade do confronto ----------
     Mesma base do Raio-X: ELO encolhido para 1500 em cartel curto.
     Quando o scraper trouxe odds de mercado (mkt_pa/mkt_pb), elas são
     combinadas com o ELO — mercado pesa mais porque já embute lesão,
     corte de peso e notícia de bastidor, que não estão nos dados. */
  function prob(f) {
    // nota efetiva: ELO encolhido para 1500 em cartel curto; estreante usa a nota-base
    // estimada pelo cartel profissional (±40 em torno de 1500); sem nenhum dado, 1500
    const eff = id => {
      const a = an(id); if (a) return BASE + (a.e - BASE) * a.n / (a.n + 3);
      const e = est(id); return e ? e[4] : (F(id) ? BASE : null);
    };
    const ea = eff(f.a.id), eb = eff(f.b.id);
    const pElo = ea != null && eb != null && (an(f.a.id) || an(f.b.id) || est(f.a.id) || est(f.b.id))
      ? 1 / (1 + Math.pow(10, (eb - ea) / 400)) : null;
    const pMkt = (typeof f.mkt_pa === 'number' && typeof f.mkt_pb === 'number' && (f.mkt_pa + f.mkt_pb) > 0)
      ? f.mkt_pa / (f.mkt_pa + f.mkt_pb) : null;
    if (pElo == null && pMkt == null) return { p: null, src: 'none' };
    if (pElo == null) return { p: pMkt, src: 'mkt' };
    if (pMkt == null) return { p: pElo, src: 'elo' };
    return { p: 0.35 * pElo + 0.65 * pMkt, src: 'both' };
  }

  const sum = x => x.reduce((m, n) => m + n, 0);
  // cartel UFC: só lutas no UFC (analytics.json); vazio = estreia
  const recUfc = id => { const a = an(id); return a ? `${sum(a.w)}-${sum(a.l)}-${a.d}` : ''; };
  // cartel profissional completo, como publicado na ficha do ufcstats (inclui NC quando houver)
  const recMma = id => String((F(id) || {}).record || '').replace(/^record:\s*/i, '').trim();
  const nUfc = id => { const a = an(id); return a ? a.n : 0; };
  // texto curto para tabela e imagem: "MMA 17-0-0 · UFC 9-0-0"
  const recLine = id => {
    const m = recMma(id), u = recUfc(id), b = [];
    if (m) b.push('MMA ' + m);
    b.push(u ? 'UFC ' + u : T('UFC debut', 'estreia no UFC'));
    return b.join('  ·  ');
  };
  // siglas usadas por fãs e imprensa (W = feminino)
  const AB = {Strawweight: 'SW', Flyweight: 'FLW', Bantamweight: 'BW', Featherweight: 'FW', Lightweight: 'LW',
              Welterweight: 'WW', Middleweight: 'MW', 'Light Heavyweight': 'LHW', Heavyweight: 'HW'};
  const abbr = d => d.startsWith("Women's ") ? 'W-' + (AB[d.slice(8)] || d.slice(8)) : (AB[d] || d);
  const divsOf = id => { const a = an(id); return a && a.divs ? a.divs.map(d => d[0]).filter(d => !['Catch Weight', 'Open Weight', 'Outros'].includes(d)) : []; };

  /* ---------- BBCode para o fórum ---------- */
  function bb() {
    const e = Q.up.events[Q.ev], L = [];
    L.push('[B][SIZE=5]' + e.name + '[/SIZE][/B]');
    L.push('[I]' + fmt(e.date) + (e.location ? ' — ' + e.location : '') + '[/I]');
    L.push('');
    L.push('[TABLE]');
    L.push('[TR][TH]Bout[/TH][TH]Div[/TH][TH]OVR[/TH][TH]MMA record[/TH][TH]UFC record[/TH][TH]Win %[/TH][/TR]');
    e.fights.forEach(f => {
      const { p } = prob(f), oa = ovrOf(f.a.id), ob = ovrOf(f.b.id), ov = o => o ? o.v + (o.tag === 'EST' ? ' (est)' : o.tag) : '—';
      const pa = p == null ? '—' : pct(p), pb = p == null ? '—' : pct(1 - p);
      L.push(`[TR][TD][B]${nm(f.a)}[/B] vs ${nm(f.b)}${f.title ? ' [B](TITLE)[/B]' : ''}[/TD]` +
             `[TD]${f.div}[/TD][TD]${ov(oa)} / ${ov(ob)}[/TD]` +
             `[TD]${recMma(f.a.id) || '—'} / ${recMma(f.b.id) || '—'}[/TD]` +
             `[TD]${recUfc(f.a.id) || 'debut'} / ${recUfc(f.b.id) || 'debut'}[/TD][TD]${pa} / ${pb}[/TD][/TR]`);
    });
    L.push('[/TABLE]');
    L.push('');
    L.push('[SIZE=1][I]Ratings & win probabilities: ELO adjusted for strength of schedule' +
           (Q.cd ? ', OVR on a 48–98 population-calibrated scale' : '') +
           '. MMA record = full pro record; UFC record = UFC bouts only. OVR (est) = pre-UFC estimate from the pro record. Probabilities, not predictions. Source: ufcstats.com[/I][/SIZE]');
    return L.join('\n');
  }

  /* ---------- desenho ---------- */
  const PW = 1020, PH = 240, GAP = 14, PAD = 42, HEAD = 250, FOOT = 120;

  function octPath(x, cx, cy, r) {
    x.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = Math.PI / 8 + i * Math.PI / 4;
      x[i ? 'lineTo' : 'moveTo'](cx + r * Math.cos(a), cy + r * Math.sin(a));
    }
    x.closePath();
  }
  function fitText(x, t, max, size, weight = 900, fam = FD) {
    let s = size; x.font = `${weight} ${s}px ${fam}`;
    while (x.measureText(t).width > max && s > 14) { s -= 2; x.font = `${weight} ${s}px ${fam}`; }
    return s;
  }
  function chamfer(x, X, Y, w, h, c) {
    x.beginPath();
    x.moveTo(X + c, Y); x.lineTo(X + w - c, Y); x.lineTo(X + w, Y + c);
    x.lineTo(X + w, Y + h - c); x.lineTo(X + w - c, Y + h); x.lineTo(X + c, Y + h);
    x.lineTo(X, Y + h - c); x.lineTo(X, Y + c); x.closePath();
  }

  // desenha UM confronto dentro de um retângulo PW x PH
  function panel(x, X, Y, f, imgs) {
    const { p, src } = prob(f);
    x.save();
    chamfer(x, X, Y, PW, PH, 12);
    x.fillStyle = '#13151a'; x.fill();
    x.strokeStyle = f.title ? GOLD : LINE; x.lineWidth = f.title ? 3 : 1.5; x.stroke();
    x.clip();

    // faixa superior: divisão / cinturão
    x.fillStyle = f.title ? GOLD : '#1b1e25';
    x.fillRect(X, Y, PW, 36);
    x.textAlign = 'left';
    x.fillStyle = f.title ? '#14110a' : MUT;
    x.font = `800 21px ${FB}`;
    x.fillText((f.div || '').toUpperCase() + (f.title ? '  •  TITLE BOUT' : ''), X + 20, Y + 25);

    const my = Y + 36, mh = PH - 36, cy = my + mh / 2 - 12;
    const PHO = 74, CX = X + PW / 2;

    // retrato + nome + OVR de um lado
    const side = (key, dir) => {
      const fg = f[key], col = dir < 0 ? GOLD : BLUE;
      const px = dir < 0 ? X + 24 + PHO / 2 : X + PW - 24 - PHO / 2;
      const img = imgs[fg.id];
      x.save(); octPath(x, px, cy - 6, PHO / 2); x.clip();
      x.fillStyle = '#242832'; x.fillRect(px - PHO / 2, cy - 6 - PHO / 2, PHO, PHO);
      if (img) x.drawImage(img, px - PHO / 2, cy - 6 - PHO / 2, PHO, PHO);
      else {
        x.fillStyle = MUT; x.textAlign = 'center'; x.font = `800 30px ${FD}`;
        x.fillText(ini(nm(fg)), px, cy + 5);
      }
      x.restore();
      x.strokeStyle = col; x.lineWidth = 3; octPath(x, px, cy - 6, PHO / 2); x.stroke();

      const tx = dir < 0 ? px + PHO / 2 + 18 : px - PHO / 2 - 18;
      x.textAlign = dir < 0 ? 'left' : 'right';
      x.fillStyle = TXT;
      // largura livre até o selo de OVR, com folga para o nome nunca encostar nele
      const avail = PW / 2 - PHO - (ovrOf(fg.id) ? 182 : 96);
      fitText(x, nm(fg).toUpperCase(), avail, 40);
      x.fillText(nm(fg).toUpperCase(), tx, cy - 14);
      const c = ovrOf(fg.id), a2 = an(fg.id);
      // linha 1: cartel completo de MMA + cartel no UFC
      x.fillStyle = TXT; fitText(x, recLine(fg.id), avail + 40, 21, 600, FB);
      x.fillText(recLine(fg.id), tx, cy + 14);
      // linha 2: índices do UFC (ou aviso de estreia / amostra curta)
      const bits = [];
      if (a2 && a2.e != null) bits.push('ELO ' + Math.round(a2.e));
      if (a2 && a2.dli != null) bits.push('DLI ' + a2.dli);
      const dv = divsOf(fg.id);
      if (dv.length > 1) bits.push(dv.map(abbr).join(' + '));
      if (!a2) bits.push(est(fg.id) ? T('OVR estimated from pro record', 'OVR estimado pelo cartel') : T('no UFC data yet', 'sem dados no UFC ainda'));
      else if (a2.n < 3) bits.push(T('provisional', 'provisório'));
      x.fillStyle = MUT; fitText(x, bits.join('  ·  '), avail + 40, 19, 500, FB);
      x.fillText(bits.join('  ·  '), tx, cy + 40);
      if (c) {                                   // selo de OVR
        const ox = dir < 0 ? X + PW / 2 - 92 : X + PW / 2 + 60;
        x.fillStyle = col; x.textAlign = 'center';
        x.font = `900 46px ${FD}`; x.fillText(String(c.v), ox + 16, cy + 2);
        x.fillStyle = MUT; x.font = `700 15px ${FB}`; x.fillText(c.tag === 'EST' ? 'EST' : 'OVR' + c.tag, ox + 16, cy + 22);
      }
    };
    side('a', -1); side('b', 1);

    // VS central
    x.textAlign = 'center'; x.fillStyle = MUT; x.font = `800 26px ${FD}`;
    x.fillText('VS', CX, cy - 24);

    // barra de probabilidade
    const bw = PW - 160, bx = X + 80, by = my + mh - 30;
    if (p != null) {
      x.fillStyle = GOLD; x.fillRect(bx, by, bw * p, 12);
      x.fillStyle = BLUE; x.fillRect(bx + bw * p, by, bw * (1 - p), 12);
      x.textAlign = 'left'; x.fillStyle = GOLD; x.font = `900 24px ${FD}`;
      x.fillText(pct(p), bx, by - 8);
      x.textAlign = 'right'; x.fillStyle = BLUE;
      x.fillText(pct(1 - p), bx + bw, by - 8);
      const debut = !an(f.a.id) || !an(f.b.id);
      const lbl = [src === 'mkt' ? 'market odds' : src === 'both' ? 'ELO + market' : '', debut ? T('debut: pre-UFC estimate', 'estreante: estimativa pré-UFC') : ''].filter(Boolean).join(' · ');
      if (lbl) {
        x.textAlign = 'center'; x.fillStyle = MUT; x.font = `600 14px ${FB}`;
        x.fillText(lbl, CX, by - 10);
      }
    } else {
      x.textAlign = 'center'; x.fillStyle = MUT; x.font = `600 17px ${FB}`;
      x.fillText(T('no rating data', 'sem dados de rating'), CX, by + 10);
    }
    x.restore();
  }

  // pré-carrega os retratos (CORS: ESPN serve com Access-Control-Allow-Origin)
  function photos(ids) {
    return Promise.all(ids.map(id => new Promise(res => {
      const src = (S.me.ph && S.me.ph[mid(id)]) || (F(id) || {}).img;
      if (!src) return res([id, null]);
      const im = new Image();
      im.crossOrigin = 'anonymous';
      im.onload = () => res([id, im]);
      im.onerror = () => res([id, null]);
      im.src = src;
    }))).then(ps => Object.fromEntries(ps));
  }

  async function render() {
    const e = Q.up.events[Q.ev], fs = e.fights || [];
    if (!fs.length) return null;
    const imgs = await photos(fs.flatMap(f => [f.a.id, f.b.id]));
    const row = Q.lay === 'row';
    const cols = row ? Math.min(2, fs.length) : 1;
    const rows = Math.ceil(fs.length / cols);
    const W = PAD * 2 + cols * PW + (cols - 1) * GAP;
    const H = HEAD + rows * PH + (rows - 1) * GAP + FOOT;

    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const x = cv.getContext('2d');

    x.fillStyle = BG; x.fillRect(0, 0, W, H);
    // textura diagonal discreta
    x.strokeStyle = 'rgba(255,255,255,.035)'; x.lineWidth = 1;
    for (let i = -H; i < W; i += 44) {
      x.beginPath(); x.moveTo(i, 0); x.lineTo(i + H, H); x.stroke();
    }
    // moldura
    x.strokeStyle = GOLD; x.lineWidth = 5;
    chamfer(x, 14, 14, W - 28, H - 28, 26); x.stroke();

    // cabeçalho
    x.textAlign = 'left'; x.fillStyle = GOLD; x.font = `900 34px ${FD}`;
    x.fillText('SÚMULA UFC', PAD + 6, 76);
    x.fillStyle = TXT;
    const s = fitText(x, e.name.toUpperCase(), W - PAD * 2 - 12, 82);
    x.fillText(e.name.toUpperCase(), PAD + 4, 150);
    x.fillStyle = MUT; x.font = `500 26px ${FB}`;
    x.fillText(fmt(e.date) + (e.location ? '  ·  ' + e.location : '') + '  ·  ' +
               fs.length + ' ' + T('bouts', 'lutas'), PAD + 6, 192);
    x.strokeStyle = LINE; x.lineWidth = 2;
    x.beginPath(); x.moveTo(PAD, 218); x.lineTo(W - PAD, 218); x.stroke();

    // painéis
    fs.forEach((f, i) => {
      const c = row ? i % cols : 0, r = row ? Math.floor(i / cols) : i;
      panel(x, PAD + c * (PW + GAP), HEAD + r * (PH + GAP), f, imgs);
    });

    // rodapé
    const fy = H - FOOT + 46;
    x.textAlign = 'left'; x.fillStyle = MUT; x.font = `500 21px ${FB}`;
    const src = 'ufcstats.com · ' + new Date().toLocaleDateString(S.pt ? 'pt-BR' : 'en-US');
    const foot = T('MMA = full pro record · UFC = UFC bouts · ELO adjusted for opposition' + (Q.cd ? ' · OVR 48–98 (* provisional, EST = pre-UFC estimate)' : '') + ' · probabilities, not predictions',
                   'MMA = cartel profissional completo · UFC = só lutas no UFC · ELO ajustado à oposição' + (Q.cd ? ' · OVR 48–98 (* provisório, EST = estimativa pré-UFC)' : '') + ' · probabilidades, não previsões');
    x.fillStyle = MUT; x.font = `500 21px ${FB}`;
    const room = W - PAD * 2 - 12, wf = x.measureText(foot).width, ws = x.measureText(src).width;
    if (wf + ws + 40 <= room) {                       // cabe numa linha: texto à esquerda, fonte à direita
      x.fillText(foot, PAD + 6, fy);
      x.textAlign = 'right'; x.fillText(src, W - PAD - 6, fy);
    } else {                                          // formato estreito: duas linhas
      fitText(x, foot, room, 21, 500, FB); x.fillText(foot, PAD + 6, fy - 14);
      x.font = `500 21px ${FB}`; x.fillText(src, PAD + 6, fy + 16);
    }
    return cv;
  }

  /* =================== LUTA REALIZADA (com tags) =================== */
  const DEC_TAG = () => [
    [T('CONSISTENT DECISION', 'DECISÃO COERENTE'), '#34d399'],
    [T('CLOSE DECISION', 'DECISÃO APERTADA'), '#f5c518'],
    [T('QUESTIONABLE', 'QUESTIONÁVEL'), '#ff9f43'],
    [T('POSSIBLE ROBBERY', 'POSSÍVEL ROUBO'), '#ff4d5e']
  ];
  const BONUS = () => ({ fight: T('FIGHT OF THE NIGHT', 'LUTA DA NOITE'), perf: T('PERFORMANCE OF THE NIGHT', 'PERFORMANCE DA NOITE'),
                         sub: T('SUBMISSION OF THE NIGHT', 'FINALIZAÇÃO DA NOITE'), ko: T('KO OF THE NIGHT', 'NOCAUTE DA NOITE') });
  const fightById = id => S.fg.find(f => f.id === id) || null;
  const evById = id => S.ev.find(e => e.id === id) || null;

  // todas as tags da luta, cada uma com o número que a justifica
  function fightTags(f) {
    const t = [], won = f.res === 'a' || f.res === 'b';
    if (f.title) t.push([T('TITLE FIGHT', 'CINTURÃO'), GOLD]);
    const d = Q.dec && Q.dec.fights && Q.dec.fights[f.id];
    if (d) t.push([DEC_TAG()[d[1]][0], DEC_TAG()[d[1]][1], d]);
    const lv = Q.live && Q.live.fights && Q.live.fights[f.id];
    if (lv && won) {
      if (lv[0] < 0.35) t.push([T('UPSET', 'ZEBRA') + ' · ' + pct(lv[0]), '#c084fc']);
      if (lv.length > 1 && Math.min(...lv.slice(1)) < 0.25) t.push([T('COMEBACK', 'VIRADA'), '#38bdf8']);
    }
    for (const b of f.bonus || []) if (BONUS()[b]) t.push([BONUS()[b], '#e5e7eb']);
    if (won && /^(ko|tko|sub)/i.test(f.method || '') && String(f.round) === '1' && secs(f.time) <= 60)
      t.push([T('FIRST-MINUTE FINISH', 'FINALIZOU NO 1º MINUTO'), '#fb7185']);
    return t;
  }

  function bg(x, W, H) {
    x.fillStyle = BG; x.fillRect(0, 0, W, H);
    x.strokeStyle = 'rgba(255,255,255,.035)'; x.lineWidth = 1;
    for (let i = -H; i < W; i += 44) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i + H, H); x.stroke(); }
    x.strokeStyle = GOLD; x.lineWidth = 5; chamfer(x, 14, 14, W - 28, H - 28, 26); x.stroke();
  }
  function portrait(x, img, cx, cy, r, col, label) {
    x.save(); octPath(x, cx, cy, r); x.clip();
    x.fillStyle = '#242832'; x.fillRect(cx - r, cy - r, 2 * r, 2 * r);
    if (img) x.drawImage(img, cx - r, cy - r, 2 * r, 2 * r);
    else { x.fillStyle = MUT; x.textAlign = 'center'; x.font = `800 ${Math.round(r * 0.8)}px ${FD}`; x.fillText(ini(label), cx, cy + r * 0.28); }
    x.restore(); x.strokeStyle = col; x.lineWidth = 6; octPath(x, cx, cy, r); x.stroke();
  }
  function chips(x, list, cx, y, maxW) {
    // quebra em linhas centralizadas
    x.font = `800 24px ${FB}`;
    const rows = [[]]; let w = 0;
    for (const c of list) {
      const cw = x.measureText(c[0]).width + 36;
      if (w + cw > maxW && rows.at(-1).length) { rows.push([]); w = 0; }
      rows.at(-1).push([c, cw]); w += cw + 12;
    }
    rows.forEach((r, k) => {
      const tw = r.reduce((a, [, cw]) => a + cw, 0) + 12 * (r.length - 1);
      let xx = cx - tw / 2;
      for (const [c, cw] of r) {
        chamfer(x, xx, y + k * 56, cw, 44, 8); x.fillStyle = c[1]; x.fill();
        x.fillStyle = '#0b0c10'; x.textAlign = 'center'; x.fillText(c[0], xx + cw / 2, y + k * 56 + 31);
        xx += cw + 12;
      }
    });
    return rows.length * 56;
  }

  async function renderFight() {
    const f = fightById(Q.fid); if (!f) return null;
    await loadFightExtras();
    const W = 1080, H = 1350, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const x = cv.getContext('2d'), e = evById(f.ev) || {}, imgs = await photos([f.a.id, f.b.id]);
    bg(x, W, H);
    x.textAlign = 'left'; x.fillStyle = GOLD; x.font = `900 32px ${FD}`; x.fillText('SÚMULA UFC', 56, 78);
    x.fillStyle = TXT; fitText(x, (e.name || '').toUpperCase(), W - 112, 56); x.fillText((e.name || '').toUpperCase(), 56, 138);
    x.fillStyle = MUT; x.font = `500 24px ${FB}`;
    x.fillText([fmt(f.date), e.location, f.div].filter(Boolean).join('  ·  '), 56, 176);

    const res = f.res, col = s => res === s ? GOLD : (res === 'a' || res === 'b') ? '#5b6170' : TXT;
    for (const [s, cx] of [['a', 270], ['b', 810]]) {
      const fg = f[s];
      portrait(x, imgs[fg.id], cx, 352, 110, res === s ? GOLD : res === 'draw' || res === 'nc' ? MUT : '#3a3f4b', nm(fg));
      x.textAlign = 'center'; x.fillStyle = col(s); fitText(x, nm(fg).toUpperCase(), 440, 50); x.fillText(nm(fg).toUpperCase(), cx, 522);
      x.fillStyle = MUT; fitText(x, recLine(fg.id), 440, 20, 600, FB); x.fillText(recLine(fg.id), cx, 556);
      const o = ovrOf(fg.id);
      if (o) { x.font = `800 22px ${FB}`; x.fillText(`OVR ${o.v}${o.tag === 'EST' ? ' (est)' : o.tag}`, cx, 588); }
      if (res === s) { x.fillStyle = GOLD; x.font = `900 30px ${FD}`; x.fillText(T('WINNER', 'VENCEDOR'), cx, 232); }
    }
    x.fillStyle = MUT; x.textAlign = 'center'; x.font = `800 40px ${FD}`; x.fillText('VS', W / 2, 367);

    // resultado
    const outTxt = res === 'draw' ? T('DRAW', 'EMPATE') : res === 'nc' ? T('NO CONTEST', 'SEM RESULTADO') : (f.method || '').toUpperCase();
    x.fillStyle = TXT; fitText(x, outTxt, W - 140, 54); x.fillText(outTxt, W / 2, 660);
    const d = Q.dec && Q.dec.fights && Q.dec.fights[f.id];
    const sub = [f.round ? `R${f.round} · ${f.time}` : '', d && d[3] ? T('judges ', 'juízes ') + d[3].split(',').join(' · ') : ''].filter(Boolean).join('   |   ');
    x.fillStyle = MUT; fitText(x, sub, W - 140, 24, 600, FB); x.fillText(sub, W / 2, 698);

    // tags
    const tg = fightTags(f);
    let y = 728;
    if (tg.length) y += chips(x, tg, W / 2, y, W - 120) + 10;

    // estatísticas lado a lado
    const Ta = f.totals && f.totals.a, Tb = f.totals && f.totals.b;
    if (Ta && Tb) {
      const rows = [['KD', 'KD', 0], [T('Sig. strikes', 'Golpes sig.'), 'Sig. str.', 0], [T('Total strikes', 'Golpes totais'), 'Total str.', 0],
                    [T('Takedowns', 'Quedas'), 'Td', 0], [T('Control', 'Controle'), 'Ctrl', 1], [T('Sub. attempts', 'Tent. finaliz.'), 'Sub. att', 0]];
      const rh = Math.min(62, (H - 170 - y) / rows.length);
      rows.forEach(([lb, k, isT], i) => {
        const yy = y + 20 + i * rh, va = isT ? secs(Ta[k]) : num(Ta[k]), vb = isT ? secs(Tb[k]) : num(Tb[k]);
        x.fillStyle = MUT; x.textAlign = 'center'; x.font = `700 21px ${FB}`; x.fillText(lb.toUpperCase(), W / 2, yy + 8);
        x.font = `900 36px ${FD}`;
        x.textAlign = 'left'; x.fillStyle = va > vb ? GOLD : TXT; x.fillText(String(Ta[k] || '0'), 80, yy + 12);
        x.textAlign = 'right'; x.fillStyle = vb > va ? BLUE : TXT; x.fillText(String(Tb[k] || '0'), W - 80, yy + 12);
        const tot = va + vb || 1, bw = 360, bx = W / 2 - bw / 2;
        x.fillStyle = '#1f232b'; x.fillRect(bx, yy + 18, bw, 8);
        x.fillStyle = GOLD; x.fillRect(bx, yy + 18, bw * va / tot, 8);
        x.fillStyle = BLUE; x.fillRect(bx + bw * va / tot, yy + 18, bw * vb / tot, 8);
      });
    }

    // nota de rodapé que explica as tags com números
    const notes = [];
    if (d) notes.push(T(`Decision audit: the stats give ${pct(d[0])} to the official winner.`, `Auditoria: os números dão ${pct(d[0])} ao vencedor oficial.`));
    const lv = Q.live && Q.live.fights && Q.live.fights[f.id];
    if (lv && (res === 'a' || res === 'b')) notes.push(T(`Winner's pre-fight chance: ${pct(lv[0])}.`, `Chance pré-luta do vencedor: ${pct(lv[0])}.`));
    x.textAlign = 'left'; x.fillStyle = MUT;
    fitText(x, notes.join('  '), W - 112, 22, 500, FB); x.fillText(notes.join('  '), 56, H - 96);
    x.font = `500 20px ${FB}`; x.fillText(T('Records shown are current. Probabilities, not verdicts. Source: ufcstats.com', 'Cartéis exibidos são os atuais. Probabilidades, não veredictos. Fonte: ufcstats.com'), 56, H - 60);
    return cv;
  }

  /* =================== CARD DE LUTADOR =================== */
  const TIER = o => o >= 93 ? T('LEGEND', 'LENDA') : o >= 89 ? 'ELITE' : o >= 82 ? 'CONTENDER' : o >= 74 ? T('VETERAN', 'VETERANO') : T('PROSPECT', 'PROSPECTO');
  async function renderFighter() {
    const id = mid(Q.pid), p = F(id); if (!p) return null;
    const W = 1080, H = 1350, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const x = cv.getContext('2d'), imgs = await photos([id]), a = an(id), o = ovrOf(id);
    bg(x, W, H);
    x.textAlign = 'left'; x.fillStyle = GOLD; x.font = `900 32px ${FD}`; x.fillText('SÚMULA UFC', 56, 78);
    portrait(x, imgs[id], 820, 260, 170, GOLD, p.name);
    if (o) {
      x.fillStyle = GOLD; x.font = `900 220px ${FD}`; x.fillText(String(o.v), 56, 300);
      x.font = `800 40px ${FD}`; x.fillText((o.tag === 'EST' ? T('PRE-UFC ESTIMATE', 'ESTIMATIVA PRÉ-UFC') : 'OVR' + (o.tag ? ' · ' + T('PROVISIONAL', 'PROVISÓRIO') : '')), 62, 352);
      x.fillStyle = TXT; x.fillText(TIER(o.v), 62, 400);
    } else { x.fillStyle = MUT; x.font = `800 40px ${FD}`; x.fillText(T('NO OVR YET', 'SEM OVR AINDA'), 62, 300); }

    x.fillStyle = TXT; fitText(x, p.name.toUpperCase(), W - 112, 96); x.fillText(p.name.toUpperCase(), 56, 530);
    x.fillStyle = MUT; x.font = `500 26px ${FB}`;
    const dv = a && a.divs ? a.divs.filter(d => !['Catch Weight', 'Open Weight', 'Outros'].includes(d[0])).map(d => d[0] + (d[6] ? ' 🏆' + (d[6] > 1 ? d[6] : '') : '')) : [];
    x.fillText([p.nick ? `"${p.nick}"` : '', dv.join(' · '), p.country || ''].filter(Boolean).join('   ·   '), 58, 574);
    x.fillStyle = TXT; x.font = `700 30px ${FB}`; x.fillText(recLine(id), 58, 630);

    let y = 690;
    const c = o && o.c;
    if (c) {
      const L = [T('STRIKING', 'TROCAÇÃO'), T('DEFENSE', 'DEFESA'), T('WRESTLING', 'LUTA AGARRADA'), T('SUBMISSION', 'FINALIZAÇÃO'), T('POWER', 'PEGADA'), T('CARDIO', 'CARDIO')];
      L.forEach((lb, i) => {
        const yy = y + i * 64;
        x.fillStyle = MUT; x.textAlign = 'left'; x.font = `800 26px ${FB}`; x.fillText(lb, 58, yy + 30);
        x.fillStyle = '#1f232b'; x.fillRect(340, yy + 10, 560, 26);
        x.fillStyle = GOLD; x.fillRect(340, yy + 10, 560 * c[i + 1] / 99, 26);
        x.fillStyle = TXT; x.textAlign = 'right'; x.font = `900 44px ${FD}`; x.fillText(String(c[i + 1]), W - 58, yy + 38);
      });
      y += 6 * 64 + 20;
    } else if (o && o.tag === 'EST') {
      x.fillStyle = MUT; x.font = `500 26px ${FB}`;
      x.fillText(T('No UFC fight yet: no strike/grappling statistics exist.', 'Ainda sem luta no UFC: não há estatísticas de golpes e quedas.'), 58, y + 30);
      x.fillText(T('The overall is estimated from the professional record and is replaced', 'O overall é estimado pelo cartel profissional e é substituído'), 58, y + 70);
      x.fillText(T('by the statistical one after the first UFC fight.', 'pelo estatístico depois da primeira luta no UFC.'), 58, y + 110);
      y += 170;
    }
    if (a) {
      const kv = [['ELO', Math.round(a.e)], [T('PEAK', 'PICO'), Math.round(a.pk)], ['DLI', a.dli ?? '—'],
                  [T('FINISH %', '% FINALIZ.'), a.fin != null ? Math.round(a.fin * 100) + '%' : '—'],
                  ['KO / SUB / DEC', `${a.w[0]} / ${a.w[1]} / ${a.w[2]}`]];
      const cw = (W - 112) / kv.length;
      kv.forEach(([k, v], i) => {
        x.textAlign = 'center'; x.fillStyle = MUT; x.font = `700 20px ${FB}`; x.fillText(k, 56 + cw * i + cw / 2, y + 20);
        x.fillStyle = TXT; x.font = `900 46px ${FD}`; x.fillText(String(v), 56 + cw * i + cw / 2, y + 70);
      });
    }
    const ft = T('MMA = full pro record · UFC = UFC bouts · OVR 48–98 population-calibrated · ufcstats.com', 'MMA = cartel profissional completo · UFC = só UFC · OVR 48–98 calibrado na população · ufcstats.com') +
               ' · ' + new Date().toLocaleDateString(S.pt ? 'pt-BR' : 'en-US');
    x.textAlign = 'left'; x.fillStyle = MUT; fitText(x, ft, W - 112, 20, 500, FB); x.fillText(ft, 56, H - 60);
    return cv;
  }

  /* =================== saída =================== */
  function fileName() {
    const slug = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\W+/g, '-').replace(/^-|-$/g, '').toLowerCase();
    if (Q.mode === 'fight') { const f = fightById(Q.fid); return 'sumula-' + (f ? slug(nm(f.a) + '-vs-' + nm(f.b)) : 'luta') + '.png'; }
    if (Q.mode === 'fighter') return 'sumula-card-' + slug((F(Q.pid) || {}).name || 'lutador') + '.png';
    return 'sumula-' + slug(Q.up.events[Q.ev].name) + '-' + Q.lay + '.png';
  }
  function out(cv, how) {
    const file = fileName();
    cv.toBlob(b => {
      if (!b) { Q.note = T('Could not generate the image.', 'Não foi possível gerar a imagem.'); return draw(); }
      const f = new File([b], file, { type: 'image/png' });
      if (how === 'share' && navigator.canShare && navigator.canShare({ files: [f] })) {
        navigator.share({ files: [f], title: file }).catch(() => {});
      } else {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(b); a.download = file; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      }
    }, 'image/png');
  }

  async function act(how) {
    if (Q.busy) return;
    Q.busy = true; Q.note = T('Rendering…', 'Gerando…'); draw();
    try {
      const cv = await (Q.mode === 'fight' ? renderFight() : Q.mode === 'fighter' ? renderFighter() : render());
      if (!cv) Q.note = Q.mode === 'event' ? T('This event has no bouts listed yet.', 'Este evento ainda não tem lutas listadas.') : T('Pick something first.', 'Escolha primeiro.');
      else if (how === 'preview') {
        Q.busy = false; Q.note = ''; draw();
        const h = $('#sdprev');
        if (h) { cv.style.width = '100%'; cv.style.maxWidth = Q.mode === 'event' ? '' : '540px'; cv.style.height = 'auto';
                 cv.style.border = '1px solid var(--ln)'; cv.style.borderRadius = '8px'; h.innerHTML = ''; h.appendChild(cv); }
        return;
      } else { out(cv, how); Q.note = T('Image ready.', 'Imagem pronta.'); }
    } catch (err) {
      Q.note = T('Error generating: ', 'Erro ao gerar: ') + (err && err.message || err);
    }
    Q.busy = false; draw();
  }

  async function copyBB() {
    try {
      await navigator.clipboard.writeText(bb());
      Q.note = T('BBCode copied — paste it into the Sherdog reply box.', 'BBCode copiado — cole na caixa de resposta do Sherdog.');
    } catch { Q.note = T('Copy failed; select the text below manually.', 'Falha ao copiar; selecione o texto abaixo manualmente.'); }
    draw();
  }

  /* =================== interface =================== */
  const btns = (extra = '') => `<div class="seg" style="margin-top:.9rem">
      <button data-sda="preview">${T('Preview', 'Pré-visualizar')}</button>
      <button data-sda="png">${T('Download PNG', 'Baixar PNG')}</button>
      <button data-sda="share">${T('Share…', 'Compartilhar…')}</button>${extra}</div>
    ${Q.note ? `<p class="mu sm">${esc(Q.note)}</p>` : ''}<div id="sdprev" style="margin:1rem 0"></div>`;

  function bodyEvent() {
    if (!Q.up) return `<p class="empty">${T('data/upcoming.json not found. Run the workflow once so the scraper generates it.', 'data/upcoming.json não encontrado. Rode o workflow uma vez para o scraper gerá-lo.')}</p>`;
    const evs = Q.up.events, n = (evs[Q.ev].fights || []).length;
    const lay = (k, l, d) => `<button data-sdl="${k}" class="${Q.lay === k ? 'on' : ''}">${l}<br><small class="mu">${d}</small></button>`;
    return `<div class="ctl"><label>${T('Event', 'Evento')}<select data-sdf="ev">${evs.map((v, i) => `<option value="${i}"${i === Q.ev ? ' selected' : ''}>${esc(v.name)} — ${fmt(v.date)}</option>`).join('')}</select></label></div>
      <h2>${T('Image layout', 'Formato da imagem')}</h2>
      <div class="seg">${lay('row', T('Row', 'Fileira'), T('wide, 2 bouts per line', 'largo, 2 lutas por linha'))}${lay('col', 'Vertical', T('narrow, 1 bout per line', 'estreito, 1 luta por linha'))}</div>
      ${btns(`<button data-sda="bb">${T('Copy BBCode', 'Copiar BBCode')}</button>`)}
      <h2>${T('How to post on Sherdog', 'Como postar no Sherdog')}</h2>
      <div class="card" style="padding:.8rem 1.1rem"><p class="sm">1. ${T('Download the PNG.', 'Baixe o PNG.')}<br>2. ${T('Upload it to an image host (imgur, postimages) or your repo and copy the direct link.', 'Suba num host de imagem (imgur, postimages) ou no seu repositório e copie o link direto.')}<br>3. ${T('In the reply box paste', 'Na resposta, cole')} <code>[IMG]${T('your-link.png', 'seu-link.png')}[/IMG]</code><br>4. ${T('Optionally add the BBCode table below (searchable text).', 'Opcionalmente cole a tabela BBCode abaixo (texto pesquisável).')}</p></div>
      <h2>${T('BBCode table', 'Tabela em BBCode')} <span class="mu sm">(${n} ${T('bouts', 'lutas')})</span></h2>
      <textarea id="sdbb" readonly rows="12" style="width:100%;background:var(--s1);color:var(--tx);border:1px solid var(--ln);border-radius:8px;padding:.7rem;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace">${esc(bb())}</textarea>`;
  }

  function bodyFight() {
    if (!S.ev.length || !S.fg.length) return `<p class="empty">${T('No completed fights loaded.', 'Nenhuma luta realizada carregada.')}</p>`;
    const f0 = fightById(Q.fid);
    if (!Q.fev) Q.fev = f0 ? f0.ev : S.ev[0].id;
    const fs = S.fg.filter(f => f.ev === Q.fev).sort((a, b) => (a.ord || 0) - (b.ord || 0));
    if (!fs.some(f => f.id === Q.fid)) Q.fid = fs.length ? fs[0].id : '';
    return `<div class="ctl"><label>${T('Event', 'Evento')}<select data-sdf="fev">${S.ev.slice(0, 400).map(e => `<option value="${e.id}"${e.id === Q.fev ? ' selected' : ''}>${esc(e.name)} — ${fmt(e.date)}</option>`).join('')}</select></label>
      <label>${T('Fight', 'Luta')}<select data-sdf="fid">${fs.map(f => `<option value="${f.id}"${f.id === Q.fid ? ' selected' : ''}>${esc(nm(f.a))} vs ${esc(nm(f.b))}</option>`).join('')}</select></label></div>
      <p class="mu sm">${T('Tags are computed from the data: decision audit (consistent / close / questionable / possible robbery), upset and comeback from the win-probability model, title and night bonuses.', 'As tags saem dos dados: auditoria da decisão (coerente / apertada / questionável / possível roubo), zebra e virada pelo modelo de probabilidade, cinturão e bônus da noite.')}</p>
      ${btns()}`;
  }

  function bodyFighter() {
    const p = F(Q.pid);
    const sel = p ? `<div class="card" style="padding:.8rem 1rem"><div class="sel">${av(mid(Q.pid), p.name, 'sm')}<b>${esc(p.name)}</b><button data-sdc="1">×</button></div></div>`
                  : `<input data-sdq="1" type="search" value="${esc(Q.pq)}" placeholder="${T('Search a fighter…', 'Buscar lutador…')}"><div class="res" id="sdres"></div>`;
    return `${sel}<p class="mu sm">${T('Any fighter in the base: statistical OVR, provisional (*) with few UFC fights, or a pre-UFC estimate (EST) for debutants.', 'Qualquer lutador da base: OVR estatístico, provisório (*) com poucas lutas no UFC, ou estimativa pré-UFC (EST) para estreantes.')}</p>${p ? btns() : ''}`;
  }

  function body() {
    const md = (k, l) => `<button data-sdm="${k}" class="${Q.mode === k ? 'on' : ''}">${l}</button>`;
    const miss = [!Q.an && 'analytics.json', !Q.cd && 'cards.json'].filter(Boolean);
    return `<div class="seg">${md('event', T('Upcoming event', 'Evento futuro'))}${md('fight', T('Completed fight', 'Luta realizada'))}${md('fighter', T('Fighter card', 'Card de lutador'))}</div>
      ${miss.length ? `<p class="dn sm">${T('Missing ', 'Faltando ')}${miss.join(', ')}: ${T('images still render, without those numbers.', 'as imagens ainda são geradas, sem esses números.')}</p>` : ''}
      ${Q.mode === 'fight' ? bodyFight() : Q.mode === 'fighter' ? bodyFighter() : bodyEvent()}`;
  }

  function searchList() {
    const r = $('#sdres'); if (!r) return;
    const t = Q.pq.toLowerCase().trim();
    r.innerHTML = t.length < 2 ? '' : [...S.F.values()].filter(f => (f.name + ' ' + (f.nick || '')).toLowerCase().includes(t)).slice(0, 8)
      .map(f => { const o = ovrOf(f.id); return `<button data-sdp="${f.id}"><span>${esc(f.name)}</span><span class="mu">${esc(f.record || '')}${o ? ' · ' + o.v + (o.tag === 'EST' ? ' est' : o.tag) : ''}</span></button>`; }).join('');
  }

  function draw() {
    const el = $('#sd'); if (!el) return;
    el.innerHTML = body();
    const m = $('#m');
    m.onclick = ev => {
      const t = ev.target.closest('[data-sdl],[data-sda],[data-sdm],[data-sdp],[data-sdc]'); if (!t) return;
      const d = t.dataset;
      if (d.sdm) { Q.mode = d.sdm; Q.note = ''; draw(); }
      else if (d.sdl) { Q.lay = d.sdl; Q.note = ''; draw(); }
      else if (d.sdp) { Q.pid = d.sdp; Q.pq = ''; Q.note = ''; draw(); act('preview'); }
      else if (d.sdc) { Q.pid = ''; Q.note = ''; draw(); }
      else if (d.sda === 'bb') copyBB();
      else act(d.sda);
    };
    m.onchange = ev => {
      const f = ev.target.closest('[data-sdf]'); if (!f) return;
      const k = f.dataset.sdf;
      if (k === 'ev') Q.ev = +f.value || 0;
      else if (k === 'fev') { Q.fev = f.value; Q.fid = ''; }
      else if (k === 'fid') Q.fid = f.value;
      Q.note = ''; draw();
      if (Q.mode === 'fight' && Q.fid) act('preview');
    };
    m.oninput = ev => { const q = ev.target.closest('[data-sdq]'); if (!q) return; Q.pq = q.value; searchList(); };
    if (Q.mode === 'fighter' && !Q.pid) { searchList(); const i = $('[data-sdq]'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }
  }

  // rotas: #/sherdog  ·  #/sherdog/f/<id da luta>  ·  #/sherdog/p/<id do lutador>
  async function view(kind, id) {
    if (kind === 'f' && id) { Q.mode = 'fight'; Q.fid = id; const f = fightById(id); Q.fev = f ? f.ev : ''; }
    else if (kind === 'p' && id) { Q.mode = 'fighter'; Q.pid = id; }
    M(`<h1>${T('Share as image', 'Compartilhar como imagem')}</h1><div id="sd"><p class="mu">${T('Loading…', 'Carregando…')}</p></div>`);
    await load();
    draw();
    if ((Q.mode === 'fight' && Q.fid) || (Q.mode === 'fighter' && Q.pid)) act('preview');
  }

  // registro no roteador, encadeando com os módulos já existentes
  const pT = window.XT, pV = window.XV, pB = window.XB;
  window.XT = () => [...(pT ? pT() : []), ['sherdog', T('Share', 'Compartilhar')]];
  window.XV = { ...(pV || {}), sherdog: view };
  // atalho "PNG" em cada luta da página de evento (encadeia a etiqueta de auditoria que já existe)
  window.XB = f => (pB ? pB(f) : '') + `<a class="tag" href="#/sherdog/f/${f.id}" title="${T('Share as PNG', 'Compartilhar como PNG')}">PNG</a>`;
})();
