# Cycling indicators (Level of Traffic Stress accessibility)

Optional GHSCI workflow that classifies the routable network by **Level of Traffic
Stress (LTS 1–4)** and computes cycling accessibility to destinations, aggregated to sample
points, the population grid, and the city/region.

It follows the Global Cycling Indicators manuscript (LTS classification per Jafari et al.)
and the R reference implementation, extended in response to the first round of collaborator
validation: rather than a single definition of a usable route, the **same origins are
evaluated under several measures**, and the spread between them is itself reportable.

### The measures

Each measure is a (routable sub-network, edge cost) pair; see `MEASURES` in
`_cycling_accessibility.py`. All distances are in metres.

| Key | Column infix | Routable sub-network | Cost |
|---|---|---|---|
| `lts1` | `lts1_` | LTS ≤ 1, rideable **or** walkable | `cost_dist` (geometric) |
| `low_stress_ride` | `ride_` | LTS ≤ 2, **rideable only** (no dismount) | `cost_dist` (geometric) |
| `low_stress` | `safe_` | LTS ≤ 2, rideable **or** walkable | `cost_dist` (geometric) |
| `danger_weighted` | *(none)* | whole routable network | `cost_lts` (stress penalty) |

Which measures run is set per region by `cycling_indicators.contrasts` (default
`[[low_stress, danger_weighted]]`); every measure named in a contrast is calculated.

> **Terminology.** The user-facing name for `danger_weighted` is **"stress penalty"**. The
> measure key, the column infix and the `danger_weight` constant keep their original names
> for continuity with existing configurations and result columns.

### The edge costs

`_cycling_lts_network.py` writes two costs per edge:

- `cost_dist` — geometric length, except that walk-the-bike (`foot_dismount`) links are
  charged `length × dismount_weight` (**default 3.0**, ≈ walking a bike at 5 km/h against
  riding at 15 km/h). Used by the three low-stress measures.
- `cost_lts` / `cost_lts_reverse` — `cost_dist` with LTS 3–4 rideable links additionally
  multiplied by `danger_weight` (default 1.25), plus the two-component LTS impedance
  (link term + directional unsignalised-intersection term). Used by `danger_weighted`.

Low-stress access is therefore computed by routing the **LTS ≤ 2 sub-network directly** on
geometric distance — not by routing the whole network and then testing whether the chosen
path happened to be low-stress (the R approach). There is no cap on how far a dismount
excursion may extend; the `dismount_weight` multiplier is the only brake.

Routing is **undirected**, consistent with the GHSCI accessibility engine. Origins and
destinations are evaluated from the two terminal nodes of their associated edge with
along-edge offsets (the GHSCI "full distance" paradigm), not a single nearest-node snap.

Where a destination sits on the **same edge** as the sample point, the distance is the
direct stretch of edge between them whenever that is shorter than a route by way of a
terminal node (`setup_sp.apply_same_edge_distances`). Without this, a long edge with no
intersections sends the point out to one end and back: on Suzhou's 1,073 m 时进路 segment,
points 116–266 m from a shop were measured at 986–1,070 m. Like the terminal offsets, the
direct stretch is charged in plain metres under every measure, and it is censored at the
largest distance band. The same correction applies to the pedestrian analyses. It covers
nearest distances and the access scores derived from them; destination *counts* (and the
diversity scores built on them) remain node-based estimates.

The workflow is completely optional and only runs if a `cycling_indicators` configuration
is present.

