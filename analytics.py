#!/usr/bin/env python3
"""analytics.py: consolida estatísticas avançadas a partir de data/fights.json.

Roda logo depois do scraper.py e grava arquivos leves em data/:
  - analytics.json (ELO, DLI, currículo, SoS e benchmarks por divisão)
  - decisions.json (auditoria de decisões / "roubo?" via regressão logística L2)
  - live.json (probabilidade de vitória ao vivo round a round - WPA)
  - cards.json (cards científicos ponderados por Z-Score, SoS e Gatekeeping de título)
  - validation.json (Brier Score, Log-Loss e curva de calibração dos modelos)

Usa somente a biblioteca padrão do Python.
"""
import bisect
import json
import math
import re
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("data")

# ---------- Parâmetros (todos ajustáveis e gravados no JSON para auditoria) ----------
BASE = 1500.0                 # nota inicial de todo lutador
K_NEW, K_MID, K_VET = 38.0, 30.0, 22.0   # K calibrado para evitar superinflação em streaks curtas
TITLE_MULT = 1.18             # lutas de cinturão têm peso superior comprovado
PRIOR_STRIKES = 1500          # "pseudo-golpes" (~4 knockdowns de dúvida inicial) para encolhimento Bayesiano
KO_MULT = {1: 1.40, 2: 1.32, 3: 1.25}      # KO/TKO: amortecido para não distorcer ELO contra oposição fraca
SUB_MULT = {1: 1.35, 2: 1.28, 3: 1.20}     # finalização (4+ = 1.18)
DEC_MULT = {"unanimous": 1.00, "majority": 0.90, "split": 0.80}
DQ_MULT = 0.90

KEYS = ("ko", "sub", "dec", "oth")


# ---------- utilitários ----------
def num(v):
    """'34 of 71' -> 34.0 ; '0' -> 0.0 ; '---' -> 0.0"""
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(v if v is not None else ""))
    return float(m.group(1)) if m else 0.0


