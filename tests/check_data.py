#!/usr/bin/env python3
"""Automated data quality gate for Súmula UFC.

Runs in CI before committing data updates so corrupted or inconsistent
scrapes/analytics never reach production.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path("data")
TOURN_RE = re.compile(
    r"ultimate fighter|\btuf\b|road to ufc|tournament|ultimate ultimate|ultimate japan",
    re.I,
)
ACTIVE_DIVS = [
    "Heavyweight", "Light Heavyweight", "Middleweight", "Welterweight",
    "Lightweight", "Featherweight", "Bantamweight", "Flyweight",
    "Women's Bantamweight", "Women's Flyweight", "Women's Strawweight",
]


def load(name):
    p = DATA / name
    assert p.exists(), f"Arquivo ausente: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    errors = []

    events = load("events.json")
    fights = load("fights.json")
    fighters = load("fighters.json")
    analytics = load("analytics.json")
    cards = load("cards.json")
    decisions = load("decisions.json")
    live = load("live.json")
    overrides = load("overrides.json")

    assert isinstance(events, list) and len(events) > 700, "events.json inválido"
    assert isinstance(fights, list) and len(fights) > 8000, "fights.json inválido"
    assert isinstance(fighters, list) and len(fighters) > 2500, "fighters.json inválido"
    assert isinstance(overrides, dict), "overrides.json inválido"

    emap = {e["id"]: e for e in events}
    fmap = {f["id"]: f for f in fighters}
    if len(emap) != len(events):
        errors.append("IDs duplicados em events.json")
    if len(fmap) != len(fighters):
        errors.append("IDs duplicados em fighters.json")
    if len({f["id"] for f in fights}) != len(fights):
        errors.append("IDs duplicados em fights.json")

    # Referential integrity + title checks
    for f in fights:
        a, b = f["a"]["id"], f["b"]["id"]
        if a == b:
            errors.append(f"Luta contra si mesmo: {f['id']}")
        if f["ev"] not in emap:
            errors.append(f"Luta sem evento: {f['id']}")
        if a not in fmap or b not in fmap:
            errors.append(f"Lutador ausente em fighters.json na luta {f['id']}")
        tt = f.get("tt") or ""
        if f.get("title") and TOURN_RE.search(tt):
            errors.append(f"Torneio/TUF marcado como cinturão: {f['id']} ({tt})")
        if "superfight" in tt.lower() and (not f.get("title") or f.get("div") != "Open Weight"):
            errors.append(f"Superfight mal classificado: {f['id']} (title={f.get('title')}, div={f.get('div')})")

    # Duplicate espn_id check
    espn_owners = Counter()
    for p in fighters:
        eid = p.get("espn_id")
        if eid:
            espn_owners[str(eid)] += 1
    dup_espn = [k for k, v in espn_owners.items() if v > 1]
    if dup_espn:
        errors.append(f"espn_id duplicado entre lutadores distintos: {dup_espn}")

    # Stale 2021 rankings file must not exist
    if (DATA / "ufc_rankings.json").exists():
        errors.append("data/ufc_rankings.json obsoleto ainda existe")

    # Active champions check
    ch = {}
    for f in sorted(fights, key=lambda x: (x["date"], -x.get("ord", 0))):
        if not f.get("title") or f.get("res") not in ("a", "b"):
            continue
        if "interim" in (f.get("tt") or "").lower():
            continue
        ch[f["div"]] = (f[f["res"]]["name"], f["date"], f.get("tt", ""))
    for dv in ACTIVE_DIVS:
        if dv not in ch:
            errors.append(f"Divisão ativa sem campeão identificado: {dv}")
        elif TOURN_RE.search(ch[dv][2]):
            errors.append(f"Campeão atual inválido (TUF/torneio) em {dv}: {ch[dv]}")

    # Sync check with analytics & derived JSONs
    an_fighters = analytics.get("fighters", {})
    if len(an_fighters) < 2500:
        errors.append(f"analytics.json com poucos lutadores: {len(an_fighters)}")
    if not cards.get("cards"):
        errors.append("cards.json vazio")
    if not decisions.get("fights"):
        errors.append("decisions.json vazio")
    if not live.get("fights"):
        errors.append("live.json vazio")

    if errors:
        print("FALHA NA VALIDAÇÃO DE DADOS:")
        for e in errors:
            print(" -", e)
        sys.exit(1)

    print(
        f"OK: {len(events)} eventos, {len(fights)} lutas, {len(fighters)} lutadores, "
        f"{len(ACTIVE_DIVS)} campeões ativos válidos, 0 inconsistências."
    )


if __name__ == "__main__":
    main()
