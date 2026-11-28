#!/usr/bin/env python3
"""Scraper do UFC Stats (ufcstats.com) + Enriquecimento via ESPN API.

1ª execução: baixa tudo (eventos, lutas com estatísticas, lutadores).
Demais execuções: só eventos novos + reprocessa os últimos N eventos
(o site às vezes corrige resultados) + enriquece fichas com fotos PNG,
país/bandeira e academia (ESPN API).
Se o tempo acabar, salva o progresso e continua de onde parou na próxima execução.

Uso: python scraper.py [--max-minutes 300] [--refresh 3] [--enrich-limit 150]
"""
import argparse
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

BASE = "http://ufcstats.com"
ESPN_SEARCH_API = "https://site.web.api.espn.com/apis/common/v3/search"
OUT = Path("data")
DELAY = 0.7

DIVS = [
    "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
    "Women's Featherweight", "Light Heavyweight", "Strawweight", "Flyweight",
    "Bantamweight", "Featherweight", "Lightweight", "Welterweight",
    "Middleweight", "Heavyweight", "Catch Weight", "Open Weight"
]

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})
DATE_RE = re.compile(r"([A-Z][a-z]{2,8}\.? \d{1,2}, \d{4})")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHALLENGE = "Checking your browser"
_ctx = _page = None
_solved = 0


def _start():
    global _ctx, _page
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"]
    )
    _ctx = browser.new_context(
        user_agent=UA,
        locale="en-US",
        viewport={"width": 1280, "height": 800}
    )
    _page = _ctx.new_page()


def _ok(html):
    """Página completa e real: sem a verificação anti-robô, com corpo e tamanho de página de verdade.
    (Sem isso, o scraper aceitava o ESQUELETO da página durante o recarregamento e achava '0 eventos'.)"""
    return bool(html) and CHALLENGE not in html and "</body>" in html.lower() and len(html) > 1500


def _solve(url):
    """Abre a página no navegador e espera a verificação terminar E a página real carregar por inteiro."""
    global _solved
    _page.goto(url, wait_until="domcontentloaded", timeout=60000)
    for i in range(120):
        time.sleep(1)
        if i in (25, 60, 90):  # se travou num esqueleto, reabre (o cookie da verificação já existe)
            try:
                _page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                pass
        try:
            _page.wait_for_load_state("load", timeout=5000)
            html = _page.content()
        except Exception:  # a página está recarregando
            continue
        if _ok(html):
            _solved += 1
            if _solved <= 3:
                print(f"Verificação do site resolvida ({_solved}).")
            return html
    return ""


def get(url, tries=5):
    if _ctx is None:
        _start()
    for i in range(tries):
        try:
            html = None
            r = _ctx.request.get(url, timeout=30000)  # rápido, usa os cookies do navegador
            if r.status == 200:
                html = r.text()
            if not _ok(html):
                html = _solve(url)
            if _ok(html):
                time.sleep(DELAY)
                return BeautifulSoup(html, "lxml")
            print(f"aviso: página incompleta em {url} ({len(html or '')} bytes), tentativa {i + 1}")
        except Exception as ex:
            print(f"aviso: tentativa {i + 1} falhou em {url}: {str(ex)[:120]}")
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"falha ao baixar {url}")


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def uid(url):
    return url.rstrip("/").split("/")[-1]


