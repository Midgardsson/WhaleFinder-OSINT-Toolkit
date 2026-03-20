#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  🐋 Cetdetektor v1.0 — Midgardsson OSINT Kit                ║
║  Cetészlelések — GBIF Occurrence API (NO/IS/GL/FO)          ║
║  Forrás: api.gbif.org | Licenc: CC BY 4.0                   ║
╚══════════════════════════════════════════════════════════════╝

Használat:
  python3 cetdetektor.py                        # utolsó 30 nap, NO+IS+GL+FO
  python3 cetdetektor.py --days 90              # utolsó 90 nap
  python3 cetdetektor.py --species orca         # csak orca
  python3 cetdetektor.py --region nord          # Észak-Norvégia
  python3 cetdetektor.py --countries NO IS      # egyedi országlista
  python3 cetdetektor.py --lat 69.6 --lon 18.9 --radius 100  # koordináta alapú
  python3 cetdetektor.py --save                 # napi JSON mentés data/ mappába
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

import httpx
from rich import box
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# ── GBIF taxon kulcsok ─────────────────────────────────────────
GBIF_ORDER_CETACEA = 733  # Cetacea rend

SPECIES_KEYS = {
    "orca":       2440483,   # Orcinus orca
    "humpback":   2440718,   # Megaptera novaeangliae
    "minke":      2440557,   # Balaenoptera acutorostrata
    "sperm":      2440523,   # Physeter macrocephalus
    "fin":        2440537,   # Balaenoptera physalus
    "blue":       2440530,   # Balaenoptera musculus
    "narwhal":    2440067,   # Monodon monoceros
    "beluga":     5220006,   # Delphinapterus leucas
    "bottlenose": 2440090,   # Tursiops truncatus
    "porpoise":   2440076,   # Phocoena phocoena
}

SPECIES_NO = {
    "orca":       "Spekkhogger",
    "humpback":   "Knølhval",
    "minke":      "Vågehval",
    "sperm":      "Spermhval",
    "fin":        "Finnhval",
    "blue":       "Blåhval",
    "narwhal":    "Narhval",
    "beluga":     "Hvithval / Beluga",
    "bottlenose": "Stor tannhval",
    "porpoise":   "Nise",
}

# ── Régió bounding box-ok ──────────────────────────────────────
REGIONS = {
    "nord":     {"decimalLatitude": "67,72",  "decimalLongitude": "14,32"},  # Észak-NO
    "tromsø":   {"decimalLatitude": "69,71",  "decimalLongitude": "17,21"},
    "lofoten":  {"decimalLatitude": "67,69",  "decimalLongitude": "13,16"},
    "svalbard": {"decimalLatitude": "74,81",  "decimalLongitude": "10,30"},
    "oslo":     {"decimalLatitude": "58,60",  "decimalLongitude": "9,11"},
    "vest":     {"decimalLatitude": "58,63",  "decimalLongitude": "4,8"},
}

# ── Adatstruktúra ──────────────────────────────────────────────
@dataclass
class CetSighting:
    gbif_key:     int    = 0
    species:      str    = ""
    common_no:    str    = ""
    date:         str    = ""
    lat:          float  = 0.0
    lon:          float  = 0.0
    count:        int    = 1
    locality:     str    = ""
    region:       str    = ""
    recorded_by:  str    = ""
    source:       str    = ""
    image_url:    str    = ""
    ref_url:      str    = ""
    country:      str    = ""


# ── API lekérés ────────────────────────────────────────────────
# ── Alapértelmezett országok ───────────────────────────────────
DEFAULT_COUNTRIES = ["NO", "IS", "GL", "FO"]

COUNTRY_NAMES = {
    "NO": "Norvégia", "IS": "Izland",
    "GL": "Grönland", "FO": "Feröer",
    "SJ": "Svalbard", "DK": "Dánia", "GB": "Egyesült Királyság",
}


