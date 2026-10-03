#!/usr/bin/env python3
"""Scraper do UFC Stats (ufcstats.com).

1ª execução: baixa tudo (eventos, lutas com estatísticas, lutadores).
Demais execuções: só eventos novos + reprocessa os últimos N eventos
(o site às vezes corrige resultados). Se o tempo acabar, salva o progresso
e continua de onde parou na próxima execução.

Uso: python scraper.py [--max-minutes 300] [--refresh 2]
"""
import argparse
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "http://ufcstats.com"
OUT = Path("data")
DELAY = 0.7  # pausa entre requisições, para não sobrecarregar o site

# Ordem importa: nomes mais específicos antes dos genéricos.
DIVS = ["Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
        "Women's Featherweight", "Light Heavyweight", "Strawweight", "Flyweight",
        "Bantamweight", "Featherweight", "Lightweight", "Welterweight",
        "Middleweight", "Heavyweight", "Catch Weight", "Open Weight"]

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (arquivo pessoal de estatisticas UFC)"


def get(url, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                time.sleep(DELAY)
                return BeautifulSoup(r.text, "lxml")
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"falha ao baixar {url}")


def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def uid(url):
    return url.rstrip("/").split("/")[-1]


def load(name, default):
    p = OUT / name
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), "utf-8")


def parse_date(t):
    for fmt in ("%B %d, %Y", "%b. %d, %Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            pass
    return t


def division(title):
    t = title.replace("Catchweight", "Catch Weight").lower()
    return next((d for d in DIVS if d.lower() in t), "Outros")


# ---------- páginas ----------

def list_events():
    soup = get(f"{BASE}/statistics/events/completed?page=all")
    out = []
    for row in soup.select("tr.b-statistics__table-row"):
        a = row.select_one("a.b-link")
        if not a:
            continue
        loc = row.select_one("td.b-statistics__table-col_style_big-top-padding")
        out.append({"id": uid(a["href"]), "name": txt(a),
                    "date": parse_date(txt(row.select_one("span.b-statistics__date"))),
                    "location": txt(loc)})
    return [e for e in out if re.fullmatch(r"\d{4}-\d\d-\d\d", e["date"])]


def event_fight_urls(eid):
    soup = get(f"{BASE}/event-details/{eid}")
    return [r["data-link"] for r in soup.select("tr.b-fight-details__table-row[data-link]")]


def parse_tables(s):
    """Totais e golpes significativos (por luta e por round)."""
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
    return {"totals": T[0][0] if T and T[0] else None,
            "sig": G[0][0] if G and G[0] else None,
            "rounds": {"totals": T[1] if len(T) > 1 else [],
                       "sig": G[1] if len(G) > 1 else []}}


def parse_fight(url, ev, order):
    s = get(url)
    ppl = []
    for p in s.select("div.b-fight-details__person")[:2]:
        a = p.select_one("a.b-fight-details__person-link")
        ppl.append({"id": uid(a["href"]) if a and a.get("href") else None,
                    "name": txt(a), "st": txt(p.select_one("i.b-fight-details__person-status"))})
    if len(ppl) < 2 or not ppl[0]["id"] or not ppl[1]["id"]:
        return None
    st = (ppl[0]["st"], ppl[1]["st"])
    res = ("a" if st[0] == "W" else "b" if st[1] == "W"
           else "draw" if "D" in st else "nc" if "NC" in st else None)
    if not res:  # luta sem resultado (cancelada / futura)
        return None
    tl = s.select_one("i.b-fight-details__fight-title")
    title = txt(tl)
    info = {}
    for it in s.select("i.b-fight-details__text-item, i.b-fight-details__text-item_first"):
        k, _, v = txt(it).partition(":")
        info[k.strip().lower()] = v.strip()
    ps = s.select("p.b-fight-details__text")
    return {"id": uid(url), "ev": ev["id"], "date": ev["date"], "ord": order,
            "a": {"id": ppl[0]["id"], "name": ppl[0]["name"]},
            "b": {"id": ppl[1]["id"], "name": ppl[1]["name"]},
            "res": res, "div": division(title), "title": "title" in title.lower(),
            "tt": title,
            "bonus": [i["src"].rsplit("/", 1)[-1].split(".")[0] for i in tl.select("img")] if tl else [],
            "method": info.get("method", ""), "round": info.get("round", ""),
            "time": info.get("time", ""), "fmt": info.get("time format", ""),
            "ref": info.get("referee", ""),
            "detail": txt(ps[1]).split(":", 1)[-1].strip() if len(ps) > 1 else "",
            **parse_tables(s)}


def parse_fighter(fid):
    s = get(f"{BASE}/fighter-details/{fid}")
    d = {"id": fid, "name": txt(s.select_one("span.b-content__title-highlight")),
         "nick": txt(s.select_one("p.b-content__Nickname")),
         "record": txt(s.select_one("span.b-content__title-record")).replace("Record:", "").strip()}
    for li in s.select("li.b-list__box-list-item"):
        label = txt(li.select_one("i.b-list__box-item-title"))
        val = txt(li).replace(label, "", 1).strip()
        if label and val:
            d[label.rstrip(":").strip()] = val
    return d


# ---------- validação ----------

def validate(events, fights, fighters):
    issues, used = [], set()
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
    ap.add_argument("--refresh", type=int, default=2,
                    help="reprocessa os N eventos mais recentes")
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
        meta.update(done=sorted(done), updated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    n_events=len(events), n_fights=len(fights), n_fighters=len(fighters))
        save("events.json", sorted(events.values(), key=lambda e: e["date"], reverse=True))
        save("fights.json", sorted(fights.values(), key=lambda f: (f["date"], -f["ord"])))
        save("fighters.json", sorted(fighters.values(), key=lambda p: p["name"]))
        save("meta.json", meta)

    today = date.today().isoformat()
    listed = sorted((e for e in list_events() if e["date"] <= today), key=lambda e: e["date"])
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
            new = {}
            for i, u in enumerate(urls):
                fid = uid(u)
                if fid in fights and e["id"] not in recent:
                    continue
                f = parse_fight(u, e, i)
                if f:
                    new[fid] = f
            fights.update(new)
            events[e["id"]] = {**e, "n": len(urls)}
            done.add(e["id"])
            if e["id"] in recent:
                touched |= {x for f in new.values() for x in (f["a"]["id"], f["b"]["id"])}
            print(f"[{n}/{len(todo)}] {e['date']} {e['name']}: {len(new)} lutas")
        except Exception as ex:  # um evento com erro não derruba a execução
            print(f"ERRO em {e['name']}: {ex}")
        if n % 5 == 0:
            persist()

    need = {x for f in fights.values() for x in (f["a"]["id"], f["b"]["id"])}
    pending = [x for x in need if x not in fighters] + [x for x in touched if x in fighters]
    for k, fid in enumerate(pending, 1):
        if not has_time():
            print("Tempo esgotado nas fichas; continua na próxima execução.")
            break
        try:
            fighters[fid] = parse_fighter(fid)
        except Exception as ex:
            print(f"ERRO no lutador {fid}: {ex}")
        if k % 100 == 0:
            persist()

    persist()
    issues = validate(events, fights, fighters)
    save("validation.json", {"updated": meta["updated"], "count": len(issues), "issues": issues})
    print(f"Pronto: {len(events)} eventos, {len(fights)} lutas, {len(fighters)} lutadores, "
          f"{len(issues)} avisos de validação.")


if __name__ == "__main__":
    main()
