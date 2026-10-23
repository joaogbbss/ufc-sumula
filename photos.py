#!/usr/bin/env python3
"""photos.py (v2, em ONDAS): junta fotos VERIFICADAS dos lutadores a partir de várias fontes e grava data/photos.json.

Ondas (cada uma tenta uma fonte/estratégia; rode várias vezes e a cobertura só cresce):
  1 audit     confere o espn_id que o scraper já guardou (nome e ano de nascimento batem?) e verifica se a foto existe
  2 espn      procura na ESPN por nome EXATO (sem "pegar o primeiro resultado") e confirma pelo ano de nascimento
  3 wikidata  Wikidata (aberto): nome + data de nascimento -> imagem da Wikimedia Commons (licença livre, dar crédito)
  4 ufc       página do atleta no ufc.com (og:image), recusando imagens genéricas
  5 relaxed   variações do nome (sem Jr., sem apelido, nome do meio, ordem invertida), exigindo ano de nascimento

Regras: só grava foto quando (a) o nome bate, (b) o ano de nascimento bate quando as duas fontes o informam, e (c) a imagem
responde 200 com tipo image/*. Foto errada é pior que nenhuma. Prioridade: lutadores dos próximos eventos, depois os ativos
recentes, depois os veteranos, depois o resto. Cada fonte tem disjuntor: se falhar muitas vezes seguidas, é pulada na execução.

Uso: python photos.py [--wave auto|all|1..5|audit,espn,...] [--limit 500] [--max-minutes 25] [--delay 0.2]
Somente biblioteca padrão.
"""
import argparse, json, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path("data"); OUT = DATA / "photos.json"; REPORT = DATA / "photos_report.json"
UA = "Mozilla/5.0 (arquivo pessoal de estatisticas UFC)"
ESPN_SEARCH = "https://site.web.api.espn.com/apis/common/v3/search?query={q}&limit=8&type=player"
ESPN_ATHLETE = "https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/athletes/{id}"
HEADSHOT = "https://a.espncdn.com/i/headshots/mma/players/full/{id}.png"
WD = "https://www.wikidata.org/w/api.php?format=json&"
COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/{f}?width=300"
UFC = "https://www.ufc.com/athlete/{slug}"
STAGES = ["audit", "espn", "wikidata", "ufc", "relaxed"]
GENERIC = ("default", "placeholder", "silhouette", "no-image", "noimage", "generic", "athlete_bio_full_body_default")


# ---------- rede (isolada para teste) ----------
def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,image/*,*/*", "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, "", b""


class Src:
    """Disjuntor por fonte: muitas falhas seguidas desligam a fonte nesta execução."""
    def __init__(self, name, limit=12): self.name, self.limit, self.fails, self.off, self.calls = name, limit, 0, False, 0
    def ok(self): self.fails = 0
    def fail(self, why=""):
        self.fails += 1
        if self.fails >= self.limit and not self.off:
            self.off = True; print(f"photos: fonte '{self.name}' desligada nesta execução ({self.fails} falhas seguidas; {why})")


SRC = {k: Src(k) for k in ("espn", "wikidata", "ufc")}


def fetch(src, url):
    s = SRC[src]
    if s.off: return 0, "", b""
    s.calls += 1
    try: st, ct, body = http_get(url)
    except Exception as ex: s.fail(str(ex)[:60]); return 0, "", b""
    (s.ok() if st == 200 else s.fail(f"HTTP {st}"))
    return st, ct, body


def jget(src, url):
    st, _, body = fetch(src, url)
    if st != 200 or not body: return None
    try: return json.loads(body.decode("utf-8", "replace"))
    except ValueError: return None


def is_image(src, url):
    st, ct, body = fetch(src, url)
    return st == 200 and ct.lower().startswith("image") and len(body) > 200


# ---------- nomes e datas ----------
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def year_of(s):
    m = re.search(r"(19|20)\d\d", str(s or "")); return int(m.group(0)) if m else None


def year_ok(a, b): return a is None or b is None or abs(a - b) <= 1


def variants(name):
    base = norm(name); n = re.sub(r"[\"“”'‘’].*?[\"“”'‘’]", " ", name)
    toks = n.split(); suff = {"jr", "sr", "ii", "iii", "iv"}; t2 = [t for t in toks if norm(t) not in suff]
    cand = [" ".join(t2), " ".join([t2[0], t2[-1]]) if len(t2) > 2 else None, " ".join(t2[::-1]) if len(t2) == 2 else None, name.replace("-", " ")]
    out, seen = [], {base}
    for c in cand:
        if c and norm(c) not in seen: seen.add(norm(c)); out.append(c)
    return out


# ---------- ESPN ----------
def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)


def espn_cands(data):
    seen, out = set(), []
    for d in walk(data):
        name = d.get("displayName") or d.get("fullName") or d.get("name"); pid = str(d.get("id") or "")
        if not pid.isdigit():
            m = re.search(r"a:(\d+)", str(d.get("uid") or "")); pid = m.group(1) if m else ""
        if not name or not pid or pid in seen: continue
        b = json.dumps(d).lower()
        if "mma" not in b and "ufc" not in b: continue
        seen.add(pid); out.append((pid, name))
    return out


