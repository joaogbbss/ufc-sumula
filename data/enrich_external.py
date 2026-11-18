#!/usr/bin/env python3
"""enrich_external.py: Integra bases abertas oficiais e históricas ao Súmula UFC.

Fontes integradas:
1. TidyTuesday / fightr (ufc_athletes.csv): 3.145 perfis oficiais ufc.com
   -> Preenche hometown, country, team (academia), Reach, Height, leg_reach, style (estilo base).
2. TidyTuesday / Ultimate UFC Dataset (ultimate_ufc_dataset.csv): ~7.177 lutas com Odds
   -> Gera data/market.json com odds de fechamento (moneyline + prop odds KO/SUB/DEC),
      ranking oficial no dia da luta, auditoria Vegas vs Modelo, Maiores Zebras e ROI por lutador.
3. Wikipedia Live API (UFC_rankings) + Histórico Oficial Semanal 2013-2026 (ufc_rankings_dataset.csv)
   -> Gera data/ufc_rankings.json com o Top 15 + P4P atual ao vivo, próxima luta agendada,
      e currículo histórico no ranking oficial (melhor posição, semanas no Top 15, Top 5 e P4P).
4. Wikipedia API (Dana White's Contender Series Seasons 1-10, WEC, PRIDE, Strikeforce)
   -> Enriquece o campo `origin` em data/fighters.json (DWCS, WEC, PRIDE, Strikeforce, TUF, RTU).
"""
import csv
import io
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests

DATA = Path("data")
H = {"User-Agent": "SumulaUFC/2.0 (https://github.com/joaogbbss/ufc-sumula)"}
TT_BASE = "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2026/2026-07-07"

