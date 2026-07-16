"""Cycling indicator validation report (region-generic template).

Produces a self-contained HTML report for a study region analysed with the GHSCI
cycling workflow, structured to support collaborators completing the project's
CyclingValidation.xlsx form (Part 1: accessibility web-map validation questions
1.1-1.4; Part 2: Level of Traffic Stress validation).

Sections render from whatever is available in the region database, so the script
can be run mid-analysis for a partial report and re-run after _12_aggregation for
the complete one.  Maps are embedded as base64 PNGs (no external files), so the
single .html can be emailed or hosted as-is.

Usage (inside the ghsci container):
    /env/bin/python _validation_report.py "data/Cycling/Dar es Salaam/DarEsSalaam.yml"

Optional region config keys used if present (all free-form, non-breaking):
    cycling_indicators:
      validation:
        collaborator: Name shown in the header
        provenance: [list of markdown-ish strings describing local inputs]
        limitations: [list of strings noting known data caveats]
"""

import base64
import io
import os
import random
import sys
from datetime import date

os.chdir('/home/ghsci/process')
sys.path.insert(0, '/home/ghsci/process/subprocesses')

import geopandas as gpd  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use('Agg')
import contextily as cx  # noqa: E402
import matplotlib.lines as mlines  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import ghsci  # noqa: E402
from _cycling_accessibility import (  # noqa: E402
    MEASURE_ORDER,
    MEASURES,
    resolve_contrasts,
    resolve_measures,
)
from batlow import batlow_map  # noqa: E402  (Crameri Scientific Colour Maps)

# Measures with the longest column infix first, so 'lts1_' / 'safe_' resolve before
# the bare danger-weighted prefix when parsing column names.
_MEASURES_BY_INFIX = sorted(
    MEASURES.items(), key=lambda kv: len(kv[1]['infix']), reverse=True,
)


def split_measure_col(col, base):
    """Resolve a ``<base><measure infix><stem>`` column to ``(measure_key, stem)``.

    E.g. ``split_measure_col('pct_access_cycle_safe_pt_any_2000m',
    'pct_access_cycle_')`` -> ``('low_stress', 'pt_any_2000m')``.  The empty
    (danger-weighted) infix always matches, so every column resolves.
    """
    rest = col[len(base):]
    for key, m in _MEASURES_BY_INFIX:
        if rest.startswith(m['infix']):
            return key, rest[len(m['infix']):]
    return None, rest

LTS_COLORS = {1: '#1a9850', 2: '#a6d96a', 3: '#fdae61', 4: '#d7191c'}
LTS_LABELS = {
    1: 'LTS 1 — lowest stress (suitable for all ages and abilities)',
    2: 'LTS 2 — low stress (most adults)',
    3: 'LTS 3 — moderate stress (confident cyclists)',
    4: 'LTS 4 — high stress (strong and fearless)',
}
# Perceptually-uniform, colour-blind-safe sequential map (Crameri batlow):
# dark blue (low access) -> teal/green -> pale yellow (high access).
ACCESS_CMAP = batlow_map
# Neutral grey for the "no access within any configured distance" isochrone band
# (distinct from all ACCESS_CMAP values so it reads unambiguously as absence).
ISOCHRONE_NO_ACCESS_COLOR = '#888888'
# Sample-point colours for the dual-panel case-study maps: blue = point with
# access, grey = point without (grey-as-absence matching the isochrone band).
PT_ACCESS = '#2166ac'
PT_NO_ACCESS = '#969696'


def _batlow_cell_bg(value, kind='pct'):
    """Return a CSS ``background-color`` rgba string at 0.3 alpha for an HTML
    table cell, mapping the value through the batlow colour scale.

    kind='pct':  value 0–100 (percentage) → batlow(value / 100); 100 % = pale
                 yellow/pink end (good), 0 % = dark blue (poor).
    kind='dist': value in metres → batlow(1 − min(value, 5000) / 5000); 0 m =
                 pale end (very close), ≥ 5000 m = dark blue (far/no access).

    Returns an empty string if *value* is NaN or None (no background applied).
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ''
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ''
    if kind == 'pct':
        t = max(0.0, min(1.0, v / 100.0))
    else:  # dist
        t = max(0.0, 1.0 - min(v, 5000.0) / 5000.0)
    r, g, b, _ = ACCESS_CMAP(t)
    return f'background-color: rgba({int(r * 255)},{int(g * 255)},{int(b * 255)},0.3);'


DEST_LABELS = {
    'fresh_food_market': 'Fresh food market (strict)',
    'fresh_food_pooled': 'Fresh food incl. convenience (lenient)',
    'public_open_space_large': 'Large public open space (strict)',
    'public_open_space_any': 'Any public open space (lenient)',
    'pt_frequent': 'Frequent public transport (strict)',
    'pt_any': 'Any public transport (lenient)',
    'all_strict': 'All categories — strict variants',
    'all_lenient': 'All categories — lenient variants',
    'activity_centre_local': 'Local activity centre (lenient cluster)',
    'activity_centre_complete': 'Complete activity centre (strict cluster)',
}

# Canonical row order for indicator tables.  Strict and lenient variants of each
# destination category are kept as adjacent pairs; composite (all-categories) and
# activity-centre rows follow individual indicators.
DEST_TABLE_ORDER = [
    ('fresh_food_market',        'Food'),
    ('fresh_food_pooled',        'Food'),
    ('public_open_space_large',  'Public open space'),
    ('public_open_space_any',    'Public open space'),
    ('pt_frequent',              'Public transport'),
    ('pt_any',                   'Public transport'),
    ('all_strict',               'All destinations'),
    ('all_lenient',              'All destinations'),
    ('activity_centre_complete', 'Activity centres'),
    ('activity_centre_local',    'Activity centres'),
]


def _table_row_order(available_names):
    """Return ``(name, group_label, is_first_in_group)`` tuples in canonical order.

    Indicators present in *DEST_TABLE_ORDER* are listed first, filtered to those
    in *available_names*.  Any remaining names are appended alphabetically under
    the group label ``'Other'``.
    """
    seen = set()
    result = []
    for name, group in DEST_TABLE_ORDER:
        if name not in available_names:
            continue
        result.append((name, group, group not in seen))
        seen.add(group)
    known = {n for n, _ in DEST_TABLE_ORDER}
    for name in sorted(set(available_names) - known):
        result.append((name, 'Other', 'Other' not in seen))
        seen.add('Other')
    return result


def _pct_col_sort_key(col):
    """Sort key for ``pct_access_cycle_*`` grid columns.

    Orders by canonical indicator position (DEST_TABLE_ORDER), then distance
    ascending, then measure (strictest first: LTS 1 only, then low-stress
    LTS 1–2, then danger-weighted).
    """
    key, stem = split_measure_col(col, 'pct_access_cycle_')
    rank = MEASURE_ORDER.index(key) if key in MEASURE_ORDER else 99
    parts = stem.rsplit('_', 1)
    if len(parts) == 2 and parts[1].endswith('m') and parts[1][:-1].isdigit():
        name, d = parts[0], int(parts[1][:-1])
        pos = next((i for i, (n, _) in enumerate(DEST_TABLE_ORDER) if n == name), 999)
        return (pos, d, rank)
    return (999, 0, 0)


def fig_to_b64(fig, dpi=110):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def img_tag(fig, alt, dpi=110):
    return (
        f'<figure><img src="data:image/png;base64,{fig_to_b64(fig, dpi)}" '
        f'alt="{alt}" style="max-width:100%"/>'
        f'<figcaption>{alt}</figcaption></figure>'
    )


def add_basemap(ax, crs):
    """Light grayscale basemap (so the coloured data reads clearly); degrade
    gracefully when offline."""
    try:
        cx.add_basemap(
            ax, crs=crs, source=cx.providers.CartoDB.Positron,
            attribution_size=5,
        )
    except Exception as e:
        print(f'  (basemap unavailable: {e})')


# Reference destinations to overlay on each indicator map (the "targets" the
# indicator measures access to), keyed by indicator/spec name.  Marker colours are
# chosen from the magenta/red family so they contrast with the batlow scale
# (blue -> teal -> green -> yellow) and stay visible over any access value; a white
# edge is added when plotting for further separation.
DEST_OVERLAY = {
    'fresh_food_market': (
        "SELECT geom FROM destinations WHERE dest_name = 'fresh_food_market'",
        '#e6194b', 'fresh food market'),
    'fresh_food_pooled': (
        "SELECT geom FROM destinations WHERE dest_name IN "
        "('fresh_food_market', 'convenience')", '#e6194b',
        'fresh food / convenience'),
    'public_open_space_large': (
        'SELECT geom FROM aos_public_large_nodes_30m_line', '#f032e6',
        'large open-space access point'),
    'public_open_space_any': (
        'SELECT geom FROM aos_public_any_nodes_30m_line', '#f032e6',
        'open-space access point'),
    'pt_any': (
        "SELECT geom FROM destinations WHERE dest_name = 'pt_any'", '#e6194b',
        'public transport stop'),
    'activity_centre_local': (
        'SELECT geom FROM activity_centre_local', '#f032e6',
        'local activity centre'),
    'activity_centre_complete': (
        'SELECT geom FROM activity_centre_complete', '#f032e6',
        'complete activity centre'),
}


def add_scalebar(ax):
    """Draw a metric scale bar (lower-left), sized to the current axis extent.

    Assumes a projected CRS in metres (all maps here are drawn in the region's
    analysis CRS).  The bar length is the 1/2/5 x 10^n value nearest a quarter of
    the map width, so it stays a round, legible number at any zoom (city-wide or
    case-study window).  Call after the final extent is set (i.e. after
    ``add_basemap``).
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span = x1 - x0
    if not np.isfinite(span) or span <= 0:
        return
    target = span * 0.25
    mag = 10 ** int(np.floor(np.log10(target)))
    length = next((m * mag for m in (5, 2, 1) if target >= m * mag), mag)
    xr = x0 + span * 0.05
    yb = y0 + (y1 - y0) * 0.06
    h = (y1 - y0) * 0.013
    half = length / 2.0
    # conventional two-tone bar (white | black) with a thin outline
    ax.add_patch(mpatches.Rectangle(
        (xr, yb), half, h, facecolor='white', edgecolor='black',
        lw=0.8, zorder=20))
    ax.add_patch(mpatches.Rectangle(
        (xr + half, yb), half, h, facecolor='black', edgecolor='black',
        lw=0.8, zorder=20))
    label = f'{length / 1000:g} km' if length >= 1000 else f'{length:g} m'
    ax.text(
        xr + length / 2.0, yb + h * 1.7, label, ha='center', va='bottom',
        color='white', fontsize=9, fontweight='bold', zorder=21,
        path_effects=[pe.withStroke(linewidth=2.5, foreground='black')],
    )


def get_gdf_generic(r, sql_or_table, geom_col='geom'):
    gdf = r.get_gdf(sql_or_table, geom_col=geom_col)
    gdf = gdf.set_geometry(geom_col)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=int(r.config['crs']['srid']))
    return gdf