def espn_detail(pid):
    d = jget("espn", ESPN_ATHLETE.format(id=pid))
    a = (d or {}).get("athlete") if isinstance(d, dict) else None
    return a if isinstance(a, dict) else (d if isinstance(d, dict) else {})


def ath_name(a): return a.get("displayName") or a.get("fullName") or a.get("name")
def ath_year(a):
    for k in ("dateOfBirth", "birthDate", "dob"):
        if a.get(k): return year_of(a[k])
def ath_img(a):
    h = a.get("headshot"); return (h.get("href") if isinstance(h, dict) else h) or None


def espn_photo(pid, ath):
    u = ath_img(ath)
    if u and is_image("espn", u): return u
    u = HEADSHOT.format(id=pid)
    return u if is_image("espn", u) else None


def stage_audit(f, ctx):
    pid = str(f.get("espn_id") or "")
    if not pid: return "skip"
    ath = espn_detail(pid)
    if not ath: return None
    if norm(ath_name(ath)) != norm(f["name"]) or not year_ok(year_of(f.get("DOB")), ath_year(ath)):
        ctx["bad"][f["id"]] = pid; return None       # o ID guardado é de OUTRA pessoa: nunca usar a foto dele
    u = espn_photo(pid, ath)
    return {"u": u, "s": "espn", "e": pid} if u else None


def espn_search(f, name, need_dob):
    data = jget("espn", ESPN_SEARCH.format(q=urllib.parse.quote(name)))
    if not data: return None
    want, dy = norm(name), year_of(f.get("DOB")); ok = [(p, n) for p, n in espn_cands(data) if norm(n) == want][:3]
    for pid, _ in ok:
        ath = espn_detail(pid); ay = ath_year(ath)
        if need_dob and not (dy and ay and year_ok(dy, ay)): continue
        if not year_ok(dy, ay): continue
        if ay is None and len(ok) > 1: continue          # homônimos sem data para desempatar: não chuta
        u = espn_photo(pid, ath)
        if u: return {"u": u, "s": "espn", "e": pid}
    return None


def stage_espn(f, ctx): return espn_search(f, f["name"], False)


# ---------- Wikidata ----------
def wd_search(f, name, need_dob):
    q = urllib.parse.quote(name); data = jget("wikidata", WD + f"action=wbsearchentities&search={q}&language=en&type=item&limit=7")
    ids = [x["id"] for x in (data or {}).get("search", []) if "mixed martial" in (x.get("description") or "").lower() and norm(x.get("label")) == norm(name)]
    if not ids: return None
    ent = jget("wikidata", WD + "action=wbgetentities&props=claims&ids=" + "|".join(ids[:4]))
    dy, hits = year_of(f.get("DOB")), []
    for qid in ids[:4]:
        cl = ((ent or {}).get("entities", {}).get(qid, {}) or {}).get("claims", {})
        def val(p):
            try: return cl[p][0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError, TypeError): return None
        b, img = val("P569"), val("P18"); by = year_of(b["time"]) if isinstance(b, dict) else None
        if not img or (need_dob and not (dy and by)) or not year_ok(dy, by): continue
        hits.append((qid, img))
    if len(hits) != 1: return None                       # nenhum ou ambíguo: não chuta
    u = COMMONS.format(f=urllib.parse.quote(hits[0][1].replace(" ", "_")))
    return {"u": u, "s": "wikidata", "w": hits[0][0]} if is_image("wikidata", u) else None


def stage_wikidata(f, ctx): return wd_search(f, f["name"], False)


# ---------- ufc.com ----------
def stage_ufc(f, ctx):
    slug = "-".join(norm(f["name"]).split())
    st, _, body = fetch("ufc", UFC.format(slug=slug))
    if st != 200 or not body: return None
    html = body.decode("utf-8", "replace")
    img = re.search(r'property="og:image"\s+content="([^"]+)"', html) or re.search(r'content="([^"]+)"\s+property="og:image"', html)
    ttl = re.search(r'property="og:title"\s+content="([^"]+)"', html) or re.search(r'<title>([^<]+)</title>', html)
    if not img or not ttl or not all(t in norm(ttl.group(1)) for t in norm(f["name"]).split()): return None
    u = img.group(1).replace("&amp;", "&")
    if any(g in u.lower() for g in GENERIC): return None
    return {"u": u, "s": "ufc"} if is_image("ufc", u) else None


# ---------- nomes alternativos (sempre exigindo o ano de nascimento) ----------
def stage_relaxed(f, ctx):
    if not year_of(f.get("DOB")): return None
    for v in variants(f["name"]):
        r = espn_search(f, v, True) or wd_search(f, v, True)
        if r: return r
    return None


FUNCS = {"audit": stage_audit, "espn": stage_espn, "wikidata": stage_wikidata, "ufc": stage_ufc, "relaxed": stage_relaxed}
NEEDS = {"espn": "espn", "wikidata": "wikidata", "ufc": "ufc", "audit": "espn", "relaxed": "espn"}