async def fetch_sightings(
    days: int = 30,
    species_key: int = None,
    region: str = None,
    lat: float = None,
    lon: float = None,
    radius_km: int = None,
    limit: int = 50,
    countries: list = None,
) -> list[CetSighting]:
    """GBIF Occurrence API lekérés — több ország, párhuzamosan."""

    if countries is None:
        countries = DEFAULT_COUNTRIES

    base = "https://api.gbif.org/v1/occurrence/search"
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Alap params — country nélkül, azt minden kéréshez külön adjuk
    base_params = {
        "orderKey":         GBIF_ORDER_CETACEA,
        "hasCoordinate":    "true",
        "occurrenceStatus": "PRESENT",
        "eventDate":        f"{since},{today}",
        "limit":            limit,
    }

    if species_key:
        base_params["taxonKey"] = species_key
        del base_params["orderKey"]

    if region and region in REGIONS:
        r = REGIONS[region]
        base_params["decimalLatitude"]  = r["decimalLatitude"]
        base_params["decimalLongitude"] = r["decimalLongitude"]

    if lat and lon and radius_km:
        base_params["decimalLatitude"]  = f"{lat-0.5},{lat+0.5}"
        base_params["decimalLongitude"] = f"{lon-0.5},{lon+0.5}"

    async def fetch_one(cl, country):
        params = {**base_params, "country": country}
        try:
            r = await cl.get(base, params=params)
            if r.status_code != 200:
                console.print(f"[red]GBIF {country} hiba: HTTP {r.status_code}[/]")
                return [], 0
            data = r.json()
            return data.get("results", []), data.get("count", 0)
        except Exception as e:
            console.print(f"[red]GBIF {country} exception: {e}[/]")
            return [], 0

    all_results = []
    total_count = 0

    async with httpx.AsyncClient(
        timeout=20,
        headers={"User-Agent": "MidgardsonCetDetector/1.1 python-httpx"}
    ) as cl:
        tasks = [fetch_one(cl, c) for c in countries]
        responses = await asyncio.gather(*tasks)
        for (recs, cnt), country in zip(responses, countries):
            total_count += cnt
            cname = COUNTRY_NAMES.get(country, country)
            console.print(f"  [dim]{cname}: {cnt} találat[/]")
            # ország taget hozzáadjuk a rekordhoz
            for rec in recs:
                rec["_country"] = country
            all_results.extend(recs)

    console.print(f"  [dim]Összesen: {total_count} | Lekérve: {len(all_results)}[/]")

    results = []
    seen_keys = set()
    for rec in all_results:
        # Duplikáció szűrés
        key = rec.get("key", 0)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Fajnév
        species = rec.get("species", rec.get("scientificName", "Ismeretlen"))
        common  = rec.get("vernacularName", "")

        if not common:
            for sp_key, sci_pattern in [
                ("orca", "Orcinus"), ("humpback", "Megaptera"),
                ("minke", "Balaenoptera acutorostrata"),
                ("sperm", "Physeter"), ("fin", "Balaenoptera physalus"),
                ("blue", "Balaenoptera musculus"), ("narwhal", "Monodon"),
                ("beluga", "Delphinapterus"), ("porpoise", "Phocoena"),
            ]:
                if sci_pattern.lower() in species.lower():
                    common = SPECIES_NO[sp_key]
                    break

        # Kép URL
        image_url = ""
        media = rec.get("extensions", {}).get(
            "http://rs.gbif.org/terms/1.0/Multimedia", []
        )
        if media:
            image_url = media[0].get("http://purl.org/dc/terms/identifier", "")

        # Referencia URL
        ref_url = rec.get("references", "")
        if not ref_url:
            refs = [
                m.get("http://purl.org/dc/terms/references", "")
                for m in media if m.get("http://purl.org/dc/terms/references")
            ]
            ref_url = refs[0] if refs else ""

        sighting = CetSighting(
            gbif_key    = key,
            species     = species,
            common_no   = common,
            date        = rec.get("eventDate", "")[:10],
            lat         = rec.get("decimalLatitude", 0.0),
            lon         = rec.get("decimalLongitude", 0.0),
            count       = rec.get("individualCount", 1) or 1,
            locality    = rec.get("locality", rec.get("verbatimLocality", "")),
            region      = rec.get("stateProvince", rec.get("county", "")),
            recorded_by = rec.get("recordedBy", ""),
            source      = rec.get("datasetName", rec.get("publishingCountry", "")),
            country     = rec.get("_country", ""),
            image_url   = image_url,
            ref_url     = ref_url,
        )
        results.append(sighting)

    # Dátum szerint rendezve
    results.sort(key=lambda x: x.date, reverse=True)
    return results

    return results


# ── Megjelenítés ───────────────────────────────────────────────
def print_sightings(sightings: list[CetSighting], args):
    """Cetészlelések megjelenítése Rich táblában."""

    console.print()
    title = f"🐋 Cetdetektor — Norvégia"
    if args.species:
        title += f" | {SPECIES_NO.get(args.species, args.species)}"
    if args.region:
        title += f" | {args.region.capitalize()}"
    console.rule(f"[cyan]{title}[/]")

    if not sightings:
        console.print("  [dim]Nincs találat a megadott szűrőkkel.[/]")
        return

    t = Table(
        "Dátum", "Faj (NO)", "Tudományos név", "Db", "Helyszín", "Koordináta",
        box=box.SIMPLE, border_style="dim",
        show_header=True, header_style="bold cyan"
    )
    t.columns[0].width = 11
    t.columns[1].width = 18
    t.columns[2].width = 28
    t.columns[3].width = 4
    t.columns[4].width = 20
    t.columns[5].width = 18

    for s in sightings:
        coord = f"{s.lat:.3f}°N {s.lon:.3f}°E" if s.lat else "—"
        location = s.locality or s.region or "—"
        common = s.common_no or "—"

        # Faj alapú szín
        clr = "white"
        sp = s.species.lower()
        if "orcinus" in sp:      clr = "red bold"
        elif "megaptera" in sp:  clr = "cyan"
        elif "physeter" in sp:   clr = "yellow"
        elif "monodon" in sp:    clr = "magenta"
        elif "delphin" in sp:    clr = "bright_blue"

        t.add_row(
            f"[dim]{s.date}[/]",
            f"[{clr}]{common[:18]}[/]",
            f"[dim italic]{s.species[:28]}[/]",
            str(s.count),
            location[:20],
            f"[dim]{coord}[/]",
        )

    console.print(t)
    console.print(f"  [dim]{len(sightings)} észlelés | Forrás: GBIF (CC BY 4.0) | api.gbif.org[/]")
    console.print()


