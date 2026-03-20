# 🐋 WhaleFinder OSINT Toolkit

***North Atlantic cetacean sighting intelligence — CLI collector + interactive map***

Part of the [Midgardsson OSINT Kit](https://github.com/Midgardsson). Pulls verified whale and dolphin observation records from the GBIF Occurrence API, displays them in a terminal table, exports to JSON, and visualises the dataset on an interactive Leaflet map with species filtering, date range selection, country chips, and an experimental migration route overlay.

---

## Repository structure

```
WhaleFinder-OSINT-Toolkit/
├── WhaleFinder.py          # CLI data collector
├── WhaleFinder_map.html    # Standalone Leaflet map viewer
└── data/                   # Auto-created by --save
    ├── sightings_YYYYMMDD.json
    └── index.json
```

---

## WhaleFinder.py — CLI collector

### Data source

**GBIF Occurrence API** (`api.gbif.org/v1/occurrence/search`)
Taxonomic order: *Cetacea* (key 733). License: CC BY 4.0.
Default coverage: Norway · Iceland · Greenland · Faroe Islands (ISO: NO, IS, GL, FO).

### Requirements

```bash
pip install httpx rich
```

Python 3.10+ required (uses `list[type]` type hints).

### Usage

```bash
# Last 30 days, all species, NO+IS+GL+FO
python3 WhaleFinder.py

# Last 90 days
python3 WhaleFinder.py --days 90

# Filter by species
python3 WhaleFinder.py --species orca
python3 WhaleFinder.py --species humpback --days 60

# Filter by region (bounding box presets)
python3 WhaleFinder.py --region tromsø
python3 WhaleFinder.py --region svalbard --days 180

# Custom country list
python3 WhaleFinder.py --countries NO IS
python3 WhaleFinder.py --countries NO IS GL FO SJ

# Coordinate-based search
python3 WhaleFinder.py --lat 69.6 --lon 18.9 --radius 100

# Export
python3 WhaleFinder.py --json                          # timestamped JSON file
python3 WhaleFinder.py --save                          # daily accumulating JSON → data/
python3 WhaleFinder.py --days 90 --save --species orca # combine freely
```

### Available species

| Key | Norwegian | Scientific name |
|-----|-----------|-----------------|
| `orca` | Spekkhogger | *Orcinus orca* |
| `humpback` | Knølhval | *Megaptera novaeangliae* |
| `minke` | Vågehval | *Balaenoptera acutorostrata* |
| `sperm` | Spermhval | *Physeter macrocephalus* |
| `fin` | Finnhval | *Balaenoptera physalus* |
| `blue` | Blåhval | *Balaenoptera musculus* |
| `narwhal` | Narhval | *Monodon monoceros* |
| `beluga` | Hvithval / Beluga | *Delphinapterus leucas* |
| `bottlenose` | Stor tannhval | *Tursiops truncatus* |
| `porpoise` | Nise | *Phocoena phocoena* |

### Available regions

| Key | Area |
|-----|------|
| `nord` | Northern Norway (67–72°N) |
| `tromsø` | Tromsø area (69–71°N) |
| `lofoten` | Lofoten Islands |
| `svalbard` | Svalbard archipelago |
| `oslo` | Oslofjord area |
| `vest` | West coast (58–63°N) |

### How it works

Requests are sent in parallel (`asyncio.gather`) — one per country — with duplicate suppression by GBIF occurrence key. The script resolves Norwegian common names from scientific name patterns when GBIF doesn't provide a `vernacularName`. Results are sorted newest-first and rendered in a `rich` table with per-species colour coding (orca = red, humpback = cyan, sperm = yellow, narwhal = magenta, beluga = blue).

### Daily accumulation and map feed

`--save` writes to `data/sightings_YYYYMMDD.json` and merges new records into any existing file for the same day (deduplication by `gbif_key`). It also regenerates `data/index.json` listing all available daily files — this is the feed the map reads.

```bash
# Example cron: collect daily at 06:00
0 6 * * * cd /path/to/WhaleFinder && python3 WhaleFinder.py --days 7 --save
```

---

## WhaleFinder_map.html — Leaflet map viewer

A self-contained single-file web app. No build step, no server required for local use. Drop it next to the `data/` folder and open it in a browser, or serve the directory over HTTP.

### Dependencies (CDN)

- [Leaflet 1.9.4](https://leafletjs.com) — map engine
- [Leaflet.markercluster 1.5.3](https://github.com/Leaflet/Leaflet.markercluster) — cluster layer
- Google Fonts: Playfair Display, DM Sans, DM Mono

### Data loading

On startup the map fetches `data/index.json` to discover available daily files, then loads all of them in parallel and merges the records client-side. The total, visible, and species counts update in the header bar. If no `data/` folder is found, all counters show `0` and the map loads empty.

### Sidebar controls

**Date range** — From / To date pickers. Shows the number of days selected and the count of matching records in the hint below.

**Country chips** — Toggle individual countries (NO, IS, GL, FO, etc.). Built dynamically from whatever countries appear in the loaded data.

**Species list** — Toggle individual species on/off. Each species has a distinct colour and emoji marker. Select All / Clear All buttons provided.

All three filters are combined: only records matching the active date range *and* selected countries *and* selected species are shown on the map.

### Markers and popups

Each sighting is a teardrop-shaped pin coloured by species. Nearby pins are automatically clustered (small = blue, large = orange). Clicking a pin opens a popup showing:

- Norwegian common name + scientific name
- Date, individual count, locality, coordinates, country
- Photo thumbnail (if GBIF has media for the record) — click to open lightbox
- Link to the original GBIF source record

### Migration route overlay

Enabled when **exactly one species** is active and the date range covers **≥ 90 days**. Once unlocked, the route toggle appears in the sidebar.

The algorithm groups sightings by calendar month, computes a centroid for each month, then draws a dashed polyline connecting consecutive monthly centroids in chronological order. Jumps exceeding the configurable max-distance slider (50–1000 km, default 300 km) are skipped. Circle markers indicate each monthly cluster, sized proportionally to the number of sightings.

> ⚠️ This is an aggregated sighting sequence from multiple individuals — not GPS tracking data.

### Language

The UI supports Norwegian (NO) and English (EN), switchable via the toggle in the header. Labels, tooltips, and popup field names update on the fly.

### Responsive layout

On screens ≤ 768px the sidebar becomes a full-screen drawer accessible via a hamburger button. The map takes up the remaining viewport height.

---

## License

Data: [GBIF — CC BY 4.0](https://www.gbif.org/terms)
Code: MIT