class Report:
    def __init__(self, r):
        self.r = r
        self.tables = set(r.get_tables())
        self.srid = int(r.config['crs']['srid'])
        cfg = r.config.get('cycling_indicators') or {}
        self.cycling_cfg = cfg if isinstance(cfg, dict) else {}
        self.validation_cfg = self.cycling_cfg.get('validation') or {}
        self.distances = [
            int(d) for d in self.cycling_cfg.get('distances', [2000, 5000])
        ]
        # configured accessibility contrasts (ordered measure pairs); the first is the
        # established headline contrast, later pairs render as alternative contrasts
        # below it for each reporting item
        self.contrasts = resolve_contrasts(self.cycling_cfg)
        self.measures = resolve_measures(self.cycling_cfg)
        self.parts = []
        self.missing = []
        try:
            self.boundary = get_gdf_generic(r, 'urban_study_region')
        except Exception:
            self.boundary = None

    # ---------------------------------------------------------------- helpers
    def has(self, table):
        ok = table in self.tables
        if not ok:
            self.missing.append(table)
        return ok

    def region_value_cols(self, prefix):
        sql = (
            'SELECT column_name FROM information_schema.columns '
            f"WHERE table_name = '{self.r.config['city_summary']}' "
            f"AND column_name LIKE '{prefix}%'"
        )
        return sorted(self.r.get_df(sql)['column_name'])

    def available_contrasts(self, cols, base):
        """Configured contrasts whose measures both have columns present.

        Keeps the report robust mid-analysis (or on a database run before a
        newly configured measure existed): a contrast only renders once both of
        its measures have at least one ``<base><infix><stem>`` column.
        """
        present = {split_measure_col(c, base)[0] for c in cols}
        return [pair for pair in self.contrasts if set(pair) <= present]

    def cycling_runtime(self):
        """Latest recorded run time (minutes) of each cycling calculation step.

        Read from the ``script_log`` table (written by ``script_running_log`` at the
        end of each step); the most recent entry per step is used, so re-runs report
        the current engine's timing.  Returns ``(steps, total_minutes, engine)`` or
        ``None`` if the log is unavailable.  Only the cycling-specific steps are
        counted (LTS network classification + accessibility routing); the shared
        aggregation step is not attributed to cycling.
        """
        try:
            df = self.r.get_df(
                "SELECT script, task, datetime_completed, duration_mins "
                "FROM script_log WHERE script IN "
                "('_cycling_lts_network', '_cycling_accessibility')",
            )
        except Exception:
            return None
        if df is None or df.empty:
            return None
        latest = df.sort_values('datetime_completed').drop_duplicates(
            'script', keep='last',
        )
        order = {'_cycling_lts_network': 0, '_cycling_accessibility': 1}
        latest = latest.sort_values(
            'script', key=lambda s: s.map(order),
        )
        steps = [
            (row['task'], float(row['duration_mins']))
            for _, row in latest.iterrows()
        ]
        total = sum(d for _, d in steps)
        engine = str(
            self.cycling_cfg.get('routing_engine', 'pgrouting') or 'pgrouting',
        )
        return steps, total, engine

    # ---------------------------------------------------------------- header
    def header(self):
        r = self.r
        collaborator = self.validation_cfg.get('collaborator', '')
        osm_date = r.config['OpenStreetMap'].get('publication_date', '')
        boundary_notes = (r.config.get('study_region_boundary')) or ''
        runtime = self.cycling_runtime()
        if runtime:
            steps, total, engine = runtime
            breakdown = '; '.join(f'{t} {d:.2f} min' for t, d in steps)
            runtime_html = (
                f'<tr><td>Cycling calculation run time</td><td><b>{total:.2f} minutes</b> '
                f'({breakdown}; routing engine: {engine}). Excludes the shared '
                f'network build and aggregation steps.</td></tr>'
            )
        else:
            runtime_html = ''
        html = f"""
        <style>
            /* Targets only the first cell of every row inside the meta table */
            table.meta td:first-child {{
                white-space: nowrap;
                padding-right: 20px; /* Optional: adds breathing room before the second column */
            }}
        </style>
        <h1>Cycling accessibility &amp; Level of Traffic Stress — validation report</h1>
        <h2>{r.name}, {r.config.get('country', '')} ({r.config.get('year', '')})</h2>
        <table class="meta">
        <tr><td>Report generated</td><td>{date.today().isoformat()}</td></tr>
        <tr><td>Workflow</td><td>GHSCI (global-indicators) v{ghsci.__version__} with integrated cycling LTS &amp; accessibility analysis</td></tr>
        <tr><td>Study region boundary</td><td>{boundary_notes}</td></tr>
        <tr><td>OpenStreetMap extract</td><td>{osm_date}</td></tr>
        <tr><td>Coordinate system</td><td>{r.config['crs_srid']}</td></tr>
        <tr><td>Local collaborator</td><td>{collaborator}</td></tr>
        {runtime_html}
        </table>
        <p class="note">This report has been designed to support local collaborators to complete a separately shared validation spreadsheet. For many cities this follows an earlier validation round, and where this is the case, the previous feedback recorded---which this updated analysis aims to address---has been summarised at the end of the report.  Each report section notes the validation question(s) it supports. Where this is the region's first analysis, the validation is a first pass rather than a re-validation of earlier results.</p>
        """
        self.parts.append(html)

    # ---------------------------------------------------- enhancements (static)
    def enhancements(self):
        # configurable-contrast additions, shown when the stricter LTS-1-only
        # variant is configured (cycling_indicators.contrasts)
        contrast_bullet = ''
        lts1_reading = ''
        if 'lts1' in self.measures:
            contrast_bullet = """
        <li><b>Configurable measure contrasts, including a stricter
        &ldquo;LTS&nbsp;1 only&rdquo; low-stress variant.</b> The pairs of access
        measures that are calculated and juxtaposed in this report are now
        configurable per city. In addition to the established contrast (low-stress
        LTS&nbsp;1&ndash;2 route vs danger-weighted route), this report adds a second
        contrast — <i>low-stress (LTS&nbsp;1 only)</i> vs <i>low-stress
        (LTS&nbsp;1&ndash;2)</i> — as a sensitivity analysis on where the
        &ldquo;low-stress&rdquo; line is drawn, shown below the established contrast
        for each reporting item.</li>"""
            lts1_reading = """
        <li><b>Low-stress route, LTS&nbsp;1 only (a stricter sensitivity variant).</b>
        As the low-stress measure, but the route must stay entirely on LTS&nbsp;1
        streets — the calmest streets and separated paths, suitable for all ages and
        abilities including children. The gap between this and the LTS&nbsp;1&ndash;2
        figure shows how much reported &ldquo;safe&rdquo; access depends on LTS&nbsp;2
        streets (calm, but not universally comfortable) — a more intuitive
        policy target in settings where LTS&nbsp;2 streets are contested, and a check
        on the sensitivity of results to the low-stress threshold.</li>"""
        html = f"""
        <h2>1. About this analysis: the integrated GHSCI cycling workflow</h2>
        <p>Cycling indicators are now calculated within the open-source
        <a href="https://github.com/healthysustainablecities/global-indicators/tree/cycling-2025">Global Healthy and
        Sustainable City Indicators (GHSCI)</a> software as an optional analysis
        step (`cycling-2025` code branch), configured per city alongside the established walkability workflow.
        The first round of results shared for validation was produced with a
        separate research prototype implementd in R; feedback from collaborators in that round
        directly shaped this integrated implementation. Key characteristics:</p>
        <ul>
        <li><b>Self-contained and reproducible.</b> The full workflow (network,
        traffic stress, destinations, accessibility, aggregation, reporting) runs
        from a single per-city configuration file in the GHSCI Docker environment
        — so city teams can generate, inspect and re-run their own indicators,
        rather than depending on a bespoke multi-tool research pipeline.</li>
        <li><b>Locally informed configuration.</b> Default speed limits and cycling
        permissions by road type are set per city from collaborator-provided
        tables (as gathered in the 2025 speed-limit consultation), with support
        for spatial speed-limit zones (e.g. 30&nbsp;km/h zone polygons), local
        no-cycling rules, and official local reporting geographies.</li>
        <li><b>Two complementary accessibility measures.</b> Responding to feedback
        that a single hard low-stress threshold can produce all-or-nothing
        artefacts, results now report (a) a <i>safe (low-stress) route</i> measure
        — destination reachable entirely via LTS&nbsp;1–2 within the distance
        threshold — alongside (b) a <i>danger-weighted</i> measure in which
        higher-stress links remain usable but cost proportionally more, giving a
        graduated benefit-of-the-doubt view.</li>
        <li><b>Strict and lenient destination variants.</b> Each destination
        category is evaluated both using 'strict' and 'lenient' criteria.  
        For food markets, the lenient variation pools these with convenience stores
         (a suggestion from Helsinki collaborators).  For public transport, where 
        service frequency data is available and configured, this is used for the strict variation.
        For public open space, the lenient variation includes any public open space; 
        the strict variation uses a size criteria of at least 1.5 hectares.  
        This change responds to feedback that a single definition can both miss locally
        important destinations and over-include marginal ones.</li>
        <li><b>Walk-the-bike (dismount) handling.</b> Homes and destinations that
        connect to the street network via footpaths are reachable by dismounting
        and walking short sections (with the walked distance penalised
        accordingly), removing an artefact in the earlier results in which such
        locations could be reported as unreachable, or were 'teleported' through 
        snapping to the nearest node on the cyclable network.</li>
        <li><b>Local-access streets.</b> Streets restricted to local motor traffic
        (e.g. <i>motor_vehicle=destination</i>) are treated as low-stress local
        streets, improving results in cities with traffic-restricted zones.</li>
        <li><b>Link stress and crossing costs.</b> Follows the methods used in manuscript and informed by previous R code and related discussions; implemented with locally supplied
        speeds, with option to configure polygon speed zones.</li>
        </ul>
        <p><b>New indicators added following the first validation round.</b> In
        addition to the binary "within X&nbsp;km" access measures reviewed
        previously, this report also presents:</p>
        <ul>
        <li><b>Customisable distance thresholds.</b> In addition to the previous 2&nbsp;km (5 - 15 mins) and 5&nbsp;km (15 to 30 mins) thresholds, a study region can define their own locally relevant distances.  The new default distance set evaluates 500m, 1km, 2km and 5km, with these presented as graded accessibility bands (akin to isochrones) within the maps in this report.</li>
        <li><b>Distance-to-nearest metrics.</b> The network distance to the nearest
        destination of each type (by both the low-stress and danger-weighted
        measures), reported alongside the binary indicators — so a neighbourhood
        that just misses a threshold is distinguishable from one that is far from
        any destination, and improvements can be tracked continuously rather than
        only as threshold crossings.</li>
        <li><b>Corrected public open space access.</b> Public open space is now
        restricted to <i>publicly-accessible</i> space and reached at its <i>network
        entry points</i> (nodes within 30&nbsp;m of the space), rather than reducing each
        whole area — public or not — to a single nearest node as previously, with a strict
        variant (large public open space, &gt;1.5&nbsp;ha) and a lenient variant
        (any public open space). This addresses previous-round feedback that open spaces
        were being over- or under-counted depending on how a single access point was
        chosen. (&ldquo;Open space&rdquo; includes squares and plazas, not only parks.)</li>
        <li><b>Access to activity centres.</b> An activity centre is a location whose
        short pedestrian walk-shed co-locates at least one destination of every
        category (food, public open space, public transport) — i.e. somewhere a
        resident can meet several everyday needs in one trip. Safe-cycling access is
        measured to the nearest <i>local</i> centre (everyday, lenient cluster) and
        <i>complete</i> centre (higher-amenity, strict cluster), giving a
        destination-bundle indicator rather than one isolated facility at a time.</li>
        <li><b>Optional sub-region summaries.</b> The report now includes an optional summary table of accessibility indicators by local administrative area (e.g. ward, district, or neighbourhood), if the region configures a local reporting geography.  This allows city teams to see how access varies across the city and identify priority areas for improvement (see Dar-es-Salaam).</li>
        <li><b>Optimised routing analysis.</b> The routing engine has been optimised to reduce memory usage and speed up the analysis, allowing larger cities to be processed more efficiently. The new default 'in-memory' engine is much faster than the previous pgRouting approach to deliver the same results.  The latter is still used for pedestrian analyses in the GHSCI software, and optionally may still be configured for the cycling indicators.</li>{contrast_bullet}
        </ul>

        <h3>How to read these indicators (in plain language)</h3>
        <p>Each indicator asks a simple question about a place: <b>starting from
        here, can a person on a bicycle reach a given kind of destination within a
        set distance, using streets that feel safe to ride?</b> "Distance" is measured
        along the street network (not straight-line), at 2&nbsp;km (~5 to 15 mins) and 5&nbsp;km (~15 to 30 mins) — roughly a short and a longer everyday bike trip.  Distance thresholds can be customised by users, and for completeness the repeated analyses presented here also include access at 500&nbsp;m (~3 mins) and 1&nbsp;km (~6 mins) distances.</p>

        <p><b>Level of Traffic Stress (LTS).</b> Every street is graded 1–4 for how
        stressful it is to cycle on, from LTS&nbsp;1 (calm streets and separated paths,
        suitable for children and cautious riders) to LTS&nbsp;4 (busy, fast roads that
        only confident riders will use). The grade comes from the road type, speed limit,
        traffic and any cycling facility. This is the backbone of every accessibility
        result and the subject of the map in section&nbsp;2.</p>

        <p><b>The access measures — and how to interpret them.</b> For each
        destination we report the following figures:</p>
        <ul>
        <li><b>Low-stress route (the headline "safe" measure).</b> The destination
        counts as reachable only if there is a route within the distance limit that
        stays entirely on low-stress (LTS&nbsp;1–2) streets. In practice this is what a
        cautious rider — someone cycling with children, or new to riding — can reach
        without ever having to use a stressful road. This is the strict, conservative
        measure.</li>
        <li><b>Danger-weighted route (a "benefit-of-the-doubt" measure).</b> Here
        higher-stress roads are <i>allowed</i> but <i>penalised</i>: when the software
        looks for the shortest route, each stressful LTS&nbsp;3–4 segment is counted as
        1.25× its real length, so calm streets are strongly preferred but a busy road
        will be used where it genuinely shortens the trip. A destination counts as
        reachable if such a (mostly-calm, occasionally-stressful) route exists within the
        distance limit. In practice this reflects what a more <i>confident</i> rider
        could reach, and — because the penalty is proportional, not absolute — it also
        approximates what would become reachable with only modest low-stress
        improvements. It is always greater than or equal to the low-stress-route figure;
        <b>the gap between the two shows where a small number of stressful links are the
        only barrier</b> to calm-street access, i.e. where targeted infrastructure would
        help most.</li>{lts1_reading}
        </ul>
        <p><b>Strict vs lenient destinations.</b> Each category is measured both strictly
        (e.g. dedicated fresh-food markets; large public open space) and leniently (e.g.
        also counting convenience stores; any public open space), so local knowledge can
        say which definition is meaningful for the city.</p>
        <p><b>Distance-to-nearest.</b> Alongside the yes/no access figures, the report
        gives the average network distance to the nearest destination of each type — so a
        neighbourhood that <i>just</i> misses a 2&nbsp;km threshold is distinguishable from
        one that is genuinely far from everything.</p>
        <p><b>Reading the maps.</b> Coloured cells show the share of sample points in each
        100&nbsp;m neighbourhood with access — <span style="color:#1a9850">green = high</span>,
        <span style="color:#d7191c">red = low</span>. Markers show the actual reference
        destinations being measured (e.g. the open-space access points). The caption gives
        the single region-wide population figure. The network map in section&nbsp;2 is
        coloured by LTS (green calm → red stressful).</p>

        <p class="note">Supports form Part 1 context and question 1.3 (output
        communication): the same configuration can regenerate maps, grids, ward
        summaries and this report as data or definitions are refined.</p>
        """
        self.parts.append(html)

    # ------------------------------------------------------------ LTS network
    def lts_network(self):
        if not self.has('edges'):
            return
        r = self.r
        edges = get_gdf_generic(
            r,
            'SELECT ogc_fid, lvl_traf_stress, bike_permitted, foot_dismount, '
            'maxspeed_kmh, length, geom FROM edges',
        )
        n = len(edges)
        total_km = edges['length'].sum() / 1000
        dismount_km = edges.loc[edges['foot_dismount'].fillna(False), 'length'].sum() / 1000
        # Table 1 = the FULL routable network (all edges, including walkable-only dismount
        # footpaths); a cycling-permitted-only share column is shown alongside so the contrast
        # (what the classification looks like once footpaths are excluded) is explicit.
        full = (
            edges.assign(km=edges['length'] / 1000)
            .groupby('lvl_traf_stress')
            .agg(edges=('ogc_fid', 'count'), km=('km', 'sum'))
        )
        full_km = full['km'].sum()
        ride = edges[edges['bike_permitted'].fillna(False)]
        ride_by = ride.assign(km=ride['length'] / 1000).groupby('lvl_traf_stress')['km'].sum()
        ride_km = ride_by.sum()
        ride_n = len(ride)

        def fpc(i):
            return 100 * full.loc[i, 'km'] / full_km if i in full.index and full_km else 0

        def rpc(i):
            return 100 * ride_by.loc[i] / ride_km if i in ride_by.index and ride_km else 0

        rows = ''.join(
            f'<tr><td style="color:{LTS_COLORS[i]};font-weight:bold">{LTS_LABELS[i]}</td>'
            f'<td>{int(full.loc[i, "edges"]) if i in full.index else 0:,}</td>'
            f'<td>{full.loc[i, "km"] if i in full.index else 0:,.0f}</td>'
            f'<td>{fpc(i):.1f}%</td><td>{rpc(i):.1f}%</td></tr>'
            for i in [1, 2, 3, 4]
        )
        rows += (
            '<tr style="background:#f7f7f7"><td colspan="3">'
            '<b>LTS 1–2 (low-stress share)</b></td>'
            f'<td><b>{fpc(1) + fpc(2):.1f}%</b></td>'
            f'<td><b>{rpc(1) + rpc(2):.1f}%</b></td></tr>'
        )
        table = f"""
        <table><thead><tr><th>Level of Traffic Stress</th><th>Edges</th>
        <th>Length (km)</th><th>Share of full<br/>routable network</th>
        <th>Share of cycling-<br/>permitted network</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p>The full routable network is {n:,} edges ({total_km:,.0f}&nbsp;km): {ride_n:,} edges
        ({ride_km:,.0f}&nbsp;km) where cycling is permitted, plus {dismount_km:,.0f}&nbsp;km of
        <b>walkable-only</b> footways/paths (all classified LTS&nbsp;1, drawn thin on the map).
        <b>Why classify edges that cannot be ridden?</b> They are part of the routable network:
        a rider can dismount and walk the bicycle along a footpath (at a penalised cost) to reach
        the cycling network, or a destination that sits on one — so each is classified (off-road
        footpaths are LTS&nbsp;1) and given a crossing impedance, letting routing treat the whole
        network consistently. The final column isolates the classification of the edges that are
        actually ridden.</p>
        """

        fig, ax = plt.subplots(figsize=(12, 12))
        if self.boundary is not None:
            self.boundary.boundary.plot(ax=ax, color='white', linewidth=1.2, zorder=5)
        plot_edges = edges
        for lts, c in LTS_COLORS.items():
            seg = plot_edges[plot_edges['lvl_traf_stress'] == lts]
            if len(seg):
                lw = 0.4 if lts <= 2 else 1.0
                seg.plot(ax=ax, color=c, linewidth=lw, alpha=0.85, zorder=3 + (lts > 2))
        add_basemap(ax, plot_edges.crs)
        add_scalebar(ax)
        ax.legend(
            handles=[
                mlines.Line2D([], [], color=c, lw=2, label=f'LTS {k}')
                for k, c in LTS_COLORS.items()
            ],
            loc='upper right', fontsize=9, framealpha=0.9,
        )
        ax.set_axis_off()
        ax.set_title(f'{r.name}: street network by cycling Level of Traffic Stress')
        html = (
            '<h2>2. Level of Traffic Stress classification</h2>'
            '<p class="formlink">Supports form <b>Part 2 (LTS validation)</b>: the'
            ' map and statistics below summarise the street-level stress'
            ' classification that a MapRoulette challenge (as used in the previous'
            ' round) samples for local review.</p>'
            + table
            + self._r_lts_comparison_table(edges)
            + img_tag(fig, f'{r.name}: network coloured by LTS class (walkable-only footpaths drawn thin; higher-stress roads on top)')
        )
        self.parts.append(html)

    def _r_lts_comparison_table(self, edges):
        """Separate R-vs-GHSCI LTS class-share table (R then GHSCI), or '' if no R gpkg.

        The apples-to-apples basis is the **cycling-permitted network within the study-region
        boundary** — the previous R network was boundary-clipped and excluded footpaths, so
        GHSCI is restricted the same way here (a different basis from the full-network table
        above, which spans the whole analysis buffer and includes dismount footpaths).  Class
        *shares* by length are compared, not absolute km (the R network was one-way-split).
        """
        import glob

        gpkgs = glob.glob(
            f'/home/ghsci/r_output/{self.r.name}/*_cyclingIndicators.gpkg',
        )
        if not gpkgs:
            return ''
        try:
            R = gpd.read_file(gpkgs[0], layer='edges').to_crs(edges.crs)
        except Exception as e:
            print(f'  (R LTS comparison unavailable: {e})')
            return ''
        if 'length' not in R.columns or pd.to_numeric(
            R['length'], errors='coerce',
        ).isna().all():
            R = R.assign(length=R.geometry.length)
        # GHSCI: cycling-permitted edges within the study-region boundary (match R's basis)
        G = edges[edges['bike_permitted'].fillna(False)]
        clipped = ''
        if self.boundary is not None:
            bnd = self.boundary.to_crs(edges.crs).geometry.union_all()
            G = G[G.geometry.representative_point().within(bnd)]
            clipped = ' within the study-region boundary'

        def shares(df):
            km = (
                df.assign(km=pd.to_numeric(df['length'], errors='coerce') / 1000)
                .groupby('lvl_traf_stress')['km'].sum()
            )
            tot = km.sum()
            return {
                i: (100 * km.loc[i] / tot if i in km.index and tot else 0)
                for i in (1, 2, 3, 4)
            }

        rs, gs = shares(R), shares(G)
        rows = ''.join(
            f'<tr><td style="color:{LTS_COLORS[i]};font-weight:bold">LTS {i}</td>'
            f'<td>{rs[i]:.1f}%</td><td>{gs[i]:.1f}%</td></tr>'
            for i in (1, 2, 3, 4)
        )
        rows += (
            '<tr style="background:#f7f7f7"><td><b>LTS 1–2 (low-stress)</b></td>'
            f'<td><b>{rs[1] + rs[2]:.1f}%</b></td>'
            f'<td><b>{gs[1] + gs[2]:.1f}%</b></td></tr>'
        )
        return (
            '<h3>Comparison with the previous (R) classification</h3>'
            f'<p>For a like-for-like comparison, both columns are the <b>cycling-permitted'
            f' network{clipped}</b> — i.e. the cycling-permitted column of the table above'
            ' (walkable-only footpaths already excluded), further <b>clipped to the study-region'
            ' boundary</b>. The clip matters because the previous R network was boundary-clipped,'
            ' whereas the tables above span the full 5000&nbsp;m analysis buffer (which adds lower'
            '-stress peri-urban roads, so the buffer-wide low-stress share is a little higher).'
            ' Class <b>shares</b> are compared, not absolute lengths, because the R network was'
            ' one-way-split.</p>'
            '<table><thead><tr><th>Level of Traffic Stress</th>'
            '<th>Previous R<br/>(share)</th><th>GHSCI<br/>(share)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
            '<p class="note">The same LTS rules are applied in both. Where a street reads'
            ' higher-stress in GHSCI at the same location it reflects a network-build difference,'
            ' not a classification error — GHSCI carries a separated cycle track as its own'
            ' low-stress edge (so the arterial carriageway is scored on its own merits,'
            ' LTS&nbsp;3–4, where R folded the track onto the carriageway → LTS&nbsp;1), and GHSCI'
            ' keeps bus roads (<code>busway</code>) that R dropped. See the technical comparison'
            ' (<code>cycling_R_vs_GHSCI.md</code>).</p>'
        )

    # ------------------------------------------------------------ destinations
    def destinations(self):
        if not self.has('destinations'):
            return
        r = self.r
        destinations = r.config['cycling_indicators'].get('destinations', {})
        counts = {}
        dests = {}
        for d in destinations:
            sql = f"""SELECT '{d['name']}' dest_name, geom FROM {d['layer']} WHERE {d.get('where','TRUE')}"""
            dests[d['name']] = r.get_gdf(sql)
            if dests[d['name']] is not None:
                counts[d['name']] = {}
                counts[d['name']]['n'] = dests[d['name']].shape[0]
                counts[d['name']]['where'] = d.get('where',d.get('layer',''))
        counts = pd.DataFrame.from_dict(
                    counts,orient='index'
                ).sort_index().rename_axis('dest_name').reset_index()
        pos_note = 'Note: Public open space access points are generated every 30&nbsp;m along the edge of areas of open space with publicly accessible areas; this does not represent the actual count of public open spaces.'
        rows = ''.join(
            f'<tr><td>{d.dest_name}</td><td>{int(d.n):,}</td><td>{d.where}</td></tr>'
            for d in counts.itertuples()
        )
        dests = pd.concat(dests.values())
        fig, ax = plt.subplots(figsize=(12, 12))
        # palette chosen for each category in dests to contrast with the batlow access colour scale (blue → teal → green → yellow)
        palette = {
            'fresh_food_market': ("#ff9900", 20, 8),
            'fresh_food_pooled': ("#f1dea0", 10, 7),
            'pt_frequent': ("#2e50e7", 20, 6),
            'pt_any': ("#89c2f0", 10, 5),
            'public_open_space_large': ("#397c3f", 5, 4),
            'public_open_space_any': ("#a8eb97", 5, 3),
            'activity_centre_complete': ("#ee10e3", 20, 2),
            'activity_centre_local': ("#f0afec", 10, 1),
        }
        others = dests[~dests['dest_name'].isin(palette)]['dest_name'].unique()
        for other in others:
            random_colour = "#%06x" % random.randint(0, 0xFFFFFF)
            palette[other] = (random_colour, 10, 10)
        if self.boundary is not None:
            self.boundary.boundary.plot(ax=ax, color='white', linewidth=1.2, zorder=6)
        handles = []
        for name, (color, size, z) in palette.items():
            sub = dests[dests['dest_name'] == name]
            if len(sub):
                sub.plot(ax=ax, color=color, markersize=size, alpha=0.8, zorder=z)
                handles.append(
                    mlines.Line2D(
                        [], [], color=color, marker='o', ls='',
                        label=f'{name} ({len(sub):,})',
                    ),
                )
        add_basemap(ax, dests.crs)
        add_scalebar(ax)
        ax.legend(handles=handles, loc='upper right', fontsize=9, framealpha=0.9)
        ax.set_axis_off()
        ax.set_title(f'{r.name}: destinations compiled from OpenStreetMap')
        html = (
            '<h2>3. Destination distribution</h2>'
            '<p class="formlink">Supports form question <b>1.4 (destination'
            ' distribution)</b>: are any key destinations missing, or definitions'
            ' too broad/narrow for this city? Both a strict and a lenient variant'
            ' of each category is analysed, so local advice can inform which'
            ' definition is most meaningful.</p>'
            f'<table><thead><tr><th>Destination (OSM-derived)</th><th>Count</th><th>Location</th></tr></thead><tbody>{rows}</tbody></table>'
            f'<ul>{pos_note}</ul>'
            + img_tag(fig, f'{r.name}: compiled destination points')
        )
        self.parts.append(html)

    # ------------------------------------------------------- city-level access
    def city_summary(self):
        if not self.has(self.r.config['city_summary']):
            return
        # city-level cycling values carry the aggregation's population-weighting
        # prefix: pop_pct_access_cycle_[safe_]<name>_<d>m
        cols = self.region_value_cols('pop_pct_access_cycle')
        if not cols:
            self.missing.append('cycling columns on city summary (run _12_aggregation)')
            return
        city = self.r.get_df(
            f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} '
            f'FROM {self.r.config["city_summary"]}',
        ).iloc[0]

        available_names = {
            split_measure_col(c, 'pop_pct_access_cycle_')[1].rsplit('_', 1)[0]
            for c in cols
        }
        n_dist_cols = 1 + 2 * len(self.distances)

        def contrast_table(ma, mb):
            rows = ''
            for name, group, is_first in _table_row_order(available_names):
                if is_first:
                    rows += (
                        f'<tr class="cat-hdr"><td colspan="{n_dist_cols}">'
                        f'{group}</td></tr>'
                    )
                label = DEST_LABELS.get(name, name)
                cells = ''
                for d in self.distances:
                    for mk in (ma, mb):
                        col = (
                            f'pop_pct_access_cycle_'
                            f'{MEASURES[mk]["infix"]}{name}_{d}m'
                        )
                        if col in city.index and not pd.isna(city[col]):
                            val = float(city[col])
                            style = _batlow_cell_bg(val, 'pct')
                            cells += f'<td style="{style}">{val:.1f}%</td>'
                        else:
                            cells += '<td>—</td>'
                rows += f'<tr><td>{label}</td>{cells}</tr>'
            header_cells = ''.join(
                f'<th>{d / 1000:g} km<br/>{MEASURES[ma]["label"]}</th>'
                f'<th>{d / 1000:g} km<br/>{MEASURES[mb]["label"]}</th>'
                for d in self.distances
            )
            return (
                f'<table><thead><tr><th>Destination</th>{header_cells}</tr>'
                f'</thead><tbody>{rows}</tbody></table>'
            )

        contrasts = self.available_contrasts(cols, 'pop_pct_access_cycle_')
        if not contrasts:
            contrasts = self.contrasts[:1]
        ma, mb = contrasts[0]
        tables = (
            f'<p>Estimated share of the region\'s population with access to each'
            f' destination type within the network distance thresholds, comparing'
            f' the <b>{MEASURES[ma]["label"].lower()}</b> and'
            f' <b>{MEASURES[mb]["label"].lower()}</b> measures.</p>'
            + contrast_table(ma, mb)
        )
        for ma, mb in contrasts[1:]:
            tables += (
                f'<p><b>Alternative contrast (sensitivity):'
                f' {MEASURES[ma]["label"]} vs {MEASURES[mb]["label"]}.</b>'
                f' The same population-access results, juxtaposing the'
                f' {MEASURES[ma]["label"].lower()} measure against the'
                f' {MEASURES[mb]["label"].lower()} measure.</p>'
                + contrast_table(ma, mb)
            )
        dist_table = self._distance_table()
        html = f"""
        <h2>4. City-level results: population access and distance to destinations</h2>
        <p class="formlink">Supports form questions <b>1.1 and 1.2</b> (is the
        distribution of accessibility within {' and '.join(f'{d / 1000:g} km' for d in self.distances)}
        as expected?) and <b>1.3</b> (percent-of-population is the headline
        communication measure, as favoured by most collaborators in the previous
        round).</p>
        {tables}
        {dist_table}
        """
        self.parts.append(html)

    def _distance_table(self):
        """Population-weighted mean network distance to the nearest destination.

        Uses the ``pop_avg_cycle_dist_[safe_]<name>`` city columns (metres).  These
        are averaged over sample points that can reach the destination within the
        largest threshold, so they describe typical proximity where access exists —
        a companion to the binary access percentages above (new post-validation
        distance metric).
        """
        dcols = self.region_value_cols('pop_avg_cycle_dist')
        if not dcols:
            return ''
        city = self.r.get_df(
            f'SELECT {", ".join(chr(34) + c + chr(34) for c in dcols)} '
            f'FROM {self.r.config["city_summary"]}',
        ).iloc[0]

        available_names = {
            split_measure_col(c, 'pop_avg_cycle_dist_')[1] for c in dcols
        }

        def contrast_table(ma, mb):
            rows = ''
            for name, group, is_first in _table_row_order(available_names):
                if is_first:
                    rows += (
                        f'<tr class="cat-hdr"><td colspan="3">'
                        f'{group}</td></tr>'
                    )
                cells = ''
                for mk in (ma, mb):
                    col = f'pop_avg_cycle_dist_{MEASURES[mk]["infix"]}{name}'
                    if col in city.index and not pd.isna(city[col]):
                        v = float(city[col])
                        style = _batlow_cell_bg(v, 'dist')
                        disp = f'{v / 1000:.2f} km' if v >= 1000 else f'{v:.0f} m'
                        cells += f'<td style="{style}">{disp}</td>'
                    else:
                        cells += '<td>—</td>'
                rows += (
                    f'<tr><td>{DEST_LABELS.get(name, name)}</td>{cells}</tr>'
                )
            return (
                '<table><thead><tr><th>Destination</th>'
                f'<th>{MEASURES[ma]["label"]}</th>'
                f'<th>{MEASURES[mb]["label"]}</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>'
            )

        contrasts = self.available_contrasts(dcols, 'pop_avg_cycle_dist_')
        if not contrasts:
            contrasts = self.contrasts[:1]
        html = (
            '<p><b>Average distance to the nearest destination</b> (new'
            ' post-validation metric): population-weighted mean network distance'
            ' among residents able to reach each destination type, by each'
            ' access measure. Note that the measure columns have different'
            ' denominators (each averages over the residents reachable under'
            ' that measure).</p>'
            + contrast_table(*contrasts[0])
        )
        for ma, mb in contrasts[1:]:
            html += (
                f'<p><b>Alternative contrast (sensitivity):'
                f' {MEASURES[ma]["label"]} vs {MEASURES[mb]["label"]}.</b></p>'
                + contrast_table(ma, mb)
            )
        return html

    # ------------------------------------------------- comparison with R results
    def r_comparison(self):
        """Contrast the directly comparable strict-safe indicators with the previous
        R-based results, where a prior R gpkg exists for this region (mounted at
        /home/ghsci/r_output/<City>/).  Skipped for first-pass cities (no R gpkg,
        e.g. Dar es Salaam).  GHSCI-only indicators are featured in other sections."""
        import glob

        if 'sample_points_cycling' not in self.tables:
            return
        gpkgs = glob.glob(
            f'/home/ghsci/r_output/{self.r.name}/*_cyclingIndicators.gpkg',
        )
        if not gpkgs:
            return
        try:
            R = gpd.read_file(gpkgs[0], layer='sample_points_accessibility')
        except Exception as e:
            print(f'  (R comparison unavailable: {e})')
            return
        # R strict-safe binary column template -> (GHSCI spec name, label).
        # A None template = a GHSCI-only indicator (no comparable R column) shown for
        # context.  R's open-space measure was the whole (unfiltered) open_space_areas
        # layer reduced to one nearest node, so its closest GHSCI comparator is the
        # 'any' public-open-space variant; the '> 1.5 ha' variant is added as a stricter
        # GHSCI-only indicator.
        mapping = [
            ('fresh_food_market_safe_{}km', 'fresh_food_market', 'Fresh food market'),
            ('pt_any_safe_{}km', 'pt_any', 'Public transport (any stop)'),
            ('public_open_space_safe_{}km', 'public_open_space_any',
             'Public open space (any)*'),
            (None, 'public_open_space_large',
             'Public open space (&gt; 1.5&nbsp;ha)&dagger;'),
            ('all_safe_access_{}km', 'all_strict', 'All categories'),
        ]
        dists = [d for d in (2, 5) if d * 1000 in self.distances]
        spc_cols = {
            c.lower()
            for c in self.r.get_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sample_points_cycling'")['column_name']
        }
        want = [
            f'sp_cycle_safe_access_{g}_{d * 1000}m'
            for _, g, _ in mapping for d in dists
        ]
        want = [c for c in want if c in spc_cols]
        G = (
            self.r.get_df(
                f'SELECT {", ".join(chr(34) + c + chr(34) for c in want)} '
                'FROM sample_points_cycling')
            if want else None
        )
        n_ghsci = self.r.get_df(
            'SELECT count(*) AS n FROM sample_points_cycling')['n'][0]

        def pct(frame, col):
            if frame is None or col not in frame.columns:
                return '—'
            s = pd.to_numeric(frame[col], errors='coerce')
            return f'{100 * s.mean():.1f}%' if s.notna().any() else '—'

        rows = ''
        for tmpl, gname, label in mapping:
            cells = ''
            for d in dists:
                r_cell = pct(R, tmpl.format(d)) if tmpl else '—'
                cells += f'<td>{r_cell}</td>'
                cells += f'<td>{pct(G, f"sp_cycle_safe_access_{gname}_{d * 1000}m")}</td>'
            rows += f'<tr><td>{label}</td>{cells}</tr>'
        headers = ''.join(
            f'<th>R {d} km</th><th>GHSCI {d} km</th>' for d in dists)
        maps = self._r_comparison_maps(gpkgs[0])
        html = f"""
        <h2>5. Comparison with previous (R-based) results</h2>
        <p class="formlink">For cities analysed in the earlier round, this contrasts the
        <b>directly comparable</b> strict low-stress-route indicators. Both figures are the
        share of sample points with access, computed identically; the two analyses use
        independently generated sample points ({len(R):,} R vs {n_ghsci:,} GHSCI), so this
        is an aggregate comparison, not point-by-point.</p>
        <table><thead><tr><th>Destination (strict, low-stress route)</th>{headers}</tr></thead>
        <tbody>{rows}</tbody></table>
        <p class="note">* <b>Public open space is not a like-for-like comparison.</b> The previous
        R analysis measured access to <b>every</b> area of open space (public <i>and</i> non-public,
        any size) reduced to its single nearest network node; GHSCI measures access to
        <b>publicly&nbsp;accessible</b> open space at its network <b>entry points</b> — an
        improvement in both the data (public only) and the representation (entrances, not one
        node per area). The GHSCI <b>&ldquo;any&rdquo;</b> variant is the closest comparator and is
        shown against the R figure. &dagger; The stricter <b>&ldquo;&gt;&nbsp;1.5&nbsp;ha&rdquo;</b>
        variant is an additional GHSCI indicator with no R equivalent.</p>
        <p class="note">Differences chiefly reflect the workflow enhancements in section 1
        — walk-the-bike access to footpath-connected origins and destinations, an expanded
        low-stress network from the corrected traffic-stress and cycling-permission rules,
        and the corrected public-open-space definition — rather than errors. The GHSCI-only
        indicators (lenient variants, the graduated danger-weighted measure, activity
        centres, the 500 m/1000 m bands and distance-to-nearest metrics) have no R
        equivalent and are presented in the other sections.</p>
        {maps}
        """
        self.parts.append(html)

    def _r_comparison_maps(self, gpkg):
        """Side-by-side previous-R vs GHSCI isochrone maps for comparable strict-safe
        indicators at 2 km and 5 km (the only distances available in the legacy R
        output).  GHSCI is also restricted to 2 km / 5 km here for a fair comparison;
        the full multi-band isochrone across all configured distances is in section 6."""
        try:
            r_grid = gpd.read_file(gpkg, layer='grid_accessibility').to_crs(epsg=self.srid)
        except Exception as e:
            print(f'  (R comparison maps unavailable: {e})')
            return ''
        grid_table = self.r.config['grid_summary']
        gcols = set(self.r.get_df(
            'SELECT column_name FROM information_schema.columns '
            f"WHERE table_name = '{grid_table}'")['column_name'])
        # (R column prefix, GHSCI indicator name, label) — measure always 'safe'
        pair_specs = [
            ('all_safe_access',        'all_strict',              'All categories'),
            ('fresh_food_market_safe',  'fresh_food_market',       'Fresh food market'),
            ('public_open_space_safe',  'public_open_space_any',   'Public open space (any)'),
            ('pt_any_safe',             'pt_any',                  'Public transport'),
        ]
        valid_pairs = [
            (rp, gn, lbl) for rp, gn, lbl in pair_specs
            if f'{rp}_2km' in r_grid.columns
            and f'pct_access_cycle_safe_{gn}_2000m' in gcols
        ]
        if not valid_pairs:
            return ''
        # Comparison fixed at 2 km / 5 km (R legacy distances)
        comp_dists = [2000, 5000]
        n_bands = len(comp_dists) + 1  # 3: within 2 km / 5 km / no access
        # Load GHSCI grid with all comparison columns (2 km + 5 km)
        g_needed = sorted({
            f'pct_access_cycle_safe_{gn}_{d}m'
            for _, gn, _ in valid_pairs
            for d in comp_dists
            if f'pct_access_cycle_safe_{gn}_{d}m' in gcols
        })
        g_grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, {", ".join(chr(34) + c + chr(34) for c in g_needed)}, geom '
            f'FROM {grid_table}')
        imgs = ''
        for r_pfx, g_name, lbl in valid_pairs:
            # R isochrone: values are 0-1 proportions, threshold >= 0.5
            r_cat = pd.Series(n_bands - 1, index=r_grid.index, dtype=int)
            for i, d in reversed(list(enumerate(comp_dists))):
                r_col = f'{r_pfx}_{d // 1000}km'
                if r_col in r_grid.columns:
                    r_cat[
                        pd.to_numeric(r_grid[r_col], errors='coerce').fillna(0) >= 0.5
                    ] = i
            # GHSCI isochrone: 0-100 pct, threshold >= 50, fixed to comp_dists
            g_comp = [d for d in comp_dists
                      if f'pct_access_cycle_safe_{g_name}_{d}m' in gcols]
            g_cat, g_n_bands, _ = self._isochrone_cat(
                g_grid, g_name, g_comp, measure='low_stress')
            if g_n_bands < n_bands:
                g_cat[g_cat == g_n_bands - 1] = n_bands - 1

            fig, axes = plt.subplots(1, 2, figsize=(16, 8))
            for ax, gdf, isocat, tag in [
                (axes[0], r_grid, r_cat, 'Previous (R)'),
                (axes[1], g_grid, g_cat, 'GHSCI (this analysis)'),
            ]:
                iso_handles = self._plot_isochrone_ax(
                    ax, gdf, isocat, n_bands, comp_dists)
                if self.boundary is not None:
                    self.boundary.boundary.plot(
                        ax=ax, color='black', linewidth=0.8)
                add_basemap(ax, gdf.crs)
                add_scalebar(ax)
                ax.legend(handles=iso_handles, loc='lower right',
                          fontsize=8, framealpha=0.9)
                ax.set_axis_off()
                ax.set_title(tag, fontsize=11)
            fig.suptitle(
                f'{self.r.name}: {lbl} — low-stress access, R vs GHSCI',
                fontsize=12)
            fig.tight_layout()
            imgs += img_tag(
                fig,
                f'{self.r.name}: {lbl} — isochrone comparison (2 km / 5 km):'
                ' previous R (left) vs GHSCI (right). Same colour scale.')
        return (
            '<p class="note">Side-by-side isochrone maps (R left, GHSCI right)'
            ' using the 2 km and 5 km bands available in the legacy R results.'
            ' Each band shows where the majority (≥ 50 %) of grid-cell sample'
            ' points have access within that distance. GHSCI is restricted to'
            ' 2 km / 5 km here for a fair comparison; the full multi-band'
            ' isochrone across all configured distances is in section 6.</p>'
            + imgs)

    # ------------------------------------------------------- map helper overlays
    def overlay_destinations(self, ax, crs, name):
        """Overlay the reference destinations an indicator measures access to.

        Returns a legend handle, or None if there is no overlay for this indicator
        (e.g. the composite 'all categories' maps, which have no single target)."""
        spec = DEST_OVERLAY.get(name)
        if spec is None:
            return None
        sql, color, label = spec
        try:
            g = get_gdf_generic(self.r, sql).to_crs(crs)
        except Exception:
            return None
        if not len(g):
            return None
        # markers stay near-opaque with a white edge so they read over any batlow value
        g.plot(ax=ax, color=color, markersize=5, alpha=0.9, zorder=6,
               edgecolor='white', linewidth=0.3)
        return mlines.Line2D(
            [], [], color=color, marker='o', ls='', markersize=6,
            markeredgecolor='white', label=f'{label} (n={len(g):,})')

    def _region_pct(self):
        """{pop_pct_access_cycle_* column: value} for map captions."""
        cols = self.region_value_cols('pop_pct_access_cycle')
        if not cols:
            return {}
        row = self.r.get_df(
            f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} '
            f'FROM {self.r.config["city_summary"]}').iloc[0]
        return {
            c: (None if pd.isna(row[c]) else float(row[c])) for c in cols
        }

    # -------------------------------------------------- isochrone helpers
    def _isochrone_cat(self, grid, name, distances, measure='low_stress'):
        """Assign each grid cell to an isochrone band.

        The band is the *minimum* configured distance at which ≥ 50 % of the
        cell's sample points have access (majority threshold).  Band 0 = closest
        configured distance (best); band n_bands − 1 = no access within any
        configured distance.

        Returns ``(cat, n_bands, sorted_dists)``.
        """
        sorted_dists = sorted(distances)
        n_bands = len(sorted_dists) + 1
        prefix = f'pct_access_cycle_{MEASURES[measure]["infix"]}{name}_'
        cat = pd.Series(n_bands - 1, index=grid.index, dtype=int)
        # Iterate reversed so the smallest distance (best) wins by overwriting
        for i, d in reversed(list(enumerate(sorted_dists))):
            col = f'{prefix}{d}m'
            if col in grid.columns:
                cat[grid[col].fillna(0) >= 50] = i
        return cat, n_bands, sorted_dists

    def _plot_isochrone_ax(self, ax, grid, cat, n_bands, sorted_dists):
        """Paint isochrone bands on *ax* (outer/worst first, inner/best last).

        Active distance bands use equally-spaced batlow colours:
          • cat 0 (closest distance, best access) → pale yellow/pink end
          • cat n_bands − 2 (farthest distance)   → dark blue end
        The "no access" band (cat n_bands − 1) uses neutral mid-grey.

        Returns a list of ``mpatches.Patch`` legend handles.
        """
        n_active = n_bands - 1  # number of distance bands
        colors = [
            ACCESS_CMAP(1.0 - i / max(n_active - 1, 1))
            for i in range(n_active)
        ]
        colors.append(ISOCHRONE_NO_ACCESS_COLOR)  # "no access" band

        working = grid.copy()
        working['_cat'] = cat
        # Paint worst → best so inner (closest) bands appear on top
        for i in range(n_bands - 1, -1, -1):
            sub = working[working['_cat'] == i]
            if len(sub):
                sub.plot(ax=ax, color=colors[i], alpha=0.7, linewidth=0)

        handles = [
            mpatches.Patch(facecolor=colors[i], alpha=0.7,
                           label=f'Within {d / 1000:g} km')
            for i, d in enumerate(sorted_dists)
        ]
        handles.append(mpatches.Patch(
            facecolor=ISOCHRONE_NO_ACCESS_COLOR, alpha=0.7,
            label=f'No access within {sorted_dists[-1] / 1000:g} km',
        ))
        return handles

    # ------------------------------------------------------------- grid maps
    def grid_maps(self):
        grid_table = self.r.config['grid_summary']
        if not self.has(grid_table):
            return
        cols = set(
            self.r.get_df(
                'SELECT column_name FROM information_schema.columns '
                f"WHERE table_name = '{grid_table}'",
            )['column_name'],
        )
        pct_cols = [c for c in cols if c.startswith('pct_access_cycle_')]
        contrasts = self.available_contrasts(pct_cols, 'pct_access_cycle_')
        if not contrasts:
            contrasts = self.contrasts[:1]
        contrast_measures = [
            m for m in MEASURE_ORDER if any(m in pair for pair in contrasts)
        ]
        # Include every configured destination/indicator for which at least one
        # access distance column (any contrast measure) exists in the grid summary.
        wanted_names = [
            name for name in DEST_LABELS
            if any(
                f'pct_access_cycle_{MEASURES[m]["infix"]}{name}_{d}m' in cols
                for m in contrast_measures
                for d in self.distances
            )
        ]
        if not wanted_names:
            self.missing.append('cycling columns on grid summary (run _12_aggregation)')
            return
        # Collect all needed columns (all contrast measures, all distances) in one query
        all_grid_cols = [
            c
            for name in wanted_names
            for d in self.distances
            for c in (
                f'pct_access_cycle_{MEASURES[m]["infix"]}{name}_{d}m'
                for m in contrast_measures
            )
            if c in cols
        ]
        grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, pop_est, '
            f'{", ".join(chr(34) + c + chr(34) for c in all_grid_cols)}, geom '
            f'FROM {grid_table}',
        )
        region = self._region_pct()
        imgs = ''
        for name in wanted_names:
            label = DEST_LABELS[name]
            for ci, (ma, mb) in enumerate(contrasts):
                fig, axes = plt.subplots(1, 2, figsize=(18, 9))
                caption_stats = []
                for ax, measure in [(axes[0], ma), (axes[1], mb)]:
                    meas_label = MEASURES[measure]['label']
                    cat, n_bands, sorted_dists = self._isochrone_cat(
                        grid, name, self.distances, measure)
                    iso_handles = self._plot_isochrone_ax(
                        ax, grid, cat, n_bands, sorted_dists)
                    if self.boundary is not None:
                        self.boundary.boundary.plot(
                            ax=ax, color='black', linewidth=1.0)
                    dest_handle = self.overlay_destinations(ax, grid.crs, name)
                    add_basemap(ax, grid.crs)
                    add_scalebar(ax)
                    all_handles = iso_handles + ([dest_handle] if dest_handle else [])
                    ax.legend(handles=all_handles, loc='lower right',
                              fontsize=7.5, framealpha=0.9)
                    ax.set_axis_off()
                    ax.set_title(meas_label, fontsize=11)
                    pfx = f'pop_pct_access_cycle_{MEASURES[measure]["infix"]}'
                    dist_stats = []
                    for d in sorted_dists:
                        rv = region.get(f'{pfx}{name}_{d}m')
                        if rv is not None:
                            dist_stats.append(f'{d / 1000:g} km: {rv:.1f}%')
                    if dist_stats:
                        caption_stats.append(
                            meas_label + ': ' + '; '.join(dist_stats))
                alt = ' (alternative contrast)' if ci else ''
                fig.suptitle(
                    f'{self.r.name}: {label} — isochrone access bands{alt}',
                    fontsize=12)
                fig.tight_layout()
                region_note = (' — region: ' + ' | '.join(caption_stats)
                               if caption_stats else '')
                imgs += img_tag(
                    fig,
                    f'{self.r.name}: {label} — isochrone bands (colour = minimum'
                    ' distance with ≥ 50 % sample-point access; left:'
                    f' {MEASURES[ma]["label"].lower()}, right:'
                    f' {MEASURES[mb]["label"].lower()};'
                    f' 100 m population grid){region_note}.')
        contrast_desc = '; then, below it, '.join(
            f'<b>{MEASURES[ma]["label"]}</b> (left) vs'
            f' <b>{MEASURES[mb]["label"]}</b> (right)'
            for ma, mb in contrasts
        )
        html = (
            '<h2>6. Spatial distribution of accessibility (population grid)</h2>'
            '<p class="formlink">Supports form questions <b>1.1</b> and <b>1.2</b>:'
            ' review whether the spatial pattern of cycling access looks plausible'
            ' for neighbourhoods you know. Each pair of maps shows all configured'
            ' distance bands as a single isochrone: the colour of each grid cell is'
            ' the <em>closest</em> configured distance at which the majority'
            ' (≥ 50 %) of the cell\'s sample points have access. For each indicator'
            f' the configured measure contrasts are shown in turn: {contrast_desc}.'
            ' Destination markers are overlaid'
            ' where applicable. Region-wide population percentages appear in each'
            ' figure caption.</p>'
            + imgs
        )
        self.parts.append(html)

    # ------------------------------------------------------------- ward table
    def custom_area_summary(self):
        """Population-weighted cycling indicators for configured custom areas.

        The standard pipeline aggregates its walkability indicator list to custom
        areas; cycling columns are aggregated here from the grid so validation can
        use official local geographies (e.g. wards).
        """
        aggs = self.r.config.get('custom_aggregations') or {}
        grid_table = self.r.config['grid_summary']
        if not aggs or grid_table not in self.tables:
            return
        all_grid_cols = [
            c
            for c in self.r.get_df(
                'SELECT column_name FROM information_schema.columns '
                f"WHERE table_name = '{grid_table}'",
            )['column_name']
            if c.startswith('pct_access_cycle_')
        ]
        if not all_grid_cols:
            return
        # Sort by canonical indicator order → distance ascending → measure
        # (strictest first), so each indicator's measure columns sit adjacent
        cols = sorted(all_grid_cols, key=_pct_col_sort_key)
        grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, pop_est, {", ".join(chr(34) + c + chr(34) for c in cols)}, geom '
            f'FROM {grid_table}',
        )
        # Build two-row column header once (shared across all aggregation geographies)
        def _col_info(c):
            mkey, stem = split_measure_col(c, 'pct_access_cycle_')
            parts = stem.rsplit('_', 1)
            if len(parts) == 2 and parts[1].endswith('m') and parts[1][:-1].isdigit():
                return parts[0], int(parts[1][:-1]), mkey
            return stem, 0, mkey
        col_infos = [_col_info(c) for c in cols]
        head1_parts, head2_parts = [], []
        prev_iname, span, pending_label = None, 0, ''
        for iname, d, mkey in col_infos:
            if iname != prev_iname:
                if prev_iname is not None:
                    head1_parts.append(f'<th colspan="{span}">{pending_label}</th>')
                pending_label = DEST_LABELS.get(iname, iname)
                span, prev_iname = 1, iname
            else:
                span += 1
            d_label = f'{d // 1000:g}&nbsp;km' if d >= 1000 else f'{d}&nbsp;m'
            head2_parts.append(f'<th>{MEASURES[mkey]["short"]} {d_label}</th>')
        if prev_iname is not None:
            head1_parts.append(f'<th colspan="{span}">{pending_label}</th>')
        head1 = ''.join(head1_parts)
        head2 = ''.join(head2_parts)
        # Sort areas by composite strict safe access at the largest distance (fallback: first col)
        sort_col = next(
            (c for c in reversed(cols)
             if 'all_strict' in c and c.startswith('pct_access_cycle_safe_')),
            cols[0],
        )
        for agg, spec in aggs.items():
            # the aggregation loader lowercases table names (agg_{name.lower()})
            table = f'agg_{agg.replace(" ", "_").lower()}'
            if table not in self.tables:
                self.missing.append(f'{table} (custom aggregation: {agg})')
                continue
            # resolve configured column names case-insensitively (OGR launders
            # imported identifiers to lowercase)
            actual = self.r.get_df(
                'SELECT column_name FROM information_schema.columns '
                f"WHERE table_name = '{table}'",
            )['column_name'].tolist()
            lower = {c.lower(): c for c in actual}
            name_col = lower.get(
                str(spec.get('keep_columns', '')).split(',')[0].strip().lower(), '',
            )
            id_col = lower.get(
                str(spec.get('id', 'ogc_fid')).lower(), 'ogc_fid',
            )
            areas = get_gdf_generic(
                self.r,
                f'SELECT "{id_col}"{", " + chr(34) + name_col + chr(34) if name_col else ""}, geom '
                f'FROM {table}',
            )
            joined = gpd.sjoin(
                grid, areas, how='inner', predicate='intersects',
            )
            weighted = []
            for key, sub in joined.groupby(id_col):
                w = sub['pop_est'].fillna(0)
                row = {'id': key}
                if name_col:
                    row['name'] = sub[name_col].iloc[0]
                row['pop_est'] = w.sum()
                for c in cols:
                    vals = sub[c]
                    mask = vals.notna() & (w > 0)
                    row[c] = (
                        (vals[mask] * w[mask]).sum() / w[mask].sum()
                        if w[mask].sum() > 0
                        else np.nan
                    )
                weighted.append(row)
            wdf = pd.DataFrame(weighted).sort_values(sort_col, ascending=False)
            body = ''
            for _, row in wdf.iterrows():
                name_cell = row.get('name', row['id'])
                cells = f'<td>{name_cell}</td><td>{row["pop_est"]:,.0f}</td>'
                for c in cols:
                    v = row[c]
                    if pd.isna(v):
                        cells += '<td>—</td>'
                    else:
                        style = _batlow_cell_bg(float(v), 'pct')
                        cells += f'<td style="{style}">{v:.1f}%</td>'
                body += f'<tr>{cells}</tr>'
            area_label = agg[:-1] if agg.endswith('s') else agg
            present_measures = [
                k for k in MEASURE_ORDER if any(m == k for _, _, m in col_infos)
            ]
            measure_legend = '; '.join(
                f'<b>{MEASURES[k]["short"]}</b> = {MEASURES[k]["label"].lower()}'
                for k in present_measures
            )
            html = f"""
            <h2>7. Accessibility by local reporting geography: {agg}</h2>
            <p class="formlink">Supports question <b>1.3 (output communication)</b>:
            population-weighted cycling access summarised to the
            configured official areas ({agg}, {len(wdf)} areas), responding to
            previous-round feedback that sub-city summaries aid interpretation.</p>
            <p class="note">Measure columns: {measure_legend}.</p>
            <div style="overflow-x:auto">
            <table><thead>
            <tr><th rowspan="2">{area_label}</th>
            <th rowspan="2">Population (grid est.)</th>{head1}</tr>
            <tr>{head2}</tr>
            </thead><tbody>{body}</tbody></table></div>
            """
            self.parts.append(html)

    # ------------------------------------------------------------ case studies
    def case_studies(self, n_cases=4):
        if 'sample_points_cycling' not in self.tables or 'edges' not in self.tables:
            self.missing.append('sample_points_cycling (case studies)')
            return
        import glob

        gpkgs = glob.glob(
            f'/home/ghsci/r_output/{self.r.name}/*_cyclingIndicators.gpkg')
        # where prior R results exist, feature clusters of notable change instead
        if gpkgs and self._difference_case_studies(gpkgs[0], n_cases):
            return
        self._generic_case_studies(n_cases)

    def _difference_case_studies(self, r_gpkg, n_cases):
        """Destination-specific case studies of R-vs-GHSCI change, shown as dual
        maps so both sample-point sets are seen in full (not overplotted).

        For each comparable destination type, previous-R sample points are matched
        to the nearest GHSCI point (within 12 m) for the strict low-stress measure
        at 2 km, to locate where access changed.  The densest local windows of
        change (one gained, one lost where available) are each rendered twice,
        side by side: previous-R points on the left and GHSCI points on the right,
        both coloured by that analysis's own access result.  Contiguous change
        clusters within a window (DBSCAN, re-run on the window's points only, so a
        region-wide chain of change cannot drag a box off the map) are enclosed in
        numbered boxes clamped to the window and drawn on both panels, with a
        summary table beneath the map.  Returns False (fall back to generic) if no
        comparable data are available."""
        from sklearn.cluster import DBSCAN
        from shapely.geometry import Point
        r = self.r
        srid = self.srid
        spc = {
            c for c in r.get_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sample_points_cycling'")['column_name']
        }
        # (label, R access col, GHSCI access col, GHSCI distance col, overlay sql)
        DESTS = [
            ('Fresh food market', 'fresh_food_market_safe_2km',
             'sp_cycle_safe_access_fresh_food_market_2000m',
             'sp_cycle_safe_nearest_node_fresh_food_market',
             "SELECT geom FROM destinations WHERE dest_name = 'fresh_food_market'"),
            ('Public open space (any)', 'public_open_space_safe_2km',
             'sp_cycle_safe_access_public_open_space_any_2000m',
             'sp_cycle_safe_nearest_node_public_open_space_any',
             'SELECT geom FROM aos_public_any_nodes_30m_line'),
            ('Public transport', 'pt_any_safe_2km',
             'sp_cycle_safe_access_pt_any_2000m',
             'sp_cycle_safe_nearest_node_pt_any',
             "SELECT geom FROM destinations WHERE dest_name = 'pt_any'"),
        ]
        try:
            R = gpd.read_file(r_gpkg, layer='sample_points_accessibility')
        except Exception:
            return False
        DESTS = [d for d in DESTS if d[1] in R.columns and d[2] in spc]
        if not DESTS:
            return False
        r_cols = [d[1] for d in DESTS]
        R = R[r_cols + ['geometry']].to_crs(epsg=srid)
        for c in r_cols:
            R[c] = pd.to_numeric(R[c], errors='coerce').fillna(0).astype(int)
        g_acc = [d[2] for d in DESTS]
        g_dist = [d[3] for d in DESTS if d[3] in spc]
        gsel = [f'"{c}"' for c in g_acc + g_dist]
        G = get_gdf_generic(
            r, f'SELECT {", ".join(gsel)}, geom FROM sample_points_cycling',
        ).rename_geometry('geometry')
        for c in g_acc:
            G[c] = pd.to_numeric(G[c], errors='coerce').fillna(0).astype(int)
        # matched pairs classify change; the panels plot the full point sets
        m = gpd.sjoin_nearest(
            R, G[g_acc + g_dist + ['geometry']], how='inner', max_distance=12)
        if not len(m):
            return False
        self._DBSCAN = DBSCAN
        self._Point = Point
        self._edges = get_gdf_generic(
            r, 'SELECT highway, lvl_traf_stress, length, geom FROM edges')
        blocks = ''
        for label, r_col, g_col, g_dist_col, overlay_sql in DESTS:
            blocks += self._dest_case_block(
                m, R, G, label, r_col, g_col, g_dist_col, overlay_sql)
        if not blocks:
            return False
        self.parts.append(
            '<h2>8. Case studies of notable change vs the previous (R) results</h2>'
            '<p class="formlink">Supports questions <b>1.1/1.2</b> comments. For each'
            ' destination type, previous-R sample points are matched to the nearest'
            ' GHSCI point (within 12 m) for the strict low-stress measure at 2 km, to'
            ' locate where access changed. Each case shows the same local window twice:'
            ' the previous R sample points on the left and the GHSCI sample points on'
            ' the right, each coloured by that analysis&rsquo;s own result'
            f' (<span style="color:{PT_ACCESS}">blue = access</span>,'
            f' <span style="color:{PT_NO_ACCESS}">grey = no access</span>), so both'
            ' point sets are seen in full rather than one plotted over the other.'
            ' Numbered black boxes mark contiguous clusters of change, drawn at the'
            ' same location on both panels for comparison; the table beneath each map'
            ' characterises them.</p>' + blocks)
        return True

    def _dest_case_block(self, m, R, G, label, r_col, g_col, g_dist_col,
                         overlay_sql):
        cat = np.where((m[r_col] == 1) & (m[g_col] == 0), 'lost',
                       np.where((m[r_col] == 0) & (m[g_col] == 1), 'gained', 'same'))
        mm = m.assign(cat=cat)
        n_gain = int((cat == 'gained').sum())
        n_lost = int((cat == 'lost').sum())
        intro = (f'<h3>{label}</h3><p class="note">Comparing the strict low-stress 2 km'
                 f' measure point-by-point: <b>{n_gain:,}</b> matched locations gained'
                 f' access under GHSCI and <b>{n_lost:,}</b> lost it.</p>')
        if n_gain + n_lost < 5:
            return intro + '<p class="note">Too little change to feature case studies.</p>'
        # one window for the densest gained area, one for the densest lost area
        centres = []
        for direction in ['gained', 'lost']:
            centres += self._pick_windows(
                mm[mm.cat == direction], existing=centres)
        if not centres:
            return intro + ('<p class="note">No sufficiently concentrated change to'
                            ' feature.</p>')
        try:
            overlay = get_gdf_generic(self.r, overlay_sql).to_crs(mm.crs)
        except Exception:
            overlay = None
        content = ''
        for wc in centres:
            content += self._case_window(
                mm, R, G, wc, label, r_col, g_col, g_dist_col, overlay)
        return intro + content

    def _pick_windows(self, changed, existing=(), max_windows=1, half=900,
                      min_sep=1600, min_points=5):
        """Centres of the densest case-study windows of changed points.

        Points are binned on a coarse grid (bin size = the window half-width) and
        the fullest bins become window candidates, keeping *min_sep* from any
        already-chosen centre.  Density binning stays meaningful at any scale of
        change — from a handful of altered points to region-wide change, where a
        cluster mean can land between the changed areas (or outside the network
        entirely)."""
        if not len(changed):
            return []
        x = changed.geometry.x.to_numpy()
        y = changed.geometry.y.to_numpy()
        bins = pd.DataFrame({
            'bx': np.floor(x / half).astype(int),
            'by': np.floor(y / half).astype(int),
        })
        counts = bins.groupby(['bx', 'by']).size().sort_values(ascending=False)
        centres = list(existing)
        chosen = []
        for (i, j), n in counts.items():
            if n < min_points or len(chosen) >= max_windows:
                break
            sel = ((bins['bx'] == i) & (bins['by'] == j)).to_numpy()
            c = self._Point(x[sel].mean(), y[sel].mean())
            if all(c.distance(cc) > min_sep for cc in centres):
                centres.append(c)
                chosen.append(c)
        return chosen

    def _window_boxes(self, mm, xlim, ylim, max_boxes=6, pad=60):
        """Numbered change-cluster boxes for one case-study window.

        DBSCAN is re-run on the changed points *inside the window only* (dense
        region-wide change chains into one huge cluster whose bounds would dwarf
        the window), and box bounds are padded then clamped to sit within the
        window, so no box or label can extend beyond the mapped extent."""
        win = mm.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        boxes = []
        for direction in ['gained', 'lost']:
            sub = win[win.cat == direction]
            if len(sub) < 5:
                continue
            xy = np.c_[sub.geometry.x.to_numpy(), sub.geometry.y.to_numpy()]
            labels = self._DBSCAN(eps=70, min_samples=5).fit_predict(xy)
            for cl, s in sub.assign(_cl=labels).groupby('_cl'):
                if cl == -1:
                    continue
                x0, y0, x1, y1 = s.total_bounds
                bounds = (
                    max(x0 - pad, xlim[0] + 20), max(y0 - pad, ylim[0] + 20),
                    min(x1 + pad, xlim[1] - 20), min(y1 + pad, ylim[1] - 20),
                )
                boxes.append((direction, s, bounds))
        boxes.sort(key=lambda t: len(t[1]), reverse=True)
        return boxes[:max_boxes]

    def _case_window(self, mm, R, G, wc, label, r_col, g_col, g_dist_col,
                     overlay):
        half = 900
        xlim = (wc.x - half, wc.x + half)
        ylim = (wc.y - half, wc.y + half)
        boxes = self._window_boxes(mm, xlim, ylim)
        e = self._edges.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        ov = None
        if overlay is not None:
            ov = overlay.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        R_win = R.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        G_win = G.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        for ax, pts, acc_col, tag in [
            (axes[0], R_win, r_col, 'Previous (R) sample points'),
            (axes[1], G_win, g_col, 'GHSCI sample points (this analysis)'),
        ]:
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            for lts, c in LTS_COLORS.items():
                seg = e[e['lvl_traf_stress'] == lts]
                if len(seg):
                    seg.plot(ax=ax, color=c, linewidth=1.0, alpha=0.85, zorder=3)
            acc = pd.to_numeric(pts[acc_col], errors='coerce').fillna(0).astype(int)
            for target, color in [(0, PT_NO_ACCESS), (1, PT_ACCESS)]:
                s = pts[acc == target]
                if len(s):
                    s.plot(ax=ax, color=color, markersize=10, alpha=0.75,
                           zorder=4, edgecolor='white', linewidth=0.2)
            if ov is not None and len(ov):
                ov.plot(ax=ax, color='black', marker='^', markersize=26, zorder=6,
                        edgecolor='white', linewidth=0.4)
            for bi, (direction, sub, bounds) in enumerate(boxes, 1):
                x0, y0, x1, y1 = bounds
                ax.add_patch(mpatches.Rectangle(
                    (x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor='black',
                    linewidth=2.2, zorder=8))
                ax.text(x0 + 15, y1 - 15, f' {bi} ', fontsize=11,
                        fontweight='bold', color='white', ha='left', va='top',
                        zorder=9, clip_on=True,
                        bbox=dict(boxstyle='square,pad=0.15', facecolor='black',
                                  edgecolor='none'))
            add_basemap(ax, mm.crs)
            add_scalebar(ax)
            ax.set_axis_off()
            ax.set_title(tag, fontsize=11)
        legend = [
            mlines.Line2D([], [], color=c, lw=2, label=f'LTS {k}')
            for k, c in LTS_COLORS.items()
        ] + [
            mlines.Line2D([], [], color=PT_ACCESS, marker='o', ls='',
                          markeredgecolor='white', label='point with access'),
            mlines.Line2D([], [], color=PT_NO_ACCESS, marker='o', ls='',
                          markeredgecolor='white', label='point without access'),
            mlines.Line2D([], [], color='black', marker='^', ls='',
                          markeredgecolor='white', label=label.lower()),
            mpatches.Patch(fill=False, edgecolor='black',
                           label='change cluster (see table)'),
        ]
        axes[1].legend(handles=legend, loc='upper right', fontsize=7.5,
                       framealpha=0.9)
        fig.suptitle(
            f'{label}: local change in strict low-stress access at 2 km '
            '— previous R (left) vs GHSCI (right)', fontsize=12)
        # keep the suptitle clear of the panel titles
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        summaries = [
            self._box_summary(bi, direction, sub, R_win, G_win, r_col, g_col,
                              g_dist_col, bounds)
            for bi, (direction, sub, bounds) in enumerate(boxes, 1)
        ]
        img = img_tag(
            fig, f'{label}: a local window of change, shown for both analyses '
            '(left: previous R points; right: GHSCI points; blue = access, '
            'grey = no access). Numbered boxes are contiguous clusters of '
            'change, summarised in the table below.')
        return img + self._summary_table(summaries, label)

    def _box_summary(self, num, direction, cluster, R_win, G_win, r_col, g_col,
                     g_dist_col, bounds):
        x0, y0, x1, y1 = bounds
        r_in = R_win.cx[x0:x1, y0:y1]
        g_in = G_win.cx[x0:x1, y0:y1]
        r_pct = (
            100 * pd.to_numeric(r_in[r_col], errors='coerce').fillna(0).mean()
            if len(r_in) else np.nan
        )
        g_pct = (
            100 * pd.to_numeric(g_in[g_col], errors='coerce').fillna(0).mean()
            if len(g_in) else np.nan
        )
        e_in = self._edges.cx[x0:x1, y0:y1]
        tags, lts12 = '—', np.nan
        if len(e_in) and e_in['length'].sum() > 0:
            hw = (e_in['highway'].fillna('unknown').astype(str)
                  .str.replace(r"[\[\]']", '', regex=True)
                  .str.split(',').str[0].str.strip())
            top = e_in.assign(h=hw).groupby('h')['length'].sum().sort_values(
                ascending=False).head(3)
            tags = ', '.join(top.index)
            lts12 = (100 * e_in[e_in['lvl_traf_stress'].isin([1, 2])]['length'].sum()
                     / e_in['length'].sum())
        dist = 'n/a'
        if g_dist_col in g_in.columns and len(g_in):
            acc = pd.to_numeric(g_in[g_col], errors='coerce').fillna(0).astype(int)
            dd = pd.to_numeric(
                g_in.loc[acc == 1, g_dist_col], errors='coerce').dropna()
            if len(dd) >= 3:
                dist = (f'{dd.median():.0f} m '
                        f'(IQR {dd.quantile(.25):.0f}–{dd.quantile(.75):.0f})')
        return dict(num=num, direction=direction, n=len(cluster), r_pct=r_pct,
                    g_pct=g_pct, tags=tags, lts12=lts12, dist=dist)

    def _summary_table(self, summaries, label):
        if not summaries:
            return ('<p class="note">No contiguous change clusters within this'
                    ' window (the change here is dispersed).</p>')
        rows = ''
        for s in summaries:
            lts = '—' if pd.isna(s['lts12']) else f"{s['lts12']:.0f}%"
            rp = '—' if pd.isna(s['r_pct']) else f"{s['r_pct']:.0f}%"
            gp = '—' if pd.isna(s['g_pct']) else f"{s['g_pct']:.0f}%"
            rows += (
                f'<tr><td><b>{s["num"]}</b></td><td>{s["direction"]}</td>'
                f'<td>{s["n"]}</td><td>{rp} &rarr; {gp}</td>'
                f'<td>{s["tags"]} (low-stress {lts})</td><td>{s["dist"]}</td></tr>')
        return (
            '<table><thead><tr><th>Box</th><th>Change</th><th>Changed points</th>'
            f'<th>{label} access in box (R &rarr; GHSCI)</th>'
            '<th>Network (predominant types; low-stress share)</th>'
            f'<th>Distance to {label.lower()} (GHSCI, reachable)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')

    def _generic_case_studies(self, n_cases=4, d=2000):
        r = self.r
        col = f'sp_cycle_safe_access_all_lenient_{d}m'
        cols = set(
            r.get_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sample_points_cycling'",
            )['column_name'],
        )
        if col not in cols:
            candidates = sorted(c for c in cols if c.startswith('sp_cycle_safe_access_'))
            if not candidates:
                return
            col = candidates[0]
        pts = get_gdf_generic(
            r, f'SELECT point_id, "{col}" AS access, geom FROM sample_points_cycling',
        ).rename_geometry('geometry')
        edges = get_gdf_generic(
            r, 'SELECT lvl_traf_stress, geom FROM edges',
        )
        dests = None
        if 'destinations' in self.tables:
            dests = get_gdf_generic(r, 'SELECT dest_name, geom FROM destinations')

        chosen = []
        for target in [1, 0]:
            cand = pts[pts['access'].fillna(0).astype(int) == target].reset_index(drop=True)
            if not len(cand):
                continue
            sel = [cand.iloc[0]]
            while len(sel) < max(1, n_cases // 2) and len(cand) > len(sel):
                dist = cand.geometry.apply(
                    lambda g: min(g.distance(s.geometry) for s in sel),
                )
                sel.append(cand.loc[dist.idxmax()])
            chosen += [(target, s) for s in sel]

        win = d + 500
        imgs = ''
        legend = [
            mlines.Line2D([], [], color=c, lw=2, label=f'LTS {k}')
            for k, c in LTS_COLORS.items()
        ] + [
            mlines.Line2D([], [], color='yellow', marker='*', ls='',
                          markeredgecolor='k', markersize=14, label='case-study point'),
            mlines.Line2D([], [], color='#d7191c', marker='o', ls='', label='fresh food market'),
            mlines.Line2D([], [], color='#2b83ba', marker='o', ls='', label='public transport stop'),
        ]
        for i, (target, pt) in enumerate(chosen, 1):
            x, y = pt.geometry.x, pt.geometry.y
            xlim, ylim = (x - win, x + win), (y - win, y + win)
            fig, ax = plt.subplots(figsize=(10, 10))
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            e = edges.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
            for lts, c in LTS_COLORS.items():
                seg = e[e['lvl_traf_stress'] == lts]
                if len(seg):
                    seg.plot(ax=ax, color=c, linewidth=1.0, alpha=0.9, zorder=3)
            if dests is not None:
                dd = dests.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
                for name, color in [('fresh_food_market', '#d7191c'), ('pt_any', '#2b83ba')]:
                    sub = dd[dd['dest_name'] == name]
                    if len(sub):
                        sub.plot(ax=ax, color=color, markersize=26, zorder=4,
                                 edgecolor='white', linewidth=0.5)
            gpd.GeoSeries([pt.geometry.buffer(d)], crs=pts.crs).boundary.plot(
                ax=ax, color='white', linestyle='--', linewidth=1.5, zorder=5,
            )
            ax.scatter([x], [y], s=340, marker='*', color='yellow',
                       edgecolor='black', linewidth=1.2, zorder=6)
            add_basemap(ax, pts.crs)
            add_scalebar(ax)
            status = 'HAS' if target else 'does NOT have'
            title = (
                f'Case {i}: point {int(pt.point_id)} {status} low-stress access '
                f'to all (lenient) destination categories within {d / 1000:g} km'
            )
            ax.set_title(title, fontsize=11)
            ax.set_axis_off()
            ax.legend(handles=legend, loc='upper right', fontsize=8, framealpha=0.9)
            imgs += img_tag(fig, title)
        if imgs:
            html = (
                '<h2>8. Case studies</h2>'
                '<p class="formlink">Supports questions <b>1.1/1.2</b> comments:'
                ' spatially spread examples with and without composite low-stress'
                f' access at {d / 1000:g} km, showing the LTS-classified network,'
                ' nearby destinations and the distance ring, so reviewers can'
                ' judge concrete locations rather than only the overall pattern.</p>'
                + imgs
            )
            self.parts.append(html)

    # ------------------------------------------------------------ form guide
    def form_guide(self):
        provenance = self.validation_cfg.get('provenance') or []
        limitations = self.validation_cfg.get('limitations') or []
        actions = self.validation_cfg.get('actions') or []
        prov_html = (
            '<h3>Local inputs used</h3><ul>'
            + ''.join(f'<li>{x}</li>' for x in provenance)
            + '</ul>'
            if provenance
            else ''
        )
        lim_html = (
            '<h3>Known limitations for this first pass</h3><ul>'
            + ''.join(f'<li>{x}</li>' for x in limitations)
            + '</ul>'
            if limitations
            else ''
        )
        actions_html = (
            '<h3>Actions implemented in response to feedback</h3><ul>'
            + ''.join(f'<li>{x}</li>' for x in actions)
            + '</ul>'
            if actions
            else ''
        )
        html = f"""
        <h2>9. Completing the validation form</h2>
        {prov_html}
        {lim_html}
        {actions_html}
        <table><thead><tr><th>CyclingValidation.xlsx item</th><th>Use</th></tr></thead>
        <tbody>
        <tr><td><b>1.1</b> Accessibility within 2 km (Yes/No/Unsure + comments)</td>
        <td>Sections 4, 6 and 8 (2 km results, maps and cases); section 5 vs previous results</td></tr>
        <tr><td><b>1.2</b> Accessibility within 5 km</td>
        <td>Sections 4 and 6 (5 km columns and maps); section 5 vs previous results (where applicable)</td></tr>
        <tr><td><b>1.3</b> Output communication</td>
        <td>Sections 4 and 7 (optional, custom aggregation to local areas) — is % of population (city and ward level) the right
        headline? What else would help local policy audiences?</td></tr>
        <tr><td><b>1.4</b> Destination distribution</td>
        <td>Section 3 — flag missing/over-included destinations; note whether the
        strict or lenient variant better matches local reality.</td></tr>
        </tbody></table>
        """
        self.parts.append(html)

    def survey_feedback_section(self):
        fb = self.validation_cfg.get('survey_feedback') or []
        if not fb:
            return
        items = ''.join(f'<li>{x}</li>' for x in fb)
        html = (
            '<h2>10. Collaborator working group survey feedback</h2>'
            '<p class="note">Summarised responses from the GOHSC Cycling Indicators Working Group'
            ' indicator development survey (2026)</p>'
            f'<ul>{items}</ul>'
        )
        self.parts.append(html)

    # ---------------------------------------------------------------- render
    def render(self, out_path):
        body = '\n'.join(self.parts)
        missing = (
            '<p class="note">Sections not yet available (analysis incomplete): '
            + ', '.join(sorted(set(self.missing)))
            + '</p>'
            if self.missing
            else ''
        )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<title>{self.r.name} cycling validation report</title>
<style>
 body {{ font-family: Arial, Helvetica, sans-serif; margin: 2em auto; max-width: 1100px;
        color: #222; line-height: 1.45; }}
 h1 {{ font-size: 1.6em; }} h2 {{ margin-top: 1.6em; border-bottom: 2px solid #ddd; }}
 table {{ border-collapse: collapse; margin: 0.8em 0; }}
 th, td {{ border: 1px solid #ccc; padding: 4px 10px; text-align: left; font-size: 0.92em; }}
 th {{ background: #f2f2f2; }}
 table.meta td {{ border: none; padding: 2px 12px 2px 0; }}
 table.meta td:first-child {{ font-weight: bold; }}
 figure {{ margin: 1em 0; }} figcaption {{ font-size: 0.85em; color: #555; }}
 .note {{ color: #555; font-size: 0.9em; }}
 .formlink {{ background: #eef6ee; border-left: 4px solid #1a9850; padding: 6px 10px; }}
 .cat-hdr td {{ background: #e8e8e8; font-style: italic; font-size: 0.88em; padding: 3px 10px; }}
</style></head><body>
{body}
{missing}
<p class="note">Generated by _validation_report.py (GHSCI cycling workflow).</p>
</body></html>"""
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Wrote {out_path}')
        # # companion PDF for easy sharing (fpdf2)
        # try:
        #     from _html2pdf import html_to_pdf

        #     pdf_path = out_path.rsplit('.', 1)[0] + '.pdf'
        #     pages = html_to_pdf(html, pdf_path)
        #     print(f'Wrote {pdf_path} ({pages} pages)')
        # except Exception as e:
        #     print(f'  (PDF generation skipped: {e})')


def main():
    codename = sys.argv[1] if len(sys.argv) > 1 else None
    r = ghsci.Region(codename)
    report = Report(r)
    report.header()
    report.enhancements()
    report.lts_network()
    report.destinations()
    report.city_summary()
    report.r_comparison()
    report.grid_maps()
    report.custom_area_summary()
    report.case_studies()
    report.survey_feedback_section()
    report.form_guide()
    out = f'{r.config["region_dir"]}/{r.codename}_cycling_validation_report.html'
    report.render(out)


if __name__ == '__main__':
    main()