def export_json(sightings: list[CetSighting], filename: str):
    """JSON export."""
    import os
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    data = [s.__dict__ for s in sightings]
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    console.print(f"  [green]✓ JSON mentve: {filename} ({len(sightings)} észlelés)[/]")


def save_daily(sightings: list[CetSighting], prefix: str = None):
    """Napi akkumulált JSON mentés — data/sightings_YYYYMMDD.json.
    
    Ha a fájl már létezik, merge-eli az új észleléseket (gbif_key alapján deduplikálva).
    """
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir   = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    today    = datetime.now().strftime("%Y%m%d")
    filename = os.path.join(data_dir, f"sightings_{today}.json")

    existing = {}
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for item in json.load(f):
                    existing[item["gbif_key"]] = item
        except Exception:
            pass

    new_count = 0
    for s in sightings:
        if s.gbif_key not in existing:
            existing[s.gbif_key] = s.__dict__
            new_count += 1

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(list(existing.values()), f, ensure_ascii=False, indent=2)

    console.print(f"  [green]✓ Napi mentés: {filename} | +{new_count} új | összesen: {len(existing)}[/]")
    return filename


# ── Main ───────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🐋 Cetdetektor — Norvég cetészlelések (GBIF)"
    )
    parser.add_argument("--days",    type=int,   default=30,   help="Visszatekintés napokban (alap: 30)")
    parser.add_argument("--limit",   type=int,   default=50,   help="Max találat (alap: 50)")
    parser.add_argument("--species", type=str,   default=None,
        help=f"Faj: {', '.join(SPECIES_KEYS.keys())}")
    parser.add_argument("--region",  type=str,   default=None,
        help=f"Régió: {', '.join(REGIONS.keys())}")
    parser.add_argument("--lat",      type=float, default=None,  help="Szélesség (pl. 69.6)")
    parser.add_argument("--lon",      type=float, default=None,  help="Hosszúság (pl. 18.9)")
    parser.add_argument("--radius",   type=int,   default=100,   help="Keresési sugár km-ben")
    parser.add_argument("--countries",nargs="+",  default=None,
        help=f"Országkódok (alap: NO IS GL FO) pl. --countries NO IS")
    parser.add_argument("--json",     action="store_true",        help="JSON export (egyedi fájl)")
    parser.add_argument("--save",     action="store_true",        help="Napi akkumulált mentés → data/sightings_YYYYMMDD.json")
    parser.add_argument("--output",   type=str,   default="ceteszleles", help="JSON fájlnév prefix")

    args = parser.parse_args()

    # Fejléc
    countries = [c.upper() for c in args.countries] if args.countries else None
    country_list = ", ".join(countries) if countries else "NO+IS+GL+FO"
    console.print(Panel(
        f"[bold cyan]🐋 Cetdetektor v1.1 — Midgardsson OSINT Kit[/]\n"
        f"[dim]Visszatekintés: {args.days} nap | "
        f"Faj: {args.species or 'összes'} | "
        f"Országok: {country_list} | "
        f"Régió: {args.region or '—'}[/]",
        border_style="cyan"
    ))

    # Species key
    species_key = None
    if args.species:
        species_key = SPECIES_KEYS.get(args.species.lower())
        if not species_key:
            console.print(f"[red]Ismeretlen faj: {args.species}[/]")
            console.print(f"Elérhető: {', '.join(SPECIES_KEYS.keys())}")
            sys.exit(1)

    # Lekérés
    sightings = asyncio.run(fetch_sightings(
        days=args.days,
        species_key=species_key,
        region=args.region,
        lat=args.lat,
        lon=args.lon,
        radius_km=args.radius if args.lat else None,
        limit=args.limit,
        countries=countries,
    ))

    # Megjelenítés
    print_sightings(sightings, args)

    # JSON export (egyedi fájl)
    if args.json and sightings:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"{args.output}_{ts}.json"
        export_json(sightings, filename)

    # Napi akkumulált mentés
    if args.save:
        save_daily(sightings)
        # index.json frissítése a térkép számára
        import os, glob
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir   = os.path.join(script_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        files = sorted([os.path.basename(f) for f in glob.glob(os.path.join(data_dir, "sightings_*.json"))])
        idx_path = os.path.join(data_dir, "index.json")
        with open(idx_path, "w") as f:
            json.dump({"files": files, "updated": datetime.now().isoformat()}, f, indent=2)
        console.print(f"  [dim]index.json frissítve: {idx_path} ({len(files)} fájl)[/]")


if __name__ == "__main__":
    main()