# ---------- orquestração ----------
def load(p, default): return json.loads(p.read_text("utf-8")) if p.exists() else default


def tiers_of(fighters):
    up = {s["id"] for e in load(DATA / "upcoming.json", {}).get("events", []) for ft in e.get("fights", []) for s in (ft["a"], ft["b"])}
    last, n, cut = {}, {}, (date.today() - timedelta(days=730)).isoformat()
    for ft in load(DATA / "fights.json", []):
        for s in "ab":
            i = ft[s]["id"]; last[i] = max(last.get(i, ""), ft.get("date", "")); n[i] = n.get(i, 0) + 1
    tier = {f["id"]: 1 if f["id"] in up else 2 if last.get(f["id"], "") >= cut else 3 if n.get(f["id"], 0) >= 4 else 4 for f in fighters}
    return tier, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="auto"); ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--max-minutes", type=float, default=25); ap.add_argument("--delay", type=float, default=0.2)
    ap.add_argument("--retry-days", type=int, default=45)
    a = ap.parse_args()
    fighters = load(DATA / "fighters.json", [])
    if not fighters: print("photos: data/fighters.json ausente; nada a fazer."); return 0
    store = load(OUT, {}); ctx = {"bad": store.get("bad", {})}
    P, SRCM, STATE, EID = store.get("photos", {}), store.get("src", {}), store.get("state", {}), store.get("eid", {})
    tier, last = tiers_of(fighters); today = date.today(); t0 = time.time()
    order = sorted(fighters, key=lambda f: (tier[f["id"]], "".join(chr(255 - ord(c)) for c in last.get(f["id"], ""))))
    def eligible(f, st):
        if f["id"] in P: return False
        if st == "audit" and (not f.get("espn_id") or f["id"] in ctx["bad"]): return False
        d = STATE.get(f["id"], {}).get("s", {}).get(st)
        return d is None or (today - date.fromisoformat(d)).days >= a.retry_days
    if a.wave == "auto":
        stages = next(([s] for s in STAGES if any(eligible(f, s) for f in order)), [])
    elif a.wave == "all": stages = STAGES
    else: stages = [STAGES[int(w) - 1] if w.isdigit() else w for w in a.wave.split(",")]
    print(f"photos: {len(P)}/{len(fighters)} com foto | onda(s): {', '.join(stages) or 'nenhuma pendente'}")
    def save():
        DATA.mkdir(exist_ok=True)
        rej = sorted(set(ctx["bad"]) | {i for i, v in STATE.items() if "audit" in v.get("s", {}) and i not in P})   # o app esconde a foto NÃO verificada do scraper
        OUT.write_text(json.dumps({"v": 2, "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "photos": P, "src": SRCM,
                                   "eid": EID, "bad": ctx["bad"], "rej": rej, "state": STATE}, ensure_ascii=False, separators=(",", ":")), "utf-8")
    new, tried, out_of_time = {}, 0, False
    for f in order:
        if tried >= a.limit: break
        if (time.time() - t0) / 60 >= a.max_minutes: out_of_time = True; break
        todo = [s for s in stages if eligible(f, s) and not SRC[NEEDS[s]].off]
        if not todo: continue
        tried += 1
        for st in todo:
            try: r = FUNCS[st](f, ctx)
            except Exception as ex: r = None; print(f"photos: erro em {st} ({f['name']}): {str(ex)[:80]}")
            if r != "skip": STATE.setdefault(f["id"], {}).setdefault("s", {})[st] = today.isoformat()
            if isinstance(r, dict):
                P[f["id"]] = r["u"]; SRCM[f["id"]] = r["s"]; new[r["s"]] = new.get(r["s"], 0) + 1
                if r.get("e"): EID[f["id"]] = r["e"]
                break
        time.sleep(a.delay)
        if tried % 40 == 0: save()
    save()
    cov = lambda t: (sum(1 for f in fighters if tier[f["id"]] == t and f["id"] in P), sum(1 for f in fighters if tier[f["id"]] == t))
    rep = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "total": [len(P), len(fighters)], "por_fonte": {s: list(SRCM.values()).count(s) for s in set(SRCM.values())},
           "por_prioridade": {"proximos_eventos": cov(1), "ativos_2_anos": cov(2), "veteranos_4plus": cov(3), "demais": cov(4)}, "ids_da_espn_recusados": len(ctx["bad"]),
           "pendentes_por_onda": {s: sum(1 for f in fighters if eligible(f, s)) for s in STAGES}, "fontes_desligadas": [k for k, v in SRC.items() if v.off]}
    REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
    print(f"photos: +{sum(new.values())} fotos novas {new or ''} em {tried} lutadores{' (tempo esgotado)' if out_of_time else ''}; cobertura {len(P)}/{len(fighters)} ({len(P)/len(fighters)*100:.0f}%)")
    for k, v in rep["por_prioridade"].items(): print(f"   {k:18s} {v[0]}/{v[1]}")
    print(f"   pendentes por onda: {rep['pendentes_por_onda']}")
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as ex: print(f"photos: erro ({ex}); photos.json não foi atualizado."); sys.exit(0)
