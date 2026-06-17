# Cycling indicators (Level of Traffic Stress accessibility)

Optional GHSCI workflow that classifies the routable network by **Level of Traffic
Stress (LTS 1–4)** and computes **safe-route (LTS ≤ 2) cycling accessibility** to
destinations, aggregated to sample points, the population grid, and the city/region.

It ports the prior R implementation and follows the Global Cycling Indicators
manuscript (LTS classification per Jafari et al.; two-component LTS impedance).
Routing is **undirected**, consistent with the GHSCI pgRouting accessibility engine.

The workflow is completely optional and only runs if a `cycling_indicators` configuration 
is present.

---

## 1. Enabling and configuring (region YAML)

Add a `cycling_indicators` block to a region configuration. Set it to `true` to enable
with built-in defaults, or provide a mapping of options. All `data` paths are relative
to `process/data`.

```yaml
cycling_indicators:
  speed_limits:
    # Per-highway default speeds (km/h) used where OSM maxspeed is missing.
    defaults:
      motorway: 100
      trunk: 80
      primary: 70
      secondary: 55
      tertiary: 50
      residential: 40
      living_street: 30
      service: 25
    # ...or instead of `defaults`, a CSV with columns: highway, default_maxspeed
    # defaults_csv: MyCity_2025/speed_defaults.csv
    # Optional spatial speed overrides (ports the R assignBufferSpeed).
    # zones:
    #   - data: MyCity_2025/low_speed_zones.gpkg  # polygon or line dataset
    #     layer: zones                            # optional layer name
    #     speed: 30                               # km/h assigned to matched edges
    #     buffer: 20                              # buffer (m) for line zone geometry
    #     method: overlap                         # overlap (default) | intersects | within
    #     overlap_threshold: 0.5                  # min share of edge footprint in-zone
    #     edge_buffer: 10                         # edge footprint width (m); default max(5, buffer/2)
    #     apply_to: missing                       # missing (default) | all
  no_cycle: [steps, corridor]                     # highway classes where cycling is banned
  distances: [2000, 5000]                         # catchment thresholds (m)
  # Destination specs (default shown). Each maps a layer + optional SQL `where` to an
  # indicator `name`, tagged by `category` and strictness `variant`; composite
  # "all categories" indicators are derived per variant. Specs whose layer is absent
  # (e.g. pt_stops_headway with no GTFS feed) are skipped.
  destinations:
    - {name: fresh_food_market,       category: food, variant: strict,  layer: destinations, where: "dest_name = 'fresh_food_market'"}
    - {name: fresh_food_pooled,       category: food, variant: lenient, layer: destinations, where: "dest_name IN ('fresh_food_market', 'convenience')"}
    - {name: public_open_space_large, category: pos,  variant: strict,  layer: aos_public_large_nodes_30m_line}
    - {name: public_open_space_any,   category: pos,  variant: lenient, layer: aos_public_any_nodes_30m_line}
    - {name: pt_frequent,             category: pt,   variant: strict,  layer: pt_stops_headway, where: "headway <= 20"}
    - {name: pt_any,                  category: pt,   variant: lenient, layer: destinations, where: "dest_name = 'pt_any'"}
```

### Speed-zone matching (`method`)

- **`overlap`** (default; the R "bufferRatio") — an edge qualifies when at least
  `overlap_threshold` (default 0.5) of its buffered footprint (`edge_buffer` m, default
  `max(5, buffer/2)`) lies within the unioned, buffered zone.
- **`intersects` / `within`** — cruder `ST_Intersects` / `ST_Within` predicates (use for
  clean polygon-area zones).

`apply_to: missing` (default) overrides only edges whose OSM speed was missing
(preserving tagged speeds, as R does); `apply_to: all` overrides every matched edge.

The JSON schema for these options is in
`configuration/regions/region-json-schema.json`; a fully documented example is in
`configuration/templates/region_template.yml`.

---

## 2. Pipeline steps

Run automatically as part of `analysis` (and skipped when not configured):

| Step | Runs after | Produces |
|---|---|---|
| `_cycling_lts_network.py` | `_03_create_network_resources` | LTS columns on the `edges` table |
| `_cycling_accessibility.py` | `_11_neighbourhood_analysis` | the `sample_points_cycling` table |
| `_12_aggregation.py` → `calc_cycling_indicators` | the standard aggregation | cycling columns on the grid and city summaries |

Each can also be run directly: `python subprocesses/_cycling_lts_network.py <codename>`
and `python subprocesses/_cycling_accessibility.py <codename>`.

---

## 3. Outputs (tables and columns)

**`edges`** (added by `_cycling_lts_network`):