def seconds(v):
    m = re.match(r"^\s*(\d+):(\d+)\s*$", str(v if v is not None else ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def fight_minutes(f):
    try:
        rnd = int(f.get("round") or 0)
    except ValueError:
        rnd = 0
    sec = seconds(f.get("time"))
    return (rnd - 1) * 5 + sec / 60 if rnd and sec else 0.0


def klass(method):
    """Classifica o desfecho: ko, sub, dec ou oth (+ subtipo da decisão)."""
    m = (method or "").lower()
    if m.startswith(("ko", "tko")) or "ko/tko" in m:
        return "ko", None
    if m.startswith("sub"):
        return "sub", None
    if "decision" in m:
        sub = "split" if "split" in m else "majority" if "major" in m else "unanimous"
        return "dec", sub
    return "oth", None


def multiplier(f):
    """Peso do desfecho: KO no 1º round vale mais que decisão dividida."""
    kind, sub = klass(f.get("method"))
    try:
        rnd = int(f.get("round") or 0)
    except ValueError:
        rnd = 0
    if kind == "ko":
        m = KO_MULT.get(rnd, 1.20)
    elif kind == "sub":
        m = SUB_MULT.get(rnd, 1.18)
    elif kind == "dec":
        m = DEC_MULT[sub]
    else:
        m = DQ_MULT if "dq" in (f.get("method") or "").lower() else 1.0
    return m * (TITLE_MULT if f.get("title") else 1.0)


def k_factor(n):
    return K_NEW if n < 5 else K_MID if n < 15 else K_VET


def r1(x, d=1):
    return None if x is None else round(x, d)


# ---------- carga ----------
def load_fights():
    fp = DATA / "fights.json"
    if not fp.exists():
        return []
    fights = json.loads(fp.read_text("utf-8"))
    ov_p = DATA / "overrides.json"
    ov = json.loads(ov_p.read_text("utf-8")) if ov_p.exists() else {}
    merges, divs, excl = ov.get("merges", {}), ov.get("div", {}), set(ov.get("exclude", []))
    out = []
    for f in fights:
        if f.get("id") in excl or f.get("res") not in ("a", "b", "draw"):
            continue
        g = dict(f)
        g["a"] = {**f["a"], "id": merges.get(f["a"]["id"], f["a"]["id"])}
        g["b"] = {**f["b"], "id": merges.get(f["b"]["id"], f["b"]["id"])}
        if g["a"]["id"] == g["b"]["id"]:
            continue
        g["div"] = divs.get(f["id"], f.get("div") or "Outros")
        out.append(g)
    # ordem cronológica; no mesmo evento, o card termina pelo main event (ord 0), então inverte
    out.sort(key=lambda f: (f.get("date", ""), -(f.get("ord") or 0)))
    return out


# ---------- 1) ELO dinâmico com amortecimento de SoS e rastreio de cinturão ----------
def run_elo(fights, pre_out=None):
    st = {}

    def get(i):
        if i not in st:
            st[i] = {"r": BASE, "pk": BASE, "n": 0, "opp": [], "wins_opp": [], "w": [0] * 4, "l": [0] * 4,
                     "d": 0, "tw": 0, "tf": 0, "last": "", "divs": Counter(), "dv": {}}
        return st[i]

    for f in fights:
        A, B = get(f["a"]["id"]), get(f["b"]["id"])
        ea = 1.0 / (1.0 + 10 ** ((B["r"] - A["r"]) / 400.0))
        if pre_out is not None:
            pre_out[f["id"]] = (A["r"], B["r"])      # nota de cada um ANTES da luta (sem vazamento do futuro)
        s = 1.0 if f["res"] == "a" else 0.0 if f["res"] == "b" else 0.5
        m = multiplier(f)
        
        # Amortecimento de finalização sobre azarões: evita que finalizar oponentes fracos infle o ELO ao infinito
        if s == 1.0 and A["r"] - B["r"] > 120 and not f.get("title"):
            m = 1.0 + (m - 1.0) * (1.0 / (1.0 + (A["r"] - B["r"] - 120) / 200.0))
        elif s == 0.0 and B["r"] - A["r"] > 120 and not f.get("title"):
            m = 1.0 + (m - 1.0) * (1.0 / (1.0 + (B["r"] - A["r"] - 120) / 200.0))

        da = k_factor(A["n"]) * m * (s - ea)
        db = k_factor(B["n"]) * m * ((1 - s) - (1 - ea))
        kind = KEYS.index(klass(f.get("method"))[0])
        is_title = bool(f.get("title"))
        if is_title:
            A["tf"] += 1
            B["tf"] += 1
        A["opp"].append(B["r"])
        B["opp"].append(A["r"])
        if f["res"] == "a":
            A["wins_opp"].append(B["r"]); A["w"][kind] += 1; B["l"][kind] += 1
            if is_title:
                A["tw"] += 1
        elif f["res"] == "b":
            B["wins_opp"].append(A["r"]); B["w"][kind] += 1; A["l"][kind] += 1
            if is_title:
                B["tw"] += 1
        else:
            A["d"] += 1; B["d"] += 1
        for X, d, side in ((A, da, "a"), (B, db, "b")):
            X["r"] += d
            X["pk"] = max(X["pk"], X["r"])
            X["n"] += 1
            X["last"] = f["date"]
            X["divs"][f["div"]] += 1
            # cartel separado por divisão: um lutador pertence a TODAS as divisões
            # em que lutou (ex.: campeão de duas categorias aparece nas duas)
            g = X["dv"].setdefault(f["div"], {"n": 0, "w": 0, "l": 0, "d": 0, "last": "", "tw": 0})
            g["n"] += 1
            g["last"] = f["date"]
            if f["res"] == side:
                g["w"] += 1
                g["tw"] += 1 if is_title else 0
            elif f["res"] == "draw":
                g["d"] += 1
            else:
                g["l"] += 1
    return st


# divisões "de verdade": catchweight / open weight não definem onde o lutador compete
NONSTD = {"Catch Weight", "Open Weight", "Outros"}


def division_profile(e):
    """Divisão atual, divisão principal e a lista completa de divisões de um lutador.

    - div      : divisão ATUAL = a da luta mais recente em categoria oficial
    - div_main : divisão com mais lutas (usada para comparar estatísticas entre pares)
    - divs     : [[divisão, lutas, V, D, E, última luta, cinturões]] da mais recente para a mais antiga
    """
    items = sorted(e["dv"].items(), key=lambda kv: kv[1]["last"], reverse=True)
    std = [k for k, _ in items if k not in NONSTD]
    cur = std[0] if std else items[0][0]
    main_std = [k for k, _ in e["divs"].most_common() if k not in NONSTD]
    main = main_std[0] if main_std else e["divs"].most_common(1)[0][0]
    divs = [[k, g["n"], g["w"], g["l"], g["d"], g["last"], g["tw"]] for k, g in items]
    return cur, main, divs


# ---------- 2) DLI: dano e letalidade ----------
def run_damage(fights):
    acc = defaultdict(lambda: {"sl": 0.0, "sa": 0.0, "kd": 0.0, "ka": 0.0, "fs": 0})
    tot_sl = tot_kd = 0.0
    for f in fights:
        T = f.get("totals")
        if not T or not T.get("a") or not T.get("b"):
            continue
        for me, op, i in (("a", "b", f["a"]["id"]), ("b", "a", f["b"]["id"])):
            sl, sa = num(T[me].get("Sig. str.")), num(T[op].get("Sig. str."))
            kd, ka = num(T[me].get("KD")), num(T[op].get("KD"))
            x = acc[i]
            x["sl"] += sl; x["sa"] += sa; x["kd"] += kd; x["ka"] += ka; x["fs"] += 1
            tot_sl += sl
            tot_kd += kd
    p0 = tot_kd / tot_sl if tot_sl else 0.0       # knockdowns por golpe significativo, média da UFC
    return acc, p0


# ---------- 3) benchmarks por divisão ----------
def run_benchmarks(fights):
    agg = defaultdict(lambda: {"n": 0, "m": [0] * 4, "r1": 0, "min": 0.0, "nmin": 0, "kd": 0.0, "sl": 0.0,
                               "td": 0.0, "ns": 0, "du": 0, "ds": 0, "dm": 0})
    for f in fights:
        if f["res"] == "draw":
            continue
        kind, sub = klass(f.get("method"))
        for key in (f["div"], "ALL"):
            g = agg[key]
            g["n"] += 1
            g["m"][KEYS.index(kind)] += 1
            if kind in ("ko", "sub") and str(f.get("round")) == "1":
                g["r1"] += 1
            if kind == "dec":
                g["du" if sub == "unanimous" else "ds" if sub == "split" else "dm"] += 1
            mn = fight_minutes(f)
            if mn:
                g["min"] += mn; g["nmin"] += 1
            T = f.get("totals")
            if T and T.get("a") and T.get("b"):
                g["ns"] += 1
                for s in "ab":
                    g["kd"] += num(T[s].get("KD"))
                    g["sl"] += num(T[s].get("Sig. str."))
                    g["td"] += num(T[s].get("Td"))
    out = {}
    for k, g in agg.items():
        n = g["n"] or 1
        decs = (g["du"] + g["ds"] + g["dm"]) or 1
        out[k] = {"n": g["n"], "m": [round(x / n, 4) for x in g["m"]], "r1": round(g["r1"] / n, 4),
                  "min": r1(g["min"] / g["nmin"], 2) if g["nmin"] else None,
                  "kd": r1(g["kd"] / g["ns"], 3) if g["ns"] else None,
                  "sl": r1(g["sl"] / g["ns"], 1) if g["ns"] else None,
                  "td": r1(g["td"] / g["ns"], 2) if g["ns"] else None,
                  "dec": [round(g["du"] / decs, 3), round(g["ds"] / decs, 3), round(g["dm"] / decs, 3)]}
    return out


# ---------- 4) checagem de decisões: o resultado oficial bate com os números? ----------
DEC_NAMES = ["sig", "tot", "td", "kd", "ctrl", "sub", "led_sig", "led_ctrl"]
CLS_CUTS = (0.60, 0.35, 0.15)     # P(resultado oficial | números): >=.60 coerente, >=.35 apertada, >=.15 questionável, abaixo disso: possível roubo
FOLDS = 5


def sgn(x):
    return (x > 0) - (x < 0)


def round_pairs(f):
    """Estatísticas round a round (A, B). Sem dados por round, usa os totais da luta como um bloco só."""
    rows = [(r["a"], r["b"]) for r in ((f.get("rounds") or {}).get("totals") or []) if r.get("a") and r.get("b")]
    T = f.get("totals")
    if not rows and T and T.get("a") and T.get("b"):
        rows = [(T["a"], T["b"])]
    return rows


def round_vec(a, b):
    """Diferenças A menos B de UM round. A soma desses vetores é o vetor da luta: o modelo decompõe por round."""
    sig = num(a.get("Sig. str.")) - num(b.get("Sig. str."))
    ctl = (seconds(a.get("Ctrl")) - seconds(b.get("Ctrl"))) / 60.0
    return [sig / 10.0, (num(a.get("Total str.")) - num(b.get("Total str."))) / 10.0,
            num(a.get("Td")) - num(b.get("Td")), num(a.get("KD")) - num(b.get("KD")), ctl,
            num(a.get("Sub. att")) - num(b.get("Sub. att")), float(sgn(sig)), float(sgn(ctl)) if abs(ctl) >= 0.5 else 0.0]


def judge_scores(detail):
    out = []
    for x, y in re.findall(r"(\d{2})\s*-\s*(\d{2})", detail or ""):
        x, y = int(x), int(y)
        if 20 <= x <= 50 and 20 <= y <= 50 and abs(x - y) <= 5:
            out.append((x, y))
    return out


def judge_order(fights):
    """Descobre se os placares dos juízes vêm na ordem dos lutadores listados ou com o vencedor primeiro."""
    listed = winner_first = n = 0
    for f in fights:
        kind, sub = klass(f.get("method"))
        if kind != "dec" or sub != "unanimous" or f["res"] not in ("a", "b"):
            continue
        sc = judge_scores(f.get("detail"))
        if len(sc) < 2:
            continue
        n += 1
        listed += all(((x - y) if f["res"] == "a" else (y - x)) > 0 for x, y in sc)
        winner_first += all(x > y for x, y in sc)
    return ("winner_first" if winner_first > listed else "listed"), listed, winner_first, n


def inv(M):
    n = len(M)
    A = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        d = A[i][i] or 1e-12
        A[i] = [v / d for v in A[i]]
        for r in range(n):
            if r != i and A[r][i]:
                f = A[r][i]
                A[r] = [a - f * b for a, b in zip(A[r], A[i])]
    return [row[n:] for row in A]


def fit_lr(X, y, lam=1.0):
    """Regressão logística ridge (Newton), variáveis padronizadas. Sem dependências."""
    n, k = len(X), len(X[0])
    sd = [math.sqrt(sum(x[j] ** 2 for x in X) / n) or 1.0 for j in range(k)]
    Z = [[x[j] / sd[j] for j in range(k)] for x in X]
    b, H = [0.0] * k, None
    for _ in range(30):
        g, H = [0.0] * k, [[0.0] * k for _ in range(k)]
        for z, t in zip(Z, y):
            s = max(-30.0, min(30.0, sum(bj * zj for bj, zj in zip(b, z))))
            p = 1.0 / (1.0 + math.exp(-s))
            w = p * (1.0 - p)
            for j in range(k):
                g[j] += (t - p) * z[j]
                for l in range(j + 1):
                    H[j][l] += w * z[j] * z[l]
        for j in range(k):
            g[j] -= lam * b[j]
            H[j][j] += lam
            for l in range(j):
                H[l][j] = H[j][l]
        Hi = inv(H)
        d = [sum(Hi[j][l] * g[l] for l in range(k)) for j in range(k)]
        b = [bj + dj for bj, dj in zip(b, d)]
        if max(abs(v) for v in d) < 1e-6:
            break
    Hi = inv(H)
    return {"b": b, "sd": sd, "se": [math.sqrt(max(Hi[j][j], 0.0)) for j in range(k)]}


def lr_logit(m, x):
    return sum(bj * xj / sj for bj, xj, sj in zip(m["b"], x, m["sd"]))


def sig_(z):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


DEC_GROUPS = {"strike": [0, 1, 6], "grap": [2, 4, 7], "sub": [5], "kd": [3]}


def cv_logloss(rows, drop=()):
    """Log-loss da validação cruzada sem as variáveis em `drop` (importância por grupo)."""
    keep = [j for j in range(len(DEC_NAMES)) if j not in drop]
    tot = 0.0
    for k in range(FOLDS):
        tr = [r for r in rows if r["fold"] != k]
        m = fit_lr([[r["x"][j] for j in keep] for r in tr], [r["y"] for r in tr])
        for r in (r for r in rows if r["fold"] == k):
            p = sig_(lr_logit(m, [r["x"][j] for j in keep]))
            tot -= math.log(max(p if r["y"] == 1.0 else 1.0 - p, 1e-6))
    return tot / len(rows)


def run_decisions(fights):
    rows = []
    for f in fights:
        kind, sub = klass(f.get("method"))
        if kind != "dec" or f["res"] not in ("a", "b"):
            continue
        rp = round_pairs(f)
        if not rp:
            continue
        vs = [round_vec(a, b) for a, b in rp]
        fl = zlib.crc32(f["id"].encode()) & 1
        sign = -1.0 if fl else 1.0
        x = [sign * sum(v[j] for v in vs) for j in range(len(DEC_NAMES))]
        subj_won = (f["res"] == "a") != bool(fl)
        rows.append({"id": f["id"], "x": x, "y": 1.0 if subj_won else 0.0, "rv": [[sign * c for c in v] for v in vs],
                     "fold": zlib.crc32(f["id"].encode()) % FOLDS, "sub": sub, "f": f, "sj": subj_won})
    if len(rows) < 300:
        return None
    full = fit_lr([r["x"] for r in rows], [r["y"] for r in rows])
    models = [fit_lr([r["x"] for r in rows if r["fold"] != k], [r["y"] for r in rows if r["fold"] != k]) for k in range(FOLDS)]
    order, n_listed, n_wf, n_un = judge_order(fights)
    out, cnt = {}, Counter()
    agree, ll, by = 0, 0.0, defaultdict(lambda: [0, 0])
    for r in rows:
        m = models[r["fold"]]
        p = sig_(lr_logit(m, r["x"]))
        po = p if r["y"] == 1.0 else 1.0 - p
        cls = 0 if po >= CLS_CUTS[0] else 1 if po >= CLS_CUTS[1] else 2 if po >= CLS_CUTS[2] else 3
        cnt[cls] += 1
        agree += po > 0.5
        ll -= math.log(max(po, 1e-6))
        by[r["sub"]][0] += po > 0.5
        by[r["sub"]][1] += 1
        flip = 1.0 if r["sj"] else -1.0
        rs = [round(flip * lr_logit(m, v), 2) for v in r["rv"]]
        f = r["f"]
        sc = judge_scores(f.get("detail"))
        if sc and order == "listed" and f["res"] == "b":
            sc = [(y, x) for x, y in sc]
        out[r["id"]] = [round(po, 3), cls, (r["sub"] or "unanimous")[0], ",".join(f"{x}-{y}" for x, y in sc), rs]
    n = len(rows)
    model = {"n": n, "acc": round(agree / n, 4), "ll": round(ll / n, 4),
             "acc_by": {k: [round(v[0] / v[1], 4), v[1]] for k, v in by.items()},
             "classes": [cnt[i] for i in range(4)], "cuts": list(CLS_CUTS), "folds": FOLDS, "names": DEC_NAMES,
             "judge_order": order, "judge_check": [n_listed, n_wf, n_un],
             "imp": {g: round(cv_logloss(rows, ix) - ll / n, 4) for g, ix in DEC_GROUPS.items()},
             "b": [round(full["b"][j] / full["sd"][j], 4) for j in range(len(DEC_NAMES))],
             "se": [round(full["se"][j] / full["sd"][j], 4) for j in range(len(DEC_NAMES))]}
    return {"v": 1, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "fights": out}


# ---------- 5) probabilidade de vitória AO VIVO (round a round) ----------
LIVE_NAMES = ["prior", "sig", "tot", "td", "kd", "ctrl", "sub"]


def run_live(fights, pre):
    items = []
    for f in fights:
        if f["res"] not in ("a", "b") or f["id"] not in pre:
            continue
        rp = [(r["a"], r["b"]) for r in ((f.get("rounds") or {}).get("totals") or []) if r.get("a") and r.get("b")]
        if not rp:
            continue
        kind, _ = klass(f.get("method"))
        vs = [round_vec(a, b)[:6] for a, b in rp]
        last = len(vs) if kind == "dec" else len(vs) - 1
        fl = zlib.crc32(f["id"].encode()) & 1
        sign = -1.0 if fl else 1.0
        ea, eb = pre[f["id"]]
        prior = sign * (ea - eb) / 400.0
        won = (f["res"] == "a") != bool(fl)
        cum, rows = [0.0] * 6, []
        for r in range(1, last + 1):
            cum = [c + sign * v for c, v in zip(cum, vs[r - 1])]
            rows.append([prior] + cum[:])
        items.append({"id": f["id"], "prior": prior, "y": 1.0 if won else 0.0, "rows": rows, "fold": zlib.crc32(f["id"].encode()) % FOLDS})
    if len(items) < 300:
        return None
    m0 = [fit_lr([[i["prior"]] for i in items if i["fold"] != k], [i["y"] for i in items if it_fold != k])
          for k in range(FOLDS) for it_fold in [k]]
    groups = {}
    for i in items:
        for r, x in enumerate(i["rows"], 1):
            groups.setdefault(min(r, 4), []).append((i, x))
    mg = {g: [fit_lr([x for it, x in rows if it["fold"] != k], [it["y"] for it, x in rows if it["fold"] != k]) for k in range(FOLDS)]
          for g, rows in groups.items() if len(rows) >= 150}
    out, gstats, lows = {}, [], []
    for it in items:
        p0 = sig_(lr_logit(m0[it["fold"]], [it["prior"]]))
        seq = [p0 if it["y"] == 1.0 else 1 - p0]
        for r, x in enumerate(it["rows"], 1):
            g = min(r, 4)
            if g not in mg:
                break
            p = sig_(lr_logit(mg[g][it["fold"]], x))
            seq.append(p if it["y"] == 1.0 else 1 - p)
        seq = [min(0.995, max(0.005, v)) for v in seq]
        out[it["id"]] = [round(v, 3) for v in seq]
        if len(seq) > 1:
            lows.append((min(seq[1:]), it["id"], 1 + seq[1:].index(min(seq[1:]))))
    for g in sorted(groups):
        if g not in mg:
            continue
        n = ll0 = ll = 0
        for it, x in groups[g]:
            p = sig_(lr_logit(mg[g][it["fold"]], x))
            q = sig_(lr_logit(m0[it["fold"]], [it["prior"]]))
            ll -= math.log(max(p if it["y"] == 1.0 else 1 - p, 1e-6))
            ll0 -= math.log(max(q if it["y"] == 1.0 else 1 - q, 1e-6))
            n += 1
        gstats.append({"g": g, "n": n, "ll0": round(ll0 / n, 4), "ll": round(ll / n, 4)})
    lows.sort()
    return {"v": 1, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": {"n": len(items), "groups": gstats, "names": LIVE_NAMES},
            "comebacks": [[i, round(p, 3), r] for p, i, r in lows[:60]], "fights": out}


# ---------- 6) cards de atributos científicos (Z-Score + SoS + Gatekeeping de Título) ----------
CARD_MIN_FIGHTS, CARD_MIN_MIN = 1, 0.0   # 1 luta basta: o encolhimento bayesiano puxa amostra curta para a média
# Pesos internos de cada atributo:
# tro: [volume_por_min (2), precisao (1.2), kd_rate (0.8)]
# def: [def_str (1.5), -sapm (1.2), def_td (1.2), -kas_queixo (1.5)]
# lut: [td_por_15m (1.5), td_acc (1.0), tempo_controle (1.5)]
# sub: [sub_att_15m (1.0), sub_win_rate (1.8)]
# peg: [ks_letalidade (1.8), ko_win_rate (1.2)]
# car: [ritmo_r3_vs_r1 (1.5), duracao_media (0.8)]
CARD_W = {
    "tro": [2.0, 1.2, 0.8],
    "def": [1.5, 1.2, 1.2, 1.5],
    "lut": [1.5, 1.0, 1.5],
    "sub": [1.0, 1.8],
    "peg": [1.8, 1.2],
    "car": [1.5, 0.8],
}


def att_of(v):
    m = re.search(r"of\s+(\d+)", str(v if v is not None else ""))
    return float(m.group(1)) if m else 0.0


def z_to_fifa_rating(z, sos_adj=0.0, low=48.0, high=98.0, k=0.72):
    """Converte Z-Score + ajuste de Nível de Oposição (SoS) em nota estilo FIFA/EA UFC (48 a 98).
    Z = 0.0 -> ~73 | Z = +1.0 -> ~82 | Z = +2.0 -> ~89 | Z = +3.0 -> ~94+"""
    z_eff = max(-3.5, min(3.8, z + sos_adj))
    p = 1.0 / (1.0 + math.exp(-k * (z_eff - 0.15)))
    return int(round(low + p * (high - low)))


def run_cards(fights, fighters):
    A = defaultdict(lambda: defaultdict(float))
    for f in fights:
        T = f.get("totals")
        if not T or not T.get("a") or not T.get("b"):
            continue
        mn = fight_minutes(f)
        if not mn:
            continue
        rp = [(r["a"], r["b"]) for r in ((f.get("rounds") or {}).get("totals") or []) if r.get("a") and r.get("b")]
        full = klass(f.get("method"))[0] == "dec"
        done = rp if full else rp[:-1]                          # só rounds completos entram no cardio
        for me, op, i in (("a", "b", f["a"]["id"]), ("b", "a", f["b"]["id"])):
            x, a, o = A[i], T[me], T[op]
            x["mn"] += mn
            x["fs"] += 1
            x["sl"] += num(a.get("Sig. str.")); x["sat"] += att_of(a.get("Sig. str."))
            x["sa"] += num(o.get("Sig. str.")); x["oat"] += att_of(o.get("Sig. str."))
            x["tl"] += num(a.get("Td")); x["ta"] += att_of(a.get("Td"))
            x["otl"] += num(o.get("Td")); x["ota"] += att_of(o.get("Td"))
            x["ct"] += seconds(a.get("Ctrl")); x["sb"] += num(a.get("Sub. att"))
            if len(done) >= 3:
                x["c1"] += num(done[0][0 if me == "a" else 1].get("Sig. str.")); x["n1"] += 1
                late = [num(r[0 if me == "a" else 1].get("Sig. str.")) for r in done[2:]]
                x["c3"] += sum(late); x["n3"] += len(late)
    tot = defaultdict(float)
    for x in A.values():
        for k, v in x.items():
            tot[k] += v
    if not tot["mn"] or not tot["sat"]:
        return None
    K = 25.0  # Maior encolhimento Bayesiano para evitar extremos com pouca minutagem
    g_sl, g_acc = tot["sl"] / tot["mn"], tot["sl"] / tot["sat"]
    g_tl, g_ta = tot["tl"] / tot["mn"], tot["tl"] / max(tot["ta"], 1)
    g_ct, g_sb = tot["ct"] / 60.0 / tot["mn"], tot["sb"] / tot["mn"]
    g_dur = tot["mn"] / max(tot["fs"], 1)

    met = {}
    for i, x in A.items():
        f = fighters.get(i)
        if not f or f["n"] < CARD_MIN_FIGHTS or x["mn"] <= CARD_MIN_MIN or "ks" not in f:
            continue
        mn = x["mn"]
        sh = lambda v, g, k=K: (v + g * k) / (mn + k)
        card = lambda v, att, g, k: (v + g * k) / (att + k)
        ratio = ((x["c3"] / x["n3"]) / (x["c1"] / x["n1"])) if x["n3"] >= 2 and x["c1"] > 0 else 1.0
        ratio = (ratio * x["n3"] + 1.0 * 4) / (x["n3"] + 4)
        avg_dur = (mn + g_dur * 4) / (x["fs"] + 4)
        wins = sum(f["w"])
        ko_rate = (f["w"][0] + 0.8) / (wins + 6)
        sub_rate = (f["w"][1] + 0.6) / (wins + 6)
        
        met[i] = {
            "tro": [sh(x["sl"], g_sl), card(x["sl"], x["sat"], g_acc, 70), f["ks"]],
            "def": [1 - card(x["sa"], x["oat"], g_acc, 70), -sh(x["sa"], g_sl), 1 - card(x["otl"], x["ota"], g_ta, 10), -f["kas"]],
            "lut": [15 * sh(x["tl"], g_tl), card(x["tl"], x["ta"], g_ta, 10), sh(x["ct"] / 60.0, g_ct)],
            "sub": [15 * sh(x["sb"], g_sb), sub_rate],
            "peg": [f["ks"], ko_rate],
            "car": [ratio, avg_dur],
        }

    groups = defaultdict(list)
    for i in met:
        groups[fighters[i].get("div_main", fighters[i]["div"])].append(i)
    big = {d: ids for d, ids in groups.items() if len(ids) >= 12}
    pools = {i: (d if d in big else "ALL") for d, ids in groups.items() for i in ids}
    members = defaultdict(list)
    for i, d in pools.items():
        members[d].append(i)

    raw = {}
    for d, ids in members.items():
        if d == "ALL":
            ids = list(met)
        z = {}
        for key in ("tro", "def", "lut", "sub", "peg", "car"):
            cols = []
            for j in range(len(met[ids[0]][key])):
                vals = [met[i][key][j] for i in ids]
                mu = sum(vals) / len(vals)
                sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals)) or 1.0
                cols.append([(v - mu) / sd for v in vals])
            wt = CARD_W[key]
            z[key] = [sum(w * c[k] for w, c in zip(wt, cols)) / sum(wt) for k in range(len(ids))]

        for k, i in enumerate(ids):
            if pools[i] != d and d != "ALL":
                continue
            f = fighters[i]
            elo_cur = f["e"]
            elo_pk = f["pk"]
            opp_elo = f.get("opp") or BASE
            qw_elo = f.get("qw") or opp_elo
            tw = f.get("tw", 0)
            tf = f.get("tf", 0)

            # Ajuste científico de Força de Calendário (SoS):
            # Quem enfrenta oponentes com média > 1540 ganha bônus nos atributos; < 1490 sofre desconto
            sos_adj = max(-0.45, min(0.55, (opp_elo - 1510.0) / 110.0)) + max(-0.20, min(0.35, (elo_cur - 1520.0) / 350.0))

            tro = z_to_fifa_rating(z["tro"][k], sos_adj * 0.85)
            dfn = z_to_fifa_rating(z["def"][k], sos_adj * 0.80)
            lut = z_to_fifa_rating(z["lut"][k], sos_adj * 0.85)
            sub = z_to_fifa_rating(z["sub"][k], sos_adj * 0.75)
            peg = z_to_fifa_rating(z["peg"][k], sos_adj * 0.80)
            car = z_to_fifa_rating(z["car"][k], sos_adj * 0.60)

            # ----- Overall (OVR): 1ª passagem, nota BRUTA em escala livre -----
            # A nota final só é fechada depois, quando toda a população já foi pontuada
            # (ver calibrate_ovr): assim o intervalo 48-98 é sempre ocupado por inteiro.

            # 1) Nota Técnica ponderando as especialidades (impede que striker puro ou grappler puro seja punido)
            s_attrs = sorted([tro, dfn, lut, sub, peg, car], reverse=True)
            tech_ovr = (0.30 * s_attrs[0] + 0.25 * s_attrs[1] + 0.20 * s_attrs[2] +
                        0.12 * s_attrs[3] + 0.08 * s_attrs[4] + 0.05 * s_attrs[5])

            # 2) Dominância/ELO: posição RELATIVA na população, não limiares absolutos.
            #    (o ELO de pico real do acervo chega a ~1820, então cortes fixos de
            #     1780/1830 eram inalcançáveis e achatavam todo mundo no mesmo valor)
            elo_comp = 0.50 * elo_cur + 0.30 * elo_pk + 0.20 * qw_elo

            # 3) Currículo em disputas de cinturão, com retorno decrescente
            title_bonus = TITLE_CAP * (1.0 - math.exp(-TITLE_RATE * tw)) + (0.8 if tf > 0 and tw == 0 else 0.0)

            raw[i] = {"tech": tech_ovr, "elo_comp": elo_comp, "pk": elo_pk,
                      "title": title_bonus, "n": f["n"], "attrs": [tro, dfn, lut, sub, peg, car], "d": d,
                      "divs": [x[0] for x in f.get("divs", []) if x[0] not in NONSTD] or [f["div"]]}

    return calibrate_ovr(raw)


