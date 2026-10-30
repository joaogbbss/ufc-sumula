/* extras.js: aba "Extras" com seis seções. Módulo acoplável: se o arquivo for removido, o app continua igual.
   1 Mercado (modelo x odds)  2 Seja o juiz  3 Scouting  4 Card dos sonhos  5 Estilos  6 Prospectos
   Lê os arquivos gerados pelo extras.py (market, excitement, styles, prospects) e, quando existem, decisions, analytics e cards.
   Todo resultado traz validação e tamanho de amostra; onde um modelo não prevê além do acaso, a tela diz isso. */
(function () {
  'use strict';
  const X = { tab: 'mkt', d: {}, jg: { f: null, sc: [], rev: false }, sc: '', cd: [], ca: '', cb: '', sy: '', pp: 2 };
  const sum = a => a.reduce((x, y) => x + y, 0), p0 = v => (v * 100).toFixed(0) + '%', p1 = v => (v * 100).toFixed(1) + '%';
  const nm = id => (S.F.get(id) || {}).name || id, fm = () => X._fm || (X._fm = new Map(S.fg.map(f => [f.id, f])));
  const sg = z => 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z))));
  const erf = x => { const s = Math.sign(x); x = Math.abs(x); const t = 1 / (1 + .3275911 * x); return s * (1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - .284496736) * t + .254829592) * t * Math.exp(-x * x)); };
  const pval = z => 2 * (1 - .5 * (1 + erf(Math.abs(z) / Math.SQRT2)));
  const llf = (p, y) => -Math.log(Math.max(y ? p : 1 - p, 1e-6));

  /* ---------- carga sob demanda ---------- */
  async function need(names) {
    const g = async n => { if (n in X.d) return; try { const r = await fetch('data/' + n + '.json', { cache: 'no-cache' }); X.d[n] = r.ok ? await r.json() : null; } catch { X.d[n] = null; } };
    await Promise.all(names.map(g));
  }
  const TABS = () => [['mkt', T('Market', 'Mercado')], ['jg', T('Be the judge', 'Seja o juiz')], ['sc', 'Scouting'], ['cd', T('Dream card', 'Card dos sonhos')], ['sy', T('Styles', 'Estilos')], ['pp', T('Prospects', 'Prospectos')]];
  const miss = f => `<p class="empty">${T('File ' + f + '.json not found. Run the workflow so the scripts generate it (extras.py needs analytics.py to run before it).', 'Arquivo ' + f + '.json não encontrado. Rode o workflow para os scripts gerarem (o extras.py precisa que o analytics.py rode antes).')}</p>`;
  const slot = (k, lbl) => { const id = X[k], p = S.F.get(id); return `<div class="card" style="padding:.8rem 1rem"><div class="mu sm">${lbl}</div>${p ? `<div class="sel">${typeof av === 'function' ? av(id, p.name, 'sm') : ''}<b>${esc(p.name)}</b><button data-xc="${k}">×</button></div>` : `<input data-xq="${k}" type="search" placeholder="${T('Search a fighter…', 'Buscar lutador…')}"><div class="res" id="xs${k}"></div>`}</div>`; };

  /* ================= 1) MERCADO ================= */
  const slope1 = pairs => { let c = Math.LN10; if (pairs.length < 100) return c; for (let i = 0; i < 14; i++) { let g = 0, h = 0; for (const [x, y] of pairs) { const p = sg(c * x); g += (y - p) * x; h += p * (1 - p) * x * x; } if (!h) break; const d = g / h; c += d; if (Math.abs(d) < 1e-6) break; } return c; };
  function mktEval() {
    const H = (X.d.market && X.d.market.hist) || {}, all = pre().rows.filter(r => r.nx >= 3 && r.ny >= 3), rows = all.filter(r => H[r.fid]);
    if (rows.length < 30) return { n: rows.length };
    const cal = {}; for (const y of new Set(rows.map(r => r.date.slice(0, 4)))) cal[y] = slope1(all.filter(r => r.date < y + '-01-01').map(r => [r.x[0], r.y]));   /* calibrado SÓ com o passado */
    const M = [], K = [], Y = [], F = fm();
    for (const r of rows) { const h = H[r.fid], f = F.get(r.fid); if (!f) continue; K.push(mid(f.a.id) === r.ix ? h[0] : h[1]); M.push(sg(cal[r.date.slice(0, 4)] * r.x[0])); Y.push(r.y); }
    const n = Y.length, met = P => ({ ll: sum(P.map((p, i) => llf(p, Y[i]))) / n, br: sum(P.map((p, i) => (p - Y[i]) ** 2)) / n, ac: P.filter((p, i) => (p > .5) === (Y[i] === 1)).length / n });
    const d = M.map((p, i) => llf(p, Y[i]) - llf(K[i], Y[i])), md = sum(d) / n, se = Math.sqrt(sum(d.map(v => (v - md) ** 2)) / (n - 1) / n);
    const dis = []; M.forEach((p, i) => { if (Math.abs(p - K[i]) >= .08) { const x = p > K[i]; dis.push({ pm: x ? K[i] : 1 - K[i], y: x ? Y[i] : 1 - Y[i] }); } });
    const dz = dis.length ? sum(dis.map(o => o.y - o.pm)) / Math.sqrt(sum(dis.map(o => o.pm * (1 - o.pm)))) : 0;
    const src = Object.values(H).reduce((a, h) => (a[h[3]] = (a[h[3]] || 0) + 1, a), {});
    return { n, model: met(M), mkt: met(K), md, z: se ? md / se : 0, dis: dis.length, dz, dwin: dis.length ? sum(dis.map(o => o.y)) / dis.length : 0, dexp: dis.length ? sum(dis.map(o => o.pm)) / dis.length : 0, src };
  }
  function tMkt() {
    const E = mktEval(); let h = `<p class="mu sm">${T('The honest test of a model: does it keep up with the betting market? Probabilities are compared on fights that already happened. This is information, not a betting tip.', 'O teste honesto de um modelo: ele acompanha o mercado de apostas? As probabilidades são comparadas em lutas que já aconteceram. É informação, não dica de aposta.')}</p>`;
    if (E.n < 30) h += `<p class="empty">${T(`Only ${E.n} fights with historical odds. The log starts when the workflow runs with odds for upcoming events; for history right away, import a CSV once: python extras.py --odds-csv file.csv`, `Só ${E.n} lutas com odds históricas. O registro começa quando o workflow roda com odds dos próximos eventos; para ter histórico já, importe um CSV uma vez: python extras.py --odds-csv arquivo.csv`)}</p>`;
    else {
      const m = E.model, k = E.mkt, better = Math.abs(E.z) < 2 ? T('No measurable difference between the model and the market.', 'Sem diferença mensurável entre o modelo e o mercado.') : E.md < 0 ? T('The model is measurably better than the market on these fights.', 'O modelo é mensuravelmente melhor que o mercado nestas lutas.') : T('The market is measurably better than the model: it knows things the model does not (injuries, camp, styles).', 'O mercado é mensuravelmente melhor que o modelo: ele sabe coisas que o modelo não sabe (lesões, preparação, estilos).');
      h += `<div class="card" style="padding:.8rem 1.1rem"><b>${better}</b><div class="tb hd" style="margin-top:.6rem"><span></span><span>${T('Accuracy', 'Acerto')}</span><span>Log-loss</span><span>Brier</span></div>
       <div class="tb"><span>${T('Model (Elo, past only)', 'Modelo (Elo, só passado)')}</span><span>${p1(m.ac)}</span><span>${m.ll.toFixed(3)}</span><span>${m.br.toFixed(3)}</span></div><div class="tb"><span>${T('Market (no vig)', 'Mercado (sem margem)')}</span><span>${p1(k.ac)}</span><span>${k.ll.toFixed(3)}</span><span>${k.br.toFixed(3)}</span></div>
       <p class="mu sm">${E.n.toLocaleString(S.pt ? 'pt-BR' : 'en-US')} ${T('fights', 'lutas')} (${Object.entries(E.src).map(([a, b]) => a + ' ' + b).join(', ')}). ${T('Log-loss difference (model − market)', 'Diferença de log-loss (modelo − mercado)')}: ${E.md >= 0 ? '+' : ''}${E.md.toFixed(4)}, z = ${E.z.toFixed(1)}. ${T('The Elo is recalibrated each year using only earlier fights.', 'O Elo é recalibrado a cada ano usando só lutas anteriores.')}</p></div>
       <div class="card" style="padding:.8rem 1.1rem"><b>${T('When the model disagrees with the market (8+ points)', 'Quando o modelo discorda do mercado (8+ pontos)')}</b><p>${E.dis} ${T('fights', 'lutas')}. ${T('The side the model liked more won', 'O lado que o modelo preferia venceu')} <b>${p0(E.dwin)}</b> ${T('of the time; the market implied', 'das vezes; o mercado indicava')} <b>${p0(E.dexp)}</b>. ${Math.abs(E.dz) < 2 ? T('The disagreements carry no extra information (z = ' + E.dz.toFixed(1) + '): when they differ, trust the market.', 'As discordâncias não trazem informação extra (z = ' + E.dz.toFixed(1) + '): quando divergem, confie no mercado.') : E.dz > 0 ? T('The disagreements were informative (z = ' + E.dz.toFixed(1) + ').', 'As discordâncias foram informativas (z = ' + E.dz.toFixed(1) + ').') : T('The disagreements were WRONG more often than the market (z = ' + E.dz.toFixed(1) + ').', 'As discordâncias erraram MAIS que o mercado (z = ' + E.dz.toFixed(1) + ').')}</p></div>`;
    }
    const ups = (S.up || []).flatMap(e => (e.fights || []).filter(f => f.mkt_pa != null).map(f => ({ e, f })));
    h += `<h2>${T('Upcoming fights: model x market', 'Próximas lutas: modelo x mercado')}</h2>` + (ups.length ? ups.map(({ e, f }) => {
      const ia = mid(f.a.id), ib = mid(f.b.id), pr = typeof probs === 'function' ? probs(ia, ib) : null, pm = pr ? ({ Elo: pr.pE, WHR: pr.pW, Stats: pr.pS, Blend: pr.pB })[pr.best] : null, d = pm == null ? null : pm - f.mkt_pa;
      return `<div class="card" style="padding:.7rem 1.1rem"><div class="sr"><b style="color:var(--gd)">${esc(f.a.name || nm(ia))}</b><span class="mu sm">${esc(e.name || '')}</span><b style="color:var(--cb)">${esc(f.b.name || nm(ib))}</b></div>
       <div class="sr"><span>${T('Market', 'Mercado')} ${p0(f.mkt_pa)}</span><span></span><span>${p0(1 - f.mkt_pa)}</span></div>${pm == null ? `<p class="mu sm">${T('No model rating for one of them.', 'Sem nota do modelo para um deles.')}</p>` : `<div class="sr"><span>${T('Model', 'Modelo')} ${p0(pm)}</span><span class="lb ${Math.abs(d) >= .08 ? 'dn' : 'mu'}">${d >= 0 ? '+' : ''}${(d * 100).toFixed(0)} pp</span><span>${p0(1 - pm)}</span></div>`}</div>`;
    }).join('') : `<p class="mu sm">${T('No upcoming fight with market odds yet.', 'Nenhuma próxima luta com odds de mercado ainda.')}</p>`);
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
    const r = Object.entries(P.fighters).filter(([i, v]) => v[0] >= X.pp).sort((a, b) => b[1][1] - a[1][1]).slice(0, 30);
    h += r.length ? r.map(([i, v], k) => `<div class="card" style="padding:.7rem 1.1rem"><div class="sr" style="grid-template-columns:1.5rem 1fr auto"><b>${k + 1}</b><span><a href="#/fighter/${i}"><b>${esc(nm(i))}</b></a> <span class="mu sm">${v[0]} ${T('fights', 'lutas')}</span></span><b style="color:var(--gd)">${p0(v[1])}</b></div>
      <div class="xg"><span>${T('chance of elite', 'chance de elite')} <b>${p1(v[1])}</b> (${T('base', 'base')} ${p1(P.base_elite)})</span><span>${T('stays 4+ fights', 'chega a 4+ lutas')} <b>${p0(v[3])}</b></span><span>8+ ${T('fights', 'lutas')} <b>${p0(v[2])}</b></span>${v[5] != null ? `<span>${T('later perf.', 'desempenho posterior')} <b>${v[5]}–${v[7]}</b> (${T('median', 'mediana')} ${v[6]})</span>` : ''}</div>
      <p class="mu sm">${T('Looks like', 'Parece com')}: ${(v[8] || []).map(a => esc(nm(a))).join(', ')}</p></div>`).join('') : `<p class="empty">${T('No prospect with these filters.', 'Nenhum prospecto com esses filtros.')}</p>`;
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
  const VIEW = { mkt: tMkt, jg: tJg, sc: tSc, cd: tCd, sy: tSy, pp: tPp };
  const DATA = { mkt: ['market'], jg: ['decisions'], sc: ['analytics', 'cards', 'styles'], cd: ['excitement'], sy: ['styles'], pp: ['prospects'] };
  async function draw() {
    const el = document.querySelector('#xx'); if (!el) return;
    await need(DATA[X.tab]); if (!document.querySelector('#xx')) return;
    el.innerHTML = `<div class="seg">${TABS().map(([k, l]) => `<button data-xt="${k}" class="${X.tab === k ? 'on' : ''}">${l}</button>`).join('')}</div>` + VIEW[X.tab]() + `<p class="mu sm" style="margin-top:1rem">${T('Everything here is exploratory and validated on past data: patterns are hypotheses, not proof.', 'Tudo aqui é exploratório e validado em dados passados: padrões são hipóteses, não provas.')}</p>`;
    const m = document.querySelector('#m');
    m.onclick = e => {
      const t = e.target.closest('[data-xt],[data-xp],[data-xc],[data-xj],[data-xjr],[data-xjn],[data-xsh],[data-xad],[data-xrm]'); if (!t) return; const d = t.dataset;
      if (d.xt) { X.tab = d.xt; draw(); } else if (d.xp) { const [k, id] = d.xp.split(':'); X[k] = id; draw(); } else if (d.xc) { X[d.xc] = ''; draw(); }
      else if (d.xj) { const [i, v] = d.xj.split(':'); X.jg.sc[+i] = +v; draw(); } else if (d.xjr) { X.jg.rev = true; draw(); } else if (d.xjn) { jNew(); draw(); }
      else if (d.xsh) shareImg(d.xsh); else if (d.xad != null) { X.cd.push({ a: mid(X.ca), b: mid(X.cb), t: d.xad === '1' }); X.ca = X.cb = ''; draw(); }
      else if (d.xrm) { const [a, b] = d.xrm.split(':'); X.cd = X.cd.filter(o => !(o.a === a && o.b === b)); draw(); }
    };
    m.oninput = e => {
      const q = e.target.closest('[data-xq]');
      if (q) { const k = q.dataset.xq, t = q.value.toLowerCase().trim(), r = document.querySelector('#xs' + k); const cards = (X.d.cards || {}).cards, exf = (X.d.excitement || {}).fighters, an = (X.d.analytics || {}).fighters;
        const ok = f => k === 'ca' || k === 'cb' ? (exf ? exf[f.id] : true) : k === 'sc' ? (an ? an[f.id] : true) : k === 'sy' ? (X.d.styles ? X.d.styles.fighters[f.id] != null : true) : true;
        if (r) r.innerHTML = t ? [...S.F.values()].filter(f => ok(f) && (f.name + ' ' + (f.nick || '')).toLowerCase().includes(t)).slice(0, 6).map(f => `<button data-xp="${k}:${f.id}"><span>${esc(f.name)}</span><span class="mu">${esc(f.record || '')}</span></button>`).join('') : ''; return; }
      const pp = e.target.closest('[data-xpp]'); if (pp) { X.pp = Math.max(2, Math.min(6, +pp.value || 2)); draw(); }
    };
  }
  async function view() { document.querySelector('#m').innerHTML = `<h1>Extras</h1><div id="xx"><p class="mu">${T('Loading…', 'Carregando…')}</p></div>`; await draw(); }
  const pT = window.XT, pV = window.XV;
  window.XT = () => [...(pT ? pT() : []), ['extras', 'Extras']];
  window.XV = { ...(pV || {}), extras: view };
})();