> **Shared with the pedestrian analysis.** *What* access is measured to — the destination
> specs, activity-centre definitions and combined-access sets described below — is not
> specific to a mode of travel; only the network and cost used to reach it are. Those
> parts live in `_accessibility_spec.py` and can be declared once in a region's
> **`accessibility:`** block, where both this analysis and the optional pedestrian
> accessibility analysis (`_pedestrian_accessibility.py`) pick them up. Anything
> `cycling_indicators` sets itself still takes precedence for cycling, so every existing
> configuration behaves exactly as before. See [§1a](#1a-sharing-the-specification-with-the-pedestrian-analysis).

---

## 1. Enabling and configuring (region YAML)

Add a `cycling_indicators` block to a region configuration. Set it to `true` to enable
with built-in defaults, or provide a mapping of options. All `data` paths are relative
to `process/data`.

> **Study region extent (cycling study regions, from 2026-09-13).** Every cycling study
> region is the urban portion of an *administrative* boundary, under one shared
> definition of urban: `study_region_boundary.urban_intersection: true` with
> `urban_region` set to the GHSL Urban Centre Database R2024A
> (`urban_regions/GHS_UCDB_GLOBE_R2024A_V1_0/GHS_UCDB_GLOBE_R2024A.gpkg:GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A`).
> `_01_create_study_region` keeps the urban centres intersecting the boundary and clips
> them to it, giving `urban_study_region`. Do not use a boundary that is itself an urban
> definition (a UCDB polygon, a national urban area, a Finnish taajama), and do not
> substitute a national urban dataset for `urban_region`, or the cross-city results stop
> being comparable. `urban_region` and `urban_study_region` are created only if absent,
> so drop the study region database before re-running after a boundary change.
> Where the boundary also intersects other urban centres that are not the city (a
> detached town, a neighbouring city, the edge of another metropolis), select the
> intended urban centre by its UCDB id, e.g.
> `…GHS_UCDB_GLOBE_R2024A.gpkg:GHS_UCDB_THEME_GENERAL_CHARACTERISTICS_GLOBE_R2024A -where "ID_UC_G0 = 7181"`
> (Minneapolis). As of 2026-09-14, this applies to Minneapolis (7181), Suzhou (11199),
> Tarragona (4743) and Curitiba (6350). Barcelona (AMB) and Melbourne deliberately keep
> the adjoining satellite urban centres within their metropolitan boundaries.

> **Custom measures are mapped as well as tabulated.** A destination spec with a
> non-standard `name` (e.g. `bike_rack`, `fresh_food_not_bakery`), a named
> `combined_access` set, or a named `activity_centres` definition is picked up by
> `custom_indicators()` in `_accessibility_spec.py`. The validation report then draws
> isochrone maps for it, with its destinations overlaid, and lists it in the tables
> under "Local (custom) measures". The dashboard export adds its grid columns, a
> `custom_dest` overlay layer and a `custom_indicators` manifest entry, so it appears
> in that city's Destination menu. Each of these may carry optional `label` and
> `description` keys (presentation only; they do not affect the analysis), e.g.
> `{name: bike_rack, label: "Bicycle parking", description: "…", category: bike_rack, variant: any, layer: destinations, where: "dest_name = 'bike_rack'"}`.
> Without a label, a tidied version of the name is shown.

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
  no_cycle: [steps, corridor]                     # highway classes where riding is banned;
                                                  # matched against every token of a merged
                                                  # OSM tag ("['footway', 'steps']") for
                                                  # steps/corridor, which a ramp:bicycle
                                                  # exempts.  Walking the bike is governed
                                                  # separately (NO_DISMOUNT_HIGHWAYS), so
                                                  # listing footway/path here bans riding
                                                  # without making footways unwalkable.
  # Optional overrides of the LTS classification thresholds.  Changing one makes
  # results not directly comparable with regions using the defaults, so record any
  # change in the region's validation provenance.
  # lts_rules:
  #   mixed_traffic_lts1_speed: 30                # speed (km/h) at or below which a
  #                                               # low-volume local street in mixed
  #                                               # traffic is LTS 1 rather than LTS 2.
  #                                               # Default 30 (Mekuria, Furth & Nixon);
  #                                               # 40 treats US-style 25 mph residential
  #                                               # streets as all ages and abilities.
  #                                               # Moves streets between LTS 1 and 2, so
  #                                               # only the lts1 measure can change --
  #                                               # low_stress (LTS <= 2) cannot.
  distances: [2000, 5000]                         # catchment thresholds (m)
  # Accessibility measure contrasts: ordered pairs of measures calculated and
  # juxtaposed in the validation report (first pair = headline; later pairs render
  # below it as alternative contrasts).  Available measures: lts1 (fully LTS 1
  # routes, geometric distance), low_stress (fully LTS 1-2 routes, geometric
  # distance; the established headline), low_stress_ride (as low_stress but ridden
  # throughout -- links the rider would have to dismount and walk are excluded),
  # danger_weighted (all streets routable, higher-stress length penalised).  Every
  # measure named in a contrast is calculated; `measures: [...]` may add extras
  # without a contrast.
  contrasts:
    - [low_stress, danger_weighted]               # default when omitted
    - [lts1, low_stress]                          # LTS-1-only sensitivity contrast
    - [low_stress_ride, low_stress]               # with/without-dismount sensitivity;
                                                  # also derives the dmgap_ columns
  dismount_priority: true                         # rank the walked links by the
                                                  # population whose nearest-destination
                                                  # route depends on them, into
                                                  # cycling_dismount_priority (needs
                                                  # routing_engine: inmemory and the
                                                  # contrast above; no extra routing)
  danger_weight: 1.25                             # LTS 3-4 length multiplier in routing
                                                  # cost (higher => avoid high-stress links
                                                  # more strongly; ~strictly low-stress as
                                                  # it grows). Default 1.25 (manuscript).
  dismount_weight: 3.0                            # length multiplier for walk-the-bike
                                                  # (footway/path/pedestrian) links: the
                                                  # rider dismounts and walks through.
                                                  # Default 3.0 (~5 km/h walking a bike vs
                                                  # ~15 km/h riding). There is no distance
                                                  # cap on a dismount excursion.
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

### Activity centres (destination clusters) — shared

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

Because co-location is evaluated on the *pedestrian* network, the centres are the same
whichever analysis derives them: whichever of the pedestrian and cycling steps runs
first writes the layers (recording the threshold and members it used as the table's
comment), and the other reuses them rather than repeating the walk-shed routing. With
the `accessibility:` block configured, walking access and mean walking distance to each
centre are reported alongside the cycling measures — which is what a policy expressed as
"services within a five-minute walk" actually asks for.

### 1a. Sharing the specification with the pedestrian analysis

`destinations`, `activity_centres` and `combined_access` may be declared once under a
top-level **`accessibility:`** block instead of (or as well as) under
`cycling_indicators`. Doing so also enables the optional pedestrian accessibility
analysis, which measures walking access to the same destinations over the plain
pedestrian network at every configured band:

```yaml
accessibility:
  pedestrian:
    distances: [500, 1000, 1500]   # walking bands (m); default 500
    # routing_engine: inmemory     # default: the region's top-level setting
    # pedestrian: false            # declare destinations for cycling only
  destinations:
    - {name: fresh_food_market, category: food, variant: strict, layer: destinations, where: "dest_name = 'fresh_food_market'"}
    # ...
  activity_centres:
    local_services: {walk_threshold: 300, categories: [food, pharmacy, health], tiers: {local: lenient}}
```

Outputs, written to `sample_points_pedestrian` and aggregated by `_12_aggregation`:

| Scale | Access | Distance |
|---|---|---|
| sample point | `sp_walk_access_<name>_<d>m` | `sp_walk_nearest_node_<name>` |
| grid / custom areas | `pct_access_walk_<name>_<d>m` | `avg_walk_dist_<name>` |
| city | `pop_pct_access_walk_<name>_<d>m` | `pop_avg_walk_dist_<name>` |

Two per-destination options refine this:

- **`distances: [250]`** on a spec evaluates *that* destination at its own
  policy-relevant band instead of the region's, without adding a band to everything
  else.
- **`direction: avoid`** marks a destination a *disamenity* — proximity is the harm,
  not the benefit. Its threshold columns become `sp_walk_beyond_<name>_<d>m`, scoring
  1 where the nearest one is further than `d` metres (or absent within the largest
  band), and aggregate to `pct_beyond_walk_<name>_<d>m` — "percentage of population
  living further than `d` metres from one". This is the spec-level counterpart of the
  `greater_than_or_equal_to(N)` sample point analysis in `indicators.yml`, and the
  polarity has to be carried in the name: an access column of the same value would
  mean the opposite thing. Avoided destinations are excluded from the combined-access
  composites and are not usable as activity-centre categories.

Two further things to note:

- Distances are censored at the **largest configured band**, not at the project's 500 m
  `accessibility_distance`. That is the point of the bands: a mean distance to the
  nearest destination computed from 500 m-censored values is a mean *among those who
  already have access*, biased hardest exactly where access is worst. Set the outer band
  to the range over which the mean should be interpretable.
- The core walking indicators driven by `configuration/indicators.yml`
  (`sp_access_<dest>_score`, `pct_access_500m_<dest>_score`, the daily living score and
  the walkability index) are **unchanged** and are produced whether or not this block is
  present. The `sp_walk_*` family is additional, so cross-city comparability is not
  affected by a region opting in.

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

### Region-specific open space definitions (`areas_of_interest: osm_open_space`)

What counts as public open space is defined globally in
`configuration/osm_open_space.yml`, which is necessarily a compromise across cities.
Where a locally-relevant typology is missed, a region can override individual
definitions — as a sibling of, and distinct from, the custom `public_open_space`
**data** entry — instead of pre-processing a custom layer.

**Any definition not listed keeps its global default; a definition that is listed has
its `criteria` replaced outright.** The intended workflow is to copy the relevant
`criteria` from `configuration/osm_open_space.yml` and edit it, so the definition
actually in use is explicit and reviewable in the region configuration:

```yaml
areas_of_interest:
  osm_open_space:
    os_landuse:
      criteria: |-
        'common','conservation',...,'beach','cemetery','meadow','allotments'
    os_inclusion:
      criteria: |-
        p.leisure IS NOT NULL OR ... OR p."natural" IN ('wood')
```

The value may be given as the replacement `criteria` directly, or as a mapping
containing a `criteria` key so a whole block can be copied and edited. List-valued
definitions (`os_required`) take a list. An unknown definition name, or a mapping
without `criteria`, raises an informative error rather than being ignored.

Note that open space must pass **two** independent tests, so a new typology often
needs two definitions changed: whether it qualifies as open space at all
(`os_inclusion`, `os_landuse`, `os_boundary`) and whether it is publicly accessible
(`public_not_in`). Helsinki is the worked example — `natural=wood` needed adding to
`os_inclusion`, because `natural` is otherwise not an inclusion criterion at all, *and*
removing from `public_not_in`, which would otherwise mark it non-public.

Three qualifications: this has no effect where `public_open_space` is configured with
`replace: true` (the OpenStreetMap derivation is then unused); overriding a definition
opts the region out of later improvements to the global default; and because the
definitions change what is counted, results are **not comparable** with regions using
the defaults — record any override in the region's `validation` provenance, as
Helsinki does.

Resolved per region by `ghsci.osm_open_space_config()`, which returns a copy (so
overrides cannot leak between regions analysed in the same session) and recomposes the
derived criteria (`public_space`, `exclusion_criteria`) from their source definitions.

---

## 2. Pipeline steps

Run automatically as part of `analysis` (and skipped when not configured):

| Step | Runs after | Produces |
|---|---|---|
| `_cycling_lts_network.py` | `_03_create_network_resources` | LTS columns on the `edges` table |
| `_pedestrian_accessibility.py` | `_11_neighbourhood_analysis` | `activity_centre_*` layers and the `sample_points_pedestrian` table |
| `_cycling_accessibility.py` | `_pedestrian_accessibility` | the `sample_points_cycling` table |
| `_12_aggregation.py` → `calc_pedestrian_indicators`, `calc_cycling_indicators` | the standard aggregation | walking and cycling columns on the grid, city and custom area summaries |

Each can also be run directly, e.g. `python subprocesses/_cycling_lts_network.py <codename>`,
`python subprocesses/_pedestrian_accessibility.py <codename>` and
`python subprocesses/_cycling_accessibility.py <codename>`.  `_pedestrian_accessibility`
runs first only so that the activity-centre layers exist before either analysis needs
them; either order gives the same result, and whichever runs second reuses the layers.

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
| `cost_dist` | float | geometric cost: `length`, or `length × dismount_weight` on walked links. Cost for the `lts1`, `low_stress_ride` and `low_stress` measures |
| `cost_lts` | float | forward stress-penalty cost = `cost_dist`, with LTS 3–4 rideable links × `danger_weight`, + `lts_imped` |
| `cost_lts_reverse` | float | as `cost_lts` but with the `from`-node intersection penalty |
| `bike_permitted` | bool | whether cycling is permitted on the edge |
| `foot_dismount` | bool | not rideable but walkable: the rider may push the bike through |

> **`lvl_traf_stress` is an internal value on every edge, but is only *reported* for
> edges a rider may ride.** Every off-road class is LTS 1 (`OFFROAD`), including
> footways where riding is banned and staircases a bike cannot be pushed up, so the
> class alone does not say whether a link is usable. The validation report and
> dashboard therefore present three mutually exclusive categories, derived from the
> triple (`lvl_traf_stress`, `bike_permitted`, `foot_dismount`) — see
> `edge_categories` in `subprocesses/_cycling_validation_report.py`:
>
> | Condition | Category |
> |---|---|
> | `bike_permitted` | LTS 1 … LTS 4 by `lvl_traf_stress` |
> | `foot_dismount` | Footway (dismount required) |
> | neither | Not available for cycling |
>
> A footway signed for shared use (`bicycle=yes`/`designated`) is `bike_permitted`, so
> it keeps its LTS class. Routing is unaffected: the measures filter on
> `lvl_traf_stress` **and** the two flags together (`_cycling_accessibility.MEASURES`),
> so this is a presentation distinction only. Introduced in response to round 2
> validation feedback (Minneapolis, Sep 2026): grading a footway the rider must walk
> as "LTS 1 — suitable for all ages and abilities" implied riders may ride the
> sidewalk, which in a US context they may not.

**`sample_points_cycling`** (added by `_cycling_accessibility`): `point_id`, `grid_id`,
`edge_ogc_fid`, `geom`, plus one column set per configured *measure* (column infix:
`lts1_` fully LTS 1, `ride_` fully LTS ≤ 2 ridden throughout, `safe_` fully LTS ≤ 2
including footway dismount, none for danger-weighted), destination spec
`<name>` and threshold `<d>`:

- `sp_cycle_<infix>nearest_node_<name>` — the measure's routing distance (m) to the
  nearest destination (`<name>` includes `activity_centre_<tier>` and
  `activity_centre_<set>_<tier>` centres)
- `sp_cycle_<infix>access_<name>_<d>m` — binary access (1/0) within `<d>` metres
- `sp_cycle_<infix>access_all_<variant>_<d>m` — standard composite (all global categories
  of a variant reachable); named sets add `sp_cycle_<infix>access_all_<set>_<variant>_<d>m`

Where both measures of the dismount pair (`low_stress_ride`, `low_stress`) are computed,
their paired per-point contrast is derived under the pseudo-infix `dmgap_`:

- `sp_cycle_dmgap_extra_<name>` — extra metres of riding needed to reach the nearest
  destination without dismounting (NA unless *both* routes exist, so its mean is taken
  over points reachable either way)
- `sp_cycle_dmgap_access_<name>_<d>m` — 1 where access at `<d>` exists only because the
  rider may get off and walk

Derived **`activity_centre_<tier>`** (and `activity_centre_<set>_<tier>`) point layers (the
centre nodes themselves) are also written for QA / mapping and exported by `generate`.

**`cycling_dismount_priority`** (when `dismount_priority: true`): one row per walked link
carrying routed population — `ogc_fid`, `osmid`, `name`, `highway`, `length`,
`dm_pop_served`, `dm_pop_dependent`, `dm_specs`, `geom`. Accumulated from the
shortest-path trees the in-memory router already builds (one O(n) pass per destination
type, no extra routing). Scores rank candidate infrastructure locations; they are not
additive across links, since one route may walk several.

**Grid summary** (added by `calc_cycling_indicators`):
`pct_access_cycle_[lts1_|ride_|safe_|dmgap_]<name>_<d>m` and
`pct_access_cycle_[lts1_|ride_|safe_|dmgap_]all_<variant>_<d>m` (grid-cell % with access;
for `dmgap_`, % whose access depends on dismounting),
`avg_cycle_dist_[lts1_|ride_|safe_]<name>` (grid-cell mean distance, m) and
`avg_cycle_extra_dmgap_<name>` (grid-cell mean extra distance to ride around the walked
links, m).

**City summary**: the population-weighted versions, `pop_pct_access_cycle_…`,
`pop_avg_cycle_dist_…` and `pop_avg_cycle_extra_dmgap_…`.

When `cycling_indicators` is enabled, `generate` exports the LTS `edges`, the cycling
grid/city columns, and `sample_points_cycling` to the region GeoPackage.

---

## 4. Developer reference (key functions)

### `_cycling_lts_network.py`
- `cycling_lts_network(codename)` — subprocess entry point.
- `cycling_config(r)` — returns the region's cycling config dict, or `None` if disabled.
- `compute_cycling_lts(r, config)` — orchestrates classification and write-back.
- `classify_cycleway(edges)` → `(highway, bike_facility)` (ports R `createCycleway`).
- `load_speed_defaults(speed_config)` — CSV / inline mapping **layered over** the built-in
  global table (so classes a region omits still get a speed instead of falling to LTS 4).
- `assign_speed(edges, defaults)`, `assign_adt(highway)`,
  `assign_lts(highway, facility, speed, adt)` — LTS Table 1 cascade.
- `motor_restricted(series)` / `apply_motor_restriction(edges, speed, adt)` — edges whose
  `motor_vehicle` tag bars general through-traffic (`destination`, `no`, `private`, …) are
  treated as low-stress local streets (speed capped at 30 km/h, ADT to the local floor).
- `assign_bike_permitted(edges, no_cycle)` — an explicit `bicycle ∈ {yes, designated,
  official}` overrides the `no_cycle` class ban; only `bicycle ∈ {no, dismount, private}`
  (or a no-cycle class without explicit permission) bars cycling. The `steps` / `corridor`
  ban is tested against every token of the **raw** OSM `highway` tag, since OSMnx merges
  ways and `_pick_highway` would otherwise resolve `"['footway', 'steps']"` to `footway`
  and let a staircase through; a `ramp:bicycle` on the staircase lifts that part of the ban.
- `load_bike_ramp(r, edges)` — per-edge `ramp:bicycle` flag, read from
  `{osm_prefix}_line.tags` (osm2pgsql `--hstore`) and joined on `edges.osmid`, because the
  tag is not retained on the `edges` table. An edge counts as ramped only if *every* one of
  its `highway=steps` ways has a positive value — one un-ramped staircase still blocks it.
- `compute_foot_dismount(edges)` — walkable-but-not-ridable ways. Excludes
  `NO_DISMOUNT_HIGHWAYS` (`steps`, `corridor`) by raw tag, unexempted by a ramp: you cannot
  push a bike up a staircase either. Deliberately keyed off that fixed list rather than the
  region's `no_cycle`, which bans *riding* and often includes the very footways dismount
  exists to make walkable.
- `add_impedance(r, edges)` — two-component impedance and directional costs.
- `apply_speed_zones(r, edges, zones)` — spatial speed overrides (R `assignBufferSpeed`).

### `_cycling_accessibility.py`
- `cycling_accessibility(codename)` — subprocess entry point.
- `MEASURES` / `MEASURE_ORDER` / `DEFAULT_CONTRASTS` — the measure definitions (sub-network
  `where` clause, cost column, column infix and display label) described at the top of this
  document. `measure_contrasts(config)` and `configured_measures(config)` resolve which run.
- `cycling_poi_distance(r, distance, specs)` — per-node distance to the nearest destination
  for each measure. Dispatches to one of two equivalent engines by
  `routing_engine`:
  - `_nearest_distances_inmemory(...)` — exact in-process multi-source Dijkstra
    (`scipy.sparse.csgraph`) over a CSR matrix, using a virtual super-source wired to each
    destination node at its offset cost (`routing_engine: inmemory`);
  - `_banded_distances(...)` — banded `pgr_drivingDistance` via
    `setup_sp.build_dest_node_lookup` (`routing_engine: pgrouting`, the default).
  Both are **origin-seeded and banded**: each ascending distance band re-routes only those
  origins that have not yet resolved every spec, which is exact provided the bands include
  the thresholds. See `cycling_banding_plan.md`.
- `cycling_sample_point_access(r, nodes_poi_dist, node_index, thresholds)` — maps node
  distances to sample points and derives binary access scores.
- `DismountPriority` — accumulates population load over the shortest-path trees the
  in-memory engine already builds, ranking walked links as candidates for infrastructure
  (table `cycling_dismount_priority`).

> **Legacy, no longer on the live path:** `build_safe_components(r)` (component labelling of
> the LTS ≤ 2 subgraph) and `_safe_dist_from_lookup(...)` date from an earlier design in
> which the whole network was routed and low-stress reachability applied afterwards as a
> same-component test. The measure architecture above routes each sub-network directly, so
> neither function is called. They are retained for reference only.
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
  cost='length', reverse_cost='length', where=None)` — `pgr_drivingDistance` over a
  parameterised sub-network. Cycling passes the `where` clause and cost column of the
  measure being calculated (see `MEASURES`), so each measure routes its own sub-network
  directly. Pedestrian defaults are unchanged.

### `_12_aggregation.py`
- `calc_cycling_indicators(r)` — gated grid + population-weighted city aggregation of the
  cycling sample-point indicators (adds columns to the existing summary tables).

---

## 5. Validating against the R pipeline

> The narrative comparison of the two implementations lives in
> `process/cycling_R_vs_GHSCI.md`. It is now a **standalone historical document**: the R
> comparison was removed from the per-city cycling validation report, so it is not
> regenerated per run. Where that document and the code disagree, the code wins.

`compare_cycling_r_python.py` (in `process/`) quantifies how closely the Python
implementation reproduces the original R pipeline's outputs for a region:

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
`python_only_access_indicators`) are covered DB-free by `test_0_26_r_python_comparison_metrics` in `tests/tests.py`.
Writing the Markdown report needs `tabulate` (pandas `to_markdown`); the metrics do not.

---

## 6. Notes and current limitations

- **Routing is undirected.** The R one-way edge expansion and its ADT halving are both
  omitted; because the halving cancelled against the LTS thresholds, LTS results are
  unchanged. Accessibility is evaluated from origins to nearest destinations rather than as
  directed trips, and stress classification is not direction-specific, so a directed
  representation is not required. The manuscript is being updated to match (it previously
  described a one-way representation, per `cyclingIndicators/KNOWN_ISSUES.md` #3).
- **Only the `danger_weighted` measure uses a weighted distance.** Its `cost_lts` inflates
  LTS 3–4 links by `danger_weight` and adds the LTS impedance, so a route using high-stress
  links spends more of its budget on them, and the distance thresholds apply to that
  effective distance. The `lts1`, `low_stress_ride` and `low_stress` measures route their
  sub-network on geometric distance (`cost_dist`), where the only inflation is the
  `dismount_weight` on walked links.
- **Default distance bands are 500, 1000, 2000 and 5000 m** (`distances`); the bands also
  serve as the routing brackets, so any threshold reported must be one of the bands.
- **Speed defaults** ship as a global standard table; a per-region `defaults` / `defaults_csv`
  is **layered over** it (not a replacement), so omitting a class no longer forces it to
  LTS 4. `motor_vehicle`-restricted edges (local-access-only) are treated as 30 km/h local.
- **Under the `danger_weighted` measure, higher-stress and walked links are usable at a
  penalty**, so a destination or origin on, or just off, the low-stress network — an amenity
  fronting an arterial, a sample point on an LTS 3–4 junction node, or a point in a
  footway-only enclave — is reached via a short penalised hop rather than being stranded.
  The `low_stress` measure (columns `sp_cycle_safe_*`) reports the stricter fully-LTS ≤ 2
  case alongside it, and `low_stress_ride` (`sp_cycle_ride_*`) the stricter case again
  without any dismount. Raise `danger_weight` / `dismount_weight` to admit penalised links
  only as short connectors. See `cycling_wurzburg_diagnosis.md`.
- **Scope so far:** fresh food, public open space and public transport, each in a
  stricter and a less-strict / pooled variant, measured under the configured subset of the
  four measures, with binary access, distance to nearest, composite "all categories"
  indicators, and the paired dismount-dependence (`dmgap_`) contrast; plus the **activity
  centre** (co-located cluster) indicator in `local` and `complete` tiers. Still to come:
  the speed-zone
  `angleDiff` refinement (a buffered overlap approximates it), and — pending sign-off —
  a "% within a 10-minute safe bike ride" headline band (add e.g. `3000` to `distances`).
- **Activity-centre rule:** the default anchor rule (all categories within one node's
  walk-shed) and 400 m threshold are the `INDICATOR_DESIGN.md` §4 *proposed* defaults,
  pending methods sign-off; both are configurable.
- Specs whose layer is absent are skipped — e.g. `pt_frequent` needs `pt_stops_headway`
  (a GTFS feed), and the public-open-space variants need the `aos_public_*_nodes_30m_line`
  layers from `_06_open_space_areas_setup`.