# ---------- 6b) Calibração do OVR na população inteira ----------
# Sem isto o OVR vira um amontoado: as notas brutas ficam num intervalo estreito e
# qualquer teto/piso fixo cola dezenas de lutadores no MESMO número. Aqui a nota
# bruta é convertida em posição percentil e a posição é esticada por uma normal,
# o que garante: (a) intervalo completo OVR_LOW..OVR_HIGH, (b) poucos no topo e
# poucos no fundo, muitos no meio, (c) nenhum buraco na escala.
OVR_LOW, OVR_HIGH = 48, 98
OVR_MU, OVR_SD = 72.0, 8.2        # centro e dispersão da curva final
W_TECH, W_ELO = 0.42, 0.53        # peso da nota técnica e da dominância
TITLE_CAP, TITLE_RATE = 6.0, 0.55  # bônus máximo de cinturão e velocidade de saturação
LEGACY_BONUS = 3.5                # prêmio para o pico de ELO no topo 10% histórico
PRIOR_N = 4                       # lutas-fantasma: puxa cartel curto para a média
PROVISIONAL_N = 4                 # abaixo disso o card é marcado como provisório na interface


def _ranker(values):
    """Devolve f(v) = percentil de v na população (média entre empates)."""
    s = sorted(values)
    n = float(len(s)) or 1.0
    def rank(v):
        return (bisect.bisect_left(s, v) + bisect.bisect_right(s, v)) / (2.0 * n)
    return rank