| Column | Type | Description |
|---|---|---|
| `bike_facility` | text | cycling infrastructure class (bikepath / shared_path / separated_lane / simple_lane / shared_street / no lane/track/path) |
| `maxspeed_kmh` | float | parsed / imputed speed limit (km/h) |
| `adt` | float | assumed average daily traffic by road hierarchy |
| `lvl_traf_stress` | int | Level of Traffic Stress, 1 (low) – 4 (high) |
| `lts_imped` | float | forward LTS impedance (m): link term + `to`-node intersection penalty |
| `cost_lts` | float | forward safe-routing cost = length + `lts_imped` |
| `cost_lts_reverse` | float | reverse safe-routing cost (length + `from`-node penalty) |
| `bike_permitted` | bool | whether cycling is permitted on the edge |

**`sample_points_cycling`** (added by `_cycling_accessibility`): `point_id`, `grid_id`,
`edge_ogc_fid`, `geom`, plus per destination spec `<name>` and threshold `<d>`:

- `sp_cycle_nearest_node_<name>` — safe-route distance (m) to the nearest destination
- `sp_cycle_access_<name>_<d>m` — binary access (1/0) within `<d>` metres
- `sp_cycle_access_all_<variant>_<d>m` — composite: all categories of a variant reachable

**Grid summary** (added by `calc_cycling_indicators`):
`pct_access_cycle_<name>_<d>m` and `pct_access_cycle_all_<variant>_<d>m` (grid-cell % with
access) and `avg_cycle_dist_<name>` (grid-cell mean distance, m).

**City summary**: the population-weighted versions, `pop_pct_access_cycle_…` and
`pop_avg_cycle_dist_<name>`.

When `cycling_indicators` is enabled, `generate` exports the LTS `edges`, the cycling
grid/city columns, and `sample_points_cycling` to the region GeoPackage.

---

## 4. Developer reference (key functions)

### `_cycling_lts_network.py`
- `cycling_lts_network(codename)` — subprocess entry point.
- `cycling_config(r)` — returns the region's cycling config dict, or `None` if disabled.
- `compute_cycling_lts(r, config)` — orchestrates classification and write-back.
- `classify_cycleway(edges)` → `(highway, bike_facility)` (ports R `createCycleway`).
- `load_speed_defaults(speed_config)` — defaults from CSV / inline mapping / built-in.
- `assign_speed(edges, defaults)`, `assign_adt(highway)`,
  `assign_lts(highway, facility, speed, adt)` — LTS Table 1 cascade.
- `add_impedance(r, edges)` — two-component impedance and directional costs.
- `apply_speed_zones(r, edges, zones)` — spatial speed overrides (R `assignBufferSpeed`).

### `_cycling_accessibility.py`
- `cycling_accessibility(codename)` — subprocess entry point.
- `cycling_poi_distance(r, distance, layer, category_field, categories)` — per-node
  safe-route distances via the destination-node lookup.
- `cycling_sample_point_access(r, nodes_poi_dist, node_index, thresholds)` — maps node
  distances to sample points and derives binary access scores.

### `setup_sp.py` (shared engine, parameterised)
- `build_dest_node_lookup(r, active_layers, distance, ..., edge_table='edges',
  cost='length', reverse_cost='length', where=None)` — destination-seeded
  `pgr_drivingDistance`. Cycling passes `edge_table='edges'`, `cost='cost_lts'`,
  `reverse_cost='cost_lts_reverse'`, `where='lvl_traf_stress <= 2 AND bike_permitted'`.
  Pedestrian defaults are unchanged.

### `_12_aggregation.py`
- `calc_cycling_indicators(r)` — gated grid + population-weighted city aggregation of the
  cycling sample-point indicators (adds columns to the existing summary tables).

---

## 5. Notes and current limitations

- **Routing is undirected** (the directional question is still under discussion); the R
  one-way edge expansion and ADT halving are omitted (the halving cancelled in the LTS
  thresholds, so LTS results are unchanged).
- **Distances are "effective"** (LTS-impedance-weighted via `cost_lts`), a few percent
  above true metres on LTS 2 links; route `cost='length'` if pure-metre distance is wanted.
- **Speed defaults** ship as a global standard table; configure per-region `defaults`,
  `defaults_csv`, and `zones` for published analyses.
- **Scope so far:** fresh food, public open space and public transport, each in a
  stricter and a less-strict / pooled variant, with binary access, safe-route distance,
  and composite "all categories" indicators. Still to come: the **activity centre**
  (co-located cluster) composite, and the speed-zone `angleDiff` refinement (a buffered
  overlap approximates the latter).
- Specs whose layer is absent are skipped — e.g. `pt_frequent` needs `pt_stops_headway`
  (a GTFS feed), and the public-open-space variants need the `aos_public_*_nodes_30m_line`
  layers from `_06_open_space_areas_setup`.