# Mapeamento de nomes históricos / casada / apelidos para o nome em fighters.json (ufcstats)
NAME_ALIAS = {
    "bobby green": "king green",
    "katlyn chookagian": "katlyn cerminara",
    "tecia torres": "tecia pennington",
    "joanne calderwood": "joanne wood",
    "michelle waterson": "michelle waterson gomez",
    "ariane lipski": "ariane da silva",
    "yana kunitskaya": "yana santos",
    "cris cyborg": "cristiane justino",
    "nina ansaroff": "nina nunes",
    "rampage jackson": "quinton jackson",
    "minotauro nogueira": "antonio rodrigo nogueira",
    "antonio rogerio nogueira": "rogerio nogueira",
    "mirko cro cop": "mirko filipovic",
    "weili zhang": "zhang weili",
    "ronaldo souza": "jacare souza",
    "costas philippou": "constantinos philippou",
    "c b dollaway": "cb dollaway",
    "tim johnson": "timothy johnson",
    "ulka sasaki": "yuta sasaki",
    "veronica macedo": "veronica hardy",
    "polo reyes": "marco polo reyes",
    "rick glenn": "ricky glenn",
    "nico musoke": "nicholas musoke",
    "rob whiteford": "robert whiteford",
    "rafael feijao": "rafael cavalcante",
    "su mudaerji": "sumudaerji",
    "seohee ham": "seo hee ham",
    "tiago trator": "tiago dos santos e silva",
    "francisco rivera jr": "francisco rivera",
    "mara borella": "mara romero borella",
    "joseph duffy": "joe duffy",
    "chan sung jung": "chan sung jung",
    "ian garry": "ian machado garry",
    "patricio pitbull": "patricio freire",
    "alexandr romanov": "alexander romanov",
    "sergey spivak": "serghei spivac",
    "daria zheleznyakova": "darya zheleznyakova",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return NAME_ALIAS.get(s, s)


def inches_to_ft(val):
    try:
        v = int(round(float(val)))
        if 54 <= v <= 88:
            return f"{v // 12}' {v % 12}\""
    except Exception:
        pass
    return None


def cm_to_ft(val):
    try:
        cm = float(val)
        if 135 <= cm <= 225:
            return inches_to_ft(cm / 2.54)
    except Exception:
        pass
    return None


def cm_to_in(val):
    try:
        cm = float(val)
        if 135 <= cm <= 235:
            return f"{int(round(cm / 2.54))}\""
    except Exception:
        pass
    return None


def us_to_prob(o):
    try:
        v = float(o)
    except Exception:
        return None
    if v == 0 or math.isnan(v):
        return None
    return 100.0 / (100.0 + v) if v > 0 else (-v) / (-v + 100.0)


def us_payout(o):
    v = float(o)
    return (v / 100.0) if v > 0 else (100.0 / (-v))


def clean_wiki(text):
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<ref[^/>]*/\s*>", "", text)
    text = re.sub(r"\{\{nowrap\|([^}]*)\}\}", r"\1", text, flags=re.I)
    text = re.sub(r"\{\{small\|([^}]*)\}\}", r"\1", text, flags=re.I)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"''+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_wiki_wikitext(page):
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={page}&prop=wikitext&format=json"
    r = requests.get(url, headers=H, timeout=15)
    if r.status_code == 200 and "parse" in r.json():
        return r.json()["parse"]["wikitext"]["*"]
    return ""


def parse_live_wiki_rankings(by_name):
    wt = fetch_wiki_wikitext("UFC_rankings")
    if not wt:
        return None, {}
    m_rel = re.search(r"Rankings released on ([A-Za-z]+ \d{1,2}, \d{4})", wt)
    released = m_rel.group(1) if m_rel else ""
    try:
        released = datetime.strptime(released, "%B %d, %Y").date().isoformat()
    except Exception:
        pass

    idx_start = wt.find("Men's pound-for-pound")
    if idx_start < 0:
        idx_start = 0
    wt_sec = wt[idx_start:]

    sections = re.split(r"===\s*([^=]+?)\s*===", wt_sec)
    # sections[0] is before first ===, then [title1, body1, title2, body2, ...]
    # Wait: Men's pound-for-pound header itself might be matched or before
    if not wt_sec.startswith("==="):
        sections = ["Men's pound-for-pound"] + sections

    DIV_MAP = {
        "men's pound-for-pound": "Men's Pound-for-Pound",
        "women's pound-for-pound": "Women's Pound-for-Pound",
        "heavyweight": "Heavyweight",
        "light heavyweight": "Light Heavyweight",
        "middleweight": "Middleweight",
        "welterweight": "Welterweight",
        "lightweight": "Lightweight",
        "featherweight": "Featherweight",
        "bantamweight": "Bantamweight",
        "flyweight": "Flyweight",
        "women's bantamweight": "Women's Bantamweight",
        "women's flyweight": "Women's Flyweight",
        "women's strawweight": "Women's Strawweight",
    }

    divisions = {}
    fighter_live = {}
    for i in range(0, len(sections) - 1, 2):
        raw_title = sections[i].strip().lower()
        body = sections[i + 1]
        div_name = DIV_MAP.get(raw_title)
        if not div_name or div_name in divisions:
            continue
        is_p4p = "Pound-for-Pound" in div_name
        rows = body.split("|-")
        champ = None
        ranks = []
        for row in rows:
            if "flagicon" not in row:
                continue
            lines = [l.strip() for l in row.strip().splitlines() if l.strip()]
            if not lines:
                continue
            rk_line = lines[0]
            is_c = "Champion" in rk_line or "|C}}" in rk_line or "background:gold" in rk_line or bool(re.search(r"\|\s*C\s*$", rk_line))
            m_rk = re.search(r"!\s*(\d+)", rk_line)
            rk_num = 0 if is_c else (int(m_rk.group(1)) if m_rk else None)
            if rk_num is None:
                continue
            # Find fighter link after flagicon
            m_f = re.search(r"\{\{flagicon\|([A-Z]{2,3})\}\}\s*\n\s*\|\s*\[\[([^\]]+)\]\]", row)
            if not m_f:
                continue
            iso = m_f.group(1)
            f_link = m_f.group(2).split("|")[-1].strip()
            fid = by_name.get(norm(f_link))
            # Movement
            delta = 0
            if "{{increase" in row or "{{fluc|" in row:
                m_d = re.search(r"\{\{(?:increase|fluc)\|\s*([+-]?\d+)", row, re.I)
                delta = int(m_d.group(1)) if m_d else 1
            elif "{{decrease" in row:
                m_d = re.search(r"\{\{decrease\|\s*([+-]?\d+)", row, re.I)
                delta = -abs(int(m_d.group(1))) if m_d else -1
            elif "{{new" in row.lower():
                delta = 99
            # Next fight / status (last columns)
            cells = [c.strip() for c in re.split(r"\n\|", row)]
            next_info = ""
            if len(cells) >= 2:
                tail = " · ".join(clean_wiki(c) for c in cells[-2:] if clean_wiki(c) and not clean_wiki(c).startswith("align="))
                tail = re.sub(r"^colspan=\d+\s*\|\s*", "", tail).strip(" ·")
                if tail and tail.upper() != "TBD":
                    next_info = tail[:80]

            entry = {
                "rank": rk_num,
                "id": fid,
                "name": f_link,
                "iso": iso,
                "delta": delta,
                "next": next_info,
            }
            if is_c:
                champ = entry
            else:
                ranks.append(entry)
            if fid:
                info = fighter_live.setdefault(fid, {})
                if is_p4p:
                    info["p4p"] = rk_num
                    info["p4p_div"] = div_name
                else:
                    info["div"] = div_name
                    info["rank"] = rk_num
                    info["delta"] = delta
                    if next_info:
                        info["next"] = next_info
        divisions[div_name] = {"champ": champ, "ranks": ranks}
    return released, divisions, fighter_live


def _extract_wiki_name(cell):
    m = re.search(r"\{\{sortname\|([^|}]+)\|([^|}]+)(?:\|([^|}]+))?", cell, re.I)
    if m:
        return f"{m.group(1).strip()} {m.group(2).strip()}"
    m2 = re.search(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", cell)
    if m2:
        return m2.group(1).strip()
    return clean_wiki(cell)


def _extract_wiki_iso(cell):
    m = re.search(r"(?:flag\|icon\||flagicon\|)([A-Z]{2,3})", cell)
    return m.group(1) if m else ""


def _extract_wiki_dob(cell):
    m = re.search(r"\{\{age nts\|(\d{4})\|(\d{1,2})\|(\d{1,2})", cell, re.I)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _extract_wiki_date(cell):
    m = re.search(r"\{\{dts\|(\d{4})\|([A-Za-z]+|\d{1,2})\|(\d{1,2})", cell, re.I)
    if m:
        yr, mo, da = int(m.group(1)), m.group(2), int(m.group(3))
        if mo.isdigit():
            return f"{yr:04d}-{int(mo):02d}-{da:02d}"
        try:
            dt = datetime.strptime(f"{mo[:3]} {da} {yr}", "%b %d %Y").date()
            return dt.isoformat()
        except Exception:
            pass
    c = clean_wiki(cell)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(c, fmt).date().isoformat()
        except Exception:
            pass
    return c[:20]


def parse_live_wiki_roster(by_name):
    """Lê List_of_current_UFC_fighters via MediaWiki API:
    retorna plantel ativo por divisão, contratações recentes, dispensas/aposentadorias e suspensos.
    """
    wt = fetch_wiki_wikitext("List_of_current_UFC_fighters")
    if not wt:
        return None
    wt = re.sub(r"<!--.*?-->", "", wt, flags=re.S)
    ROSTER_DIVS = {
        "heavyweights": "Heavyweight",
        "light heavyweights": "Light Heavyweight",
        "middleweights": "Middleweight",
        "welterweights": "Welterweight",
        "lightweights": "Lightweight",
        "featherweights": "Featherweight",
        "bantamweights": "Bantamweight",
        "flyweights": "Flyweight",
        "women's bantamweights": "Women's Bantamweight",
        "women's flyweights": "Women's Flyweight",
        "women's strawweights": "Women's Strawweight",
    }
    parts = re.split(r"^={2,4}\s*([^=\n]+?)\s*={2,4}\s*$", wt, flags=re.M)
    active_by_div = {}
    active_map = {}  # fid -> {div, iso, dob, status}
    departures = []
    signings = []
    suspended = []

    for i in range(1, len(parts) - 1, 2):
        hdr = parts[i].strip()
        hl = hdr.lower()
        body = parts[i + 1]

        # 1) Divisões ativas
        matched_div = None
        for prefix, dname in ROSTER_DIVS.items():
            if hl.startswith(prefix):
                matched_div = dname
                break
        if matched_div:
            rows = body.split("\n|-")
            div_list = []
            for row in rows[1:]:
                cols = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip())[1:]]
                if len(cols) < 5:
                    continue
                iso = _extract_wiki_iso(cols[0])
                nm_raw = _extract_wiki_name(cols[1])
                if not nm_raw or nm_raw.lower() in ("name", "fighter"):
                    continue
                fid = by_name.get(norm(nm_raw))
                dob = _extract_wiki_dob(cols[2])
                status_txt = clean_wiki(cols[5]) if len(cols) > 5 else ""
                div_list.append({"name": nm_raw, "id": fid, "iso": iso, "dob": dob, "status": status_txt[:110]})
                if fid:
                    active_map[fid] = {"div": matched_div, "iso": iso, "dob": dob, "status": status_txt[:110]}
            active_by_div[matched_div] = div_list
            continue

        # 2) Dispensas e aposentadorias recentes
        if "recent releases and retirements" in hl:
            for row in body.split("\n|-")[1:]:
                cols = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip())[1:]]
                if len(cols) < 6:
                    continue
                dt = _extract_wiki_date(cols[0])
                iso = _extract_wiki_iso(cols[1])
                nm_raw = _extract_wiki_name(cols[2])
                if not nm_raw:
                    continue
                fid = by_name.get(norm(nm_raw))
                reason = clean_wiki(cols[4])
                dv = clean_wiki(cols[5])
                kind = "retired" if "retir" in reason.lower() else "released"
                departures.append({"date": dt, "iso": iso, "name": nm_raw, "id": fid, "reason": reason[:60], "kind": kind, "div": dv})
            continue

        # 3) Contratações recentes (ainda sem estreia ou retorno)
        if "recent signings" in hl:
            for row in body.split("\n|-")[1:]:
                cols = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip())[1:]]
                if len(cols) < 5:
                    continue
                dt = _extract_wiki_date(cols[0])
                iso = _extract_wiki_iso(cols[1])
                nm_raw = _extract_wiki_name(cols[2])
                if not nm_raw:
                    continue
                fid = by_name.get(norm(nm_raw))
                dv = clean_wiki(cols[4])
                info = clean_wiki(cols[5]) if len(cols) > 5 else ""
                rec = clean_wiki(cols[7]) if len(cols) > 7 else ""
                signings.append({"date": dt, "iso": iso, "name": nm_raw, "id": fid, "div": dv, "info": info[:100], "rec": rec[:25]})
            continue

        # 4) Lutadores suspensos
        if "suspended fighters" in hl:
            for row in body.split("\n|-")[1:]:
                cols = [c.strip() for c in re.split(r"\n\|", "\n" + row.strip())[1:]]
                if len(cols) < 5:
                    continue
                iso = _extract_wiki_iso(cols[0])
                nm_raw = _extract_wiki_name(cols[1])
                if not nm_raw or "iso" in nm_raw.lower():
                    continue
                fid = by_name.get(norm(nm_raw))
                dv = clean_wiki(cols[3]) if len(cols) > 3 else ""
                info = clean_wiki(cols[4]) if len(cols) > 4 else ""
                suspended.append({"iso": iso, "name": nm_raw, "id": fid, "div": dv, "info": info[:110]})

    return {
        "active_by_div": active_by_div,
        "active_map": active_map,
        "departures": departures,
        "signings": signings,
        "suspended": suspended,
    }