def _probit(p):
    """Inversa da normal padrão (algoritmo de Acklam). Converte percentil em z."""
    p = min(1.0 - 1e-6, max(1e-6, p))
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - lo:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def calibrate_ovr(raw):
    """2ª passagem: nota bruta -> percentil -> OVR final na escala 48-98."""
    if not raw:
        return None
    ids = list(raw)
    p_elo = _ranker([raw[i]["elo_comp"] for i in ids])
    p_pk = _ranker([raw[i]["pk"] for i in ids])

    score = {}
    for i in ids:
        r = raw[i]
        # dominância já na escala da nota (percentil esticado sobre o intervalo)
        elo_ovr = OVR_LOW + (OVR_HIGH - OVR_LOW) * p_elo(r["elo_comp"])
        # prêmio de legado: só para quem esteve no topo 10% de pico histórico
        legacy = LEGACY_BONUS * max(0.0, p_pk(r["pk"]) - 0.90) / 0.10
        s = W_TECH * r["tech"] + W_ELO * elo_ovr + r["title"] + legacy
        # encolhimento por amostra: cartel curto não ocupa extremo da escala
        score[i] = (s * r["n"] + OVR_MU * PRIOR_N) / (r["n"] + PRIOR_N)

    p_score = _ranker(list(score.values()))
    out = {}
    for i in ids:
        v = OVR_MU + OVR_SD * _probit(p_score(score[i]))
        ovr = int(round(min(float(OVR_HIGH), max(float(OVR_LOW), v))))
        # [ovr, 6 atributos, grupo de comparação, nº de lutas UFC, divisões (atual primeiro)]
        out[i] = [ovr, *raw[i]["attrs"], raw[i]["d"], raw[i]["n"], raw[i]["divs"]]

    vals = [v[0] for v in out.values()]
    return {"v": 3, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "names": ["ovr", "tro", "def", "lut", "sub", "peg", "car", "pool", "n", "divs"],
            "min_fights": CARD_MIN_FIGHTS, "provisional_below": PROVISIONAL_N,
            "ovr_scale": {"low": OVR_LOW, "high": OVR_HIGH, "mu": OVR_MU, "sd": OVR_SD,
                          "w_tech": W_TECH, "w_elo": W_ELO, "title_cap": TITLE_CAP,
                          "observed": [min(vals), max(vals)], "n": len(vals)},
            "cards": out}