def full_url(url):
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "http:" + u
    if u.startswith("/"):
        return BASE + u
    return u


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load(name, default):
    p = OUT / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def parse_date(t):
    for fmt in ("%B %d, %Y", "%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    return t


TOURN_RE = re.compile(
    r"ultimate fighter|\btuf\b|road to ufc|tournament|ultimate ultimate|ultimate japan",
    re.I,
)


def is_ufc_title(title):
    t = (title or "").lower()
    return ("title" in t or "championship" in t) and not TOURN_RE.search(t)


def division(title):
    t = title.replace("Catchweight", "Catch Weight").lower()
    if "superfight" in t:
        return "Open Weight"
    return next((d for d in DIVS if d.lower() in t), "Outros")


# ---------- páginas ufcstats ----------

def list_events():
    soup = get(f"{BASE}/statistics/events/completed?page=all")
    out, seen = [], set()
    for a in soup.select('a[href*="event-details"]'):
        eid = uid(a["href"])
        row = a.find_parent("tr") or a.parent
        m = DATE_RE.search(txt(row))
        if eid in seen or not m:
            continue
        seen.add(eid)
        loc = row.select_one("td.b-statistics__table-col_style_big-top-padding")
        if not loc:
            tds = row.select("td")
            loc = tds[-1] if tds else None
        out.append({
            "id": eid,
            "name": txt(a),
            "date": parse_date(m.group(1)),
            "location": txt(loc)
        })
    if not out:
        print(
            "DIAGNOSTICO: titulo =", txt(soup.title),
            "| links na pagina =", len(soup.select("a")),
            "| tamanho =", len(str(soup))
        )
        print("INICIO DA PAGINA:", re.sub(r"\s+", " ", str(soup))[:800])
    return [e for e in out if re.fullmatch(r"\d{4}-\d\d-\d\d", e["date"])]


def event_fight_urls(eid):
    soup = get(f"{BASE}/event-details/{eid}")
    raw = [r["data-link"] for r in soup.select("[data-link*='fight-details']") if r.get("data-link")]
    if not raw:
        raw = [a["href"] for a in soup.select("a[href*='fight-details']") if a.get("href")]
    return [full_url(u) for u in dict.fromkeys(raw) if full_url(u)]


def parse_tables(s):
    kinds = {"totals": [], "sig": []}
    for t in s.select("table"):
        th = t.select_one("thead")
        heads = [txt(h) for h in th.select("th")] if th else []
        if not heads:
            continue
        rows = []
        for tr in t.select("tbody tr"):
            cells = tr.select("td")
            if not cells:
                continue
            sides = {"a": {}, "b": {}}
            for h, c in zip(heads, cells):
                ps = [txt(p) for p in c.select("p")]
                if h != "Fighter" and len(ps) >= 2:
                    sides["a"][h], sides["b"][h] = ps[0], ps[1]
            rows.append(sides)
        kinds["sig" if "Head" in heads else "totals"].append(rows)
    T, G = kinds["totals"], kinds["sig"]
    return {
        "totals": T[0][0] if T and T[0] else None,
        "sig": G[0][0] if G and G[0] else None,
        "rounds": {
            "totals": T[1] if len(T) > 1 else [],
            "sig": G[1] if len(G) > 1 else []
        }
    }


def _norm_status(raw):
    s = (raw or "").strip().upper()
    if s in ("W", "WIN"):
        return "W"
    if s in ("L", "LOSS"):
        return "L"
    if s in ("D", "DRAW"):
        return "D"
    if s in ("NC", "NO CONTEST"):
        return "NC"
    return s


def parse_fight(url, ev, order):
    s = get(full_url(url))
    ppl = []
    for p in s.select(".b-fight-details__person")[:2]:
        a = p.select_one("a.b-fight-details__person-link") or p.select_one("a[href*='fighter-details']")
        st_el = p.select_one(".b-fight-details__person-status")
        ppl.append({
            "id": uid(a["href"]) if a and a.get("href") else None,
            "name": txt(a),
            "st": _norm_status(txt(st_el))
        })
    if len(ppl) < 2 or not ppl[0]["id"] or not ppl[1]["id"]:
        return None
    st = (ppl[0]["st"], ppl[1]["st"])
    res = (
        "a" if st[0] == "W" else "b" if st[1] == "W"
        else "draw" if "D" in st else "nc" if "NC" in st else None
    )
    if not res:
        return None
    tl = s.select_one(".b-fight-details__fight-title")
    title = txt(tl)
    info = {}
    for it in s.select(".b-fight-details__text-item, .b-fight-details__text-item_first"):
        k, _, v = txt(it).partition(":")
        info[k.strip().lower()] = v.strip()
    ps = s.select("p.b-fight-details__text")
    return {
        "id": uid(url),
        "ev": ev["id"],
        "date": ev["date"],
        "ord": order,
        "a": {"id": ppl[0]["id"], "name": ppl[0]["name"]},
        "b": {"id": ppl[1]["id"], "name": ppl[1]["name"]},
        "res": res,
        "div": division(title),
        "title": is_ufc_title(title),
        "tt": title,
        "bonus": [i["src"].rsplit("/", 1)[-1].split(".")[0] for i in tl.select("img")] if tl else [],
        "method": info.get("method", ""),
        "round": info.get("round", ""),
        "time": info.get("time", ""),
        "fmt": info.get("time format", ""),
        "ref": info.get("referee", ""),
        "detail": txt(ps[1]).split(":", 1)[-1].strip() if len(ps) > 1 else "",
        **parse_tables(s)
    }


def parse_fighter(fid):
    s = get(f"{BASE}/fighter-details/{fid}")
    d = {
        "id": fid,
        "name": txt(s.select_one("span.b-content__title-highlight")),
        "nick": txt(s.select_one("p.b-content__Nickname")),
        "record": txt(s.select_one("span.b-content__title-record")).replace("Record:", "").strip()
    }
    for li in s.select("li.b-list__box-list-item"):
        label = txt(li.select_one("i.b-list__box-item-title"))
        val = txt(li).replace(label, "", 1).strip()
        if label and val:
            d[label.rstrip(":").strip()] = val
    return d


# ---------- enriquecimento externo (ESPN API) ----------

ESPN_V = 2          # versão da verificação: nome exato + ano de nascimento conferido


def _year(t):
    m = re.search(r"(19|20)\d{2}", str(t or ""))
    return int(m.group(0)) if m else None


def _clean_espn(d):
    for k in ("espn_id", "img", "country", "flag", "team", "hometown", "espn_h", "espn_r"):
        d.pop(k, None)


def enrich_fighter_espn(d):
    """Só grava o que a ESPN confirma: nome exato e, quando os dois lados têm data de nascimento, o mesmo ano.
    Erro de rede/servidor não marca o lutador (ele é tentado de novo); 'não achei com certeza' marca e limpa dados antigos."""
    name = d.get("name", "")
    if not name:
        return d
    if d.get("espn_v", 0) >= ESPN_V and not d.get("espn_id"):
        return d                                             # já verificado como 'sem correspondência segura'
    try:
        if d.get("espn_id") and d.get("espn_v", 0) >= ESPN_V:
            cands = [str(d["espn_id"])]                      # id já verificado: só renova os dados do mesmo atleta
        else:
            r = S.get(f"{ESPN_SEARCH_API}?query={quote_plus(name)}&limit=8&type=player", timeout=10)
            if r.status_code != 200:
                return d
            target = norm_name(name)
            cands = [str(i["id"]) for i in r.json().get("items", [])
                     if (i.get("league") == "ufc" or i.get("sport") == "mma") and i.get("id") and norm_name(i.get("displayName", "")) == target][:3]
        ours, ok = _year(d.get("DOB")), []
        for cid in cands:
            ra = S.get(f"https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/athletes/{cid}", timeout=10)
            if ra.status_code != 200:
                return d
            ath = ra.json().get("athlete", {})
            if norm_name(ath.get("displayName") or ath.get("fullName") or name) != norm_name(name):
                continue
            theirs = _year(ath.get("dateOfBirth"))
            if ours and theirs and ours != theirs:
                continue                                      # outra pessoa com o mesmo nome
            ok.append((cid, ath, bool(ours and theirs)))
        if len(ok) > 1:
            ok = [x for x in ok if x[2]]                      # com homônimos só vale quem tem o nascimento conferido
        d["espn_checked"], d["espn_v"] = True, ESPN_V
        if len(ok) != 1:
            _clean_espn(d)                                    # sem certeza: não deixa nada que possa ser de outra pessoa
            return d
        cid, ath, _ = ok[0]
        d["espn_id"] = cid
        hs = (ath.get("headshot") or {}).get("href")
        if hs:
            d["img"] = hs                                     # só a foto que a ESPN devolve; nada de URL montada por padrão
        else:
            d.pop("img", None)
        for k, v in (("country", ath.get("citizenship")), ("flag", (ath.get("flag") or {}).get("href")), ("team", (ath.get("association") or {}).get("name"))):
            if v:
                d[k] = v
            else:
                d.pop(k, None)
        bp = ath.get("birthPlace") or {}
        home = ", ".join(str(x) for x in (bp.get("city"), bp.get("state"), bp.get("country")) if x)
        if home:
            d["hometown"] = home
        else:
            d.pop("hometown", None)
        for k, v in (("espn_h", ath.get("displayHeight")), ("espn_r", ath.get("displayReach"))):
            if v and re.search(r"\d", str(v)):
                d[k] = str(v)
            else:
                d.pop(k, None)
    except Exception:
        pass
    return d


def fill_bio(d):
    """Altura/alcance vazios ('--') no ufcstats são completados com o que a ESPN informou; o que já existe não é tocado."""
    for k, src in (("Height", "espn_h"), ("Reach", "espn_r")):
        if d.get(src) and str(d.get(k) or "").strip() in ("", "-", "--"):
            d[k] = d[src]
    return d





# ---------- Wikidata (API JSON aberta): só com nome exato + ano de nascimento + evidência de MMA ----------
WD_API = "https://www.wikidata.org/w/api.php"
WD_HEADERS = {"User-Agent": "SumulaUFC/1.0 (https://github.com/joaogbbss/ufc-sumula; enriquecimento com dados verificados)"}
WD = {"props": None, "labels": {}}
ARTS = {"brazilian jiu jitsu": "Brazilian Jiu-Jitsu", "sambo": "Sambo", "freestyle wrestling": "Freestyle Wrestling", "greco roman wrestling": "Greco-Roman Wrestling",
        "amateur wrestling": "Amateur Wrestling", "judo": "Judo", "muay thai": "Muay Thai", "kickboxing": "Kickboxing", "boxing": "Boxing", "karate": "Karate", "taekwondo": "Taekwondo"}


def _wd(params):
    r = S.get(WD_API, params={**params, "format": "json", "maxlag": 5}, headers=WD_HEADERS, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"wikidata HTTP {r.status_code}")
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"].get("code", "erro"))
    return j


def _en(e, k="labels"):
    return (((e or {}).get(k) or {}).get("en") or {}).get("value", "")


def wd_props():
    """Confere, pelo rótulo que a própria Wikidata devolve, quais propriedades são o Sherdog e o Tapology (não confia em número decorado)."""
    if WD["props"] is not None:
        return WD["props"]
    ids = ["P569", "P106", "P641", "P2416", "P9728", "P2818", "P9726", "P7287"]
    ent = _wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|claims", "languages": "en"}).get("entities", {})
    out = {"ok": _en(ent.get("P569")).lower() == "date of birth", "sherdog": None, "tapology": None}
    def fmt(p):
        try:
            return ent[p]["claims"]["P1630"][0]["mainsnak"]["datavalue"]["value"]
        except Exception:
            return ""
    for key, cands in (("sherdog", ["P9728", "P2818"]), ("tapology", ["P9726", "P7287"])):
        for p in cands:
            lab = _en(ent.get(p)).lower()
            if key in lab and ("id" in lab or "fighter" in lab or "athlete" in lab):
                out[key] = {"pid": p, "fmt": fmt(p)}
                break
    WD["props"] = out
    return out


def wd_labels(qids):
    need = [q for q in dict.fromkeys(qids) if q not in WD["labels"]]
    for i in range(0, len(need), 40):
        ent = _wd({"action": "wbgetentities", "ids": "|".join(need[i:i + 40]), "props": "labels", "languages": "en"}).get("entities", {})
        for q, e in ent.items():
            WD["labels"][q] = _en(e)
    return {q: WD["labels"].get(q, "") for q in qids}


def _claims(e, pid):
    out = []
    for c in ((e or {}).get("claims") or {}).get(pid, []):
        if c.get("rank") == "deprecated":
            continue
        try:
            out.append(c["mainsnak"]["datavalue"]["value"])
        except Exception:
            pass
    return out


def _qs(e, pid):
    return [v["id"] for v in _claims(e, pid) if isinstance(v, dict) and v.get("id")]


def _url(pr, key, wid, host):
    p = pr.get(key)
    if not p or not p.get("fmt") or "$1" not in p["fmt"] or not isinstance(wid, str) or not re.fullmatch(r"[\w.\-~%]+", wid):
        return None
    u = p["fmt"].replace("$1", quote_plus(wid))
    m = re.match(r"https://([^/]+)/", u)
    return u if m and (m.group(1) == host or m.group(1).endswith("." + host)) else None


def wd_match(d):
    """Devolve {} se não achou com certeza; {'wd_qid':..., ...} se achou exatamente um candidato verificado."""
    dob_y = _year(d.get("DOB"))
    if not dob_y:
        return {}
    pr = wd_props()
    ids = [x["id"] for x in _wd({"action": "wbsearchentities", "search": d["name"], "language": "en", "type": "item", "limit": 8}).get("search", [])]
    if not ids:
        return {}
    ents = _wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|aliases|descriptions|claims", "languages": "en"}).get("entities", {})
    q_all = [q for e in ents.values() for pid in ("P106", "P641", "P2416") for q in _qs(e, pid)]
    labs = wd_labels(q_all) if q_all else {}
    good = []
    for q, e in ents.items():
        names = {norm_name(_en(e))} | {norm_name(a.get("value", "")) for a in ((e.get("aliases") or {}).get("en") or [])}
        if norm_name(d["name"]) not in names:
            continue
        if dob_y not in [_year(v.get("time")) for v in _claims(e, "P569") if isinstance(v, dict)]:
            continue
        mma = "mixed martial" in _en(e, "descriptions").lower() or any("mixed martial" in labs.get(x, "").lower() for pid in ("P106", "P641", "P2416") for x in _qs(e, pid))
        if mma:
            good.append((q, e))
    if len(good) != 1:
        return {}
    q, e = good[0]
    out = {"wd_qid": q}
    for key, host in (("sherdog", "sherdog.com"), ("tapology", "tapology.com")):
        if pr.get(key):
            vals = [v for v in _claims(e, pr[key]["pid"]) if isinstance(v, str)]
            if vals:
                u = _url(pr, key, vals[0], host)
                if u:
                    out[key + "_id"], out[key + "_url"] = vals[0], u
    arts = []
    for qid in _qs(e, "P2416") + _qs(e, "P641"):
        a = ARTS.get(norm_name(WD["labels"].get(qid) or labs.get(qid) or wd_labels([qid]).get(qid, "")))
        if a and a not in arts:
            arts.append(a)
    if arts:
        out["base_arts"] = arts
    return out


def enrich_fighter_wikidata(d):
    """Falha de rede levanta exceção (o lutador NÃO é marcado). Sem certeza: marca e não grava nada."""
    if d.get("wd_checked"):
        return d
    if not wd_props()["ok"]:
        raise RuntimeError("propriedades da Wikidata não confirmadas")
    d.update(wd_match(d))
    d["wd_checked"] = True
    return d


def enrich_wd_batch(fighters, fights, upids, limit, has_time, delay=0.3):
    last = {}
    for f in fights.values():
        for s_ in "ab":
            last[f[s_]["id"]] = max(last.get(f[s_]["id"], ""), f["date"])
    cand = [x for x in list(upids) + sorted(fighters, key=lambda x: last.get(x, ""), reverse=True)
            if x in fighters and not fighters[x].get("wd_checked") and _year(fighters[x].get("DOB"))]
    cand = list(dict.fromkeys(cand))[:limit]
    if cand:
        print(f"Consultando {len(cand)} atletas na Wikidata (IDs do Sherdog/Tapology, artes marciais de base)...")
    fails = 0
    for fid in cand:
        if not has_time():
            break
        try:
            fighters[fid] = enrich_fighter_wikidata(fighters[fid]); fails = 0
        except Exception as ex:
            fails += 1
            if fails >= 5:
                print(f"aviso: Wikidata indisponível ({ex}); parei por aqui e tento de novo na próxima execução")
                break
        time.sleep(delay)
    return fails


ORIGINS = [(re.compile(r"ultimate fighter|\bTUF\b", re.I), "TUF"), (re.compile(r"road to ufc", re.I), "RTU"),
           (re.compile(r"contender series|\bDWCS\b", re.I), "DWCS"), (re.compile(r"\bWEC\b"), "WEC"),
           (re.compile(r"\bPRIDE\b"), "PRIDE"), (re.compile(r"strikeforce", re.I), "Strikeforce")]


def debut_origin(fighters, fights, events):
    """Origem quando o nome do evento de estreia OU o título de uma luta de torneio (TUF/Road to UFC) comprova."""
    first, by_tt = {}, {}
    for f in sorted(fights.values(), key=lambda f: (f["date"], -f["ord"])):
        tt = f.get("tt") or ""
        for s_ in "ab":
            fid = f[s_]["id"]
            first.setdefault(fid, f["ev"])
            if fid not in by_tt and tt:
                for rx, tag in ORIGINS:
                    if rx.search(tt):
                        by_tt[fid] = tag
                        break
    n = 0
    for i, d in fighters.items():
        if d.get("origin") == "direct":
            d.pop("origin", None)
        d.pop("origin_src", None)
        if d.get("origin"):
            continue
        name = (events.get(first.get(i)) or {}).get("name", "")
        for rx, tag in ORIGINS:
            if rx.search(name):
                d["origin"] = tag; n += 1
                break
        else:
            if i in by_tt:
                d["origin"] = by_tt[i]; n += 1
    return n


def purge_ufc(fighters):
    """Limpeza: remove o que uma versão anterior gravou de uma fonte descartada (e a cidade natal, que ela podia ter sobrescrito)."""
    n = 0
    for d in fighters.values():
        had = d.get("ufc_checked") is not None
        for k in ("leg_reach", "style", "ufc_checked", "ufc_found", "ufc_slug", "origin_src"):
            if k in d:
                d.pop(k); n += 1
        if had:
            d.pop("hometown", None); d["espn_v"] = 0          # força a reverificação na ESPN, que restaura a cidade natal verdadeira
    return n


def purge_espn(fighters):
    n = 0
    for d in fighters.values():
        if d.get("espn_v", 0) < ESPN_V:
            _clean_espn(d); d["espn_checked"] = False; n += 1
    return n

def upcoming(limit=3):
    soup = get(f"{BASE}/statistics/events/upcoming")
    evs, seen = [], set()
    for a in soup.select('a[href*="event-details"]'):
        eid = uid(a["href"])
        row = a.find_parent("tr") or a.parent
        m = DATE_RE.search(txt(row))
        if eid in seen or not m:
            continue
        seen.add(eid)
        tds = row.select("td")
        evs.append({
            "id": eid,
            "name": txt(a),
            "date": parse_date(m.group(1)),
            "location": txt(tds[-1]) if tds else ""
        })
    today = date.today().isoformat()
    evs = sorted(
        (e for e in evs if re.fullmatch(r"\d{4}-\d\d-\d\d", e["date"]) and e["date"] >= today),
        key=lambda e: e["date"]
    )[:limit]
    for e in evs:
        s = get(f"{BASE}/event-details/{e['id']}")
        e["fights"] = []
        for tr in s.select("tr"):
            fl = tr.select("a[href*='fighter-details']")
            if len(fl) >= 2:
                cells = " ".join(txt(td) for td in tr.select("td"))
                e["fights"].append({
                    "a": {"id": uid(fl[0]["href"]), "name": txt(fl[0])},
                    "b": {"id": uid(fl[1]["href"]), "name": txt(fl[1])},
                    "div": division(cells),
                    "title": is_ufc_title(cells)
                })
    return evs


# ---------- validação ----------

def validate(events, fights, fighters, extra=()):
    issues, used = [], set(extra)
    for f in fights.values():
        a, b = f["a"]["id"], f["b"]["id"]
        used |= {a, b}
        if a == b:
            issues.append(["luta_contra_si_mesmo", f["id"]])
        if f["ev"] not in events:
            issues.append(["luta_sem_evento", f["id"]])
        for x in (a, b):
            if x not in fighters:
                issues.append(["lutador_sem_ficha", x])
    for fid, p in fighters.items():
        if fid not in used:
            issues.append(["lutador_sem_luta", fid])
    by_name, by_dob, by_espn = {}, {}, {}
    for p in fighters.values():
        n, dob = p["name"].lower(), p.get("DOB", "")
        if n in by_name:
            issues.append(["mesmo_nome", by_name[n], p["id"]])
        by_name[n] = p["id"]
        if dob not in ("", "--"):
            if (n, dob) in by_dob:
                issues.append(["possivel_duplicado", by_dob[(n, dob)], p["id"]])
            by_dob[(n, dob)] = p["id"]
        eid = p.get("espn_id")
        if eid:
            eid = str(eid)
            if eid in by_espn:
                issues.append(["espn_duplicado", by_espn[eid], p["id"], eid])
            else:
                by_espn[eid] = p["id"]
    return issues


# ---------- principal ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--refresh", type=int, default=3, help="reprocessa os N eventos mais recentes")
    ap.add_argument("--enrich-limit", type=int, default=150, help="máximo de lutadores enriquecidos via ESPN por execução")
    ap.add_argument("--wd-limit", type=int, default=150, help="máximo de lutadores consultados na Wikidata por execução (0 desliga)")
    ap.add_argument("--purge-espn", action="store_true", help="apaga já os dados da ESPN ainda não verificados (senão são reverificados aos poucos)")
    args = ap.parse_args()
    t0 = time.time()

    def has_time():
        return (time.time() - t0) / 60 < args.max_minutes

    events = {e["id"]: e for e in load("events.json", [])}
    fights = {f["id"]: f for f in load("fights.json", [])}
    fighters = {f["id"]: f for f in load("fighters.json", [])}
    meta = load("meta.json", {"done": []})
    done = set(meta["done"])

    def persist():
        meta.update(
            done=sorted(done),
            updated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            n_events=len(events),
            n_fights=len(fights),
            n_fighters=len(fighters)
        )
        save("events.json", sorted(events.values(), key=lambda e: e["date"], reverse=True))
        save("fights.json", sorted(fights.values(), key=lambda f: (f["date"], -f["ord"])))
        save("fighters.json", sorted(fighters.values(), key=lambda p: p["name"]))
        save("meta.json", meta)

    today = date.today().isoformat()
    listed = sorted((e for e in list_events() if e["date"] <= today), key=lambda e: e["date"])
    if not listed:
        raise SystemExit("ERRO: nenhum evento encontrado no ufcstats.com (veja o DIAGNOSTICO acima).")
    recent = {e["id"] for e in listed[-args.refresh:]}
    todo = [e for e in reversed(listed) if e["id"] not in done or e["id"] in recent]
    print(f"{len(listed)} eventos no site, {len(todo)} para processar")

    touched = set()
    for n, e in enumerate(todo, 1):
        if not has_time():
            print("Tempo esgotado; o restante continua na próxima execução.")
            break
        try:
            eid = e["id"]
            existing_fights = {k: f for k, f in fights.items() if f["ev"] == eid}
            was_done = eid in done and eid in events and bool(existing_fights)
            urls = event_fight_urls(eid)
            ids = [uid(u) for u in urls]
            new = {}
            for i, u in enumerate(urls):
                fid = ids[i]
                if fid in fights and eid not in recent:
                    continue
                f = parse_fight(u, e, i)
                if f:
                    new[fid] = f
            resolved = set(new) | {x for x in ids if x in fights and eid not in recent}
            if was_done and ids:
                resolved |= set(ids) & set(existing_fights)
            age = (date.today() - date.fromisoformat(e["date"])).days
            complete = bool(ids) and (len(resolved) == len(ids) or (age >= 3 and resolved))
            if complete and (new or not was_done):
                if was_done and len(new) == len(ids) and ids:
                    for k in set(existing_fights) - set(ids):
                        del fights[k]
                fights.update(new)
                events[eid] = {**e, "n": len(urls)}
                done.add(eid)
                if eid in recent:
                    touched |= {x for f in new.values() for x in (f["a"]["id"], f["b"]["id"])}
                print(f"[{n}/{len(todo)}] {e['date']} {e['name']}: {len(new)} lutas")
            elif was_done:
                if new:
                    fights.update(new)
                done.add(eid)
                print(
                    f"[{n}/{len(todo)}] {e['date']} {e['name']}: refresh sem novas lutas "
                    f"({len(new)}/{len(ids)} lidas); preservando {len(existing_fights)} lutas já salvas"
                )
            else:
                for k in list(existing_fights):
                    del fights[k]
                events.pop(eid, None)
                done.discard(eid)
                print(
                    f"[{n}/{len(todo)}] {e['date']} {e['name']}: ainda não terminou, ignorado por enquanto "
                    f"({len(resolved)}/{len(ids)} lutas com resultado)"
                )
        except Exception as ex:
            print(f"ERRO em {e['name']}: {ex}")
        if n % 5 == 0:
            persist()

    n_ufc = purge_ufc(fighters)
    if n_ufc:
        print(f"Limpeza: {n_ufc} campos de uma versão anterior (fonte descartada).")
    if args.purge_espn:
        print(f"Limpeza: {purge_espn(fighters)} lutadores com dados da ESPN não verificados zerados.")
    up, upids, up_ok = [], set(), False
    try:
        up = upcoming()
        upids = {f[s]["id"] for e in up for f in e["fights"] for s in "ab"}
        up_ok = True
        print(f"Próximos eventos: {len(up)} ({sum(len(e['fights']) for e in up)} lutas)")
    except Exception as ex:
        print(f"aviso: próximos eventos não carregados: {ex}")

    need = {x for f in fights.values() for x in (f["a"]["id"], f["b"]["id"])} | upids
    pending = [x for x in need if x not in fighters] + [x for x in touched if x in fighters]
    for k, fid in enumerate(pending, 1):
        if not has_time():
            print("Tempo esgotado nas fichas; continua na próxima execução.")
            break
        try:
            prev = fighters.get(fid, {})
            d = parse_fighter(fid)
            for key in ("espn_id", "img", "country", "flag", "team", "hometown", "espn_checked", "espn_v", "espn_h", "espn_r", "sherdog_id", "sherdog_url", "tapology_id", "tapology_url", "base_arts", "wd_qid", "wd_checked"):
                if key in prev:
                    d[key] = prev[key]
            fighters[fid] = fill_bio(enrich_fighter_espn(d))
        except Exception as ex:
            print(f"ERRO no lutador {fid}: {ex}")
        if k % 100 == 0:
            persist()

    if has_time() and args.enrich_limit > 0:
        to_enrich = [
            fid for fid in list(upids) + list(fighters.keys())
            if fid in fighters and (not fighters[fid].get("espn_checked") or fighters[fid].get("espn_v", 0) < ESPN_V)
        ]
        to_enrich = list(dict.fromkeys(to_enrich))[:args.enrich_limit]
        if to_enrich:
            print(f"Enriquecendo {len(to_enrich)} lutadores via ESPN API...")
            for fid in to_enrich:
                if not has_time():
                    break
                fighters[fid] = enrich_fighter_espn(fighters[fid])
                time.sleep(0.15)

    if has_time() and args.wd_limit > 0:
        enrich_wd_batch(fighters, fights, upids, args.wd_limit, has_time)
    debut_origin(fighters, fights, events)
    for d in fighters.values():
        fill_bio(d)

    persist()
    if up_ok:
        save("upcoming.json", {"updated": meta["updated"], "events": up})
    issues = validate(events, fights, fighters, upids)
    save("scraper_validation.json", {"updated": meta["updated"], "count": len(issues), "issues": issues})
    print(
        f"Pronto: {len(events)} eventos, {len(fights)} lutas, {len(fighters)} lutadores, "
        f"{len(issues)} avisos de validação."
    )


if __name__ == "__main__":
    main()
