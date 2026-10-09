#!/usr/bin/env python3
"""analytics.py: consolida estatísticas avançadas a partir de data/fights.json.

Roda logo depois do scraper.py e grava um arquivo leve: data/analytics.json
O navegador só lê esse arquivo (nada pesado é calculado no celular).
Usa somente a biblioteca padrão do Python.

Três blocos:
  1. ELO dinâmico por nível de oposição (peso pelo método e pelo round do desfecho).
  2. DLI, Índice de Dano e Letalidade Efetiva (knockdowns por 100 golpes e golpes por knockdown).
  3. Benchmarks por divisão (% de KO, finalização e decisão, duração, volume).
  4. Checagem de decisões ("roubo?"): quanto o resultado oficial destoa dos números (data/decisions.json).
"""
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
K_NEW, K_MID, K_VET = 40.0, 32.0, 24.0   # K maior para quem tem pouca história (ELO dinâmico)
TITLE_MULT = 1.15             # lutas de cinturão pesam um pouco mais
PRIOR_STRIKES = 1500          # "pseudo-golpes" (~4 knockdowns de dúvida inicial): knockdown é raro, então amostras pequenas
                              # precisam de encolhimento forte. Calibrado em simulação: 1 KD em 20 golpes deixa de parecer elite.
KO_MULT = {1: 1.50, 2: 1.40, 3: 1.30}      # KO/TKO: round do desfecho -> multiplicador (4+ = 1.25)
SUB_MULT = {1: 1.45, 2: 1.35, 3: 1.25}     # finalização (4+ = 1.20)
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
        m = KO_MULT.get(rnd, 1.25)
    elif kind == "sub":
        m = SUB_MULT.get(rnd, 1.20)
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


# ---------- 1) ELO dinâmico ----------
def run_elo(fights):
    st = {}

    def get(i):
        if i not in st:
            st[i] = {"r": BASE, "pk": BASE, "n": 0, "opp": [], "wins_opp": [], "w": [0] * 4, "l": [0] * 4,
                     "d": 0, "last": "", "divs": Counter()}
        return st[i]

    for f in fights:
        A, B = get(f["a"]["id"]), get(f["b"]["id"])
        ea = 1.0 / (1.0 + 10 ** ((B["r"] - A["r"]) / 400.0))
        s = 1.0 if f["res"] == "a" else 0.0 if f["res"] == "b" else 0.5
        m = multiplier(f)
        da = k_factor(A["n"]) * m * (s - ea)
        db = k_factor(B["n"]) * m * ((1 - s) - (1 - ea))
        kind = KEYS.index(klass(f.get("method"))[0])
        A["opp"].append(B["r"])
        B["opp"].append(A["r"])
        if f["res"] == "a":
            A["wins_opp"].append(B["r"]); A["w"][kind] += 1; B["l"][kind] += 1
        elif f["res"] == "b":
            B["wins_opp"].append(A["r"]); B["w"][kind] += 1; A["l"][kind] += 1
        else:
            A["d"] += 1; B["d"] += 1
        for X, d in ((A, da), (B, db)):
            X["r"] += d
            X["pk"] = max(X["pk"], X["r"])
            X["n"] += 1
            X["last"] = f["date"]
            X["divs"][f["div"]] += 1
    return st


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


DEC_GROUPS = {"strike": [0, 1, 6], "grap": [2, 4, 7], "sub": [5], "kd": [3]}   # variáveis correlacionadas ficam no mesmo grupo