# ---------- 7) validação estatística do motor (Brier Score, Log-Loss e Calibração) ----------
def run_validation(fights, pre_elo):
    """Avalia o poder preditivo fora da amostra do ELO pré-luta (sem data leakage)."""
    brier = logloss = acc = n = 0
    bins = defaultdict(lambda: [0, 0.0, 0.0])  # decil -> [count, sum_pred, sum_actual]
    for f in fights:
        if f["res"] not in ("a", "b") or f["id"] not in pre_elo:
            continue
        ea, eb = pre_elo[f["id"]]
        if ea == BASE and eb == BASE:
            continue  # ignora lutas entre dois estreantes absolutos sem histórico
        p_a = 1.0 / (1.0 + 10 ** ((eb - ea) / 400.0))
        y = 1.0 if f["res"] == "a" else 0.0
        brier += (p_a - y) ** 2
        p_clip = min(0.999, max(0.001, p_a))
        logloss -= y * math.log(p_clip) + (1.0 - y) * math.log(1.0 - p_clip)
        if p_a != 0.5:
            acc += (p_a > 0.5) == (y == 1.0)
        b_idx = min(9, int(p_a * 10))
        bins[b_idx][0] += 1
        bins[b_idx][1] += p_a
        bins[b_idx][2] += y
        n += 1
    if not n:
        return None
    cal = []
    for k in range(10):
        cnt, sp, sy = bins[k]
        if cnt:
            cal.append({"bin": k, "n": cnt, "pred": round(sp / cnt, 4), "obs": round(sy / cnt, 4)})
    return {
        "v": 1,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elo_eval": {
            "n_fights": n,
            "accuracy": round(acc / n, 4),
            "brier_score": round(brier / n, 4),
            "log_loss": round(logloss / n, 4),
            "calibration": cal
        }
    }


