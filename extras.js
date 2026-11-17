/* extras.js: aba "Extras" com seis seções. Módulo acoplável: se o arquivo for removido, o app continua igual.
   Seja o juiz, Scouting, Card dos sonhos, Estilos, Prospectos, Juízes e árbitros, Academias.
   Lê os arquivos gerados pelo extras.py (excitement, styles, prospects, judges, camps) e, quando existem, decisions, analytics e cards.
   Todo resultado traz validação e tamanho de amostra; onde um modelo não prevê além do acaso, a tela diz isso. */
(function () {
  'use strict';
  const X = { tab: 'dna', os: 'z', or: 'finz', cs: 'elo', ms: 'dog', d: {}, jg: { f: null, sc: [], rev: false }, sc: '', cd: [], ca: '', cb: '', sy: '', pp: 2,
              dna: { mode: 'daily', target: '', gs: [], done: false, won: false },
              vg: { fights: [], bets: [], rev: false },
              mm: { pool: [], cap: 2400, bouts: [], pickA: '', res: null } };
  const sum = a => a.reduce((x, y) => x + y, 0), p0 = v => (v * 100).toFixed(0) + '%', p1 = v => (v * 100).toFixed(1) + '%';
  const nm = id => (S.F.get(id) || {}).name || id, fm = () => X._fm || (X._fm = new Map(S.fg.map(f => [f.id, f])));
  const sg = z => 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z))));
  const erf = x => { const s = Math.sign(x); x = Math.abs(x); const t = 1 / (1 + .3275911 * x); return s * (1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - .284496736) * t + .254829592) * t * Math.exp(-x * x)); };
  const pval = z => 2 * (1 - .5 * (1 + erf(Math.abs(z) / Math.SQRT2)));
  const llf = (p, y) => -Math.log(Math.max(y ? p : 1 - p, 1e-6));
  const fOdd = o => o == null ? '—' : (o > 0 ? '+' + o : String(o));

  /* ---------- carga sob demanda ---------- */
  async function need(names) {
    const g = async n => { if (n in X.d) return; try { const r = await fetch('data/' + n + '.json', { cache: 'no-cache' }); X.d[n] = r.ok ? await r.json() : null; } catch { X.d[n] = null; } };
    await Promise.all(names.map(g));
  }
  const TABS = () => [['dna', '🧬 ' + T('Secret DNA', 'DNA Secreto')], ['vg', '🎰 ' + T('Beat Vegas', 'Desafio Vegas')], ['mkt', '💰 ' + T('Market & Odds', 'Mercado & Odds')], ['mm', '🕶️ Matchmaker'], ['jg', T('Be the judge', 'Seja o juiz')], ['sc', 'Scouting'], ['cd', T('Dream card', 'Card dos sonhos')], ['sy', T('Styles', 'Estilos')], ['pp', T('Prospects', 'Prospectos')], ['of', T('Judges & refs', 'Juízes e árbitros')], ['cp', T('Camps', 'Academias')]];
  const miss = f => `<p class="empty">${T('File ' + f + '.json not found. Run the workflow so the scripts generate it (extras.py needs analytics.py to run before it).', 'Arquivo ' + f + '.json não encontrado. Rode o workflow para os scripts gerarem (o extras.py precisa que o analytics.py rode antes).')}</p>`;
  const slot = (k, lbl) => { const id = X[k], p = S.F.get(id); return `<div class="card" style="padding:.8rem 1rem"><div class="mu sm">${lbl}</div>${p ? `<div class="sel">${typeof av === 'function' ? av(id, p.name, 'sm') : ''}<b>${esc(p.name)}</b><button data-xc="${k}">×</button></div>` : `<input data-xq="${k}" type="search" placeholder="${T('Search a fighter…', 'Buscar lutador…')}"><div class="res" id="xs${k}"></div>`}</div>`; };

  /* ================= 1A) GAME: DNA SECRETO 2.0 (CARREIRA OCULTA + RADAR) ================= */
  const DIV_ORD = ["Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight", "Flyweight", "Bantamweight", "Featherweight", "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight"];
  function dnaPool() {
    const A = (X.d.analytics || {}).fighters || {}, C = (X.d.cards || {}).cards || {};
    return Object.keys(C).filter(id => A[id] && A[id].n >= 10 && S.F.has(id) && (A[id].e >= 1560 || A[id].pk >= 1650 || A[id].tw > 0)).sort();
  }
  function dnaInit(mode) {
    const pool = dnaPool(); if (!pool.length) return;
    const today = new Date().toISOString().slice(0, 10);
    if (mode === 'daily') {
      let h = 2166136261;
      for (const c of today) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
      const target = pool[Math.abs(h) % pool.length];
      let saved = null;
      try { saved = JSON.parse(localStorage.sumulaDna || 'null'); } catch {}
      if (saved && saved.date === today && saved.target === target) {
        X.dna = { mode: 'daily', date: today, target, gs: saved.gs || [], done: !!saved.done, won: !!saved.won };
      } else {
        X.dna = { mode: 'daily', date: today, target, gs: [], done: false, won: false };
      }
    } else {
      const target = pool[Math.floor(Math.random() * pool.length)];
      X.dna = { mode: 'free', date: today, target, gs: [], done: false, won: false };
    }
  }
  function dnaGuess(id) {
    const D = X.dna; if (D.done || !id || D.gs.includes(id)) return;
    D.gs.push(id);
    if (id === D.target) { D.done = true; D.won = true; }
    else if (D.gs.length >= 6) { D.done = true; D.won = false; }
    if (D.mode === 'daily') {
      try { localStorage.sumulaDna = JSON.stringify({ date: D.date, target: D.target, gs: D.gs, done: D.done, won: D.won }); } catch {}
    }
  }
  function tDna() {
    if (!X.d.analytics || !X.d.cards) return miss('cards');
    if (!X.dna.target) dnaInit('daily');
    const D = X.dna, tid = D.target, A = X.d.analytics.fighters, C = X.d.cards.cards, MKT = (X.d.market || {}).fights || {}, ta = A[tid], tc = C[tid], tp = S.F.get(tid) || {};
    if (!ta || !tc) return `<p class="empty">${T('Loading fighter pool…', 'Carregando base de lutadores…')}</p>`;
    const AL = [T('Striking', 'Trocação'), T('Defense', 'Defesa'), T('Wrestling', 'Quedas'), T('Submissions', 'Finalização'), T('Power', 'Pegada'), T('Cardio', 'Cardio')];
    const fs = S.fg.filter(f => f.res !== 'nc' && (mid(f.a.id) === tid || mid(f.b.id) === tid)).sort((a, b) => a.date < b.date ? -1 : 1);
    const yrs = fs.length ? `${fs[0].date.slice(0, 4)}–${fs.at(-1).date.slice(0, 4)}` : '—';
    const recent6 = fs.slice(-6).reverse();
    const nGuesses = D.gs.length;
    const hints = [
      [T('UFC Era & Style', 'Era no UFC & Estilo'), `${yrs} · ${tp.style || (X.d.styles && X.d.styles.fighters[tid] != null ? styName(X.d.styles.fighters[tid]) : T('All-rounder', 'Completo'))}${tp.origin ? ' · ' + tp.origin : ''}`],
      nGuesses >= 1 || D.done ? [T('Division & Stance', 'Divisão & Base'), `${ta.div} · ${tp.STANCE || 'Orthodox'} · ${tp.Height || ''} (${tp.Reach || ''})` ] : null,
      nGuesses >= 2 || D.done ? [T('Country & Gym', 'País & Academia'), `${tp.country || '—'} · ${tp.team || '—'}`] : null,
      nGuesses >= 3 || D.done ? [T('Hometown', 'Cidade Natal'), tp.hometown || '—'] : null,
      nGuesses >= 4 || D.done ? [T('Initials & Nickname', 'Iniciais & Apelido'), `${tp.name ? tp.name.split(/\s+/).map(w => w[0]).join('.') + '.' : ''} ${tp.nick ? '“' + tp.nick + '”' : T('(no nickname)', '(sem apelido)')}`] : null
    ].filter(Boolean);

    const rcIn = s => { const m = String(s || '').match(/(\d+)/); return m ? +m[1] : null; };
    const cmpRow = gid => {
      const ga = A[gid] || {}, gc = C[gid] || [], gp = S.F.get(gid) || {};
      const d1 = DIV_ORD.indexOf(ga.div), d2 = DIV_ORD.indexOf(ta.div);
      const dIcon = ga.div === ta.div ? '🟩' : (d1 >= 0 && d2 >= 0 && Math.abs(d1 - d2) === 1 ? '🟨' : '⬛');
      const ovG = gc[0] || 70, ovT = tc[0] || 70, ovIcon = Math.abs(ovG - ovT) <= 1 ? '🟩' : ovG < ovT ? '↑' : '↓';
      const rG = rcIn(gp.Reach), rT = rcIn(tp.Reach), rIcon = (rG && rT) ? (rG === rT ? '🟩' : rG < rT ? '↑' : '↓') : '';
      const wG = sum(ga.w || [0]), wT = sum(ta.w || [0]), wIcon = wG === wT ? '🟩' : wG < wT ? '↑' : '↓';
      const cIcon = gp.country && tp.country && gp.country === tp.country ? '🟩' : '⬛';
      return `<div class="tb" style="grid-template-columns:1.5fr 1fr .65fr .7fr .7fr 1fr"><span><b>${esc(gp.name || gid)}</b></span><span>${dIcon} ${esc(ga.div || '')}</span><span>${ovIcon} ${ovG}</span><span>${rIcon} ${esc(gp.Reach || '—')}</span><span>${wIcon} ${wG}V</span><span>${cIcon} ${esc(gp.country || '—')}</span></div>`;
    };

    let h = `<div class="acts"><button data-xdm="daily" class="${D.mode === 'daily' ? 'pk on' : ''}">${T('Daily Challenge', 'Desafio do Dia')} (${D.date})</button><button data-xdm="free" class="${D.mode === 'free' ? 'pk on' : ''}">${T('Free Play (Unlimited)', 'Modo Livre (Infinito)')}</button>${D.mode === 'free' ? `<button data-xdm="free">${T('New mystery fighter', 'Novo lutador secreto')} ↻</button>` : ''}</div>
    <p class="mu sm">${T('Guess the secret UFC fighter in up to 6 tries! Each wrong guess reveals one real opponent from their recent fight history AND unlocks a new biographical clue.', 'Descubra quem é o lutador secreto do UFC em até 6 tentativas! Cada palpite revela o nome de um adversário real do histórico recente E desbloqueia uma nova pista biográfica.')}</p>
    <div class="card" style="padding:1rem 1.1rem">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.6rem">
        <div><b style="font:900 1.5rem var(--d);color:var(--gd)">${D.done ? esc(tp.name) : '??? ' + T('SECRET FIGHTER', 'LUTADOR SECRETO')}</b><div class="mu sm">${T('UFC Record', 'Cartel no UFC')}: <b>${sum(ta.w)}-${sum(ta.l)}-${ta.d}</b> (${ta.w[0]} KO, ${ta.w[1]} SUB, ${ta.w[2]} DEC)${ta.tw ? ` · 🏆 ${ta.tw} ${T('title wins', 'vit. cinturão')}` : ''}${ta.chin ? ` · ${T('Chin', 'Queixo')} ${ta.chin}` : ''}</div></div>
        <div class="rt">${D.done ? `OVR ${tc[0]}` : 'OVR ??'}<small>${T('Try', 'Tentativa')} ${D.gs.length}/6</small></div>
      </div>
      <div class="ctl" style="margin-top:.8rem;margin-bottom:.4rem">${AL.map((l, i) => `<div><div style="display:flex;justify-content:space-between;font-size:.8rem"><span class="mu">${l}</span><b>${tc[i + 1]}</b></div><i class="mb"><b style="width:${tc[i + 1]}%"></b></i></div>`).join('')}</div>
      <div style="margin-top:.7rem;border-top:1px solid var(--ln);padding-top:.6rem"><b>🥊 ${T('Last 6 UFC Fights (1 opponent revealed per try)', 'Últimas 6 Lutas no UFC (1 rival revelado por tentativa)')}</b>
        ${recent6.map((f, idx) => {
          const isA = mid(f.a.id) === tid, opp = isA ? f.b : f.a, res = f.res === 'draw' ? 'E' : (f.res === (isA ? 'a' : 'b') ? 'V' : 'D');
          const showOpp = D.done || idx < nGuesses, mf = MKT[f.id], myOdd = mf ? (isA ? mf[0] : mf[1]) : null;
          return `<div class="sr" style="grid-template-columns:4.8rem 1.8rem 1fr auto;font-size:.84rem"><span class="mu">${f.date.slice(0, 7)}</span><b class="${res === 'V' ? 'up' : res === 'D' ? 'dn' : ''}">${res}</b><span>vs <b>${showOpp ? esc(nm(mid(opp.id))) : '🔒 ??? (' + T('Try ' + (idx + 1), 'Tentativa ' + (idx + 1)) + ')'}</b>${f.title ? ' 🏆' : ''}</span><span class="mu sm">${esc(f.method)}${f.round ? ' R' + f.round : ''}${myOdd != null ? ' · Odd ' + fOdd(myOdd) : ''}</span></div>`;
        }).join('')}
      </div>
      <div style="margin-top:.7rem;border-top:1px solid var(--ln);padding-top:.6rem">${hints.map(([k, v], i) => `<div class="sr" style="grid-template-columns:auto 1fr"><span class="mu sm">💡 ${T('Clue', 'Pista')} ${i + 1} (${k}):</span><b>${esc(v)}</b></div>`).join('')}</div>
    </div>`;

    if (D.done) {
      h += `<div class="card" style="padding:.9rem 1.1rem;border-left:3px solid ${D.won ? 'var(--win)' : 'var(--loss)'}">
        <b class="${D.won ? 'up' : 'dn'}" style="font-size:1.1rem">${D.won ? T(`Solved in ${D.gs.length}/6 tries!`, `Você acertou em ${D.gs.length}/6 tentativas!`) : T('Out of tries! The fighter was:', 'Fim das tentativas! O lutador era:')}</b>
        <div style="display:flex;align-items:center;gap:.8rem;margin-top:.6rem">${typeof av === 'function' ? av(tid, tp.name, 'sm') : ''}<div><b><a href="#/fighter/${tid}">${esc(tp.name)}</a></b> <span class="mu sm">${esc(tp.nick || '')} · ${esc(ta.div)} · OVR ${tc[0]}</span></div></div>
        <div class="acts" style="margin-top:.7rem;margin-bottom:0"><button data-xdsh="1">${T('Copy result to share', 'Copiar resultado para compartilhar')} 📋</button><button data-xdm="free">${T('Play another (Free mode)', 'Jogar outro (Modo Livre)')} ▶</button></div>
      </div>`;
    } else {
      h += `<div class="card" style="padding:.8rem 1rem"><input data-xq="dna" type="search" placeholder="${T('Type a fighter name to guess…', 'Digite o nome de um lutador para chutar…')}"><div class="res" id="xsdna"></div></div>`;
    }

    if (D.gs.length) {
      h += `<div class="card" style="padding:.5rem .9rem;overflow-x:auto"><div class="tb hd" style="grid-template-columns:1.5fr 1fr .65fr .7fr .7fr 1fr"><span>${T('Guess', 'Palpite')}</span><span>${T('Division', 'Divisão')}</span><span>OVR</span><span>${T('Reach', 'Alcance')}</span><span>${T('UFC Wins', 'Vit. UFC')}</span><span>${T('Country', 'País')}</span></div>${[...D.gs].reverse().map(cmpRow).join('')}</div>`;
    }
    return h;
  }

  /* ================= 1B) GAME: DESAFIO LAS VEGAS (BATA A BANCA COM LUTAS REAIS) ================= */
  const payUs = (stake, odd) => odd > 0 ? Math.round(stake * (odd / 100)) : Math.round(stake * (100 / -odd));
  function vgNew() {
    const M = X.d.market; if (!M || !M.fights) return;
    const pool = S.fg.filter(f => (f.res === 'a' || f.res === 'b') && M.fights[f.id] && Math.abs(M.fights[f.id][0]) <= 380 && Math.abs(M.fights[f.id][1]) <= 380);
    const pick = pool.slice().sort(() => Math.random() - .5).slice(0, 5);
    X.vg = { fights: pick, bets: pick.map(() => ({ side: 'pass', stake: 200 })), rev: false };
  }
  function tVg() {
    if (!X.d.market) return miss('market');
    if (!X.vg.fights.length) vgNew();
    const V = X.vg, M = X.d.market.fights, A = (X.d.analytics || {}).fighters || {};
    let bank = 1000, modelBank = 1000;
    const rows = V.fights.map((f, i) => {
      const mf = M[f.id], [oa, ob, pm, rka, rkb, koA, koB, subA, subB] = mf;
      const b = V.bets[i], ea = (A[mid(f.a.id)] || {}).e || 1500, eb = (A[mid(f.b.id)] || {}).e || 1500, pe = 1 / (1 + Math.pow(10, (eb - ea) / 400));
      const mPick = pe - pm > .06 ? 'a' : (1 - pe) - (1 - pm) > .06 ? 'b' : 'pass';
      let net = 0, mNet = 0;
      if (V.rev) {
        if (b.side === 'a' || b.side === 'b') net = f.res === b.side ? payUs(b.stake, b.side === 'a' ? oa : ob) : -b.stake;
        if (mPick === 'a' || mPick === 'b') mNet = f.res === mPick ? payUs(200, mPick === 'a' ? oa : ob) : -200;
        bank += net; modelBank += mNet;
      }
      const rkStr = (rka != null || rkb != null) ? ` · Rk ${rka != null ? (rka === 0 ? 'C' : '#' + rka) : 'NR'} vs ${rkb != null ? (rkb === 0 ? 'C' : '#' + rkb) : 'NR'}` : '';
      return `<div class="card" style="padding:.85rem 1.1rem">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.4rem">
          <span class="mu sm"><b>#${i + 1}</b> · ${esc(f.div)}${f.title ? ' · 🏆 ' + T('Title Fight', 'Cinturão') : ''}${rkStr}${V.rev ? ' · ' + fmt(f.date) : ''}</span>
          <span class="mu sm">${T('Vegas Implied', 'Vegas')}: <b>${p0(pm)} / ${p0(1 - pm)}</b> · ${T('Model', 'Modelo')}: <b>${p0(pe)} / ${p0(1 - pe)}</b></span>
        </div>
        <div class="fx" style="margin:.55rem 0"><span class="fa ${V.rev ? (f.res === 'a' ? 'w' : 'l') : ''}" style="color:var(--gd)">${esc(name(f.a))} <small>(${fOdd(oa)})</small></span><span class="mu">vs</span><span class="fa ${V.rev ? (f.res === 'b' ? 'w' : 'l') : ''}" style="color:var(--cb)">${esc(name(f.b))} <small>(${fOdd(ob)})</small></span></div>
        ${!V.rev ? `<div class="acts" style="margin-bottom:0">
          <button data-xvg="${i}:a:200" class="pk${b.side === 'a' && b.stake === 200 ? ' on' : ''}">$200 ${esc(name(f.a))} (${fOdd(oa)})</button>
          <button data-xvg="${i}:b:200" class="pk${b.side === 'b' && b.stake === 200 ? ' on' : ''}">$200 ${esc(name(f.b))} (${fOdd(ob)})</button>
          <button data-xvg="${i}:pass:0" class="pk${b.side === 'pass' ? ' on' : ''}">${T('Pass ($0)', 'Passar ($0)')}</button>
        </div>` : `<div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--ln);padding-top:.45rem;font-size:.88rem">
          <span>${T('Result', 'Resultado')}: <b>${esc(name(f[f.res]))}</b> (${esc(f.method)}, R${esc(f.round)}) · <a href="#/event/${f.ev}/${f.id}" style="color:var(--gd);text-decoration:underline">${T('Open fight', 'Ver luta')}</a></span>
          <b class="${net > 0 ? 'up' : net < 0 ? 'dn' : 'mu'}">${net > 0 ? '+$' + net : net < 0 ? '-$' + Math.abs(net) : '$0'}</b>
        </div>`}
      </div>`;
    }).join('');

    let best = 1000;
    try { best = Math.max(1000, +(localStorage.sumulaVegasBest || 1000)); if (V.rev && bank > best) { best = bank; localStorage.sumulaVegasBest = String(best); } } catch {}

    return `<p class="mu sm">${T('5 real historical UFC fights with official Las Vegas closing odds. Start with a $1,000 bankroll, compare Vegas implied probabilities against our model to spot value bets, or pass on traps!', '5 lutas reais da história do UFC com as Odds oficiais de fechamento de Las Vegas. Comece com $1.000 de banca, compare a probabilidade de Vegas com a do nosso modelo para achar apostas de valor (Value Bets) ou pule armadilhas!')}</p>
    <div class="card" style="padding:.85rem 1.1rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.8rem;border-left:4px solid var(--gd)">
      <div><span class="mu sm">${T('Your Bankroll', 'Sua Banca')}</span><div style="font:900 2rem/1 var(--d);color:${bank >= 1000 ? 'var(--win)' : 'var(--loss)'}">$${bank.toLocaleString('en-US')} <span class="mu sm">(${bank >= 1000 ? '+' : ''}${bank - 1000})</span></div></div>
      ${V.rev ? `<div><span class="mu sm">${T('Model Value Strategy', 'Estratégia do Modelo')}</span><div style="font:900 1.5rem/1 var(--d)">$${modelBank.toLocaleString('en-US')}</div></div>` : ''}
      <div><span class="mu sm">${T('Personal Record', 'Seu Recorde')}</span><div style="font:900 1.5rem/1 var(--d);color:var(--gd)">$${best.toLocaleString('en-US')}</div></div>
      <div class="acts" style="margin:0">${!V.rev ? `<button data-xvgr="1" style="background:var(--gd);color:#000">🎲 ${T('Reveal Real Outcomes', 'Revelar Resultados Reais')}</button>` : ''}<button data-xvgn="1">${T('New 5-Fight Card', 'Sortear Novas 5 Lutas')} ↻</button></div>
    </div>` + rows;
  }

  /* ================= 1C) PAINEL: MERCADO & ODDS (6.785 LUTAS) ================= */
  function tMkt() {
    const M = X.d.market; if (!M || !M.eval) return miss('market');
    const E = M.eval, up = M.upsets || [], F = M.fighters || {};
    const dogRows = Object.entries(F).filter(([, v]) => v[4] >= 5).sort((a, b) => X.ms === 'roi' ? b[1][6] - a[1][6] : (b[1][5] - a[1][5] || b[1][6] - a[1][6])).slice(0, 30);
    return `<p class="mu sm">${T(`Out-of-sample audit across ${E.n.toLocaleString('en-US')} UFC fights with historical Las Vegas closing odds (2010–2026). Average sportsbook overround (vig): ${p1(E.avg_vig)}.`, `Auditoria fora da amostra em ${E.n.toLocaleString('pt-BR')} lutas do UFC com odds históricas de fechamento de Las Vegas (2010–2026). Margem média das casas (overround/vig): ${p1(E.avg_vig)}.`)}</p>
    <div class="card" style="padding:.8rem 1.1rem">
      <div class="tb hd" style="grid-template-columns:1.6fr 1fr 1fr 1fr"><span>${T('Predictor', 'Fonte / Modelo')}</span><span>${T('Accuracy', 'Acertos')}</span><span>Brier Score ↓</span><span>Log-Loss ↓</span></div>
      <div class="tb best" style="grid-template-columns:1.6fr 1fr 1fr 1fr"><span><b>Las Vegas (Closing Odds)</b></span><span>${p1(E.mkt.acc)}</span><span>${E.mkt.brier}</span><span>${E.mkt.ll}</span></div>
      <div class="tb" style="grid-template-columns:1.6fr 1fr 1fr 1fr"><span><b>${T('Ensemble (65% Vegas + 35% ELO)', 'Combinado (65% Vegas + 35% ELO)')}</b></span><span>${p1(E.blend.acc)}</span><span>${E.blend.brier}</span><span>${E.blend.ll}</span></div>
      <div class="tb" style="grid-template-columns:1.6fr 1fr 1fr 1fr"><span><b>ELO Puro (Súmula)</b></span><span>${p1(E.elo.acc)}</span><span>${E.elo.brier}</span><span>${E.elo.ll}</span></div>
    </div>
    <h2>${T('Las Vegas Calibration Curve (Implied vs. Actual Win Rate)', 'Curva de Calibração de Las Vegas (Previsto vs. Observado)')}</h2>
    <div class="card" style="padding:.6rem 1.1rem"><div class="tb hd" style="grid-template-columns:.8fr 1fr 1fr 1fr"><span>${T('Fights', 'Lutas')}</span><span>${T('Vegas Implied', 'Previsto Vegas')}</span><span>${T('Actual Win %', 'Observado')}</span><span>${T('Diff', 'Diferença')}</span></div>
    ${(E.calibration || []).map(b => `<div class="tb" style="grid-template-columns:.8fr 1fr 1fr 1fr"><span>${b.n}</span><span>${p1(b.pred)}</span><span>${p1(b.obs)}</span><span class="${Math.abs(b.obs - b.pred) < .03 ? 'up' : 'mu'}">${b.obs >= b.pred ? '+' : ''}${((b.obs - b.pred) * 100).toFixed(1)} pp</span></div>`).join('')}</div>
    <h2>⚡ ${T('Biggest Betting Upsets in UFC History', 'Maiores Zebras das Casas de Aposta no UFC')}</h2>
    <div class="card" style="padding:.6rem 1.1rem">${up.slice(0, 15).map(u => `<div class="sr" style="grid-template-columns:1fr auto"><a href="#/event/${u.ev}/${u.id}"><b>${esc(nm(u.w))}</b> ${T('def.', 'venceu')} ${esc(nm(u.l))} <span class="mu sm">(${fmt(u.date)}, ${esc(u.m)})</span></a><span><b class="up">+${u.odd}</b> <span class="mu sm">(${T('Vegas', 'Vegas')} ${p1(u.p_mkt)} · ELO ${p0(u.p_elo)})</span></span></div>`).join('')}</div>
    <h2>👑 ${T('Underdog Kings & Career Betting ROI (1u flat bet)', 'Reis da Zebra & Ranking de ROI (Aposta fixa de 1u)')}</h2>
    <div class="acts"><button data-xms="dog" class="pk${X.ms === 'dog' ? ' on' : ''}">${T('Most Underdog Wins', 'Mais Vitórias como Azarão')}</button><button data-xms="roi" class="pk${X.ms === 'roi' ? ' on' : ''}">${T('Highest Net Profit (ROI)', 'Maior Lucro Líquido (ROI)')}</button></div>
    <div class="card" style="padding:.5rem .9rem;overflow-x:auto"><div class="tb hd" style="min-width:34rem;grid-template-columns:1.6fr .9fr 1fr 1fr 1fr"><span>${T('Fighter', 'Lutador')}</span><span>${T('Fights w/ Odds', 'Lutas c/ Odds')}</span><span>${T('As Favorite', 'Como Favorito')}</span><span>${T('As Underdog (>=+110)', 'Como Azarão (>=+110)')}</span><span>${T('Net Profit (1u)', 'Lucro Líquido (1u)')}</span></div>
    ${dogRows.map(([fid, v]) => `<div class="tb" style="min-width:34rem;grid-template-columns:1.6fr .9fr 1fr 1fr 1fr"><a href="#/fighter/${fid}"><b>${esc(nm(fid))}</b></a><span>${v[1]}-${v[0] - v[1]}</span><span>${v[3]}-${v[2] - v[3]}</span><span><b class="up">${v[5]}V</b> / ${v[4]} lutas</span><b class="${v[6] >= 0 ? 'up' : 'dn'}">${v[6] >= 0 ? '+' : ''}${v[6]}u</b></div>`).join('')}</div>`;
  }

  /* ================= 1B) GAME: MODO MATCHMAKER (DANA WHITE) ================= */
  function mmCost(id) {
    const c = ((X.d.cards || {}).cards || {})[id], a = ((X.d.analytics || {}).fighters || {})[id];
    const ovr = c ? c[0] : 72, tw = a ? a.tw || 0 : 0;
    return Math.round((80 + Math.pow(Math.max(0, ovr - 65), 1.75) * 4.2 + tw * 45) / 10) * 10; // em milhares ($k)
  }
  function mmInit() {
    const A = (X.d.analytics || {}).fighters || {}, C = (X.d.cards || {}).cards || {}, E = (X.d.excitement || {}).fighters || {};
    const cut = '2024-01-01';
    const dvs = ['Lightweight', 'Welterweight', 'Middleweight', 'Featherweight', 'Bantamweight', 'Heavyweight', 'Light Heavyweight'];
    const pickDvs = dvs.sort(() => Math.random() - .5).slice(0, 3);
    const pool = [];
    for (const dv of pickDvs) {
      const cands = Object.keys(C).filter(id => A[id] && E[id] && A[id].div === dv && A[id].last >= cut && S.F.has(id)).sort(() => Math.random() - .5).slice(0, 6);
      for (const id of cands) pool.push({ id, div: dv, ovr: C[id][0], cost: mmCost(id) });
    }
    pool.sort((a, b) => a.div.localeCompare(b.div) || b.ovr - a.ovr);
    X.mm = { pool, cap: 2400, bouts: [], pickA: '', res: null };
  }
  function mmSim() {
    const M = X.mm, A = X.d.analytics.fighters;
    if (M.bouts.length < 5) return;
    const out = []; let totEx = 0;
    for (let i = 0; i < M.bouts.length; i++) {
      const b = M.bouts[i], r = fotn(b.a, b.b, i === 0), pA = r ? r.pw : .5, aWins = Math.random() < pA;
      const w = aWins ? b.a : b.b, l = aWins ? b.b : b.a, wa = A[w] || {}, finR = wa.fin != null ? wa.fin : .5;
      const isFin = Math.random() < Math.min(.85, finR * (r ? r.pace : 1));
      const koShare = (wa.w && (wa.w[0] + wa.w[1]) > 0) ? wa.w[0] / (wa.w[0] + wa.w[1]) : .55;
      const method = isFin ? (Math.random() < koShare ? 'KO/TKO' : 'Submission') : (Math.random() < .22 ? 'Split Decision' : 'Unanimous Decision');
      const maxRd = i === 0 ? 5 : 3, rd = isFin ? (1 + Math.floor(Math.random() * maxRd)) : maxRd;
      const ex = (r ? r.p : .08) * (isFin ? 1.35 : method === 'Split Decision' ? 1.2 : .85) * (0.85 + Math.random() * .3);
      totEx += r ? r.p : .08;
      out.push({ ...b, w, l, method, rd, ex, fotnP: r ? r.p : .08, bal: r ? r.bal : .5, isUpset: (aWins && pA < .42) || (!aWins && pA > .58) });
    }
    const fotnIdx = out.reduce((best, x, idx) => x.ex > out[best].ex ? idx : best, 0);
    const score = Math.min(100, Math.round(totEx * 115 + out.reduce((s, x) => s + x.bal * 8, 0) + (out.filter(x => x.method !== 'Unanimous Decision').length * 4)));
    const grade = score >= 90 ? 'S+' : score >= 82 ? 'S' : score >= 74 ? 'A' : score >= 65 ? 'B' : 'C';
    const ppv = Math.round(180 + score * 8.5 + M.bouts.reduce((s, b) => s + mmCost(b.a) + mmCost(b.b), 0) * .18);
    M.res = { out, fotnIdx, score, grade, ppv };
  }
  function tMm() {
    if (!X.d.analytics || !X.d.cards || !X.d.excitement) return miss('excitement');
    if (!X.mm.pool.length) mmInit();
    const M = X.mm, used = new Set(M.bouts.flatMap(b => [b.a, b.b])), spent = M.bouts.reduce((s, b) => s + mmCost(b.a) + mmCost(b.b), 0), rem = M.cap - spent;
    let h = `<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.6rem">
      <p class="mu sm" style="margin:0">${T('Book a 5-fight UFC Main Card under the $2,400k salary cap. Pair fighters from the same division to maximize Fight of the Night excitement and competitive balance.', 'Monte um Main Card de 5 lutas respeitando o teto salarial de $2.400k. Case lutadores da mesma categoria para maximizar a chance de Fight of the Night e o equilíbrio competitivo.')}</p>
      <button data-xmm="reset">${T('New Roster Pool', 'Sortear Novo Elenco')} ↻</button>
    </div>
    <div class="card" style="padding:.8rem 1.1rem;margin-top:.6rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.8rem">
      <div><span class="mu sm">${T('Main Card Fights', 'Lutas Fechadas')}</span><div style="font:900 1.6rem var(--d)">${M.bouts.length} / 5</div></div>
      <div><span class="mu sm">${T('Budget Remaining', 'Orçamento Restante')}</span><div style="font:900 1.6rem var(--d);color:${rem < 200 ? 'var(--loss)' : 'var(--gd)'}">$${rem.toLocaleString('en-US')}k <span class="mu sm">/ $${M.cap.toLocaleString('en-US')}k</span></div></div>
      <button data-xmm="sim" style="background:var(--gd);color:#000" ${M.bouts.length === 5 ? '' : 'disabled'}>🔥 ${T('Run Event Live (5/5)', 'Realizar Evento Ao Vivo (5/5)')}</button>
    </div>`;

    if (M.bouts.length) {
      h += `<h2>${T('Booked Main Card', 'Main Card Escalado')}</h2><div class="card" style="padding:.6rem 1.1rem">${M.bouts.map((b, i) => {
        const r = fotn(b.a, b.b, i === 0), ca = mmCost(b.a), cb = mmCost(b.b);
        return `<div class="sr" style="grid-template-columns:1.5rem 1fr auto auto;align-items:center">
          <b style="color:var(--gd)">${i === 0 ? '👑' : i + 1}</b>
          <span><b>${esc(nm(b.a))}</b> vs <b>${esc(nm(b.b))}</b> <span class="mu sm">(${esc(b.div)})</span><br><span class="mu sm">${i === 0 ? T('Main Event (5 Rds)', 'Luta Principal (5 Rds)') : T('Main Card (3 Rds)', 'Card Principal (3 Rds)')} · $${ca + cb}k · FOTN ${r ? p1(r.p) : '—'} · ${T('Balance', 'Equilíbrio')} ${r ? p0(r.bal) : '—'}</span></span>
          <b style="color:var(--gd)">${r ? p1(r.p) : '—'}</b>
          <button data-xmm="rm:${i}">×</button>
        </div>`;
      }).join('')}</div>`;
    }

    if (M.res) {
      const R = M.res;
      h += `<h2>🏆 ${T('Event Results & Dana White Grade', 'Resultados do Evento & Nota de Matchmaker')}</h2>
      <div class="card" style="padding:1rem 1.1rem;border-left:4px solid var(--gd)">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.8rem">
          <div><span class="mu sm">${T('Matchmaker Grade', 'Nota do Matchmaker')}</span><div style="font:900 3rem/1 var(--d);color:var(--gd)">${R.grade} <span style="font-size:1.3rem;color:var(--tx)">(${R.score}/100)</span></div></div>
          <div style="text-align:right"><span class="mu sm">${T('Estimated PPV Buys', 'Vendas Estimadas de PPV')}</span><div style="font:900 1.8rem var(--d)">${R.ppv.toLocaleString('en-US')}k</div></div>
        </div>
        <div style="margin-top:.8rem;border-top:1px solid var(--ln);padding-top:.6rem">${R.out.map((o, i) => `<div class="sr" style="grid-template-columns:1fr auto">
          <span><b>${esc(nm(o.w))}</b> ${T('def.', 'venceu')} ${esc(nm(o.l))} <span class="mu sm">(${o.method}, R${o.rd})</span>${i === R.fotnIdx ? ` <span class="tag">🔥 FOTN $50k</span>` : ''}${o.isUpset ? ` <span class="tag" style="background:var(--cb);color:#fff">⚡ ${T('UPSET', 'ZEBRA')}</span>` : ''}</span>
          <span class="mu sm">FOTN ${p1(o.fotnP)}</span>
        </div>`).join('')}</div>
      </div>`;
    }

    if (M.bouts.length < 5) {
      const pA = M.pickA ? M.pool.find(x => x.id === M.pickA) : null;
      h += `<h2>${pA ? T(`Select opponent for ${nm(pA.id)} (${pA.div})`, `Escolha o adversário de ${nm(pA.id)} (${pA.div})`) : T('Available Roster (Tap two from the same division)', 'Elenco Disponível (Toque em dois da mesma divisão)')}</h2>
      <div class="chgrid">${M.pool.filter(x => !used.has(x.id)).map(x => {
        const isSel = M.pickA === x.id, canPair = !pA || (pA.id !== x.id && pA.div === x.div && pA.cost + x.cost <= rem), cantAfford = !pA && x.cost > rem;
        const f = S.F.get(x.id) || {};
        return `<button type="button" data-xmm="pick:${x.id}" class="card chc${isSel ? ' hl' : ''}" style="text-align:left;width:100%;opacity:${canPair && !cantAfford ? 1 : .38}" ${(!canPair || cantAfford) && !isSel ? 'disabled' : ''}>
          ${typeof av === 'function' ? av(x.id, f.name, 'sm') : ''}
          <div style="flex:1;min-width:0"><div class="chd">${esc(x.div)} · OVR ${x.ovr}</div><div class="chn" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(f.name)}</div><div class="mu sm">$${x.cost}k · ${esc(f.record || '')}</div></div>
        </button>`;
      }).join('')}</div>`;
    }
    return h;
  }

  /* ================= 2) SEJA O JUIZ ================= */
  const judges = (f, order) => { const out = []; const re = /([^\d]+?)\s*(\d{2})\s*-\s*(\d{2})/g; let m; while ((m = re.exec(f.detail || ''))) { const x = +m[2], y = +m[3], n = m[1].replace(/^[\s.,;:]+|[\s.,;:]+$/g, ''); if (n && x >= 20 && x <= 50 && y >= 20 && y <= 50 && Math.abs(x - y) <= 5) out.push({ n, w: order === 'winner_first' || f.res === 'a' ? x : y, l: order === 'winner_first' || f.res === 'a' ? y : x }); } return out; };
  const jscore = () => { try { return { g: 0, r: 0, rn: 0, w: 0, ...JSON.parse(localStorage.sumulaJuiz || '{}') }; } catch { return { g: 0, r: 0, rn: 0, w: 0 }; } };
  function jNew() {
    const D = X.d.decisions; if (!D) return;
    const pool = S.fg.filter(f => D.fights[f.id] && (f.res === 'a' || f.res === 'b') && ((f.rounds || {}).totals || []).length >= 3 && D.fights[f.id][4].length === f.rounds.totals.length);
    if (!pool.length) { X.jg.f = null; return; }
    const f = pool[Math.floor(Math.random() * pool.length)];
    X.jg = { f, flip: Math.random() < .5, sc: f.rounds.totals.map(() => null), rev: false };
  }
  function tJg() {
    if (!X.d.decisions) return miss('decisions');
    if (!X.jg.f) jNew(); const J = X.jg, f = J.f;
    if (!f) return `<p class="empty">${T('No decision with round-by-round stats yet.', 'Ainda não há decisão com estatísticas round a round.')}</p>`;
    const A = J.flip ? 'b' : 'a', B = J.flip ? 'a' : 'b', rs = f.rounds.totals, D = X.d.decisions, s = jscore();
    const line = (r, k) => { const t = r[k] || {}; return `${num(t['Sig. str.'])} sig, ${num(t.Td)} TD${num(t.KD) ? ', ' + num(t.KD) + ' KD' : ''}${t.Ctrl && t.Ctrl !== '0:00' ? ', ' + esc(t.Ctrl) : ''}${num(t['Sub. att']) ? ', ' + num(t['Sub. att']) + ' sub' : ''}`; };
    const opts = [[2, 'A 10-8'], [1, 'A 10-9'], [0, '10-10'], [-1, 'B 10-9'], [-2, 'B 10-8']];
    let h = `<p class="mu sm">${T('Score each round like a judge, using only what happened in it. Names are hidden until you reveal. Then compare with the official judges and with the stats model.', 'Pontue cada round como um juiz, só com o que aconteceu nele. Os nomes ficam escondidos até você revelar. Depois compare com os juízes oficiais e com o modelo de estatísticas.')}</p>
     <div class="card" style="padding:.8rem 1.1rem"><div class="sr"><b style="color:var(--gd)">${J.rev ? esc(nm(mid(f[A].id))) : T('Fighter A', 'Lutador A')}</b><span></span><b style="color:var(--cb)">${J.rev ? esc(nm(mid(f[B].id))) : T('Fighter B', 'Lutador B')}</b></div>
     ${rs.map((r, i) => `<div style="padding:.5rem 0;border-top:1px solid var(--ln)"><div class="sr"><span style="color:var(--gd)">${line(r, A)}</span><span class="lb">R${i + 1}</span><span style="color:var(--cb)">${line(r, B)}</span></div>
      <div class="acts">${opts.map(([v, l]) => `<button data-xj="${i}:${v}" class="pk${J.sc[i] === v ? ' on' : ''}">${l}</button>`).join('')}</div></div>`).join('')}</div>`;
    if (!J.rev) return h + `<div class="acts"><button data-xjr="1" ${J.sc.some(v => v == null) ? 'disabled' : ''}>${T('Reveal', 'Revelar')}</button><button data-xjn="1">${T('Skip', 'Pular')}</button></div><p class="mu sm">${T('Score', 'Placar')}: ${s.g} ${T('games', 'jogos')}, ${s.g ? p0(s.w / s.g) : '—'} ${T('agree with the official winner', 'concordam com o vencedor oficial')}, ${s.rn ? p0(s.r / s.rn) : '—'} ${T('of rounds agree with the model', 'dos rounds concordam com o modelo')}.</p>`;
    const dm = D.fights[f.id], rsW = dm[4], mdl = J.sc.map((_, i) => { const w = rsW[i] > .15 ? 1 : rsW[i] < -.15 ? -1 : 0; const aIsW = (A === (f.res === 'a' ? 'a' : 'b')); return aIsW ? w : -w; });
    const mine = sum(J.sc.map(v => Math.sign(v) * 1)), myA = sum(J.sc.map(v => 10 + (v > 0 ? 0 : v < 0 ? v : 0))), myB = sum(J.sc.map(v => 10 + (v < 0 ? 0 : v > 0 ? -v : 0)));
    const aW = A === (f.res === 'a' ? 'a' : 'b'), offA = aW ? 1 : -1, jd = judges(f, (D.model || {}).judge_order);
    const tot = (pts, ptsO) => pts > ptsO ? 'A' : pts < ptsO ? 'B' : T('even', 'empate');
    const myWin = myA > myB ? 'A' : myA < myB ? 'B' : null, offWin = aW ? 'A' : 'B', agreeR = J.sc.filter((v, i) => Math.sign(v) === mdl[i]).length;
    h += `<div class="card" style="padding:.8rem 1.1rem"><b>${T('You', 'Você')}: ${myA}-${myB} ${T('for', 'para')} ${myWin || T('a draw', 'empate')}</b> ${myWin === offWin ? `<b class="up">${T('agrees with the official winner', 'concorda com o vencedor oficial')}</b>` : `<b class="dn">${T('disagrees with the official winner', 'discorda do vencedor oficial')}</b>`}
      <p>${T('Official', 'Oficial')}: <b>${offWin === 'A' ? 'A' : 'B'}</b> (${esc(f.method)}, ${fmt(f.date)}) ${jd.length ? `. ${T('Judges', 'Juízes')}: ${jd.map(j => `${esc(j.n)} ${aW ? j.w : j.l}-${aW ? j.l : j.w}`).join(', ')}` : ''}</p>
      <div class="sr"><span>${T('Round', 'Round')}</span><span class="lb">${T('you', 'você')} / ${T('model', 'modelo')}</span><span></span></div>${J.sc.map((v, i) => `<div class="sr"><span>R${i + 1}</span><span class="lb">${v > 0 ? 'A' : v < 0 ? 'B' : '='} / ${mdl[i] > 0 ? 'A' : mdl[i] < 0 ? 'B' : '='}</span><span class="${Math.sign(v) === mdl[i] ? 'up' : 'dn'}">${Math.sign(v) === mdl[i] ? '✓' : '✗'}</span></div>`).join('')}
      <p class="mu sm">${agreeR} ${T('of', 'de')} ${J.sc.length} ${T('rounds agree with the stats model (chance the model gives the official winner', 'rounds concordam com o modelo de estatísticas (chance que o modelo dá ao vencedor oficial')}: ${p0(dm[0])}).</p></div><div class="acts"><button data-xjn="1">${T('Next fight', 'Próxima luta')}</button></div>`;
    if (!J.saved) { J.saved = true; const s2 = jscore(); s2.g++; s2.w += myWin === offWin ? 1 : 0; s2.r += agreeR; s2.rn += J.sc.length; try { localStorage.sumulaJuiz = JSON.stringify(s2); } catch { } }
    return h;
  }

  /* ================= 3) SCOUTING ================= */
  const LGK = () => { const a = X.d.analytics; return a && a.league ? a.league : { k100: .27, spk: 370 }; };
  function scout(id) {
    const A = (X.d.analytics || {}).fighters || {}, a = A[id], C = (X.d.cards || {}).cards || {}, c = C[id], p = S.F.get(id) || {}, L = LGK(), out = [], now = Date.now();
    if (!a) return null;
    const wins = sum(a.w || [0]), loss = sum(a.l || [0]), ko = (a.w || [])[0] || 0, sub = (a.w || [])[1] || 0, dec = (a.w || [])[2] || 0;
    const age = p.DOB && !isNaN(Date.parse(p.DOB)) ? ((now - Date.parse(p.DOB)) / 31557600000).toFixed(0) : null;
    out.push(T(`${esc(a.div || '')}${p.STANCE ? ', ' + esc(p.STANCE.toLowerCase()) : ''}${age ? ', ' + age + ' years old' : ''}${p.Height ? ', ' + esc(p.Height) : ''}${p.Reach ? ', reach ' + esc(p.Reach) : ''}. UFC record ${wins}-${loss}-${a.d || 0} in ${a.n} fights.`, `${esc(a.div || '')}${p.STANCE ? ', ' + esc(p.STANCE.toLowerCase()) : ''}${age ? ', ' + age + ' anos' : ''}${p.Height ? ', ' + esc(p.Height) : ''}${p.Reach ? ', alcance ' + esc(p.Reach) : ''}. Cartel no UFC ${wins}-${loss}-${a.d || 0} em ${a.n} lutas.`));
    if (wins >= 3) out.push(T(`${p0((ko + sub) / wins)} of his wins came by finish (${ko} KO/TKO, ${sub} submissions, ${dec} decisions).${a.fin != null && a.fin >= .7 ? ' A finisher.' : a.fin != null && a.fin <= .3 ? ' Tends to go to the judges.' : ''}`, `${p0((ko + sub) / wins)} das vitórias vieram por finalização (${ko} KO/TKO, ${sub} finalizações, ${dec} decisões).${a.fin != null && a.fin >= .7 ? ' Um finalizador.' : a.fin != null && a.fin <= .3 ? ' Costuma ir para os juízes.' : ''}`));
    if (a.opp) out.push(T(`Average rival ELO ${Math.round(a.opp)}${a.qw ? `; best three wins averaged ${Math.round(a.qw)}` : ''}. ${a.opp >= 1580 ? 'Tough schedule.' : a.opp <= 1480 ? 'Soft schedule so far: the record may flatter him.' : ''}`, `ELO médio dos rivais ${Math.round(a.opp)}${a.qw ? `; as três melhores vitórias tiveram média ${Math.round(a.qw)}` : ''}. ${a.opp >= 1580 ? 'Calendário duro.' : a.opp <= 1480 ? 'Calendário leve até aqui: o cartel pode enganar.' : ''}`));
    if (a.sl >= 400 && a.ss) out.push(T(`Lands a knockdown about every ${Math.round(a.ss)} significant strikes (UFC average: every ${Math.round(L.spk)}); DLI ${a.dli}, from ${a.sl.toLocaleString('en-US')} strikes landed.`, `Acerta um knockdown a cada ${Math.round(a.ss)} golpes significativos, em média (média da UFC: a cada ${Math.round(L.spk)}); DLI ${a.dli}, em ${a.sl.toLocaleString('pt-BR')} golpes acertados.`));
    else out.push(T('Too few recorded strikes to judge power.', 'Poucos golpes registrados para julgar a pegada.'));
    if (a.sa >= 400 && a.kas != null) { const r = a.kas / (L.k100 || .27); out.push(r > 1.3 ? T(`Vulnerable chin: gets knocked down ${p0(r - 1)} more than average per strike absorbed.`, `Queixo vulnerável: cai ${p0(r - 1)} mais que a média por golpe recebido.`) : r < .7 ? T('Hard to drop: well below the average of knockdowns suffered.', 'Difícil de derrubar: bem abaixo da média de knockdowns sofridos.') : T('Chin about average.', 'Queixo na média.')); }
    if (c) {
      const AT = [['tro', T('striking volume', 'volume de trocação')], ['def', T('defense', 'defesa')], ['lut', T('wrestling', 'luta agarrada')], ['sub', T('submissions', 'finalizações')], ['peg', T('power', 'pegada')], ['car', T('cardio', 'cardio')]], v = AT.map(([k, l], i) => [l, c[i + 1]]).sort((x, y) => y[1] - x[1]);
      out.push(T(`In his division he stands out in ${v[0][0]} (top ${100 - v[0][1]}%) and ${v[1][0]} (top ${100 - v[1][1]}%); weakest area: ${v[5][0]} (percentile ${v[5][1]}).`, `Na divisão ele se destaca em ${v[0][0]} (top ${100 - v[0][1]}%) e ${v[1][0]} (top ${100 - v[1][1]}%); ponto mais fraco: ${v[5][0]} (percentil ${v[5][1]}).`));
      if (c[6] <= 25) out.push(T('Cardio warning: output tends to fall in the late rounds.', 'Alerta de cardio: o volume tende a cair nos rounds finais.'));
    }
    if (a.last) { const mo = Math.round((now - Date.parse(a.last)) / 2629800000); out.push(mo > 18 ? T(`Last fought ${fmt(a.last)} (${mo} months ago): long layoff.`, `Última luta em ${fmt(a.last)} (${mo} meses atrás): longa inatividade.`) : T(`Last fought ${fmt(a.last)}.`, `Última luta em ${fmt(a.last)}.`)); }
    const st = X.d.styles, ms = st && st.fighters[id] != null ? st.fighters[id] : null;
    if (ms != null) { const bad = Object.entries(st.matrix).filter(([k, v]) => k.startsWith(ms + ',') && v[1] - v[2] > 0).sort((x, y) => y[1][1] - x[1][1]).slice(0, 1); if (bad.length) out.push(T(`Style watch: fighters of the style closest to “${styName(bad[0][0].split(',')[1])}” beat his style by ${bad[0][1][1] > 0 ? '+' : ''}${bad[0][1][1]} points above expectation (${bad[0][1][0]} fights)`, `Atenção ao estilo: lutadores do estilo “${styName(bad[0][0].split(',')[1])}” vencem o estilo dele ${bad[0][1][1]} pontos acima do esperado (${bad[0][1][0]} lutas)`) + '.'); }
    if (a.n < 5) out.push(T(`Small sample (${a.n} fights): treat everything above as preliminary.`, `Amostra pequena (${a.n} lutas): trate tudo acima como preliminar.`));
    return out;
  }
  function tSc() {
    if (!X.d.analytics) return miss('analytics');
    let h = `<p class="mu sm">${T('A plain-language report built from the data, every claim with its sample size.', 'Um relatório em linguagem simples feito a partir dos dados, cada afirmação com o tamanho da amostra.')}</p>${slot('sc', T('Fighter', 'Lutador'))}`;
    const r = X.sc && scout(X.sc);
    if (X.sc && !r) h += `<p class="empty">${T('No analytics for this fighter.', 'Sem análises para este lutador.')}</p>`;
    if (r) h += `<div class="card" style="padding:.9rem 1.1rem"><b style="font:900 1.6rem var(--d)">${esc(nm(X.sc))}</b>${r.map(t => `<p>${t}</p>`).join('')}</div><div class="acts"><button data-xsh="sc">${T('Share as image', 'Compartilhar como imagem')}</button></div>`;
    return h;
  }
  const styName = j => { const s = X.d.styles; if (!s) return j; const L = { tro: T('striker', 'trocador'), def: T('defensive', 'defensivo'), lut: T('wrestler', 'lutador'), sub: T('submission', 'finalizador'), peg: T('power puncher', 'pegador'), car: T('pace', 'ritmo') }; return s.names[j].map(k => L[k]).join(' + '); };

  /* ================= 4) CARD DOS SONHOS ================= */
  function fotn(ia, ib, title) {
    const E = X.d.excitement; if (!E) return null; const a = E.fighters[ia], b = E.fighters[ib]; if (!a || !b) return null;
    const p = 1 / (1 + Math.pow(10, (b[0] - a[0]) / 400)), x = [1, 1 - Math.abs(2 * p - 1), (a[2] + b[2]) / 2, ((a[3] + b[3]) / 2) / E.league_pace, title ? 1 : 0, Math.log(1 + Math.min(a[1], b[1]))];
    const z = sum(x.map((v, j) => E.model.b[j] * v / E.model.sd[j])), pr = sg(z);
    return { p: pr, mult: pr / E.model.base, bal: x[1], fin: x[2], pace: x[3], pw: p };
  }
  function tCd() {
    if (!X.d.excitement) return miss('excitement');
    const E = X.d.excitement.model, weak = E.ll >= E.ll0 - .001 || E.auc < .55;
    let h = `<p class="mu sm">${T('Pick fights and get an “excitement score”: the chance of a Fight of the Night, learned from history using only what was known before each fight (balance, finishing tendency, pace, title).', 'Escolha lutas e receba uma “nota de espetáculo”: a chance de Fight of the Night, aprendida do histórico usando só o que se sabia antes de cada luta (equilíbrio, tendência a finalizar, ritmo, cinturão).')}</p>
     <div class="card" style="padding:.6rem 1.1rem"><p class="${weak ? 'dn' : 'mu'} sm">${weak ? T('Warning: the model does NOT beat the base rate out of sample. Use it only for fun.', 'Atenção: o modelo NÃO supera a taxa-base fora da amostra. Use só por diversão.') : T('Validation out of sample', 'Validação fora da amostra')}: AUC ${E.auc}, log-loss ${E.ll} ${T('vs', 'contra')} ${E.ll0} (${T('base rate only', 'só a taxa-base')} ${p1(E.base)}; ${E.n.toLocaleString('en-US')} ${T('fights', 'lutas')}, ${E.pos} FOTN).</p></div>
     <div class="xs">${slot('ca', T('Fighter A', 'Lutador A'))}${slot('cb', T('Fighter B', 'Lutador B'))}</div>`;
    if (X.ca && X.cb && X.ca !== X.cb) h += `<div class="acts"><button data-xad="0">${T('Add fight', 'Adicionar luta')}</button><button data-xad="1">${T('Add as title fight', 'Adicionar como luta de cinturão')}</button></div>`;
    const R = X.cd.map(o => ({ ...o, r: fotn(o.a, o.b, o.t) })).sort((x, y) => (y.r ? y.r.p : -1) - (x.r ? x.r.p : -1));
    if (R.length) h += `<h2>${T('Your card', 'Seu card')}</h2><div class="card" style="padding:.6rem 1.1rem">${R.map((o, i) => `<div class="sr" style="grid-template-columns:1.5rem 1fr auto auto"><b>${i + 1}</b><span>${esc(nm(o.a))} x ${esc(nm(o.b))}${o.t ? ' <span class="tag">' + T('Title', 'Cinturão') + '</span>' : ''}${o.r ? `<br><span class="mu sm">${T('balance', 'equilíbrio')} ${p0(o.r.bal)}, ${T('finish tendency', 'tendência a finalizar')} ${p0(o.r.fin)}, ${T('pace', 'ritmo')} ×${o.r.pace.toFixed(2)}</span>` : `<br><span class="dn sm">${T('no recent data for one of them', 'sem dados recentes de um deles')}</span>`}</span><b style="color:var(--gd)">${o.r ? p1(o.r.p) : '—'}</b><button data-xrm="${o.a}:${o.b}">×</button></div>`).join('')}
      <p>${T('Expected Fights of the Night on this card', 'Fights of the Night esperadas neste card')}: <b>${sum(R.map(o => o.r ? o.r.p : 0)).toFixed(2)}</b>. ${R[0] && R[0].r ? T('Best fight to headline', 'Melhor luta para abrir o card') + ': <b>' + esc(nm(R[0].a)) + ' x ' + esc(nm(R[0].b)) + '</b>.' : ''}</p></div><div class="acts"><button data-xsh="cd">${T('Share card as image', 'Compartilhar card como imagem')}</button></div>`;
    return h;
  }

  /* ================= 5) ESTILOS ================= */
  function tSy() {
    const s = X.d.styles; if (!s) return miss('styles');
    const heat = v => { if (!v) return 'var(--s2)'; const z = Math.max(-1, Math.min(1, v[1] / 15)), sig = Math.abs(v[1]) > v[2]; return z >= 0 ? `color-mix(in srgb, var(--win) ${Math.round(z * (sig ? 90 : 35))}%, var(--s1))` : `color-mix(in srgb, var(--loss) ${Math.round(-z * (sig ? 90 : 35))}%, var(--s1))`; };
    const AL = ['STR', 'DEF', 'WRE', 'SUB', 'PWR', 'CAR'];
    let h = `<p class="mu sm">${T('Fighters grouped into styles by their six attributes. Each cell: how much the ROW style beats the COLUMN style above what their ELOs predicted (points per 100 fights). Strong color = the interval excludes zero.', 'Lutadores agrupados em estilos pelos seis atributos. Cada célula: quanto o estilo da LINHA vence o da COLUNA acima do que o ELO previa (pontos por 100 lutas). Cor forte = o intervalo exclui o zero.')}</p>
     <div class="card" style="padding:.8rem 1.1rem">${s.names.map((n, j) => `<div class="sr" style="grid-template-columns:1.3rem 1fr auto"><b>${j + 1}</b><span>${esc(styName(j))}</span><span class="mu sm">${s.sizes[j]} ${T('fighters', 'lutadores')}</span></div><div class="xg">${s.centroids[j].map((v, t) => `<span>${AL[t]} <b>${Math.round(v)}</b></span>`).join('')}</div>`).join('')}</div>
     <div class="card" style="padding:.8rem .6rem;overflow-x:auto"><table style="border-collapse:collapse;width:100%;font-size:.8rem"><tr><td></td>${s.names.map((_, j) => `<td style="text-align:center;padding:.3rem"><b>${j + 1}</b></td>`).join('')}</tr>
      ${s.names.map((_, i) => `<tr><td style="padding:.3rem"><b>${i + 1}</b></td>${s.names.map((_, j) => { const v = i === j ? null : s.matrix[i + ',' + j]; return `<td style="text-align:center;padding:.4rem .2rem;background:${i === j ? 'var(--bg)' : heat(v)}">${i === j ? '' : v ? `${v[1] > 0 ? '+' : ''}${v[1].toFixed(0)}<br><span class="mu" style="font-size:.65rem">±${v[2].toFixed(0)}, n=${v[0]}</span>` : '<span class="mu">—</span>'}</td>`; }).join('')}</tr>`).join('')}</table>
      <p class="mu sm">${T('Styles come from career-long attributes (slight leakage) and cells with few fights are noisy: read the ± and n.', 'Os estilos vêm de atributos da carreira inteira (leve vazamento) e células com poucas lutas são ruidosas: leia o ± e o n.')} ${T(`The ELO was recalibrated on these ${s.fights.toLocaleString('en-US')} fights (slope ×${s.calib}).`, `O ELO foi recalibrado nestas ${s.fights.toLocaleString('pt-BR')} lutas (inclinação ×${s.calib}).`)}</p></div>${slot('sy', T('Find a fighter’s style', 'Descubra o estilo de um lutador'))}`;
    if (X.sy) { const j = s.fighters[X.sy]; h += j == null ? `<p class="empty">${T('This fighter has no style yet (needs 4+ fights and a card).', 'Este lutador ainda não tem estilo (precisa de 4+ lutas e de um card).')}</p>` : `<div class="card" style="padding:.8rem 1.1rem"><b>${esc(nm(X.sy))}</b>: ${T('style', 'estilo')} ${j + 1}, ${esc(styName(j))}.</div>`; }
    return h;
  }

  /* ================= 6) PROSPECTOS ================= */
  function tPp() {
    const P = X.d.prospects; if (!P) return miss('prospects'); const V = P.validation, weak = V.skill <= .01;
    let h = `<p class="mu sm">${T('For fighters with 2 to 6 UFC fights: what happened to past fighters whose first two fights looked alike (results, finishes, rival strength, rating, strike difference, debut age). “Elite” = later performance in the top 10% of the cohort.', 'Para lutadores com 2 a 6 lutas no UFC: o que aconteceu com lutadores do passado cujas duas primeiras lutas eram parecidas (resultados, finalizações, força dos rivais, nota, diferença de golpes, idade na estreia). “Elite” = desempenho posterior entre os 10% melhores da coorte.')}</p>
     <div class="card" style="padding:.8rem 1.1rem"><b class="${weak ? 'dn' : ''}">${weak ? T('Weak: the projection barely beats the base rate. Read it as a curiosity.', 'Fraco: a projeção mal supera a taxa-base. Leia como curiosidade.') : T('Validated: it beats the base rate out of sample.', 'Validado: supera a taxa-base fora da amostra.')}</b>
      <p class="mu sm">${V.n} ${T('past fighters tested one by one (leave-one-out)', 'lutadores do passado testados um a um (leave-one-out)')}: ${T('skill over base rate', 'ganho sobre a taxa-base')} ${V.skill >= 0 ? '+' : ''}${V.skill}, AUC ${V.auc}. ${T('Cohort', 'Coorte')} ${P.cohort}; ${T('base rate of elite', 'taxa-base de elite')} ${p1(P.base_elite)}.</p>
      ${V.bins.length ? `<div class="tb hd"><span>${T('Predicted', 'Previsto')}</span><span>${T('Observed', 'Observado')}</span><span>n</span><span></span></div>${V.bins.map(b => `<div class="tb"><span>${p1(b[0])}</span><span>${p1(b[1])}</span><span>${b[2]}</span><span></span></div>`).join('')}` : ''}</div>
     <div class="ctl"><label>${T('Minimum fights', 'Mínimo de lutas')}<input data-xpp="1" type="number" min="2" max="6" value="${X.pp}"></label></div>`;
    const r = Object.entries(P.fighters).filter(([i, v]) => v[0] >= X.pp).sort((a, b) => b[1][1] - a[1][1] || (b[1][5] || 0) - (a[1][5] || 0) || b[1][2] - a[1][2]).slice(0, 30);   /* empate de chance: desempata pela mediana do desempenho posterior */
    h += r.length ? r.map(([i, v], k) => `<div class="card" style="padding:.7rem 1.1rem"><div class="sr" style="grid-template-columns:1.5rem 1fr auto"><b>${k + 1}</b><span style="text-align:left"><a href="#/fighter/${i}"><b>${esc(nm(i))}</b></a> <span class="mu sm">${v[0]} ${T('fights', 'lutas')}</span></span><b style="color:var(--gd)">${p0(v[1])}</b></div>
      <div class="xg"><span>${T('chance of elite', 'chance de elite')} <b>${p1(v[1])}</b> (${T('base', 'base')} ${p1(P.base_elite)})</span><span>${T('stays 4+ fights', 'chega a 4+ lutas')} <b>${p0(v[3])}</b></span><span>8+ ${T('fights', 'lutas')} <b>${p0(v[2])}</b></span>${v[4] != null ? `<span>${T('later perf.', 'desempenho posterior')} <b>${v[4]}–${v[6]}</b> (${T('median', 'mediana')} ${v[5]})</span>` : ''}</div>
      <p class="mu sm">${T('Looks like', 'Parece com')}: ${(v[7] || []).map(a => esc(nm(a))).join(', ')}</p></div>`).join('') : `<p class="empty">${T('No prospect with these filters.', 'Nenhum prospecto com esses filtros.')}</p>`;
    return h;
  }


  /* ================= 7) JUÍZES E ÁRBITROS ================= */
  const zc = z => z == null ? '<span class="mu">—</span>' : `<span class="${Math.abs(z) > 3.3 ? 'dn' : 'mu'}">${z > 0 ? '+' : ''}${z.toFixed(1)}</span>`;
  function tOf() {
    const D = X.d.judges; if (!D) return miss('judges');
    const jr = Object.entries(D.judges).sort((a, b) => X.os === 'z' ? b[1].rs - a[1].rs : (b[1][X.os] ?? -99) - (a[1][X.os] ?? -99)).slice(0, 25);
    const rr = Object.entries(D.refs).sort((a, b) => Math.abs(b[1][X.or] ?? 0) - Math.abs(a[1][X.or] ?? 0)).slice(0, 25), L = D.league;
    const bt = (k, cur, set, l) => `<button data-${set}="${k}" class="pk${cur === k ? ' on' : ''}">${l}</button>`;
    let h = `<p class="mu sm">${T('How often each official deviates from what the league does. “z” counts standard deviations from the expected value; only |z| above 3.3 is flagged, because with dozens of officials a few values near 2 appear by chance. Patterns here are hypotheses, not accusations.', 'Quanto cada oficial se desvia do que a liga faz. “z” conta desvios-padrão do valor esperado; só |z| acima de 3,3 é sinalizado, porque com dezenas de oficiais alguns valores perto de 2 aparecem por acaso. Os padrões aqui são hipóteses, não acusações.')}</p>
     <h2>${T('Judges', 'Juízes')}<span class="xbar" data-xk="x:of-j"></span></h2><div class="acts">${bt('z', X.os, 'xos', T('Dissent rate', 'Dissidência'))}${bt('spz', X.os, 'xos', T('Split decisions', 'Decisões divididas'))}${bt('c2z', X.os, 'xos', T('Questionable decisions', 'Decisões questionáveis'))}</div>
     <p class="mu sm">${T('League', 'Liga')}: ${D.league.cards.toLocaleString(S.pt ? 'pt-BR' : 'en-US')} ${T('cards', 'cartões')}, ${p1(L.dis)} ${T('vote against the official winner', 'votam contra o vencedor oficial')}${L.c2f ? `; ${T('in questionable fights', 'nas lutas questionáveis')} ${p0(L.c2f)} ${T('still favor the official winner', 'ainda favorecem o vencedor oficial')}` : ''}.</p>
     <div class="card" style="padding:.4rem .9rem;overflow-x:auto"><div class="tb hd" style="min-width:34rem;grid-template-columns:1.6fr .6fr 1fr 1fr 1.2fr"><span>${T('Judge', 'Juiz')}</span><span>${T('Cards', 'Cartões')}</span><span>${T('Dissent (shrunk)', 'Dissidência (ajustada)')}</span><span>${T('In splits', 'Nas divididas')}</span><span>${T('Questionable', 'Questionáveis')}</span></div>
     ${jr.map(([n, v]) => `<div class="tb" style="min-width:34rem;grid-template-columns:1.6fr .6fr 1fr 1fr 1.2fr"><span>${esc(n)}</span><span>${v.n}</span><span>${p1(v.rs)} ${zc(v.z)}</span><span>${v.sp >= 10 ? `${v.spd}/${v.sp} ` : ''}${zc(v.spz)}</span><span>${v.c2 ? `${v.c2f}/${v.c2} ` : ''}${zc(v.c2z)}${v.c3 ? ` <span class="mu sm">(${v.c3f}/${v.c3} ${T('robbery', 'roubo')})</span>` : ''}</span></div>`).join('')}</div>
     <p class="mu sm">${T('Questionable = fights where the stats model gave the official winner under 35%. The ratio is cards that still went to the official winner; a high z means this judge sides with the official winner there more than the league does.', 'Questionáveis = lutas em que o modelo de estatísticas deu ao vencedor oficial menos de 35%. A razão é de cartões que ainda foram para o vencedor oficial; z alto = este juiz fica do lado do vencedor oficial ali mais que a liga.')}${D.has_cls ? '' : ' ' + T('(decisions.json missing: this column is empty)', '(decisions.json ausente: esta coluna fica vazia)')}</p>
     <h2>${T('Referees', 'Árbitros')}<span class="xbar" data-xk="x:of-r"></span></h2><div class="acts">${bt('finz', X.or, 'xor', T('Finishes', 'Finalizações'))}${bt('koz', X.or, 'xor', 'KO/TKO')}${bt('subz', X.or, 'xor', T('Submissions', 'Finalizações (sub)'))}${bt('sz', X.or, 'xor', T('Stoppage timing', 'Hora da parada'))}</div>
     <p class="mu sm">${T('League finish rate', 'Taxa de finalização da liga')} ${p1(L.fin)}. ${T('Expected values come from a model using each fight’s fighters (finishing tendency, rating gap, title, era), so a referee is not blamed for refereeing finishers.', 'Os valores esperados vêm de um modelo com os lutadores de cada luta (tendência a finalizar, diferença de nota, cinturão, era), então um árbitro não é culpado por apitar finalizadores.')}</p>
     <div class="card" style="padding:.4rem .9rem;overflow-x:auto"><div class="tb hd" style="min-width:38rem;grid-template-columns:1.5fr .5fr 1.2fr .8fr .8fr 1.3fr"><span>${T('Referee', 'Árbitro')}</span><span>${T('Fights', 'Lutas')}</span><span>${T('Finish: real / expected', 'Finaliz.: real / esperado')}</span><span>KO</span><span>Sub</span><span>${T('Stoppage timing', 'Hora da parada')}</span></div>
     ${rr.map(([n, v]) => `<div class="tb" style="min-width:38rem;grid-template-columns:1.5fr .5fr 1.2fr .8fr .8fr 1.3fr"><span>${esc(n)}</span><span>${v.n}</span><span>${p0(v.fin)} / ${p0(v.fine)} ${zc(v.finz)}</span><span>${zc(v.koz)}</span><span>${zc(v.subz)}</span><span>${v.sz == null ? '<span class="mu">—</span>' : `${v.sz < -3.3 ? T('early', 'precoce') : v.sz > 3.3 ? T('late', 'tardia') : ''} ${zc(v.sz)} <span class="mu sm">(${v.sn})</span>`}</span></div>`).join('')}</div>
     <p class="mu sm">${T('Stoppage timing compares how many significant strikes the losing fighter absorbed before a TKO stoppage with other stoppages in the same round. Negative = stops earlier than usual, positive = later. It is a proxy: fighter style also matters.', 'A hora da parada compara quantos golpes significativos o perdedor absorveu antes de uma parada por TKO com outras paradas no mesmo round. Negativo = para mais cedo que o normal, positivo = mais tarde. É uma aproximação: o estilo dos lutadores também pesa.')}</p>`;
    return h;
  }

  /* ================= 8) ACADEMIAS ================= */
  function tCp() {
    const C = X.d.camps; if (!C) return miss('camps');
    const k = X.cs, rows = Object.values(C.teams).filter(t => k === 'dw' ? t.dw != null : k === 'elo' ? t.elo != null : true).sort((a, b) => k === 'elo' ? b.elo - a.elo : k === 'dw' ? b.dw - a.dw : k === 'tw' ? b.tw - a.tw || b.tf - a.tf : k === 'ch' ? b.ch - a.ch || b.tw - a.tw : b.nf - a.nf).slice(0, 30);
    const bt = (v, l) => `<button data-xcs="${v}" class="pk${k === v ? ' on' : ''}">${l}</button>`;
    let h = `<p class="mu sm">${T('Training camps ranked by their current strength and by how their fighters did when the rating system knew nothing about them.', 'Academias ranqueadas pela força atual e por como seus lutadores foram quando o sistema de notas ainda não sabia nada sobre eles.')}</p>
     <div class="card" style="padding:.6rem 1.1rem"><p class="mu sm">${T('Coverage', 'Cobertura')}: <b>${C.coverage[0]}</b> ${T('of', 'de')} ${C.coverage[1]} ${T('fighters have a gym on record (it comes from ESPN, so some are missing). The gym is the CURRENT one, applied to the whole career.', 'lutadores têm academia registrada (vem da ESPN, então alguns faltam). A academia é a ATUAL, aplicada à carreira inteira.')}</p></div>
     <div class="acts">${bt('elo', T('Current strength', 'Força atual'))}${bt('dw', T('Debut performance', 'Desempenho na estreia'))}${bt('tw', T('Titles', 'Cinturões'))}${bt('ch', T('Champions', 'Campeões'))}${bt('nf', T('Size', 'Tamanho'))}</div>
     <div class="card" style="padding:.4rem .9rem;overflow-x:auto"><div class="tb hd" style="min-width:40rem;grid-template-columns:1.7fr .7fr .8fr 1.3fr .9fr .9fr"><span>${T('Gym', 'Academia')}</span><span>${T('Active/total', 'Ativos/total')}</span><span>${T('Mean ELO', 'ELO médio')}</span><span>${T('First 3 fights vs expected', '3 primeiras lutas vs esperado')}</span><span>${T('Title wins/fights', 'Vitórias/lutas de cinturão')}</span><span>${T('Champions', 'Campeões')}</span></div>
     ${rows.map(t => `<div class="tb" style="min-width:40rem;grid-template-columns:1.7fr .7fr .8fr 1.3fr .9fr .9fr"><span><b>${esc(t.name)}</b><br><span class="mu sm">${(t.top || []).map(i => esc(nm(i))).join(', ')}</span></span><span>${t.act}/${t.nf}</span><span>${t.elo == null ? '—' : Math.round(t.elo)}</span><span>${t.dw == null ? '<span class="mu">—</span>' : `<span class="${Math.abs(t.dw) > t.ds ? (t.dw > 0 ? 'up' : 'dn') : 'mu'}">${t.dw > 0 ? '+' : ''}${t.dw.toFixed(1)}</span> <span class="mu sm">±${t.ds.toFixed(1)} (${t.dn})</span>`}</span><span>${t.tw}/${t.tf}</span><span>${t.ch}</span></div>`).join('')}</div>
     <p class="mu sm">${T('First 3 fights vs expected = points above what the rating system expected, per 100 fights, centered on the league. A colored value is outside the margin of error. This is the honest measure of a gym: in later fights the rating has already learned the fighter, so the gap tends to vanish. Small gyms are noisy: read the ± and the n.', '3 primeiras lutas vs esperado = pontos acima do que o sistema de notas esperava, por 100 lutas, centrado na liga. Valor colorido = fora da margem de erro. É a medida honesta de uma academia: nas lutas seguintes a nota já aprendeu o lutador, então a diferença tende a sumir. Academias pequenas são ruidosas: leia o ± e o n.')}</p>`;
    return h;
  }

  /* ================= imagens para compartilhar ================= */
  function shareImg(kind) {
    const cv = document.createElement('canvas'), W = 1080; cv.width = W; const F = '"Big Shoulders Display",Impact,"Arial Narrow",sans-serif', B = 'Archivo,Arial,sans-serif';
    let lines = [], title = '', sub = '';
    if (kind === 'sc') { title = nm(X.sc); lines = (scout(X.sc) || []).map(t => t.replace(/<[^>]+>/g, '')); sub = 'SCOUTING'; }
    else { title = T('Dream card', 'Card dos sonhos'); sub = T('Fight of the Night chance', 'Chance de Fight of the Night'); lines = X.cd.map(o => ({ o, r: fotn(o.a, o.b, o.t) })).sort((a, b) => (b.r ? b.r.p : -1) - (a.r ? a.r.p : -1)).map((e, i) => `${i + 1}. ${nm(e.o.a)} x ${nm(e.o.b)}${e.o.t ? ' (' + T('title', 'cinturão') + ')' : ''}: ${e.r ? p1(e.r.p) : '—'}`); }
    const x0 = cv.getContext('2d'); x0.font = `500 38px ${B}`;
    const wrap = (t, x, mw) => { const w = t.split(/\s+/), o = []; let cur = ''; for (const s of w) { const n = cur ? cur + ' ' + s : s; if (x.measureText(n).width > mw && cur) { o.push(cur); cur = s; } else cur = n; } if (cur) o.push(cur); return o; };
    const rows = lines.flatMap(l => wrap(l, x0, 920).concat(['']));
    cv.height = 300 + rows.length * 52 + 120; const x = cv.getContext('2d');
    x.fillStyle = '#090a0d'; x.fillRect(0, 0, W, cv.height); x.strokeStyle = '#f5c518'; x.lineWidth = 8; x.strokeRect(24, 24, W - 48, cv.height - 48);
    x.fillStyle = '#f5c518'; x.font = `900 50px ${F}`; x.fillText('SÚMULA UFC', 70, 120); x.fillStyle = '#8b94a5'; x.font = `800 36px ${F}`; x.fillText(sub, 70, 175);
    x.fillStyle = '#eef1f6'; x.font = `900 84px ${F}`; x.fillText(title.toUpperCase().slice(0, 28), 70, 270);
    x.font = `500 38px ${B}`; x.fillStyle = '#eef1f6'; rows.forEach((t, i) => x.fillText(t, 80, 340 + i * 52));
    cv.toBlob(b => { const f = new File([b], 'sumula.png', { type: 'image/png' }); if (navigator.canShare && navigator.canShare({ files: [f] })) navigator.share({ files: [f] }).catch(() => { }); else { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = f.name; a.click(); } });
  }

  /* ================= tela e rota ================= */
  const VIEW = { dna: tDna, vg: tVg, mkt: tMkt, mm: tMm, jg: tJg, sc: tSc, cd: tCd, sy: tSy, pp: tPp, of: tOf, cp: tCp };
  const DATA = { dna: ['analytics', 'cards', 'styles', 'market'], vg: ['market', 'analytics'], mkt: ['market'], mm: ['analytics', 'cards', 'excitement'], jg: ['decisions'], sc: ['analytics', 'cards', 'styles'], cd: ['excitement'], sy: ['styles'], pp: ['prospects'], of: ['judges'], cp: ['camps'] };
  async function draw() {
    const el = document.querySelector('#xx'); if (!el) return;
    await need(DATA[X.tab]); if (!document.querySelector('#xx')) return;
    el.innerHTML = `<div class="seg">${TABS().map(([k, l]) => `<button data-xt="${k}" class="${X.tab === k ? 'on' : ''}">${l}</button>`).join('')}</div>` + (['sc', 'cd', 'sy', 'pp', 'cp'].includes(X.tab) ? `<div class="xrow"><span class="xbar" data-xk="x:${X.tab}"></span></div>` : '') + VIEW[X.tab]() + `<p class="mu sm" style="margin-top:1rem">${T('Everything here is exploratory and validated on past data: patterns are hypotheses, not proof.', 'Tudo aqui é exploratório e validado em dados passados: padrões são hipóteses, não provas.')}</p>`;
    const m = document.querySelector('#m');
    m.onclick = e => {
      const t = e.target.closest('[data-xt],[data-xp],[data-xc],[data-xj],[data-xjr],[data-xjn],[data-xsh],[data-xad],[data-xrm],[data-xos],[data-xor],[data-xcs],[data-xdm],[data-xdsh],[data-xmm],[data-xvg],[data-xvgr],[data-xvgn],[data-xms]'); if (!t) return; const d = t.dataset;
      if (d.xt) { X.tab = d.xt; draw(); }
      else if (d.xp) { const [k, id] = d.xp.split(':'); if (k === 'dna') dnaGuess(id); else X[k] = id; draw(); }
      else if (d.xc) { X[d.xc] = ''; draw(); }
      else if (d.xdm) { dnaInit(d.xdm); draw(); }
      else if (d.xdsh) {
        const D = X.dna, txt = `Súmula UFC — DNA Secreto (${D.date}) 🧬 ${D.won ? D.gs.length : 'X'}/6\n` + D.gs.map(g => g === D.target ? '🟩🟩🟩🟩🟩' : '⬛🟨⬛⬛⬛').join('\n');
        if (navigator.clipboard) navigator.clipboard.writeText(txt).then(() => alert(T('Result copied!', 'Resultado copiado!')));
      }
      else if (d.xvg) {
        const [idx, side, stk] = d.xvg.split(':');
        X.vg.bets[+idx] = { side, stake: +stk };
        draw();
      }
      else if (d.xvgr) { X.vg.rev = true; draw(); }
      else if (d.xvgn) { vgNew(); draw(); }
      else if (d.xms) { X.ms = d.xms; draw(); }
      else if (d.xmm) {
        const M = X.mm, act = d.xmm;
        if (act === 'reset') mmInit();
        else if (act === 'sim') mmSim();
        else if (act.startsWith('rm:')) { M.bouts.splice(+act.slice(3), 1); M.res = null; }
        else if (act.startsWith('pick:')) {
          const pid = act.slice(5);
          if (M.pickA === pid) M.pickA = '';
          else if (!M.pickA) M.pickA = pid;
          else {
            const f1 = M.pool.find(x => x.id === M.pickA), f2 = M.pool.find(x => x.id === pid);
            if (f1 && f2 && f1.div === f2.div && M.bouts.length < 5) {
              M.bouts.push({ a: f1.id, b: f2.id, div: f1.div });
              M.pickA = ''; M.res = null;
            }
          }
        }
        draw();
      }
      else if (d.xj) { const [i, v] = d.xj.split(':'); X.jg.sc[+i] = +v; draw(); } else if (d.xjr) { X.jg.rev = true; draw(); } else if (d.xjn) { jNew(); draw(); }
      else if (d.xsh) shareImg(d.xsh); else if (d.xad != null) { X.cd.push({ a: mid(X.ca), b: mid(X.cb), t: d.xad === '1' }); X.ca = X.cb = ''; draw(); }
      else if (d.xos) { X.os = d.xos; draw(); } else if (d.xor) { X.or = d.xor; draw(); } else if (d.xcs) { X.cs = d.xcs; draw(); }
      else if (d.xrm) { const [a, b] = d.xrm.split(':'); X.cd = X.cd.filter(o => !(o.a === a && o.b === b)); draw(); }
    };
    m.oninput = e => {
      const q = e.target.closest('[data-xq]');
      if (q) { const k = q.dataset.xq, t = q.value.toLowerCase().trim(), r = document.querySelector('#xs' + k); const cards = (X.d.cards || {}).cards, exf = (X.d.excitement || {}).fighters, an = (X.d.analytics || {}).fighters;
        const ok = f => k === 'ca' || k === 'cb' ? (exf ? exf[f.id] : true) : k === 'sc' ? (an ? an[f.id] : true) : k === 'dna' ? (cards && an ? cards[f.id] && an[f.id] && !X.dna.gs.includes(f.id) : true) : k === 'sy' ? (X.d.styles ? X.d.styles.fighters[f.id] != null : true) : true;
        if (r) r.innerHTML = t ? [...S.F.values()].filter(f => ok(f) && (f.name + ' ' + (f.nick || '')).toLowerCase().includes(t)).slice(0, 6).map(f => `<button data-xp="${k}:${f.id}"><span>${esc(f.name)}</span><span class="mu">${esc(f.record || '')}</span></button>`).join('') : ''; return; }
      const pp = e.target.closest('[data-xpp]'); if (pp) { X.pp = Math.max(2, Math.min(6, +pp.value || 2)); draw(); }
    };
  }
  async function view() { document.querySelector('#m').innerHTML = `<h1>${T('Games & Extras', 'Games & Extras')}</h1><div id="xx"><p class="mu">${T('Loading…', 'Carregando…')}</p></div>`; await draw(); }

  /* ================= MMA MATH: menor cadeia de vitórias (BFS) ================= */
  const XM = { fast: false, a: '', b: '', G: {} };
  const isFin = m => /^(ko|tko|sub)/i.test(m || '');
  function graph(fast) {
    const key = fast ? 'f' : 'a', c = XM.G[key]; if (c && c.n === S.fg.length) return c.g;
    const g = new Map();
    for (const f of S.fg) {
      if (f.res !== 'a' && f.res !== 'b') continue; if (fast && !isFin(f.method)) continue;
      const w = mid((f.res === 'a' ? f.a : f.b).id), l = mid((f.res === 'a' ? f.b : f.a).id); if (w === l) continue;
      if (!g.has(w)) g.set(w, new Map()); const m = g.get(w), old = m.get(l); if (!old || f.date > old.date) m.set(l, f);   /* várias lutas entre o mesmo par: fica a mais recente */
    }
    XM.G[key] = { n: S.fg.length, g }; return g;
  }
  function chain(a, b, fast) {
    const g = graph(fast), dist = new Map([[a, 0]]), preds = new Map(); let fr = [a], found = false;
    for (let d = 0; d < 8 && fr.length && !found; d++) {
      const nx = [];
      for (const u of fr) for (const [v, f] of g.get(u) || []) { if (!dist.has(v)) { dist.set(v, d + 1); preds.set(v, [[u, f]]); nx.push(v); if (v === b) found = true; } else if (dist.get(v) === d + 1) preds.get(v).push([u, f]); }
      fr = nx;
    }
    if (!dist.has(b)) return null;
    const out = []; const walk = (v, tail) => { if (out.length >= 3) return; if (v === a) { out.push(tail); return; } for (const [u, f] of preds.get(v)) walk(u, [[u, v, f], ...tail]); };
    walk(b, []); return { len: dist.get(b), paths: out };
  }
  function inner() {
    const a = XM.a, b = XM.b, direct = S.fg.filter(f => (mid(f.a.id) === a && mid(f.b.id) === b) || (mid(f.a.id) === b && mid(f.b.id) === a));
    const mt = f => `${esc(f.method || '')}${f.round ? ', R' + esc(f.round) : ''}, ${esc((f.date || '').slice(0, 4))}`;
    const dir = (x, y) => {
      const r = chain(x, y, XM.fast);
      if (!r) return `<p class="mu sm">${esc(nm(x))} → ${esc(nm(y))}: ${T('no chain of wins within 8 steps' + (XM.fast ? ' (try turning off the finishes-only filter)' : ''), 'nenhuma cadeia de vitórias em até 8 passos' + (XM.fast ? ' (tente desligar o filtro de finalizações)' : ''))}.</p>`;
      return `<p><b>${esc(nm(x))} → ${esc(nm(y))}</b> <span class="mu sm">(${r.len} ${r.len === 1 ? T('step', 'passo') : T('steps', 'passos')}${r.paths.length > 1 ? ', ' + r.paths.length + ' ' + T('shortest routes shown', 'rotas mais curtas mostradas') : ''})</span></p>` + r.paths.map(p => `<div class="card" style="padding:.5rem .9rem;margin-bottom:.4rem">${p.map(([u, v, f]) => `<div class="sr" style="grid-template-columns:1fr auto 1fr"><span>${esc(nm(u))}</span><span class="lb">${T('beat', 'venceu')}</span><span>${esc(nm(v))}</span></div><div class="mu sm" style="text-align:center">${mt(f)}</div>`).join('')}</div>`).join('');
    };
    return `${direct.length ? `<p>${T('They have fought', 'Eles já lutaram')}: ${direct.map(f => `${esc(nm(mid((f.res === 'a' ? f.a : f.b).id)))} ${f.res === 'draw' ? '=' : T('won', 'venceu')} (${mt(f)})`).join('; ')}.</p>` : dir(a, b) + dir(b, a)}
     <p class="mu sm">${T('A chain of wins is not a prediction: styles, weight changes and years pass between the links. It is a conversation starter.', 'Uma cadeia de vitórias não é uma previsão: estilos, mudanças de peso e anos passam entre os elos. É um assunto de bar.')}</p>`;
  }
  XM.html = (a, b) => { a = a && mid(a); b = b && mid(b); if (!a || !b || a === b || !S.fg || !S.fg.length) return ''; XM.a = a; XM.b = b; return `<div class="card" style="padding:.8rem 1.1rem;margin-top:.8rem" id="xm"><b>MMA Math</b> <span class="mu sm">${T('shortest chain of wins between them', 'menor cadeia de vitórias entre eles')}</span>
     <div class="acts"><button id="xmf" class="pk${XM.fast ? ' on' : ''}" onclick="XM.tog()">${T('Finishes only (fast routes)', 'Só finalizações (vias rápidas)')}</button></div><div id="xmb">${inner()}</div></div>`; };
  XM.tog = () => { XM.fast = !XM.fast; const b = document.querySelector('#xmb'), bt = document.querySelector('#xmf'); if (b) b.innerHTML = inner(); if (bt) bt.classList.toggle('on', XM.fast); };
  XM.chain = chain;
  window.XM = XM;

  /* ---------- exportação (window.XEXP, definido no index.html): PNG, CSV e texto com TODAS as linhas ---------- */
  if (window.XEXP) {
    const R = window.XEXP.reg, sl = window.XEXP.slug, f1 = v => v == null ? '—' : (+v).toFixed(1);
    R('x:sc', () => { if (!X.sc) return null; const r = scout(X.sc); return r ? { kind: 'text', title: nm(X.sc), sub: 'Scouting', file: 'scouting-' + sl(nm(X.sc)), lines: r.map(t => t.replace(/<[^>]+>/g, '')) } : null; });
    R('x:cd', () => {
      const rows = X.cd.map(o => ({ o, r: fotn(o.a, o.b, o.t) })).sort((a, b) => (b.r ? b.r.p : -1) - (a.r ? a.r.p : -1)), tot = rows.reduce((s, x) => s + (x.r ? x.r.p : 0), 0);
      return { kind: 'table', title: T('Dream card', 'Card dos sonhos'), file: 'card-dos-sonhos', sub: `${T('Chance of Fight of the Night', 'Chance de Fight of the Night')} · ${T('expected on this card', 'esperadas neste card')}: ${tot.toFixed(2)}`,
        cols: ['#', T('Fight', 'Luta'), T('Title', 'Cinturão'), T('FOTN chance', 'Chance de FOTN'), T('Balance', 'Equilíbrio'), T('Finish tendency', 'Tendência a finalizar'), T('Pace (x league)', 'Ritmo (x liga)')],
        rows: rows.map((x, i) => [i + 1, `${nm(x.o.a)} x ${nm(x.o.b)}`, x.o.t ? T('yes', 'sim') : '', x.r ? p1(x.r.p) : '—', x.r ? p0(x.r.bal) : '—', x.r ? p0(x.r.fin) : '—', x.r ? x.r.pace.toFixed(2) : '—']) };
    });
    R('x:sy', () => { const s = X.d.styles; if (!s) return null; return { kind: 'table', title: T('Style matrix', 'Matriz de estilos'), file: 'matriz-de-estilos', sub: T('Points per 100 fights the ROW style beats the COLUMN style above Elo expectation', 'Pontos por 100 lutas que o estilo da LINHA vence o da COLUNA acima do esperado pelo Elo'),
      cols: [T('Style (row)', 'Estilo (linha)'), T('Style (column)', 'Estilo (coluna)'), T('Excess (pp)', 'Excesso (pp)'), '±', T('Fights', 'Lutas')],
      rows: Object.entries(s.matrix).map(([k, v]) => { const [i, j] = k.split(','); return [styName(i), styName(j), f1(v[1]), f1(v[2]), v[0]]; }).sort((a, b) => Math.abs(b[2]) - Math.abs(a[2])) }; });
    R('x:pp', () => { const P = X.d.prospects; if (!P) return null; const rows = Object.entries(P.fighters).sort((a, b) => b[1][1] - a[1][1] || (b[1][5] || 0) - (a[1][5] || 0)), mx = rows.length ? rows[0][1][1] || 1 : 1;
      return { kind: 'rank', title: T('Prospects', 'Prospectos'), file: 'prospectos', sub: `${T('Chance of becoming elite', 'Chance de virar elite')} · ${T('base rate', 'taxa-base')} ${p1(P.base_elite)} · ${T('skill over base rate', 'ganho sobre a taxa-base')} ${P.validation.skill >= 0 ? '+' : ''}${P.validation.skill}`,
        rank: rows.slice(0, 60).map(([i, v], k) => ({ pos: k + 1, name: nm(i), sub: `${v[0]} ${T('fights', 'lutas')} · ${T('looks like', 'parece com')} ${(v[7] || []).slice(0, 2).map(nm).join(', ')}`, val: p0(v[1]), pct: v[1] / mx })),
        cols: [T('Fighter', 'Lutador'), T('Fights', 'Lutas'), T('Chance of elite', 'Chance de elite'), T('8+ fights', '8+ lutas'), T('4+ fights', '4+ lutas'), 'Perf q10', 'Perf q50', 'Perf q90', T('Looks like', 'Parece com')],
        rows: rows.map(([i, v]) => [nm(i), v[0], p1(v[1]), p0(v[2]), p0(v[3]), v[4] ?? '', v[5] ?? '', v[6] ?? '', (v[7] || []).map(nm).join('; ')]) }; });
    R('x:cp', () => { const C = X.d.camps; if (!C) return null; const k = X.cs, rows = Object.values(C.teams).sort((a, b) => k === 'elo' ? (b.elo || 0) - (a.elo || 0) : k === 'dw' ? (b.dw ?? -99) - (a.dw ?? -99) : k === 'tw' ? b.tw - a.tw : k === 'ch' ? b.ch - a.ch : b.nf - a.nf);
      return { kind: 'table', title: T('Gym ranking', 'Ranking de academias'), file: 'academias', sub: `${T('Coverage', 'Cobertura')}: ${C.coverage[0]}/${C.coverage[1]} ${T('fighters', 'lutadores')}`,
        cols: [T('Gym', 'Academia'), T('Fighters', 'Lutadores'), T('Active', 'Ativos'), T('Mean ELO', 'ELO médio'), T('First 3 fights vs expected (pp)', '3 primeiras lutas vs esperado (pp)'), '±', T('Title wins', 'Vitórias de cinturão'), T('Title fights', 'Lutas de cinturão'), T('Champions', 'Campeões')],
        rows: rows.map(t => [t.name, t.nf, t.act, t.elo == null ? '—' : Math.round(t.elo), f1(t.dw), f1(t.ds), t.tw, t.tf, t.ch]) }; });
    R('x:of-j', () => { const D = X.d.judges; if (!D) return null; return { kind: 'table', title: T('Judges: dissent and robbery index', 'Juízes: dissidência e roubos'), file: 'juizes', sub: `${T('League dissent rate', 'Dissidência da liga')} ${p1(D.league.dis)} · ${D.league.cards} ${T('cards', 'cartões')}`,
      cols: [T('Judge', 'Juiz'), T('Cards', 'Cartões'), T('Dissent (shrunk)', 'Dissidência (ajustada)'), 'z', T('Splits judged', 'Divididas julgadas'), T('Dissents in splits', 'Dissidências nas divididas'), T('Questionable cards', 'Cartões questionáveis'), T('Agreeing with official winner', 'A favor do vencedor oficial'), 'z'],
      rows: Object.entries(D.judges).sort((a, b) => b[1].rs - a[1].rs).map(([n, v]) => [n, v.n, p1(v.rs), f1(v.z), v.sp, v.spd, v.c2, v.c2f, f1(v.c2z)]) }; });
    R('x:of-r', () => { const D = X.d.judges; if (!D) return null; return { kind: 'table', title: T('Referees: finishes and stoppage timing', 'Árbitros: finalizações e hora da parada'), file: 'arbitros', sub: `${T('League finish rate', 'Taxa de finalização da liga')} ${p1(D.league.fin)}`,
      cols: [T('Referee', 'Árbitro'), T('Fights', 'Lutas'), T('Finish %', 'Finalização %'), T('Expected %', 'Esperado %'), 'z', 'KO z', 'Sub z', T('Stoppage index', 'Índice da parada'), 'z', 'n'],
      rows: Object.entries(D.refs).sort((a, b) => Math.abs(b[1].finz) - Math.abs(a[1].finz)).map(([n, v]) => [n, v.n, p1(v.fin), p1(v.fine), f1(v.finz), f1(v.koz), f1(v.subz), v.si == null ? '—' : v.si, f1(v.sz), v.sn]) }; });
  }
  const pT = window.XT, pV = window.XV;
  window.XT = () => [...(pT ? pT() : []), ['extras', 'Extras']];
  window.XV = { ...(pV || {}), extras: view };
})();
