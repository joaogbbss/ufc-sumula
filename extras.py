#!/usr/bin/env python3
"""extras.py: cálculo em lote dos recursos extras. Só biblioteca padrão. Roda depois do scraper.py e do analytics.py.

  market.json     odds de mercado: registro dos próximos eventos (abertura e fechamento) + odds históricas (CSV opcional)
  excitement.json modelo de "nota de espetáculo": quanto cada característica pré-luta eleva a chance de Fight of the Night
  styles.json     estilos (k-médias nos 6 atributos dos cards) e quem vence quem, já descontada a força (Elo)
  prospects.json  projeção de estreantes por analogia com carreiras do passado, com validação leave-one-out

Todo modelo é validado FORA DA AMOSTRA e o resultado vai junto no JSON: se não prevê nada além do acaso, o app diz isso.
Uso: python extras.py [--odds-csv arquivo.csv] [--only market,excitement,styles,prospects]
"""
import argparse, csv, json, math, random, re, sys, unicodedata, zlib
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path("data")
K_ELO = 28.0
FOLDS = 5


# ---------- utilidades ----------
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def num(v):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(v if v is not None else ""))
    return float(m.group(1)) if m else 0.0


def seconds(v):
    m = re.match(r"^\s*(\d+):(\d+)\s*$", str(v if v is not None else ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def fight_minutes(f):
    try: rnd = int(f.get("round") or 0)
    except ValueError: rnd = 0
    sec = seconds(f.get("time"))
    return (rnd - 1) * 5 + sec / 60 if rnd and sec else 0.0


def klass(method):
    m = (method or "").lower()
    if m.startswith(("ko", "tko")) or "ko/tko" in m: return "ko"
    if m.startswith("sub"): return "sub"
    if "decision" in m: return "dec"
    return "oth"


def sig_(z): return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
def load(p, default): return json.loads(p.read_text("utf-8")) if p.exists() else default
def save(name, obj): (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")
def r3(x): return None if x is None else round(x, 3)


def load_fights():
    fights = load(DATA / "fights.json", [])
    ov = load(DATA / "overrides.json", {})
    merges, excl = ov.get("merges", {}), set(ov.get("exclude", []))
    out = []
    for f in fights:
        if f.get("id") in excl or f.get("res") not in ("a", "b", "draw"): continue
        g = dict(f)
        g["a"] = {**f["a"], "id": merges.get(f["a"]["id"], f["a"]["id"])}
        g["b"] = {**f["b"], "id": merges.get(f["b"]["id"], f["b"]["id"])}
        if g["a"]["id"] != g["b"]["id"]: out.append(g)
    out.sort(key=lambda f: (f.get("date", ""), -(f.get("ord") or 0)))
    return out


def inv(M):
    n = len(M)
    A = [list(r) + [1.0 if i == j else 0.0 for j in range(n)] for i, r in enumerate(M)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        d = A[i][i] or 1e-12
        A[i] = [v / d for v in A[i]]
        for r in range(n):
            if r != i and A[r][i]:
                f = A[r][i]
                A[r] = [a - f * b for a, b in zip(A[r], A[i])]
    return [r[n:] for r in A]


def fit_lr(X, y, lam=1.0):
    """Regressão logística ridge (Newton); variáveis divididas pelo desvio (a 1ª coluna pode ser a constante 1)."""
    n, k = len(X), len(X[0])
    sd = [math.sqrt(sum(x[j] ** 2 for x in X) / n) or 1.0 for j in range(k)]
    Z = [[x[j] / sd[j] for j in range(k)] for x in X]
    b = [0.0] * k
    for _ in range(30):
        g, H = [0.0] * k, [[0.0] * k for _ in range(k)]
        for z, t in zip(Z, y):
            p = sig_(sum(bj * zj for bj, zj in zip(b, z)))
            w = p * (1 - p)
            for j in range(k):
                g[j] += (t - p) * z[j]
                for l in range(j + 1): H[j][l] += w * z[j] * z[l]
        for j in range(k):
            g[j] -= lam * b[j]; H[j][j] += lam
            for l in range(j): H[l][j] = H[j][l]
        Hi = inv(H)
        d = [sum(Hi[j][l] * g[l] for l in range(k)) for j in range(k)]
        b = [bj + dj for bj, dj in zip(b, d)]
        if max(abs(v) for v in d) < 1e-6: break
    return {"b": b, "sd": sd}


def lr_p(m, x): return sig_(sum(bj * xj / sj for bj, xj, sj in zip(m["b"], x, m["sd"])))


def auc(ps, ys):
    pos = [p for p, y in zip(ps, ys) if y == 1]; neg = [p for p, y in zip(ps, ys) if y == 0]
    if not pos or not neg: return None
    order = sorted([(p, 1) for p in pos] + [(p, 0) for p in neg])
    rank_sum, i = 0.0, 0
    while i < len(order):
        j = i
        while j < len(order) and order[j][0] == order[i][0]: j += 1
        rank_sum += sum(range(i + 1, j + 1)) / (j - i) * sum(o[1] for o in order[i:j])
        i = j
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


# ---------- motor sequencial: tudo calculado só com o que se sabia ANTES de cada luta ----------
def walk(fights):
    st = defaultdict(lambda: {"e": 1500.0, "n": 0, "fin": 0, "sl": 0.0, "mn": 0.0, "last": "", "h": []})
    snaps = []
    for f in fights:
        a, b = f["a"]["id"], f["b"]["id"]
        A, B = st[a], st[b]
        kind, mnt, T = klass(f.get("method")), fight_minutes(f), f.get("totals")
        snaps.append({"f": f, "ea": A["e"], "eb": B["e"], "na": A["n"], "nb": B["n"],
                      "fa": A["fin"] / A["n"] if A["n"] else None, "fb": B["fin"] / B["n"] if B["n"] else None,
                      "pa": A["sl"] / A["mn"] if A["mn"] >= 5 else None, "pb": B["sl"] / B["mn"] if B["mn"] >= 5 else None})
        s = 1.0 if f["res"] == "a" else 0.0 if f["res"] == "b" else 0.5
        e = 1 / (1 + 10 ** ((B["e"] - A["e"]) / 400.0))
        ea0, eb0 = A["e"], B["e"]
        A["e"] += K_ELO * (s - e); B["e"] -= K_ELO * (s - e)
        for X, o, me, op, sc, opp_e in ((A, B, "a", "b", s, eb0), (B, A, "b", "a", 1 - s, ea0)):
            sd = None
            if T and T.get(me) and T.get(op) and mnt:
                sd = (num(T[me].get("Sig. str.")) - num(T[op].get("Sig. str."))) / mnt
                X["sl"] += num(T[me].get("Sig. str.")); X["mn"] += mnt
            X["h"].append({"d": f["date"], "opp": opp_e, "s": sc, "x": e if me == "a" else 1 - e, "fw": 1 if (sc == 1 and kind in ("ko", "sub")) else 0, "sd": sd})
            X["n"] += 1; X["fin"] += kind in ("ko", "sub"); X["last"] = f["date"]
            X["h"][-1]["e"] = X["e"]
    return st, snaps


def calib_slope(pairs):
    """Inclinação do Elo nestes dados (logística sem intercepto): quão forte o gap de Elo realmente prevê."""
    c = math.log(10)
    if len(pairs) < 50: return c
    for _ in range(14):
        g = h = 0.0
        for x, y in pairs:
            p = sig_(c * x); g += (y - p) * x; h += p * (1 - p) * x * x
        if not h: break
        d = g / h; c += d
        if abs(d) < 1e-6: break
    return c


# ---------- 1) MERCADO ----------
def american(o):
    try: o = float(str(o).replace("+", ""))
    except ValueError: return None
    if o == 0: return None
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def devig(oa, ob):
    pa, pb = american(oa), american(ob)
    return None if pa is None or pb is None or pa + pb <= 0 else (pa / (pa + pb), pb / (pa + pb))


def run_market(fights, csv_path=None):
    store = load(DATA / "market.json", {"log": {}, "hist": {}})
    log, hist = store.get("log", {}), store.get("hist", {})
    today = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # 1a) registro dos próximos eventos: guarda a abertura (1ª vez vista) e o fechamento (última)
    for e in load(DATA / "upcoming.json", {}).get("events", []):
        for ft in e.get("fights", []):
            pa, pb = ft.get("mkt_pa"), ft.get("mkt_pb")
            if pa is None or pb is None: continue
            k = f"{e['id']}:{ft['a']['id']}:{ft['b']['id']}"
            rec = log.setdefault(k, {"d": e["date"], "o": [pa, pb], "t0": today})
            rec["c"] = [pa, pb]; rec["t1"] = today
    # 1b) resolve: liga cada registro (e cada linha do CSV) à luta que aconteceu
    by_pair = defaultdict(list)
    for f in fights: by_pair[frozenset((f["a"]["id"], f["b"]["id"]))].append(f)
    by_name = defaultdict(list)
    for f in fights: by_name[frozenset((norm(f["a"]["name"]), norm(f["b"]["name"])))].append(f)
    def near(fs, d):
        try: dd = date.fromisoformat(d)
        except (TypeError, ValueError): return None
        c = [f for f in fs if abs((date.fromisoformat(f["date"]) - dd).days) <= 3]
        return c[0] if len(c) == 1 else None
    for k, rec in log.items():
        _, ia, ib = k.split(":")
        f = near(by_pair.get(frozenset((ia, ib)), []), rec["d"])
        if f:
            pa, pb = rec.get("c", rec["o"]); o = rec["o"]
            if f["a"]["id"] != ia: pa, pb, o = pb, pa, [o[1], o[0]]
            hist[f["id"]] = [round(pa, 4), round(pb, 4), round(o[0], 4), "log"]
    n_csv = 0
    if csv_path:
        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            cols = {c.lower(): c for c in rd.fieldnames or []}
            ca, cb = cols.get("r_fighter") or cols.get("fighter_a"), cols.get("b_fighter") or cols.get("fighter_b")
            oa, ob = cols.get("r_odds") or cols.get("odds_a"), cols.get("b_odds") or cols.get("odds_b")
            cd = cols.get("date")
            if not all((ca, cb, oa, ob, cd)): print(f"market: CSV sem as colunas esperadas (R_fighter, B_fighter, R_odds, B_odds, date): {rd.fieldnames}"); 
            else:
                for row in rd:
                    p = devig(row[oa], row[ob])
                    if not p: continue
                    f = near(by_name.get(frozenset((norm(row[ca]), norm(row[cb]))), []), row[cd][:10])
                    if not f or f["id"] in hist and hist[f["id"]][3] == "log": continue
                    pa, pb = (p if norm(f["a"]["name"]) == norm(row[ca]) else p[::-1])
                    hist[f["id"]] = [round(pa, 4), round(pb, 4), round(pa, 4), "csv"]; n_csv += 1
    save("market.json", {"v": 1, "updated": today, "log": log, "hist": hist})
    print(f"market: {len(log)} lutas no registro, {len(hist)} com odds resolvidas ({n_csv} vindas do CSV)")


# ---------- 2) ESPETÁCULO (Fight of the Night) ----------
EX_NAMES = ["const", "balance", "finish", "pace", "title", "experience"]


def run_excitement(fights, st, snaps):
    league = [s["pa"] for s in snaps if s["pa"]] + [s["pb"] for s in snaps if s["pb"]]
    lg = sum(league) / len(league) if league else 4.0
    rows = []
    for s in snaps:
        f = s["f"]
        if f["date"] < "2005-01-01" or s["na"] < 2 or s["nb"] < 2 or s["pa"] is None or s["pb"] is None: continue
        p = 1 / (1 + 10 ** ((s["eb"] - s["ea"]) / 400.0))
        x = [1.0, 1 - abs(2 * p - 1), (s["fa"] + s["fb"]) / 2, ((s["pa"] + s["pb"]) / 2) / lg, 1.0 if f.get("title") else 0.0, math.log(1 + min(s["na"], s["nb"]))]
        rows.append((x, 1 if "fight" in (f.get("bonus") or []) else 0, zlib.crc32(f["id"].encode()) % FOLDS))
    if len(rows) < 300 or sum(r[1] for r in rows) < 30:
        print("excitement: poucos dados de bônus; nada gerado."); return
    base = sum(r[1] for r in rows) / len(rows)
    oof = []
    for k in range(FOLDS):
        m = fit_lr([r[0] for r in rows if r[2] != k], [r[1] for r in rows if r[2] != k])
        oof += [(lr_p(m, r[0]), r[1]) for r in rows if r[2] == k]
    ll = -sum(math.log(max(p if y else 1 - p, 1e-9)) for p, y in oof) / len(oof)
    ll0 = -sum(math.log(base if y else 1 - base) for _, y in oof) / len(oof)
    full = fit_lr([r[0] for r in rows], [r[1] for r in rows])
    cut = (date.today() - timedelta(days=1100)).isoformat()
    fighters = {i: [round(v["e"], 1), v["n"], round(v["fin"] / v["n"], 3), round(v["sl"] / v["mn"], 3), v["last"]] for i, v in st.items() if v["n"] >= 2 and v["mn"] >= 5 and v["last"] >= cut}
    save("excitement.json", {"v": 1, "model": {"names": EX_NAMES, "b": [round(v, 4) for v in full["b"]], "sd": [round(v, 4) for v in full["sd"]], "base": round(base, 4), "n": len(rows),
           "pos": sum(r[1] for r in rows), "auc": r3(auc([p for p, _ in oof], [y for _, y in oof])), "ll": round(ll, 4), "ll0": round(ll0, 4)}, "league_pace": round(lg, 3), "fighters": fighters})
    print(f"excitement: {len(rows)} lutas, {sum(r[1] for r in rows)} Fight of the Night, AUC fora da amostra {auc([p for p,_ in oof],[y for _,y in oof]):.3f}, log-loss {ll:.4f} vs {ll0:.4f} (só a taxa-base)")


# ---------- 3) ESTILOS ----------
ATTR = ["tro", "def", "lut", "sub", "peg", "car"]


def kmeans(X, k, seed=7, restarts=8, iters=60):
    rnd, best = random.Random(seed), None
    for _ in range(restarts):
        C = [X[rnd.randrange(len(X))]]
        while len(C) < k:                                  # k-means++: centros espalhados
            d = [min(sum((a - b) ** 2 for a, b in zip(x, c)) for c in C) for x in X]
            r, acc = rnd.random() * sum(d), 0.0
            for x, di in zip(X, d):
                acc += di
                if acc >= r: C.append(x); break
        for _ in range(iters):
            lab = [min(range(k), key=lambda j: sum((a - b) ** 2 for a, b in zip(x, C[j]))) for x in X]
            NC = []
            for j in range(k):
                m = [x for x, l in zip(X, lab) if l == j]
                NC.append([sum(c) / len(m) for c in zip(*m)] if m else C[j])
            if NC == C: break
            C = NC
        inertia = sum(sum((a - b) ** 2 for a, b in zip(x, C[l])) for x, l in zip(X, lab))
        if best is None or inertia < best[0]: best = (inertia, C, lab)
    return best[1], best[2]


def run_styles(fights, st, snaps, k=6):
    cards = load(DATA / "cards.json", {}).get("cards", {})
    ids = [i for i, c in cards.items() if len(c) >= 7]
    if len(ids) < 60: print("styles: cards.json ausente ou pequeno; nada gerado."); return
    X = [[float(c) for c in cards[i][1:7]] for i in ids]
    C, lab = kmeans(X, k)
    order = sorted(range(k), key=lambda j: -C[j][0] - C[j][4])           # só para uma ordem estável
    remap = {j: n for n, j in enumerate(order)}
    style = {i: remap[l] for i, l in zip(ids, lab)}
    cent = [C[j] for j in order]
    names = [[ATTR[t] for t in sorted(range(6), key=lambda t: -(c[t] - 50))[:2]] for c in cent]   # os 2 atributos que mais se destacam
    pairs = []
    for s in snaps:
        f = s["f"]
        if f["res"] == "draw" or f["a"]["id"] not in style or f["b"]["id"] not in style or s["na"] < 3 or s["nb"] < 3: continue
        pairs.append(((s["ea"] - s["eb"]) / 400.0, 1 if f["res"] == "a" else 0, style[f["a"]["id"]], style[f["b"]["id"]]))
    c = calib_slope([(x, y) for x, y, _, _ in pairs])
    M = defaultdict(lambda: [0, 0.0, 0.0])
    for x, y, si, sj in pairs:
        if si == sj: continue
        e = sig_(c * x)
        for (p, q, yy, ee) in ((si, sj, y, e), (sj, si, 1 - y, 1 - e)):
            m = M[(p, q)]; m[0] += 1; m[1] += yy - ee; m[2] += ee * (1 - ee)
    mat = {f"{p},{q}": [m[0], round(100 * m[1] / m[0], 2), round(196 * math.sqrt(m[2]) / m[0], 2)] for (p, q), m in M.items() if m[0] >= 20}
    cnt = Counter(style.values())
    save("styles.json", {"v": 1, "k": k, "names": names, "sizes": [cnt[j] for j in range(k)], "centroids": [[round(v, 1) for v in c_] for c_ in cent],
                         "fighters": style, "matrix": mat, "calib": round(c / math.log(10), 3), "fights": len(pairs)})
    print(f"styles: {len(ids)} lutadores em {k} estilos, {len(pairs)} lutas entre estilos, {len(mat)} confrontos medidos")


# ---------- 4) PROSPECTOS ----------
def run_prospects(fights, st, snaps):
    """Projeta estreantes por analogia: perfil das 2 primeiras lutas -> como foi o resto da carreira de quem tinha perfil parecido.
    O 'futuro' é medido SÓ com as lutas depois das 2 primeiras (rating de desempenho = média dos rivais + 400 x (vitórias - derrotas)/lutas),
    para o resultado não herdar a inércia do Elo nem repetir o que já está no perfil."""
    fighters = {f["id"]: f for f in load(DATA / "fighters.json", [])}
    today = date.today(); cutd = (today - timedelta(days=4 * 365)).isoformat(); active_cut = (today - timedelta(days=3 * 365)).isoformat()
    def age(i, d):
        m = re.search(r"([A-Za-z]{3})\w* (\d+), (\d{4})", str(fighters.get(i, {}).get("DOB") or ""))
        if not m: return None
        try: b = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
        except ValueError: return None
        return (date.fromisoformat(d) - b).days / 365.25
    prof, cohort = {}, {}
    for i, v in st.items():
        h = v["h"]
        if len(h) < 2: continue
        a = age(i, h[0]["d"]); sds = [x["sd"] for x in h[:2] if x["sd"] is not None]
        prof[i] = [sum(x["s"] for x in h[:2]) / 2, sum(x["fw"] for x in h[:2]) / 2, (sum(x["opp"] for x in h[:2]) / 2 - 1500) / 100,
                   (h[1]["e"] - 1500) / 100, (sum(sds) / len(sds)) if sds else 0.0, a if a is not None else 28.0]
        if h[0]["d"] < cutd:
            later = h[2:]; perf = None
            if len(later) >= 2:
                perf = sum(x["opp"] for x in later) / len(later) + 400.0 * (2 * sum(x["s"] for x in later) - len(later)) / len(later)
            cohort[i] = {"perf": perf, "n": len(h)}
    if len(cohort) < 200: print("prospects: coorte pequena; nada gerado."); return
    defined = sorted(c["perf"] for c in cohort.values() if c["perf"] is not None)
    if len(defined) < 100: print("prospects: poucas carreiras com 4+ lutas; nada gerado."); return
    thr = defined[int(len(defined) * 0.9)]
    for c in cohort.values():
        c["elite"] = 1 if c["perf"] is not None and c["perf"] >= thr else 0
        c["long"] = 1 if c["n"] >= 8 else 0
        c["stay"] = 1 if c["n"] >= 4 else 0
    cid = sorted(cohort)
    cols = list(zip(*[prof[i] for i in cid])); mu = [sum(c) / len(c) for c in cols]; sd = [math.sqrt(sum((x - m) ** 2 for x in c) / len(c)) or 1.0 for c, m in zip(cols, mu)]
    Z = {i: [(x - m) / s for x, m, s in zip(prof[i], mu, sd)] for i in prof}
    K, M0 = 60, 30
    def knn(i, exclude_self):
        zi = Z[i]; d = sorted(((sum((a - b) ** 2 for a, b in zip(zi, Z[j])), j) for j in cid if not (exclude_self and j == i)))[:K]
        return [j for _, j in d]
    base_r = {k: sum(cohort[i][k] for i in cid) / len(cid) for k in ("elite", "long", "stay")}
    def stats(js):
        pk = sorted(cohort[j]["perf"] for j in js if cohort[j]["perf"] is not None)
        q = [round(pk[int((len(pk) - 1) * p)], 0) for p in (0.1, 0.5, 0.9)] if len(pk) >= 10 else [None, None, None]
        sh = lambda key: (sum(cohort[j][key] for j in js) + M0 * base_r[key]) / (len(js) + M0)      # encolhe para a taxa-base: evento raro + poucos vizinhos = ruído
        return {"el": sh("elite"), "lg": sh("long"), "st": sh("stay"), "q": q}
    sample = cid[::max(1, len(cid) // 900)]                          # validação leave-one-out numa amostra determinística da coorte
    base = sum(cohort[i]["elite"] for i in cid) / len(cid)
    pred = [(stats(knn(i, True))["el"], cohort[i]["elite"]) for i in sample]
    brier = sum((p - y) ** 2 for p, y in pred) / len(pred); brier0 = sum((base - y) ** 2 for _, y in pred) / len(pred)
    bins = []
    for lo, hi in ((0, .03), (.03, .08), (.08, .15), (.15, .3), (.3, 1.01)):
        g = [(p, y) for p, y in pred if lo <= p < hi]
        if len(g) >= 10: bins.append([round(sum(p for p, _ in g) / len(g), 3), round(sum(y for _, y in g) / len(g), 3), len(g)])
    out = {}
    for i, v in st.items():
        if i in prof and 2 <= v["n"] <= 6 and v["last"] >= active_cut and i not in cohort:
            nb = knn(i, False); s_ = stats(nb); out[i] = [v["n"], round(s_["el"], 3), round(s_["lg"], 3), round(s_["st"], 3), *s_["q"], nb[:5]]   # nb[:5] = as 5 carreiras mais parecidas
    save("prospects.json", {"v": 2, "k": K, "cohort": len(cohort), "base_elite": round(base, 3), "thr_perf": round(thr, 0),
                            "validation": {"n": len(pred), "brier": round(brier, 4), "brier0": round(brier0, 4), "skill": round(1 - brier / brier0, 3) if brier0 else 0,
                                           "auc": r3(auc([p for p, _ in pred], [y for _, y in pred])), "bins": bins},
                            "fighters": out})
    print(f"prospects: coorte {len(cohort)}, {len(out)} prospectos; validação: skill {1 - brier / brier0:+.3f} sobre a taxa-base (0 = nada além do acaso)")


# ---------- 5) JUÍZES E ÁRBITROS ----------
CARD = re.compile(r"([^\d]+?)\s*(\d{2})\s*-\s*(\d{2})")


def parse_cards(detail):
    out = []
    for m in CARD.finditer(detail or ""):
        name, x, y = re.sub(r"^[\s.,;:]+|[\s.,;:]+$", "", m.group(1)), int(m.group(2)), int(m.group(3))
        if name and 20 <= x <= 50 and 20 <= y <= 50 and abs(x - y) <= 5: out.append((name, x, y))
    return out


def dec_sub(method):
    m = (method or "").lower()
    return "split" if "split" in m else "majority" if "majority" in m else "unanimous" if "unanimous" in m else "other"


def detect_order(fights):
    listed = wf = 0
    for f in fights:
        if klass(f.get("method")) != "dec" or dec_sub(f.get("method")) != "unanimous": continue
        sc = [(x, y) for _, x, y in parse_cards(f.get("detail"))]
        if len(sc) < 2: continue
        listed += all(((x - y) if f["res"] == "a" else (y - x)) > 0 for x, y in sc); wf += all(x > y for x, y in sc)
    return "winner_first" if wf > listed else "listed"


def zbin(obs, n, r): return (obs - n * r) / math.sqrt(n * r * (1 - r)) if n and 0 < r < 1 else 0.0


def run_judges(fights, snaps):
    dec = load(DATA / "decisions.json", {})
    cls_of = {i: v[1] for i, v in (dec.get("fights") or {}).items()}
    order = (dec.get("model") or {}).get("judge_order") or detect_order(fights)
    J = defaultdict(lambda: {"n": 0, "dis": 0, "sp": 0, "spd": 0, "c2": 0, "c2f": 0, "c3": 0, "c3f": 0})
    tot = {"n": 0, "dis": 0, "c2": 0, "c2f": 0}
    for f in fights:
        if klass(f.get("method")) != "dec" or f["res"] not in ("a", "b"): continue
        cards = parse_cards(f.get("detail"))
        if len(cards) < 2: continue
        sp, c = dec_sub(f.get("method")) in ("split", "majority"), cls_of.get(f["id"])
        for name, x, y in cards:
            w, l = (x, y) if order == "winner_first" else ((x, y) if f["res"] == "a" else (y, x))
            agree = w > l; j = J[name]
            j["n"] += 1; j["dis"] += not agree; tot["n"] += 1; tot["dis"] += not agree
            if sp: j["sp"] += 1; j["spd"] += not agree
            if c is not None and c >= 2:
                j["c2"] += 1; j["c2f"] += agree; tot["c2"] += 1; tot["c2f"] += agree
                if c == 3: j["c3"] += 1; j["c3f"] += agree
    r0 = tot["dis"] / tot["n"] if tot["n"] else 0.0; r2 = tot["c2f"] / tot["c2"] if tot["c2"] else None; K = 40
    judges = {}
    for name, j in J.items():
        if j["n"] < 20: continue
        judges[name] = {"n": j["n"], "dis": j["dis"], "r": round(j["dis"] / j["n"], 4), "rs": round((j["dis"] + K * r0) / (j["n"] + K), 4), "z": round(zbin(j["dis"], j["n"], r0), 2),
                        "sp": j["sp"], "spd": j["spd"], "spz": round(zbin(j["spd"], j["sp"], 1 / 3), 2) if j["sp"] >= 10 else None,
                        "c2": j["c2"], "c2f": j["c2f"], "c2z": round(zbin(j["c2f"], j["c2"], r2), 2) if r2 and j["c2"] >= 10 else None, "c3": j["c3"], "c3f": j["c3f"]}
    # --- árbitros ---
    rows, lg = [], [s["fa"] for s in snaps if s["fa"] is not None] + [s["fb"] for s in snaps if s["fb"] is not None]
    lgf = sum(lg) / len(lg) if lg else 0.5
    for s in snaps:
        f = s["f"]
        if not (f.get("ref") or "").strip(): continue
        p = 1 / (1 + 10 ** ((s["eb"] - s["ea"]) / 400.0)); yr = (int(f["date"][:4]) - 2015) / 10.0; k = klass(f.get("method"))
        ft = ((s["fa"] if s["fa"] is not None else lgf) + (s["fb"] if s["fb"] is not None else lgf)) / 2
        rows.append(([1.0, 1 - abs(2 * p - 1), ft, 1.0 if f.get("title") else 0.0, yr, yr * yr, math.log(1 + min(s["na"], s["nb"]))], k, f))
    refs, lgr = {}, {}
    if len(rows) >= 400:
        X = [r[0] for r in rows]; fits = {t: fit_lr(X, [1 if (r[1] in ("ko", "sub") if t == "fin" else r[1] == t) else 0 for r in rows]) for t in ("fin", "ko", "sub")}
        per = defaultdict(lambda: {"n": 0, "o": defaultdict(int), "e": defaultdict(float), "v": defaultdict(float), "dn": 0, "ds": 0})
        for x, k, f in rows:
            r = per[f["ref"].strip()]; r["n"] += 1
            for t, m in fits.items():
                p = lr_p(m, x); y = (k in ("ko", "sub")) if t == "fin" else (k == t)
                r["o"][t] += y; r["e"][t] += p; r["v"][t] += p * (1 - p)
            if k == "dec" and f["id"] in cls_of: r["dn"] += 1; r["ds"] += cls_of[f["id"]] >= 2
        # timing da parada: golpes absorvidos pelo perdedor numa parada por TKO, comparado com outras paradas no mesmo round
        stop, buckets = defaultdict(list), defaultdict(list)
        for x, k, f in rows:
            T = f.get("totals")
            if k == "ko" and T and T.get("a") and T.get("b"):
                win = "a" if f["res"] == "a" else "b"; ab = math.log(1 + num(T[win].get("Sig. str.")))
                try: b = min(int(f.get("round") or 1), 4)
                except ValueError: continue
                buckets[b].append(ab); stop[f["ref"].strip()].append((b, ab))
        bm = {b: sum(v) / len(v) for b, v in buckets.items() if len(v) >= 20}
        allres = [ab - bm[b] for v in stop.values() for b, ab in v if b in bm]; sd_all = math.sqrt(sum(r * r for r in allres) / len(allres)) if allres else 1.0
        dn_t = sum(r["dn"] for r in per.values()); ds_t = sum(r["ds"] for r in per.values()); rd = ds_t / dn_t if dn_t else None
        for name, r in per.items():
            if r["n"] < 30: continue
            res = [ab - bm[b] for b, ab in stop.get(name, []) if b in bm]
            ent = {"n": r["n"]}
            for t in ("fin", "ko", "sub"):
                ent[t] = round(r["o"][t] / r["n"], 4); ent[t + "e"] = round(r["e"][t] / r["n"], 4); ent[t + "z"] = round((r["o"][t] - r["e"][t]) / math.sqrt(r["v"][t]), 2) if r["v"][t] > 0 else 0.0
            ent["sn"] = len(res); ent["si"] = round(sum(res) / len(res), 3) if len(res) >= 10 else None; ent["sz"] = round(sum(res) / len(res) / (sd_all / math.sqrt(len(res))), 2) if len(res) >= 10 else None
            ent["dn"] = r["dn"]; ent["ds"] = r["ds"]; ent["dz"] = round(zbin(r["ds"], r["dn"], rd), 2) if rd and r["dn"] >= 15 else None
            refs[name] = ent
        lgr = {"fin": round(sum(1 for r in rows if r[1] in ("ko", "sub")) / len(rows), 4), "ko": round(sum(1 for r in rows if r[1] == "ko") / len(rows), 4), "sub": round(sum(1 for r in rows if r[1] == "sub") / len(rows), 4), "dsus": round(rd, 4) if rd else None}
    if not judges and not refs: print("judges: sem placares de juízes nem árbitros; nada gerado."); return
    save("judges.json", {"v": 1, "order": order, "league": {"cards": tot["n"], "dis": round(r0, 4), "c2f": round(r2, 4) if r2 else None, **lgr}, "judges": judges, "refs": refs, "has_cls": bool(cls_of)})
    flag = lambda D, k, th=3.3: sum(1 for v in D.values() if v.get(k) is not None and abs(v[k]) > th)
    print(f"judges: {len(judges)} juízes ({tot['n']} cartões, ordem {order}), {len(refs)} árbitros; sinais fortes (|z|>3,3): juízes {flag(judges, 'z')}, árbitros {flag(refs, 'finz')}")


# ---------- 6) ACADEMIAS (CAMPS) ----------
ALIAS = {"att": "american top team", "american top team att": "american top team", "aka": "american kickboxing academy", "american kickboxing academy aka": "american kickboxing academy",
         "tam": "team alpha male", "alpha male": "team alpha male", "jackson wink": "jackson wink mma", "jackson winks mma": "jackson wink mma", "jackson s mma": "jackson wink mma",
         "xtreme couture": "xtreme couture mma", "kings mma": "kings mma", "chute boxe": "chute boxe academy", "chute boxe academy": "chute boxe academy", "brazilian top team": "brazilian top team", "btt": "brazilian top team",
         "city kickboxing": "city kickboxing", "tristar": "tristar gym", "tristar gym": "tristar gym", "sanford mma": "sanford mma", "fortis mma": "fortis mma", "roufusport": "roufusport mma", "roufusport mma": "roufusport mma"}


def run_camps(fights, st):
    fighters = {f["id"]: f for f in load(DATA / "fighters.json", [])}
    ov = load(DATA / "overrides.json", {}); merges = ov.get("merges", {})
    custom = {norm(k): norm(v) for k, v in load(DATA / "camp_alias.json", {}).items()}          # opcional: o usuário pode corrigir nomes
    raw, group = defaultdict(Counter), {}
    for i, fg in fighters.items():
        t = norm(fg.get("team") or "")
        if not t or i not in st: continue
        key = custom.get(t) or ALIAS.get(t) or t; group[merges.get(i, i)] = key; raw[key][str(fg["team"]).strip()] += 1
    seen = [i for i, v in st.items() if v["n"] >= 1]; cov = sum(1 for i in seen if i in group)
    if cov < 30: print(f"camps: só {cov} lutadores com academia (o team vem da ESPN); nada gerado."); return
    last = max(v["last"] for v in st.values()); act_cut = (date.fromisoformat(last) - timedelta(days=730)).isoformat()
    allx = [(x["s"] - x["x"]) for i, v in st.items() for x in v["h"]]; mu_all = sum(allx) / len(allx)
    deb = [(x["s"] - x["x"]) for i, v in st.items() for x in v["h"][:3]]; mu_deb = sum(deb) / len(deb)
    teams = defaultdict(lambda: {"f": [], "dn": 0, "dr": 0.0, "dv": 0.0, "an": 0, "ar": 0.0, "av": 0.0, "tw": 0, "tf": 0, "ch": set()})
    for i, v in st.items():
        g = group.get(i)
        if not g: continue
        t = teams[g]; t["f"].append(i)
        for k, x in enumerate(v["h"]):
            t["an"] += 1; t["ar"] += x["s"] - x["x"] - mu_all; t["av"] += x["x"] * (1 - x["x"])
            if k < 3: t["dn"] += 1; t["dr"] += x["s"] - x["x"] - mu_deb; t["dv"] += x["x"] * (1 - x["x"])
    for f in fights:
        if not f.get("title"): continue
        for side in ("a", "b"):
            g = group.get(f[side]["id"])
            if g:
                teams[g]["tf"] += 1
                if f["res"] == side: teams[g]["tw"] += 1; teams[g]["ch"].add(f[side]["id"])
    out = {}
    for g, t in teams.items():
        if len(t["f"]) < 3: continue
        actv = sorted((i for i in t["f"] if st[i]["last"] >= act_cut), key=lambda i: -st[i]["e"])
        out[g] = {"name": raw[g].most_common(1)[0][0], "nf": len(t["f"]), "act": len(actv), "elo": round(sum(st[i]["e"] for i in actv) / len(actv), 1) if actv else None, "top": actv[:3],
                  "pk": round(max(st[i]["e"] for i in t["f"]), 0), "fights": sum(st[i]["n"] for i in t["f"]),
                  "dn": t["dn"], "dw": round(100 * t["dr"] / t["dn"], 2) if t["dn"] >= 10 else None, "ds": round(196 * math.sqrt(t["dv"]) / t["dn"], 2) if t["dn"] >= 10 else None,
                  "aw": round(100 * t["ar"] / t["an"], 2) if t["an"] else None, "as": round(196 * math.sqrt(t["av"]) / t["an"], 2) if t["an"] else None,
                  "tw": t["tw"], "tf": t["tf"], "ch": len(t["ch"])}
    save("camps.json", {"v": 1, "coverage": [cov, len(seen)], "last": last, "teams": out})
    print(f"camps: {len(out)} academias com 3+ lutadores; {cov} de {len(seen)} lutadores com academia identificada")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--odds-csv"); ap.add_argument("--only", default="market,excitement,styles,prospects,judges,camps")
    a = ap.parse_args(); only = set(a.only.split(","))
    fights = load_fights()
    if not fights: print("extras: data/fights.json ausente ou vazio; nada a fazer."); return 0
    st, snaps = walk(fights)
    csv_path = a.odds_csv or (str(DATA / "odds_history.csv") if (DATA / "odds_history.csv").exists() else None)   # basta subir o CSV em data/odds_history.csv
    for name, fn in (("market", lambda: run_market(fights, csv_path)), ("excitement", lambda: run_excitement(fights, st, snaps)),
                     ("styles", lambda: run_styles(fights, st, snaps)), ("prospects", lambda: run_prospects(fights, st, snaps)),
                     ("judges", lambda: run_judges(fights, snaps)), ("camps", lambda: run_camps(fights, st))):
        if name in only:
            try: fn()
            except Exception as ex: print(f"{name}: erro ({ex}); arquivo não foi atualizado.")   # um bloco nunca derruba os outros
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as ex: print(f"extras: erro ({ex})"); sys.exit(0)
