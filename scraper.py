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
from playwright.sync_api import sync_playwright

BASE = "http://ufcstats.com"
ESPN_SEARCH_API = "https://site.web.api.espn.com/apis/common/v3/search"
ESPN_RANKINGS_API = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/rankings"
UFC_ATHLETE_URL = "https://www.ufc.com/athlete/"
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


def division(title):
    t = title.replace("Catchweight", "Catch Weight").lower()
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
    urls = [r["data-link"] for r in soup.select("[data-link*='fight-details']")]
    if not urls:
        urls = list(dict.fromkeys(a["href"] for a in soup.select("a[href*='fight-details']")))
    return urls


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


def parse_fight(url, ev, order):
    s = get(url)
    ppl = []
    for p in s.select("div.b-fight-details__person")[:2]:
        a = p.select_one("a.b-fight-details__person-link")
        ppl.append({
            "id": uid(a["href"]) if a and a.get("href") else None,
            "name": txt(a),
            "st": txt(p.select_one("i.b-fight-details__person-status"))
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
    tl = s.select_one("i.b-fight-details__fight-title")
    title = txt(tl)
    info = {}
    for it in s.select("i.b-fight-details__text-item, i.b-fight-details__text-item_first"):
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
        "title": "title" in title.lower(),
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

def enrich_fighter_espn(fighter_dict):
    name = fighter_dict.get("name", "")
    if not name:
        return fighter_dict
    try:
        url = f"{ESPN_SEARCH_API}?query={quote_plus(name)}&limit=5&type=player"
        r = S.get(url, timeout=10)
        if r.status_code != 200:
            fighter_dict["espn_checked"] = True
            return fighter_dict
        data = r.json()
        target = norm_name(name)
        best = None
        for item in data.get("items", []):
            if item.get("league") == "ufc" or item.get("sport") == "mma":
                if norm_name(item.get("displayName", "")) == target:
                    best = item
                    break
                if best is None:
                    best = item
        if best and best.get("id"):
            espn_id = str(best["id"])
            fighter_dict["espn_id"] = espn_id
            fighter_dict["img"] = f"https://a.espncdn.com/i/headshots/mma/players/full/{espn_id}.png"
            ath_url = f"https://site.web.api.espn.com/apis/common/v3/sports/mma/ufc/athletes/{espn_id}"
            ra = S.get(ath_url, timeout=10)
            if ra.status_code == 200:
                ath = ra.json().get("athlete", {})
                if ath.get("citizenship"):
                    fighter_dict["country"] = ath["citizenship"]
                if ath.get("flag", {}).get("href"):
                    fighter_dict["flag"] = ath["flag"]["href"]
                if ath.get("association", {}).get("name"):
                    fighter_dict["team"] = ath["association"]["name"]
                bp = ath.get("birthPlace") or {}
                home = ", ".join(str(x) for x in (bp.get("city"), bp.get("state"), bp.get("country")) if x)
                if home and not fighter_dict.get("hometown"):
                    fighter_dict["hometown"] = home
        fighter_dict["espn_checked"] = True
    except Exception:
        pass
    return fighter_dict


# ---------- ranking oficial do UFC (ESPN) ----------

def _pos(e):
    """Posição de um item do ranking: 0 = campeão, 1..15 = top 15, None = desconhecida."""
    for k in ("current", "rank", "position", "rankDisplay", "value"):
        v = e.get(k)
        if v is None:
            continue
        if str(v).strip().upper() in ("C", "CHAMP", "CHAMPION"):
            return 0
        try:
            return int(float(str(v).strip().lstrip("#")))
        except ValueError:
            continue
    return None


def _is_champ(e):
    if _pos(e) == 0:
        return True
    if any(e.get(k) is True for k in ("champion", "isChampion", "isChamp")):
        return True
    ath = e.get("athlete") or {}
    blob = " ".join(str(x) for x in (e.get("rankDisplay"), e.get("note"), e.get("headline"), ath.get("displayName")) if x)
    return bool(re.search(r"\(C\)|\bchampion\b", blob, re.I))


def parse_espn_rankings(data):
    """Aceita as variações conhecidas do JSON da ESPN e devolve uma lista de rankings já normalizada."""
    out = []
    lists = (data or {}).get("rankings") if isinstance(data, dict) else None
    if lists is None and isinstance(data, dict):
        lists = data.get("divisions")
    for l in lists or []:
        title = str(l.get("name") or l.get("shortName") or l.get("displayName") or l.get("headline") or "").strip()
        if not title:
            continue
        rows = []
        for e in l.get("ranks") or l.get("athletes") or l.get("entries") or []:
            ath = e.get("athlete") or e.get("team") or e
            name = re.sub(r"\s*\(C\)\s*$", "", str(ath.get("displayName") or ath.get("fullName") or ath.get("name") or "")).strip()
            if name:
                rows.append({"pos": _pos(e), "champ": _is_champ(e), "name": name, "id": str(ath.get("id") or "")})
        p4p = bool(re.search(r"pound", title, re.I))
        rows.sort(key=lambda r: (0 if (r["champ"] and not p4p) else 1, r["pos"] if r["pos"] is not None else 99))
        champ = rows[0] if (rows and rows[0]["champ"] and not p4p) else None
        rest = [r for r in rows if r is not champ][:15]
        title = re.sub(r"^men'?s\s+", "", title, flags=re.I)
        out.append({"title": title, "p4p": p4p, "champ": champ, "ranks": rest})
    return out


def _fighter_index(fighters):
    by_name, by_eid, toks = defaultdict(list), {}, {}
    for i, f in fighters.items():
        n = norm_name(f.get("name", ""))
        by_name[n].append(i)
        toks[i] = frozenset(n.split())
        if f.get("espn_id"):
            by_eid[str(f["espn_id"])] = i
    return by_name, by_eid, toks


def match_fighter(idx, name, eid):
    """Casa um atleta do ranking com o id do fighters.json sem chutar: nome exato, ou espn_id com nome parecido."""
    by_name, by_eid, toks = idx
    n = norm_name(name)
    c = by_name.get(n, [])
    if len(c) == 1:
        return c[0]
    if len(c) > 1:
        return next((i for i in c if eid and by_eid.get(eid) == i), None)
    a = frozenset(n.split())
    if eid and eid in by_eid:
        b = toks[by_eid[eid]]
        if a and b and len(a & b) / len(a | b) >= 0.5:
            return by_eid[eid]
    hit = [i for i, t in toks.items() if t == a]
    return hit[0] if len(hit) == 1 else None


def build_rankings(data, fighters):
    lists = parse_espn_rankings(data)
    if not lists:
        return None
    idx = _fighter_index(fighters)
    divisions, fr, unmatched, total, ok = {}, {}, [], 0, 0
    for L in lists:
        d = {"champ": None, "ranks": {}}
        if L["champ"]:
            total += 1
            i = match_fighter(idx, L["champ"]["name"], L["champ"]["id"])
            if i:
                ok += 1; d["champ"] = i
                if not L["p4p"]:
                    fr.setdefault(i, {"div": L["title"], "rank": 0})
            else:
                unmatched.append(L["champ"]["name"])
        for n, r in enumerate(L["ranks"], 1):
            total += 1
            i = match_fighter(idx, r["name"], r["id"])
            if not i:
                unmatched.append(r["name"]); continue
            ok += 1; d["ranks"][i] = n
            if L["p4p"]:
                fr.setdefault(i, {"div": "", "rank": None})["p4p"] = n
            else:
                fr.setdefault(i, {"div": L["title"], "rank": n})
        divisions[L["title"]] = d
    return {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "divisions": divisions, "fighter_rank": fr,
            "matched": ok, "total": total, "unmatched": unmatched[:40]}


def refresh_ufc_rankings(fighters):
    """Baixa o ranking oficial. Se algo falhar, o arquivo anterior fica intacto e a execução segue."""
    try:
        r = S.get(ESPN_RANKINGS_API, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        rk = build_rankings(r.json(), fighters)
        if not rk or not rk["divisions"] or rk["matched"] < 10:
            raise RuntimeError("resposta sem divisões reconhecíveis ou com poucos atletas casados")
        save("ufc_rankings.json", rk)
        print(f"Ranking oficial: {len(rk['divisions'])} listas, {rk['matched']}/{rk['total']} atletas casados")
        return True
    except Exception as ex:
        print(f"aviso: ranking oficial não atualizado ({ex}); mantendo o arquivo anterior")
        return False


# ---------- biometria e origem (ufc.com) ----------
UFC_HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"}


def slugify(name):
    s_ = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", s_).strip("-")


def parse_ufc_bio(html):
    """Lê a biografia da página do atleta no ufc.com. Só devolve o que está de fato na página."""
    s_ = BeautifulSoup(html, "lxml")
    fld = {}
    for f in s_.select(".c-bio__field"):
        lab, val = txt(f.select_one(".c-bio__label")).strip().lower(), txt(f.select_one(".c-bio__text"))
        if lab and val:
            fld[lab] = val
    out = {"_name": txt(s_.select_one(".hero-profile__name")) or txt(s_.select_one("h1"))}
    m = re.search(r"(\d+(?:\.\d+)?)", fld.get("leg reach", ""))
    if m and 20 <= float(m.group(1)) <= 60:
        out["leg_reach"] = f'{float(m.group(1)):.1f}"'
    style = fld.get("fighting style") or fld.get("style")
    if style:
        out["style"] = style
    home = fld.get("hometown") or fld.get("place of birth")
    if home:
        out["hometown"] = home
    scope = " ".join(txt(x) for x in s_.select(".c-bio, .hero-profile"))     # só a biografia e o topo do perfil, não o menu do site
    if re.search(r"Contender Series|\bDWCS\b", scope):
        out["_dwcs"] = True
    if re.search(r"The Ultimate Fighter|\bTUF\b", scope):
        out["_tuf"] = True
    return out


def _same_name(a, b):
    ta, tb = set(norm_name(a).split()), set(norm_name(b).split())
    return bool(ta and tb) and (ta == tb or len(ta & tb) / len(ta | tb) >= 0.6)


def enrich_fighter_ufc(d, st):
    """st = {'blocked': n seguidos, 'off': bool}. Bloqueio (403/429/5xx) não marca o lutador: ele será tentado de novo."""
    if d.get("ufc_checked") or st.get("off") or not d.get("name"):
        return d
    base = d.get("ufc_slug") or slugify(d["name"])
    for slug in dict.fromkeys([base, base + "-1"]):
        try:
            r = S.get(UFC_ATHLETE_URL + slug, headers=UFC_HEADERS, timeout=15)
        except Exception:
            st["blocked"] = st.get("blocked", 0) + 1
            if st["blocked"] >= 6:
                st["off"] = True
            return d
        if r.status_code in (403, 429) or r.status_code >= 500:
            st["blocked"] = st.get("blocked", 0) + 1
            if st["blocked"] >= 6:
                st["off"] = True
            return d
        st["blocked"] = 0
        if r.status_code != 200:
            continue
        info = parse_ufc_bio(r.text)
        if not _same_name(info.get("_name", ""), d["name"]):
            continue
        for k in ("leg_reach", "style", "hometown"):
            if info.get(k):
                d[k] = info[k]
        if info.get("_dwcs"):
            d["origin"], d["origin_src"] = "DWCS", "ufc.com"
        elif info.get("_tuf"):
            d["origin"], d["origin_src"] = "TUF", "ufc.com"
        elif not d.get("origin"):
            d["origin"], d["origin_src"] = "direct", "default"      # página lida e sem menção: contratação direta PRESUMIDA
        d["ufc_checked"], d["ufc_slug"] = True, slug
        return d
    d["ufc_checked"], d["ufc_found"] = True, False
    return d


def debut_origin(fighters, fights, events):
    """TUF / DWCS pelo evento da estreia (dado do próprio ufcstats). Vale mais que a presunção 'direct'."""
    first = {}
    for f in sorted(fights.values(), key=lambda f: (f["date"], -f["ord"])):
        for s_ in "ab":
            first.setdefault(f[s_]["id"], f["ev"])
    n = 0
    for i, ev in first.items():
        d, name = fighters.get(i), (events.get(ev) or {}).get("name", "")
        if not d or d.get("origin_src") == "ufc.com":
            continue
        tag = "TUF" if re.search(r"ultimate fighter|\bTUF\b", name, re.I) else "DWCS" if re.search(r"contender series|DWCS", name, re.I) else None
        if tag:
            d["origin"], d["origin_src"] = tag, "ufcstats"; n += 1
    return n


def enrich_ufc_batch(fighters, fights, upids, limit, has_time, delay=0.6):
    """Lê no ufc.com até `limit` atletas: primeiro os dos próximos eventos, depois os que lutaram mais recentemente."""
    last = {}
    for f in fights.values():
        for s_ in "ab":
            last[f[s_]["id"]] = max(last.get(f[s_]["id"], ""), f["date"])
    cand = [x for x in list(upids) + sorted(fighters, key=lambda x: last.get(x, ""), reverse=True) if x in fighters and not fighters[x].get("ufc_checked")]
    cand = list(dict.fromkeys(cand))[:limit]
    st = {"blocked": 0, "off": False}
    if cand:
        print(f"Lendo {len(cand)} atletas no ufc.com (alcance de perna, estilo, cidade natal, origem)...")
    for fid in cand:
        if not has_time() or st["off"]:
            break
        fighters[fid] = enrich_fighter_ufc(fighters[fid], st)
        time.sleep(delay)
    if st["off"]:
        print("aviso: ufc.com bloqueou várias requisições seguidas; parei por aqui e tento de novo na próxima execução")
    return st


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
                    "title": "title" in cells.lower()
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
    by_name, by_dob = {}, {}
    for p in fighters.values():
        n, dob = p["name"].lower(), p.get("DOB", "")
        if n in by_name:
            issues.append(["mesmo_nome", by_name[n], p["id"]])
        by_name[n] = p["id"]
        if dob not in ("", "--"):
            if (n, dob) in by_dob:
                issues.append(["possivel_duplicado", by_dob[(n, dob)], p["id"]])
            by_dob[(n, dob)] = p["id"]
    return issues


# ---------- principal ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-minutes", type=float, default=300)
    ap.add_argument("--refresh", type=int, default=3, help="reprocessa os N eventos mais recentes")
    ap.add_argument("--enrich-limit", type=int, default=150, help="máximo de lutadores enriquecidos via ESPN por execução")
    ap.add_argument("--ufc-limit", type=int, default=120, help="máximo de lutadores lidos no ufc.com por execução (0 desliga)")
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
            urls = event_fight_urls(e["id"])
            ids = [uid(u) for u in urls]
            new = {}
            for i, u in enumerate(urls):
                fid = ids[i]
                if fid in fights and e["id"] not in recent:
                    continue
                f = parse_fight(u, e, i)
                if f:
                    new[fid] = f
            resolved = set(new) | {x for x in ids if x in fights and e["id"] not in recent}
            age = (date.today() - date.fromisoformat(e["date"])).days
            complete = bool(ids) and (len(resolved) == len(ids) or (age >= 3 and resolved))
            if complete:
                fights.update(new)
                events[e["id"]] = {**e, "n": len(urls)}
                done.add(e["id"])
                if e["id"] in recent:
                    touched |= {x for f in new.values() for x in (f["a"]["id"], f["b"]["id"])}
                print(f"[{n}/{len(todo)}] {e['date']} {e['name']}: {len(new)} lutas")
            else:
                for k in [k for k, f in fights.items() if f["ev"] == e["id"]]:
                    del fights[k]
                events.pop(e["id"], None)
                done.discard(e["id"])
                print(
                    f"[{n}/{len(todo)}] {e['date']} {e['name']}: ainda não terminou, ignorado por enquanto "
                    f"({len(resolved)}/{len(ids)} lutas com resultado)"
                )
        except Exception as ex:
            print(f"ERRO em {e['name']}: {ex}")
        if n % 5 == 0:
            persist()

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
            for key in ("espn_id", "img", "country", "flag", "team", "espn_checked", "hometown", "leg_reach", "style", "origin", "origin_src", "ufc_checked", "ufc_found", "ufc_slug"):
                if key in prev:
                    d[key] = prev[key]
            fighters[fid] = enrich_fighter_espn(d)
        except Exception as ex:
            print(f"ERRO no lutador {fid}: {ex}")
        if k % 100 == 0:
            persist()

    if has_time() and args.enrich_limit > 0:
        to_enrich = [
            fid for fid in list(upids) + list(fighters.keys())
            if fid in fighters and not fighters[fid].get("espn_checked")
        ]
        to_enrich = list(dict.fromkeys(to_enrich))[:args.enrich_limit]
        if to_enrich:
            print(f"Enriquecendo {len(to_enrich)} lutadores via ESPN API...")
            for fid in to_enrich:
                if not has_time():
                    break
                fighters[fid] = enrich_fighter_espn(fighters[fid])
                time.sleep(0.15)

    if has_time() and args.ufc_limit > 0:
        enrich_ufc_batch(fighters, fights, upids, args.ufc_limit, has_time)
    debut_origin(fighters, fights, events)
    if has_time():
        refresh_ufc_rankings(fighters)

    persist()
    if up_ok:
        save("upcoming.json", {"updated": meta["updated"], "events": up})
    issues = validate(events, fights, fighters, upids)
    save("validation.json", {"updated": meta["updated"], "count": len(issues), "issues": issues})
    print(
        f"Pronto: {len(events)} eventos, {len(fights)} lutas, {len(fighters)} lutadores, "
        f"{len(issues)} avisos de validação."
    )


if __name__ == "__main__":
    main()