def main():
    fighters = json.loads((DATA / "fighters.json").read_text(encoding="utf-8"))
    fights = json.loads((DATA / "fights.json").read_text(encoding="utf-8"))
    analytics = json.loads((DATA / "analytics.json").read_text(encoding="utf-8"))
    pre_elo = {}
    # Reconstruct pre-fight ELO from analytics.py logic for market comparison
    from analytics import run_elo
    run_elo(fights, pre_elo)

    name_counts = Counter(norm(f["name"]) for f in fighters)
    by_name = {norm(f["name"]): f["id"] for f in fighters if name_counts[norm(f["name"])] == 1}
    fmap = {f["id"]: f for f in fighters}

    # Especial para Bruno Gustavo da Silva (Flyweight) vs Bruno Silva (Middleweight)
    by_name["bruno gustavo da silva"] = "294aa73dbf37d281"

    # ---------------------------------------------------------
    # 1. Enriquecer fighters.json com ufc_athletes.csv
    # ---------------------------------------------------------
    print("Baixando ufc_athletes.csv...")
    r_ath = requests.get(f"{TT_BASE}/ufc_athletes.csv", headers=H, timeout=25)
    ath_rows = list(csv.DictReader(io.StringIO(r_ath.text)))
    n_bio = 0
    for r in ath_rows:
        fid = by_name.get(norm(r.get("name")))
        if not fid:
            continue
        f = fmap[fid]
        changed = False
        rc = r.get("reach", "")
        if f.get("Reach") in ("--", "", None) and rc and rc not in ("NA", "0"):
            try:
                rv = int(round(float(rc)))
                if 54 <= rv <= 88:
                    f["Reach"] = f'{rv}"'
                    changed = True
            except Exception:
                pass
        ht = r.get("height", "")
        if f.get("Height") in ("--", "", None) and ht and ht not in ("NA", "0"):
            ft_str = inches_to_ft(ht)
            if ft_str:
                f["Height"] = ft_str
                changed = True
        tr = (r.get("trains_at") or "").strip()
        if not f.get("team") and tr and tr != "NA":
            f["team"] = tr
            changed = True
        pb = (r.get("place_of_birth") or "").strip()
        if pb and pb != "NA":
            if not f.get("hometown"):
                f["hometown"] = pb
                changed = True
            if not f.get("country"):
                f["country"] = pb.split(",")[-1].strip()
                changed = True
        st = (r.get("fighting_style") or "").strip()
        if st and st != "NA" and not f.get("style"):
            f["style"] = st
            changed = True
        lr = (r.get("leg_reach") or "").strip()
        if lr and lr not in ("NA", "0") and not f.get("leg_reach"):
            try:
                lv = int(round(float(lr)))
                if 30 <= lv <= 52:
                    f["leg_reach"] = f'{lv}"'
                    changed = True
            except Exception:
                pass
        if changed:
            n_bio += 1
    print(f"ufc_athletes.csv: {n_bio} lutadores enriquecidos com biografia/alcance/academia/estilo.")

    # ---------------------------------------------------------
    # 2. Enriquecer origens (DWCS Seasons 1-10, WEC, PRIDE, Strikeforce) via Wikipedia
    # ---------------------------------------------------------
    print("Consultando páginas históricas (DWCS / WEC / PRIDE / Strikeforce) na Wikipedia...")
    origin_pages = (
        [(f"Dana_White%27s_Contender_Series_season_{s}", "DWCS") for s in range(1, 11)]
        + [
            ("Dana_White%27s_Contender_Series", "DWCS"),
            ("List_of_WEC_champions", "WEC"),
            ("World_Extreme_Cagefighting", "WEC"),
            ("List_of_Pride_FC_champions", "PRIDE"),
            ("List_of_Strikeforce_champions", "Strikeforce"),
        ]
    )
    n_orig = 0
    for pg, tag in origin_pages:
        wt = fetch_wiki_wikitext(pg)
        if not wt:
            continue
        for m in re.findall(r"\[\[([^\]]+)\]\]", wt):
            k = norm(m.split("|")[-1])
            fid = by_name.get(k)
            if fid and not fmap[fid].get("origin"):
                fmap[fid]["origin"] = tag
                n_orig += 1
    print(f"Origens enriquecidas via Wikipedia: +{n_orig} lutadores ->", Counter(f.get("origin") for f in fighters if f.get("origin")))

    # ---------------------------------------------------------
    # 2b. Query Única SPARQL na Wikidata (Sherdog, Tapology, Artes Marciais Base e DOB)
    # ---------------------------------------------------------
    print("Executando query SPARQL em lote na Wikidata...")
    SPARQL = """
    SELECT ?item ?itemLabel ?dob ?sherdog ?tapology (GROUP_CONCAT(DISTINCT ?sportLabel; separator="|") AS ?arts) WHERE {
      { ?item wdt:P9728 ?sherdog . } UNION { ?item wdt:P9726 ?tapology . }
      OPTIONAL { ?item wdt:P569 ?dob . }
      OPTIONAL { ?item wdt:P9728 ?sherdog . }
      OPTIONAL { ?item wdt:P9726 ?tapology . }
      OPTIONAL {
        ?item wdt:P641|wdt:P2416 ?sport .
        ?sport rdfs:label ?sportLabel .
        FILTER(LANG(?sportLabel) = "en")
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en,pt". }
    }
    GROUP BY ?item ?itemLabel ?dob ?sherdog ?tapology
    """
    ARTS_MAP = {
        "brazilian jiu jitsu": "Brazilian Jiu-Jitsu",
        "sambo": "Sambo",
        "combat sambo": "Sambo",
        "freestyle wrestling": "Freestyle Wrestling",
        "greco roman wrestling": "Greco-Roman Wrestling",
        "amateur wrestling": "Amateur Wrestling",
        "collegiate wrestling": "Wrestling",
        "wrestling": "Wrestling",
        "judo": "Judo",
        "muay thai": "Muay Thai",
        "kickboxing": "Kickboxing",
        "boxing": "Boxing",
        "karate": "Karate",
        "kyokushin": "Karate",
        "taekwondo": "Taekwondo",
        "sanda": "Sanda / Wushu",
        "lethwei": "Lethwei",
    }
    try:
        r_wd = requests.get(
            "https://query.wikidata.org/sparql",
            params={"format": "json", "query": SPARQL},
            headers={**H, "Accept": "application/sparql-results+json"},
            timeout=30,
        )
        if r_wd.status_code == 200:
            wd_rows = r_wd.json().get("results", {}).get("bindings", [])
            n_wd = 0
            for b in wd_rows:
                lbl = b.get("itemLabel", {}).get("value", "")
                fid = by_name.get(norm(lbl))
                if not fid:
                    continue
                fp = fmap[fid]
                dob_val = b.get("dob", {}).get("value", "")
                # Se ambos têm ano de nascimento, confere compatibilidade
                if dob_val and len(dob_val) >= 10:
                    wy = dob_val[:4]
                    oy_m = re.search(r"(19|20)\d{2}", str(fp.get("DOB") or ""))
                    if oy_m and oy_m.group(0) != wy:
                        continue
                    if fp.get("DOB") in ("--", "", None) and re.fullmatch(r"\d{4}-\d\d-\d\d", dob_val[:10]):
                        try:
                            fp["DOB"] = datetime.strptime(dob_val[:10], "%Y-%m-%d").strftime("%b %d, %Y")
                        except Exception:
                            pass
                qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
                if qid.startswith("Q"):
                    fp["wd_qid"] = qid
                    fp["wd_checked"] = True
                sh = b.get("sherdog", {}).get("value", "")
                if sh and not fp.get("sherdog_id"):
                    fp["sherdog_id"] = sh
                    fp["sherdog_url"] = f"https://www.sherdog.com/fighter/{sh}"
                tp = b.get("tapology", {}).get("value", "")
                if tp and not fp.get("tapology_id"):
                    fp["tapology_id"] = tp
                    fp["tapology_url"] = f"https://www.tapology.com/fightcenter/fighters/{tp}"
                arts_raw = b.get("arts", {}).get("value", "")
                if arts_raw:
                    found_arts = []
                    for part in arts_raw.split("|"):
                        mapped = ARTS_MAP.get(norm(part))
                        if mapped and mapped not in found_arts:
                            found_arts.append(mapped)
                    if found_arts:
                        fp["base_arts"] = found_arts
                n_wd += 1
            print(f"Wikidata SPARQL em lote: {n_wd} lutadores enriquecidos (Sherdog/Tapology/Artes de Base).")
    except Exception as ex:
        print(f"aviso: query SPARQL Wikidata falhou ({ex}).")

    # ---------------------------------------------------------
    # 3. Processar ultimate_ufc_dataset.csv -> data/market.json + fallback físico
    # ---------------------------------------------------------
    print("Baixando ultimate_ufc_dataset.csv (Odds & Ranks no dia da luta)...")
    r_odd = requests.get(f"{TT_BASE}/ultimate_ufc_dataset.csv", headers=H, timeout=30)
    odd_rows = list(csv.DictReader(io.StringIO(r_odd.text)))

    by_pair = defaultdict(list)
    for f in fights:
        na, nb = norm(f["a"]["name"]), norm(f["b"]["name"])
        by_pair[(na, nb)].append((f, False))
        by_pair[(nb, na)].append((f, True))

    mkt_fights = {}
    upsets = []
    roi = defaultdict(lambda: {"n": 0, "w": 0, "dog_w": 0, "dog_n": 0, "fav_w": 0, "fav_n": 0, "net": 0.0})
    brier_mkt = brier_elo = brier_blend = ll_mkt = ll_elo = ll_blend = acc_mkt = acc_elo = acc_blend = n_eval = 0
    vig_sum = 0.0
    cal_bins = defaultdict(lambda: [0, 0.0, 0.0])

    for r in odd_rows:
        dt = r.get("date", "")
        if not dt:
            continue
        d0 = date.fromisoformat(dt)
        ra, rb = norm(r.get("r_fighter")), norm(r.get("b_fighter"))
        # Fallback físico (Reach, Height, Stance) para lutadores
        for pref, nm_k in (("r_", ra), ("b_", rb)):
            fid = by_name.get(nm_k)
            if not fid:
                continue
            fp = fmap[fid]
            if fp.get("Reach") in ("--", "", None):
                rc_in = cm_to_in(r.get(f"{pref}reach_cms"))
                if rc_in:
                    fp["Reach"] = rc_in
            if fp.get("Height") in ("--", "", None):
                ht_ft = cm_to_ft(r.get(f"{pref}height_cms"))
                if ht_ft:
                    fp["Height"] = ht_ft
            if fp.get("STANCE") in ("--", "", None):
                st_v = (r.get(f"{pref}stance") or "").strip()
                if st_v and st_v not in ("NA", ""):
                    fp["STANCE"] = st_v

        cands = by_pair.get((ra, rb), [])
        matched_f = None
        swapped = False
        for f_cand, sw in cands:
            if abs((date.fromisoformat(f_cand["date"]) - d0).days) <= 5:
                matched_f = f_cand
                swapped = sw
                break
        if not matched_f:
            continue

        qa, qb = us_to_prob(r.get("r_odds")), us_to_prob(r.get("b_odds"))
        if not qa or not qb:
            continue
        oa, ob = int(round(float(r["r_odds"]))), int(round(float(r["b_odds"])))
        # Ranks on fight night
        rka_raw, rkb_raw = r.get("r_match_weightclass_rank"), r.get("b_match_weightclass_rank")
        rka = int(float(rka_raw)) if rka_raw not in ("", "NA", None) else None
        rkb = int(float(rkb_raw)) if rkb_raw not in ("", "NA", None) else None
        # Prop odds
        def _odd(k):
            v = r.get(k)
            try:
                return int(round(float(v))) if v not in ("", "NA", None) else None
            except Exception:
                return None
        ko_a, ko_b = _odd("r_ko_odds"), _odd("b_ko_odds")
        sub_a, sub_b = _odd("r_sub_odds"), _odd("b_sub_odds")
        dec_a, dec_b = _odd("r_dec_odds"), _odd("b_dec_odds")

        if swapped:
            qa, qb = qb, qa
            oa, ob = ob, oa
            rka, rkb = rkb, rka
            ko_a, ko_b = ko_b, ko_a
            sub_a, sub_b = sub_b, sub_a
            dec_a, dec_b = dec_b, dec_a

        vig = (qa + qb) - 1.0
        vig_sum += vig
        p_a = round(qa / (qa + qb), 4)
        fid = matched_f["id"]
        entry = [oa, ob, p_a]
        if any(x is not None for x in (rka, rkb, ko_a, ko_b, sub_a, sub_b, dec_a, dec_b)):
            entry.extend([rka, rkb, ko_a, ko_b, sub_a, sub_b, dec_a, dec_b])
        mkt_fights[fid] = entry

        if matched_f["res"] in ("a", "b"):
            w_side = matched_f["res"]
            y_a = 1.0 if w_side == "a" else 0.0
            # ELO comparison
            ea, eb = pre_elo.get(fid, (1500.0, 1500.0))
            p_elo_a = 1.0 / (1.0 + 10.0 ** ((eb - ea) / 400.0))
            p_bl_a = 0.65 * p_a + 0.35 * p_elo_a
            # Symmetrized bin for calibration
            import zlib
            fl = zlib.crc32(fid.encode()) & 1
            pm_s = (1.0 - p_a) if fl else p_a
            pe_s = (1.0 - p_elo_a) if fl else p_elo_a
            pb_s = (1.0 - p_bl_a) if fl else p_bl_a
            y_s = (1.0 - y_a) if fl else y_a

            brier_mkt += (pm_s - y_s) ** 2
            brier_elo += (pe_s - y_s) ** 2
            brier_blend += (pb_s - y_s) ** 2
            ll_mkt -= y_s * math.log(max(1e-5, min(1 - 1e-5, pm_s))) + (1 - y_s) * math.log(max(1e-5, min(1 - 1e-5, 1 - pm_s)))
            ll_elo -= y_s * math.log(max(1e-5, min(1 - 1e-5, pe_s))) + (1 - y_s) * math.log(max(1e-5, min(1 - 1e-5, 1 - pe_s)))
            ll_blend -= y_s * math.log(max(1e-5, min(1 - 1e-5, pb_s))) + (1 - y_s) * math.log(max(1e-5, min(1 - 1e-5, 1 - pb_s)))
            acc_mkt += (pm_s > 0.5) == (y_s == 1.0)
            acc_elo += (pe_s > 0.5) == (y_s == 1.0)
            acc_blend += (pb_s > 0.5) == (y_s == 1.0)
            n_eval += 1
            b_idx = min(9, int(pm_s * 10))
            cal_bins[b_idx][0] += 1
            cal_bins[b_idx][1] += pm_s
            cal_bins[b_idx][2] += y_s

            # Upsets & fighter ROI
            w_odd = oa if w_side == "a" else ob
            w_prob = p_a if w_side == "a" else (1.0 - p_a)
            w_elo_p = p_elo_a if w_side == "a" else (1.0 - p_elo_a)
            l_side = "b" if w_side == "a" else "a"
            if w_odd >= 250:
                upsets.append({
                    "id": fid,
                    "ev": matched_f["ev"],
                    "date": matched_f["date"],
                    "w": matched_f[w_side]["id"],
                    "l": matched_f[l_side]["id"],
                    "odd": w_odd,
                    "p_mkt": round(w_prob, 4),
                    "p_elo": round(w_elo_p, 4),
                    "m": matched_f.get("method", ""),
                    "div": matched_f.get("div", ""),
                })
            for s_side, odd_v in (("a", oa), ("b", ob)):
                f_id = matched_f[s_side]["id"]
                st = roi[f_id]
                st["n"] += 1
                is_dog = odd_v >= 110
                is_fav = odd_v <= -115
                if is_dog:
                    st["dog_n"] += 1
                if is_fav:
                    st["fav_n"] += 1
                if w_side == s_side:
                    st["w"] += 1
                    st["net"] += us_payout(odd_v)
                    if is_dog:
                        st["dog_w"] += 1
                    if is_fav:
                        st["fav_w"] += 1
                else:
                    st["net"] -= 1.0

    upsets.sort(key=lambda x: (x["p_mkt"], -x["odd"]))
    cal_out = []
    for k in range(10):
        cnt, sp, sy = cal_bins[k]
        if cnt >= 5:
            cal_out.append({"bin": k, "n": cnt, "pred": round(sp / cnt, 4), "obs": round(sy / cnt, 4)})

    roi_out = {
        fid: [v["n"], v["w"], v["fav_n"], v["fav_w"], v["dog_n"], v["dog_w"], round(v["net"], 2)]
        for fid, v in roi.items() if v["n"] >= 1
    }

    market_obj = {
        "v": 2,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eval": {
            "n": n_eval,
            "avg_vig": round(vig_sum / max(n_eval, 1), 4),
            "mkt": {"acc": round(acc_mkt / max(n_eval, 1), 4), "brier": round(brier_mkt / max(n_eval, 1), 4), "ll": round(ll_mkt / max(n_eval, 1), 4)},
            "elo": {"acc": round(acc_elo / max(n_eval, 1), 4), "brier": round(brier_elo / max(n_eval, 1), 4), "ll": round(ll_elo / max(n_eval, 1), 4)},
            "blend": {"acc": round(acc_blend / max(n_eval, 1), 4), "brier": round(brier_blend / max(n_eval, 1), 4), "ll": round(ll_blend / max(n_eval, 1), 4)},
            "calibration": cal_out,
        },
        "upsets": upsets[:35],
        "fighters": roi_out,
        "fights": mkt_fights,
    }
    (DATA / "market.json").write_text(json.dumps(market_obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"market.json gerado: {len(mkt_fights)} lutas com odds, {len(roi_out)} lutadores com ROI, {len(upsets[:35])} maiores zebras.")

    # ---------------------------------------------------------
    # 4. Processar Ranking Oficial UFC (Live Wikipedia + 534 semanas históricas) -> data/ufc_rankings.json
    # ---------------------------------------------------------
    print("Baixando ufc_rankings_dataset.csv (534 semanas de histórico oficial 2013-2026)...")
    r_rk = requests.get(f"{TT_BASE}/ufc_rankings_dataset.csv", headers=H, timeout=25)
    rk_rows = list(csv.DictReader(io.StringIO(r_rk.text)))

    career_rk = defaultdict(lambda: {"peak": 99, "peak_div": "", "peak_dt": "", "w15": set(), "w5": set(), "w1": set(), "wp4p": set(), "p4p_peak": 99})
    weeks_all = set()
    for r in rk_rows:
        fid = by_name.get(norm(r.get("fighter")))
        if not fid:
            continue
        dt = r.get("date", "")
        wc = (r.get("weightclass") or "").strip()
        try:
            rk = int(float(r.get("rank")))
        except Exception:
            continue
        weeks_all.add(dt)
        c = career_rk[fid]
        if "pound" in wc.lower():
            c["wp4p"].add(dt)
            if rk < c["p4p_peak"]:
                c["p4p_peak"] = rk
        else:
            if rk <= 15:
                c["w15"].add(dt)
            if rk <= 5:
                c["w5"].add(dt)
            if rk <= 1:
                c["w1"].add(dt)
            if rk < c["peak"]:
                c["peak"] = rk
                c["peak_div"] = wc
                c["peak_dt"] = dt

    released, live_divs, live_fighters = parse_live_wiki_rankings(by_name)
    # Incorporar também os campeões atuais nas estatísticas de pico (0 = Campeão)
    for div_name, d_obj in live_divs.items():
        if "Pound" in div_name:
            continue
        ch_entry = d_obj.get("champ")
        if ch_entry and ch_entry.get("id"):
            cid = ch_entry["id"]
            c = career_rk[cid]
            c["peak"] = 0
            c["peak_div"] = div_name
            if not c["peak_dt"]:
                c["peak_dt"] = released or "2026-11-10"

    career_out = {}
    for fid, c in career_rk.items():
        lv = live_fighters.get(fid, {})
        career_out[fid] = {
            "peak": c["peak"] if c["peak"] < 99 else None,
            "peak_div": c["peak_div"],
            "peak_dt": c["peak_dt"],
            "w15": len(c["w15"]),
            "w5": len(c["w5"]),
            "w1": len(c["w1"]),
            "wp4p": len(c["wp4p"]),
            "p4p_peak": c["p4p_peak"] if c["p4p_peak"] < 99 else None,
            "cur_div": lv.get("div", ""),
            "cur_rank": lv.get("rank"),
            "cur_delta": lv.get("delta", 0),
            "p4p": lv.get("p4p"),
            "next": lv.get("next", ""),
        }
    for fid, lv in live_fighters.items():
        if fid not in career_out:
            career_out[fid] = {
                "peak": lv.get("rank"),
                "peak_div": lv.get("div", ""),
                "peak_dt": released or "",
                "w15": 1 if lv.get("rank") is not None else 0,
                "w5": 1 if (lv.get("rank") or 99) <= 5 else 0,
                "w1": 1 if (lv.get("rank") or 99) <= 1 else 0,
                "wp4p": 1 if lv.get("p4p") else 0,
                "p4p_peak": lv.get("p4p"),
                "cur_div": lv.get("div", ""),
                "cur_rank": lv.get("rank"),
                "cur_delta": lv.get("delta", 0),
                "p4p": lv.get("p4p"),
                "next": lv.get("next", ""),
            }

    rankings_obj = {
        "v": 2,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "released": released or "2026-11-10",
        "n_weeks_history": len(weeks_all),
        "divisions": live_divs,
        "fighters": career_out,
    }
    (DATA / "ufc_rankings.json").write_text(json.dumps(rankings_obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ufc_rankings.json gerado: {len(live_divs)} divisões ao vivo (release {released}), {len(career_out)} lutadores com histórico ({len(weeks_all)} semanas).")

    # ---------------------------------------------------------
    # 5. Roster Oficial Atual do UFC (Wikipedia Live List_of_current_UFC_fighters) -> data/roster.json
    # ---------------------------------------------------------
    print("Baixando Roster Oficial Atual do UFC (Wikipedia List_of_current_UFC_fighters)...")
    ros = parse_live_wiki_roster(by_name)
    if ros:
        act_map = ros["active_map"]
        # Também inclui campeões/ranqueados ao vivo e agendados em upcoming.json como ativos no roster
        up_ids = set()
        up_p = DATA / "upcoming.json"
        if up_p.exists():
            up_raw = json.loads(up_p.read_text(encoding="utf-8"))
            up_evs = up_raw.get("events", []) if isinstance(up_raw, dict) else (up_raw if isinstance(up_raw, list) else [])
            for ev in up_evs:
                for f_u in (ev.get("fights", []) if isinstance(ev, dict) else []):
                    for sd in ("a", "b"):
                        uid = (f_u.get(sd) or {}).get("id")
                        if uid:
                            up_ids.add(uid)
        dep_map = {d["id"]: d["kind"] for d in ros["departures"] if d.get("id")}
        susp_ids = {s["id"] for s in ros["suspended"] if s.get("id")}
        ranked_live_ids = {fid for fid, lv in live_fighters.items() if lv.get("rank") is not None}

        n_act = n_ret = n_rel = n_susp = 0
        for p in fighters:
            fid = p.get("id")
            if fid in susp_ids:
                p["roster"] = "suspended"
                n_susp += 1
            elif fid in act_map or fid in ranked_live_ids or fid in up_ids:
                p["roster"] = "active"
                n_act += 1
                am = act_map.get(fid)
                if am:
                    p["roster_div"] = am["div"]
                    if am.get("dob") and p.get("DOB") in ("--", "", None):
                        p["DOB"] = am["dob"]
            elif fid in dep_map:
                p["roster"] = dep_map[fid]
                if dep_map[fid] == "retired":
                    n_ret += 1
                else:
                    n_rel += 1
            else:
                p["roster"] = "former"

        roster_obj = {
            "v": 1,
            "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_wiki": sum(len(v) for v in ros["active_by_div"].values()),
            "total_matched": n_act,
            "by_div": {
                dv: {
                    "n": len(items),
                    "ids": [x["id"] for x in items if x.get("id")],
                    "unmatched": [x["name"] for x in items if not x.get("id")][:25],
                }
                for dv, items in ros["active_by_div"].items()
            },
            "departures": ros["departures"][:60],
            "signings": ros["signings"][:60],
            "suspended": ros["suspended"][:30],
        }
        (DATA / "roster.json").write_text(json.dumps(roster_obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"roster.json gerado: {roster_obj['total_wiki']} lutadores no roster oficial ({n_act} casados em fighters.json), {len(ros['departures'])} saídas recentes, {len(ros['signings'])} contratações, {n_susp} suspensos.")

    # Salvar fighters.json enriquecido
    (DATA / "fighters.json").write_text(json.dumps(fighters, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("fighters.json atualizado com sucesso.")


if __name__ == "__main__":
    main()
