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
  const Q = { up: null, an: null, cd: null, err: '', ev: 0, lay: 'row', busy: false, note: '' };

  const F = id => S.F.get(mid(id)) || null;
  const an = id => Q.an && Q.an.fighters[mid(id)] || null;
  const cd = id => Q.cd && Q.cd.cards && Q.cd.cards[mid(id)] || null;
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
    if (Q.up || Q.err) return;
    const [a, c] = await Promise.all([grab('analytics.json'), grab('cards.json')]);
    Q.an = a; Q.cd = c;
    // o app já carrega upcoming.json no boot; só busca de novo se faltar
    let u = (S.up && S.up.length) ? { events: S.up } : await grab('upcoming.json');
    if (!u || !u.events || !u.events.length) { Q.err = 'upcoming'; return; }
    Q.up = u;
  }

  /* ---------- probabilidade do confronto ----------
     Mesma base do Raio-X: ELO encolhido para 1500 em cartel curto.
     Quando o scraper trouxe odds de mercado (mkt_pa/mkt_pb), elas são
     combinadas com o ELO — mercado pesa mais porque já embute lesão,
     corte de peso e notícia de bastidor, que não estão nos dados. */
  function prob(f) {
    const A = an(f.a.id), B = an(f.b.id);
    let pElo = null;
    if (A && B) {
      const sh = x => BASE + (x.e - BASE) * x.n / (x.n + 3);
      pElo = 1 / (1 + Math.pow(10, (sh(B) - sh(A)) / 400));
    }
    const pMkt = (typeof f.mkt_pa === 'number' && typeof f.mkt_pb === 'number' && (f.mkt_pa + f.mkt_pb) > 0)
      ? f.mkt_pa / (f.mkt_pa + f.mkt_pb) : null;
    if (pElo == null && pMkt == null) return { p: null, src: 'none' };
    if (pElo == null) return { p: pMkt, src: 'mkt' };
    if (pMkt == null) return { p: pElo, src: 'elo' };
    return { p: 0.35 * pElo + 0.65 * pMkt, src: 'both' };
  }

  const recOf = id => {
    const a = an(id);
    if (a) {
      const s = x => x.reduce((m, n) => m + n, 0);
      return `${s(a.w)}-${s(a.l)}-${a.d}`;
    }
    return ((F(id) || {}).record || '').trim() || '—';
  };

  /* ---------- BBCode para o fórum ---------- */
  function bb() {
    const e = Q.up.events[Q.ev], L = [];
    L.push('[B][SIZE=5]' + e.name + '[/SIZE][/B]');
    L.push('[I]' + fmt(e.date) + (e.location ? ' — ' + e.location : '') + '[/I]');
    L.push('');
    L.push('[TABLE]');
    L.push('[TR][TH]Bout[/TH][TH]Div[/TH][TH]OVR[/TH][TH]Record[/TH][TH]Win %[/TH][/TR]');
    e.fights.forEach(f => {
      const { p } = prob(f), ca = cd(f.a.id), cb2 = cd(f.b.id);
      const pa = p == null ? '—' : pct(p), pb = p == null ? '—' : pct(1 - p);
      L.push(`[TR][TD][B]${nm(f.a)}[/B] vs ${nm(f.b)}${f.title ? ' [B](TITLE)[/B]' : ''}[/TD]` +
             `[TD]${f.div}[/TD][TD]${ca ? ca[0] : '—'} / ${cb2 ? cb2[0] : '—'}[/TD]` +
             `[TD]${recOf(f.a.id)} / ${recOf(f.b.id)}[/TD][TD]${pa} / ${pb}[/TD][/TR]`);
    });
    L.push('[/TABLE]');
    L.push('');
    L.push('[SIZE=1][I]Ratings & win probabilities: ELO adjusted for strength of schedule' +
           (Q.cd ? ', OVR on a 48–98 population-calibrated scale' : '') +
           '. Probabilities, not predictions. Source: ufcstats.com[/I][/SIZE]');
    return L.join('\n');
  }

  /* ---------- desenho ---------- */
  const PW = 1020, PH = 212, GAP = 14, PAD = 42, HEAD = 250, FOOT = 104;

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
    const { p, src } = prob(f), ca = cd(f.a.id), cb2 = cd(f.b.id);
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

    const my = Y + 36, mh = PH - 36, cy = my + mh / 2;
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
      const avail = PW / 2 - PHO - (cd(fg.id) ? 182 : 96);
      fitText(x, nm(fg).toUpperCase(), avail, 40);
      x.fillText(nm(fg).toUpperCase(), tx, cy - 8);
      x.fillStyle = MUT; x.font = `500 21px ${FB}`;
      const c = key === 'a' ? ca : cb2, a2 = an(fg.id);
      const bits = [recOf(fg.id)];
      if (a2 && a2.dli != null) bits.push('DLI ' + a2.dli);
      if (a2 && a2.e != null) bits.push('ELO ' + Math.round(a2.e));
      x.fillText(bits.join('  ·  '), tx, cy + 22);
      if (c) {                                   // selo de OVR
        const ox = dir < 0 ? X + PW / 2 - 92 : X + PW / 2 + 60;
        x.fillStyle = col; x.textAlign = 'center';
        x.font = `900 46px ${FD}`; x.fillText(String(c[0]), ox + 16, cy + 2);
        x.fillStyle = MUT; x.font = `700 15px ${FB}`; x.fillText('OVR', ox + 16, cy + 22);
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
      if (src === 'both' || src === 'mkt') {
        x.textAlign = 'center'; x.fillStyle = MUT; x.font = `600 14px ${FB}`;
        x.fillText(src === 'mkt' ? 'market odds' : 'ELO + market', CX, by - 10);
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
    x.fillText(T('ELO adjusted for strength of schedule' + (Q.cd ? ' · OVR 48–98 population-calibrated' : '') +
                 ' · probabilities, not predictions',
                 'ELO ajustado ao nível de oposição' + (Q.cd ? ' · OVR 48–98 calibrado na população' : '') +
                 ' · probabilidades, não previsões'), PAD + 6, fy);
    x.textAlign = 'right';
    x.fillText('ufcstats.com · ' + new Date().toLocaleDateString(S.pt ? 'pt-BR' : 'en-US'), W - PAD - 6, fy);
    return cv;
  }

  function out(cv, how) {
    const e = Q.up.events[Q.ev];
    const file = 'sumula-' + (e.name || 'evento').replace(/\W+/g, '-').toLowerCase() + '-' + Q.lay + '.png';
    cv.toBlob(b => {
      if (!b) { Q.note = T('Could not generate the image.', 'Não foi possível gerar a imagem.'); return draw(); }
      const f = new File([b], file, { type: 'image/png' });
      if (how === 'share' && navigator.canShare && navigator.canShare({ files: [f] })) {
        navigator.share({ files: [f], title: e.name }).catch(() => {});
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
      const cv = await render();
      if (!cv) Q.note = T('This event has no bouts listed yet.', 'Este evento ainda não tem lutas listadas.');
      else {
        if (how === 'preview') {
          const h = $('#sdprev');
          if (h) {
            cv.style.width = '100%'; cv.style.height = 'auto';
            cv.style.border = '1px solid var(--ln)'; cv.style.borderRadius = '8px';
            h.innerHTML = ''; h.appendChild(cv);
          }
          Q.note = '';
          Q.busy = false; return;
        }
        out(cv, how);
        Q.note = T('Image ready.', 'Imagem pronta.');
      }
    } catch (err) {
      Q.note = T('Error generating: ', 'Erro ao gerar: ') + (err && err.message || err);
    }
    Q.busy = false; draw();
  }

  async function copyBB() {
    const t = bb();
    try {
      await navigator.clipboard.writeText(t);
      Q.note = T('BBCode copied — paste it into the Sherdog reply box.',
                 'BBCode copiado — cole na caixa de resposta do Sherdog.');
    } catch {
      Q.note = T('Copy failed; select the text below manually.',
                 'Falha ao copiar; selecione o texto abaixo manualmente.');
    }
    draw();
  }

  /* ---------- interface ---------- */
  function body() {
    if (Q.err === 'upcoming' || !Q.up)
      return `<p class="empty">${T('data/upcoming.json not found. Run the workflow once so the scraper generates it.',
                                   'data/upcoming.json não encontrado. Rode o workflow uma vez para o scraper gerá-lo.')}</p>`;
    const evs = Q.up.events, e = evs[Q.ev], n = (e.fights || []).length;
    const miss = [];
    if (!Q.an) miss.push('analytics.json');
    if (!Q.cd) miss.push('cards.json');

    const lay = (k, l, d) => `<button data-sdl="${k}" class="${Q.lay === k ? 'on' : ''}">${l}<br><small class="mu">${d}</small></button>`;

    return `<div class="ctl"><label>${T('Event', 'Evento')}<select data-sdf="ev">${
        evs.map((v, i) => `<option value="${i}"${i === Q.ev ? ' selected' : ''}>${esc(v.name)} — ${fmt(v.date)}</option>`).join('')
      }</select></label></div>

      <h2>${T('Image layout', 'Formato da imagem')}</h2>
      <div class="seg">${lay('row', T('Row', 'Fileira'), T('wide, 2 bouts per line', 'largo, 2 lutas por linha'))}${
        lay('col', T('Vertical', 'Vertical'), T('narrow, 1 bout per line', 'estreito, 1 luta por linha'))}</div>
      <p class="mu sm">${T('Row suits desktop forum posts; vertical reads better on phones.',
                           'Fileira cai bem em post de fórum no desktop; vertical lê melhor no celular.')}</p>

      <div class="seg" style="margin-top:.9rem">
        <button data-sda="preview">${T('Preview', 'Pré-visualizar')}</button>
        <button data-sda="png">${T('Download PNG', 'Baixar PNG')}</button>
        <button data-sda="share">${T('Share…', 'Compartilhar…')}</button>
        <button data-sda="bb">${T('Copy BBCode', 'Copiar BBCode')}</button>
      </div>
      ${Q.note ? `<p class="mu sm">${esc(Q.note)}</p>` : ''}
      ${miss.length ? `<p class="dn sm">${T('Missing ', 'Faltando ')}${miss.join(', ')}: ${
        T('the card still renders, without ratings for those fields.',
          'o card ainda é gerado, sem as notas desses campos.')}</p>` : ''}

      <div id="sdprev" style="margin:1rem 0"></div>

      <h2>${T('How to post on Sherdog', 'Como postar no Sherdog')}</h2>
      <div class="card" style="padding:.8rem 1.1rem">
        <p class="sm">${T('Sherdog does not host uploads inside a post, so the image needs a public URL first.',
                          'O Sherdog não hospeda upload dentro do post, então a imagem precisa de uma URL pública antes.')}</p>
        <p class="sm">1. ${T('Download the PNG above.', 'Baixe o PNG acima.')}<br>
           2. ${T('Upload it to an image host (imgur, postimages) or to your own repo and copy the direct link.',
                  'Suba num host de imagem (imgur, postimages) ou no seu próprio repositório e copie o link direto.')}<br>
           3. ${T('In the reply box, paste:', 'Na caixa de resposta, cole:')}
           <code>[IMG]${T('your-link.png', 'seu-link.png')}[/IMG]</code><br>
           4. ${T('Optionally paste the BBCode table below under the image — it is searchable text, unlike the picture.',
                  'Opcionalmente cole a tabela BBCode abaixo sob a imagem — é texto pesquisável, ao contrário da figura.')}</p>
      </div>

      <h2>${T('BBCode table', 'Tabela em BBCode')} <span class="mu sm">(${n} ${T('bouts', 'lutas')})</span></h2>
      <textarea id="sdbb" readonly rows="12" style="width:100%;background:var(--s1);color:var(--tx);border:1px solid var(--ln);border-radius:8px;padding:.7rem;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace">${esc(bb())}</textarea>`;
  }

  function draw() {
    const el = $('#sd');
    if (!el) return;
    el.innerHTML = body();

    const m = $('#m');
    m.onclick = ev => {
      const t = ev.target.closest('[data-sdl],[data-sda]');
      if (!t) return;
      if (t.dataset.sdl) { Q.lay = t.dataset.sdl; Q.note = ''; draw(); }
      else if (t.dataset.sda === 'bb') copyBB();
      else act(t.dataset.sda);
    };
    m.onchange = ev => {
      const f = ev.target.closest('[data-sdf]');
      if (!f) return;
      Q.ev = +f.value || 0; Q.note = '';
      const p = $('#sdprev'); if (p) p.innerHTML = '';
      draw();
    };
  }

  async function view() {
    M(`<h1>${T('Share on Sherdog', 'Compartilhar no Sherdog')}</h1>
       <div id="sd"><p class="mu">${T('Loading event…', 'Carregando evento…')}</p></div>`);
    await load();
    draw();
  }

  // registro no roteador, encadeando com os módulos já existentes
  const pT = window.XT, pV = window.XV;
  window.XT = () => [...(pT ? pT() : []), ['sherdog', T('Share', 'Compartilhar')]];
  window.XV = { ...(pV || {}), sherdog: view };
})();