# ---------- montagem ----------
def main():
    fights = load_fights()
    if not fights:
        print("analytics: data/fights.json ausente ou vazio; nada a fazer.")
        return 0
    pre_elo = {}
    elo = run_elo(fights, pre_elo)
    dmg, p0 = run_damage(fights)
    bench = run_benchmarks(fights)
    k100_lg = 100 * p0
    fighters = {}
    for i, e in elo.items():
        d = dmg.get(i)
        wins = sum(e["w"])
        top3 = sorted(e["wins_opp"], reverse=True)[:3]
        cur_div, main_div, all_divs = division_profile(e)
        row = {"n": e["n"], "e": round(e["r"], 1), "pk": round(e["pk"], 1),
               "opp": r1(sum(e["opp"]) / len(e["opp"])) if e["opp"] else None,
               "qw": r1(sum(top3) / len(top3)) if top3 else None,
               "w": e["w"], "l": e["l"], "d": e["d"],
               "tw": e["tw"], "tf": e["tf"],
               "last": e["last"],
               "div": cur_div, "div_main": main_div, "divs": all_divs,
               "fin": round((e["w"][0] + e["w"][1]) / wins, 3) if wins else None}
        if d and d["fs"]:
            sl, sa, kd, ka = d["sl"], d["sa"], d["kd"], d["ka"]
            ks = 100 * (kd + p0 * PRIOR_STRIKES) / (sl + PRIOR_STRIKES)
            kas = 100 * (ka + p0 * PRIOR_STRIKES) / (sa + PRIOR_STRIKES)
            ss = (sl + PRIOR_STRIKES) / (kd + p0 * PRIOR_STRIKES) if (kd + p0 * PRIOR_STRIKES) else None
            row.update({"fs": d["fs"], "sl": int(sl), "sa": int(sa), "kd": int(kd), "ka": int(ka),
                        "k100": r1(100 * kd / sl, 2) if sl else None, "spk": r1(sl / kd, 0) if kd else None,
                        "ks": round(ks, 3), "ss": r1(ss, 0), "kas": round(kas, 3),
                        "dli": round(100 * ks / k100_lg) if k100_lg else None})
        fighters[i] = row
    out = {
        "v": 2,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {"base": BASE, "k": [K_NEW, K_MID, K_VET], "title": TITLE_MULT, "prior_strikes": PRIOR_STRIKES,
                   "ko": KO_MULT, "sub": SUB_MULT, "dec": DEC_MULT},
        "league": {"k100": round(k100_lg, 3), "spk": round(1 / p0, 1) if p0 else None},
        "divisions": bench,
        "fighters": fighters,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "analytics.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    size = (DATA / "analytics.json").stat().st_size / 1024
    print(f"analytics: {len(fighters)} lutadores, {len(bench) - 1} divisões, {size:.0f} KB -> data/analytics.json")
    try:
        dec = run_decisions(fights)
        if dec:
            (DATA / "decisions.json").write_text(json.dumps(dec, ensure_ascii=False, separators=(",", ":")), "utf-8")
            m = dec["model"]
            print(f"decisions: {m['n']} decisões, concordância {m['acc']*100:.1f}% (validação cruzada), "
                  f"classes {m['classes']} -> data/decisions.json")
        else:
            print("decisions: poucas decisões com estatísticas; nada gerado.")
    except Exception as ex:
        print(f"decisions: erro ({ex}); decisions.json não foi atualizado.")
    for nome, fn in (
        ("live", lambda: run_live(fights, pre_elo)),
        ("cards", lambda: run_cards(fights, fighters)),
        ("validation", lambda: run_validation(fights, pre_elo)),
    ):
        try:
            res = fn()
            if res:
                (DATA / f"{nome}.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), "utf-8")
                n = len(res["fights"]) if nome == "live" else len(res["cards"]) if nome == "cards" else res["elo_eval"]["n_fights"]
                print(f"{nome}: {n} registros -> data/{nome}.json")
            else:
                print(f"{nome}: dados insuficientes; nada gerado.")
        except Exception as ex:
            print(f"{nome}: erro ({ex}); data/{nome}.json não foi atualizado.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        print(f"analytics: erro ({ex}); analytics.json não foi atualizado.")
        sys.exit(0)
