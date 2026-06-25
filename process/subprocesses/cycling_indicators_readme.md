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
  # Activity centre (destination cluster) — set false to disable; defaults shown.
  activity_centres:
    walk_threshold: 400          # pedestrian co-location radius (m); ~5 min walk
    categories: [food, pos, pt]  # categories that must all be present
    tiers:                       # tier name -> destination variant it is built from
      local: lenient
      complete: strict
```

### Activity centres (destination clusters)

An **activity centre** is a network location whose **pedestrian** walk-shed
(`walk_threshold` m, default 400 ≈ 5 min) reaches at least one destination of *every*
required `category`. Two tiers are derived by default — a **local** (everyday) centre
from the lenient destination variants and a **complete** (high-amenity) centre from the
strict variants. Each tier is materialised as a derived destination layer
(`activity_centre_<tier>`) and then measured like any other destination, so the outputs
include the cycling **safe-route distance to the nearest centre** and **binary access**
within each catchment. This ports `INDICATOR_DESIGN.md` §4 (anchor rule; co-location on
the pedestrian network, cycling access measured to the centres). Tiers whose required
categories are not all present (e.g. no `strict` PT layer) are skipped.

### Locally-relevant custom destinations and "local custom" combined indicators

Any locally-relevant destination type can be added as an ordinary `destinations` spec
(after loading it via `points_of_interest`), giving per-type access + distance at each
threshold with no code change. To let it also join the **combined** indicators *without
disturbing the globally-comparable set*, use **named indicator sets**:

```yaml
cycling_indicators:
  destinations:
    # ... the global food / pos / pt specs ...
    - {name: bike_rack, category: bike_rack, variant: any, layer: destinations, where: "dest_name = 'bike_rack'"}
  combined_access:                                    # "all categories reachable" sets
    local_custom: {categories: [food, pos, pt, bike_rack]}   # 'standard' is always implicit
  activity_centres:                                   # now a map of named definitions
    local_custom:
      walk_threshold: 400
      categories: [food, pos, pt, bike_rack]
      tiers: {local: lenient, complete: strict}
```

- A **`standard`** set/definition over the global categories is *always* present and
  keeps the bare, comparable names (`all_strict` / `all_lenient`,
  `activity_centre_<tier>`); any other named set is namespaced
  (`all_local_custom_strict`, `activity_centre_local_custom_<tier>`).
- A category with a single variant (a bike rack is just `any`) joins **both** the strict
  and lenient sides via its sole spec — so it counts toward both the `local` (lenient)
  and `complete` (strict) tiers and both composite variants.
- This keeps Curitiba comparable to every other city on the standard indicators while
  adding a local-custom layer (e.g. a complete activity centre that also has a bike rack).

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
  (`<name>` includes `activity_centre_<tier>` and `activity_centre_<set>_<tier>` centres)
- `sp_cycle_access_<name>_<d>m` — binary access (1/0) within `<d>` metres
- `sp_cycle_access_all_<variant>_<d>m` — standard composite (all global categories of a
  variant reachable); named sets add `sp_cycle_access_all_<set>_<variant>_<d>m`

Derived **`activity_centre_<tier>`** (and `activity_centre_<set>_<tier>`) point layers (the
centre nodes themselves) are also written for QA / mapping and exported by `generate`.

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
- `derive_activity_centres(r, config, specs)` — identifies activity-centre nodes (one of
  each category within a pedestrian walk-shed) per definition × tier, returns them as specs.
- `activity_centre_config(config)` / `activity_centre_definitions(config)` — resolve the
  standard activity-centre options / the full `{name: definition}` map (or `{}` if disabled).
- `combined_access_sets(config, specs)` — the named "all categories reachable" sets
  (always includes `standard`).
- `_resolve_member(specs, category, variant)` — the spec for a category at a strictness
  variant, falling back to its sole spec (so a single-variant category joins both).

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

## 5. Validating against the R pipeline

`compare_cycling_r_python.py` (in `process/`) quantifies how closely the Python port
reproduces the original R pipeline's outputs for a region:

```bash
python compare_cycling_r_python.py <codename> \
    --r-gpkg  ../../cyclingIndicators/output/<City>/<City>_cyclingIndicators.gpkg \
    [--python-gpkg <region>_<buffer>m_buffer.gpkg]   # else reads PostGIS \
    [--distribution-only]                            # skip the point_id join \
    [--spatial]                                      # per-edge LTS match \
    [--out comparison.md]
```

- **Sample-point access — city rates (distribution)**: each pipeline's overall access rate
  over *its own* sample points, per indicator, with the difference. Needs no `point_id`
  alignment, so it is valid when a fresh Python run does not share sample points with an
  older R output (the usual case). The mapping adapts to the R-output **vintage** —
  older outputs tag transport `pt_any` (→ Python `pt_any`), newer ones `pt_20min_or_any`
  (→ `pt_frequent`); R `public_open_space` → Python `public_open_space_large`. The Python
  variant used is shown in the label.
- **Python-only indicators**: the access indicators the port adds beyond the R set
  (strict/lenient variants, activity centres, `all_*` composites, local-custom sets).
- **Per-point agreement** (omit with `--distribution-only`): joined on `point_id`,
  reporting agreement % and Cohen's kappa — only meaningful when both runs share the same
  `urban_sample_points`; otherwise it reports no matches.
- **Network LTS** is compared *distributionally* (class shares by edge count and length),
  since the R network is one-way-split with non-aligned ids; `--spatial` adds an optional
  nearest-edge per-edge LTS confusion matrix for same-build networks.

> The R outputs in `cyclingIndicators/output/` are an *older-methodology* baseline (12
> cities; all tag PT as `pt_any`), so lead with the distribution comparison: the Python
> port is the newer, more comprehensive method, and the report is meant to *confirm* the
> improvements, not show identity.

The pure metric functions (`binary_agreement`, `ordinal_confusion`, `class_shares`,
`compare_sample_points`, `resolve_sp_mapping`, `compare_sample_point_distributions`,
`python_only_access_indicators`) are covered DB-free by `test_0_10` in `tests/tests.py`.
Writing the Markdown report needs `tabulate` (pandas `to_markdown`); the metrics do not.

---

## 6. Notes and current limitations

- **Routing is undirected** (the directional question is still under discussion); the R
  one-way edge expansion and ADT halving are omitted (the halving cancelled in the LTS
  thresholds, so LTS results are unchanged).
- **Distances are "effective"** (LTS-impedance-weighted via `cost_lts`), a few percent
  above true metres on LTS 2 links; route `cost='length'` if pure-metre distance is wanted.
- **Speed defaults** ship as a global standard table; configure per-region `defaults`,
  `defaults_csv`, and `zones` for published analyses.
- **Scope so far:** fresh food, public open space and public transport, each in a
  stricter and a less-strict / pooled variant, with binary access, safe-route distance,
  and composite "all categories" indicators; plus the **activity centre** (co-located
  cluster) indicator in `local` and `complete` tiers. Still to come: the speed-zone
  `angleDiff` refinement (a buffered overlap approximates it), and — pending sign-off —
  a "% within a 10-minute safe bike ride" headline band (add e.g. `3000` to `distances`).
- **Activity-centre rule:** the default anchor rule (all categories within one node's
  walk-shed) and 400 m threshold are the `INDICATOR_DESIGN.md` §4 *proposed* defaults,
  pending methods sign-off; both are configurable.
- Specs whose layer is absent are skipped — e.g. `pt_frequent` needs `pt_stops_headway`
  (a GTFS feed), and the public-open-space variants need the `aos_public_*_nodes_30m_line`
  layers from `_06_open_space_areas_setup`.