def cv_logloss(rows, drop=()):
    """Log-loss da validação cruzada sem as variáveis em `drop` (importância por grupo, não por coeficiente)."""
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
        fl = zlib.crc32(f["id"].encode()) & 1          # orientação aleatória: o ufcstats sempre lista o vencedor primeiro
        sign = -1.0 if fl else 1.0
        x = [sign * sum(v[j] for v in vs) for j in range(len(DEC_NAMES))]
        subj_won = (f["res"] == "a") != bool(fl)
        rows.append({"id": f["id"], "x": x, "y": 1.0 if subj_won else 0.0, "rv": [[sign * c for c in v] for v in vs],
                     "fold": zlib.crc32(f["id"].encode()) % FOLDS, "sub": sub, "f": f, "sj": subj_won})
    if len(rows) < 300:
        return None
    full = fit_lr([r["x"] for r in rows], [r["y"] for r in rows])
    models = [fit_lr([r["x"] for r in rows if r["fold"] != k], [r["y"] for r in rows if r["fold"] != k]) for k in range(FOLDS)]
    out, cnt = {}, Counter()
    agree, ll, by = 0, 0.0, defaultdict(lambda: [0, 0])
    for r in rows:
        m = models[r["fold"]]                           # modelo que NÃO viu esta luta (validação cruzada)
        p = sig_(lr_logit(m, r["x"]))
        po = p if r["y"] == 1.0 else 1.0 - p            # P(vencedor oficial | números)
        cls = 0 if po >= CLS_CUTS[0] else 1 if po >= CLS_CUTS[1] else 2 if po >= CLS_CUTS[2] else 3
        cnt[cls] += 1
        agree += po > 0.5
        ll -= math.log(max(po, 1e-6))
        by[r["sub"]][0] += po > 0.5
        by[r["sub"]][1] += 1
        flip = 1.0 if r["sj"] else -1.0                 # contribuição de cada round do ponto de vista do vencedor oficial
        rs = [round(flip * lr_logit(m, v), 2) for v in r["rv"]]
        f = r["f"]
        sc = judge_scores(f.get("detail"))
        if sc and f["res"] == "b":
            sc = [(y, x) for x, y in sc]                # primeiro número = lutador listado primeiro (A)
        out[r["id"]] = [round(po, 3), cls, (r["sub"] or "unanimous")[0], ",".join(f"{x}-{y}" for x, y in sc), rs]
    n = len(rows)
    model = {"n": n, "acc": round(agree / n, 4), "ll": round(ll / n, 4),
             "acc_by": {k: [round(v[0] / v[1], 4), v[1]] for k, v in by.items()},
             "classes": [cnt[i] for i in range(4)], "cuts": list(CLS_CUTS), "folds": FOLDS, "names": DEC_NAMES,
             "imp": {g: round(cv_logloss(rows, ix) - ll / n, 4) for g, ix in DEC_GROUPS.items()},   # piora do log-loss sem o grupo
             "b": [round(full["b"][j] / full["sd"][j], 4) for j in range(len(DEC_NAMES))],
             "se": [round(full["se"][j] / full["sd"][j], 4) for j in range(len(DEC_NAMES))]}
    return {"v": 1, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model, "fights": out}


# ---------- montagem ----------
def main():
    fights = load_fights()
    if not fights:
        print("analytics: data/fights.json ausente ou vazio; nada a fazer.")
        return 0
    elo = run_elo(fights)
    dmg, p0 = run_damage(fights)
    bench = run_benchmarks(fights)
    k100_lg = 100 * p0
    fighters = {}
    for i, e in elo.items():
        d = dmg.get(i)
        wins = sum(e["w"])
        top3 = sorted(e["wins_opp"], reverse=True)[:3]
        row = {"n": e["n"], "e": round(e["r"], 1), "pk": round(e["pk"], 1),
               "opp": r1(sum(e["opp"]) / len(e["opp"])) if e["opp"] else None,
               "qw": r1(sum(top3) / len(top3)) if top3 else None,
               "w": e["w"], "l": e["l"], "d": e["d"], "last": e["last"],
               "div": e["divs"].most_common(1)[0][0],
               "fin": round((e["w"][0] + e["w"][1]) / wins, 3) if wins else None}
        if d and d["fs"]:
            sl, sa, kd, ka = d["sl"], d["sa"], d["kd"], d["ka"]
            ks = 100 * (kd + p0 * PRIOR_STRIKES) / (sl + PRIOR_STRIKES)        # knockdowns/100 golpes, encolhido
            kas = 100 * (ka + p0 * PRIOR_STRIKES) / (sa + PRIOR_STRIKES)       # knockdowns sofridos/100 golpes recebidos
            ss = (sl + PRIOR_STRIKES) / (kd + p0 * PRIOR_STRIKES) if (kd + p0 * PRIOR_STRIKES) else None
            row.update({"fs": d["fs"], "sl": int(sl), "sa": int(sa), "kd": int(kd), "ka": int(ka),
                        "k100": r1(100 * kd / sl, 2) if sl else None, "spk": r1(sl / kd, 0) if kd else None,
                        "ks": round(ks, 3), "ss": r1(ss, 0), "kas": round(kas, 3),
                        "dli": round(100 * ks / k100_lg) if k100_lg else None})
        fighters[i] = row
    out = {
        "v": 1,
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
    except Exception as ex:  # a checagem de decisões nunca derruba o resto
        print(f"decisions: erro ({ex}); decisions.json não foi atualizado.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:  # nunca derruba o pipeline: o scraper já gravou os dados
        print(f"analytics: erro ({ex}); analytics.json não foi atualizado.")
        sys.exit(0)
