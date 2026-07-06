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
from batlow import batlow_map  # noqa: E402  (Crameri Scientific Colour Maps)

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
        boundary_notes = (r.config.get('study_region_boundary') or {}).get(
            'notes', '',
        ) or ''
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
        <p class="note">This report accompanies the project validation form
        (<i>CyclingValidation.xlsx</i>). Each section below indicates the form
        question(s) it supports. Where this is the region's first analysis, the
        validation is a first pass rather than a re-validation of earlier results.</p>
        """
        self.parts.append(html)

    # ---------------------------------------------------- enhancements (static)
    def enhancements(self):
        html = """
        <h2>1. About this analysis: the integrated GHSCI cycling workflow</h2>
        <p>Cycling indicators are now calculated within the open-source
        <a href="https://healthysustainablecities.github.io/">Global Healthy and
        Sustainable City Indicators (GHSCI)</a> software as an optional analysis
        step, configured per city alongside the established walkability workflow.
        The first round of results shared for validation was produced with a
        separate research prototype; feedback from collaborators in that round
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
        category is evaluated both strictly (e.g. fresh food markets; large public
        open space; frequent public transport) and leniently (e.g. including
        convenience stores; any public open space; any public transport stop),
        responding to feedback that a single definition can both miss locally
        important destinations and over-include marginal ones.</li>
        <li><b>Walk-the-bike (dismount) handling.</b> Homes and destinations that
        connect to the street network via footpaths are reachable by dismounting
        and walking short sections (with the walked distance penalised
        accordingly), removing an artefact in the earlier results in which such
        locations could be reported as unreachable.</li>
        <li><b>Local-access streets.</b> Streets restricted to local motor traffic
        (e.g. <i>motor_vehicle=destination</i>) are treated as low-stress local
        streets, improving results in cities with traffic-restricted zones.</li>
        <li><b>Refined stress and crossing costs.</b> Intersection crossing
        penalties are applied directionally, and the level of traffic stress
        classification follows the published rule set with locally supplied
        speeds, so results are transparent and auditable per street segment.</li>
        </ul>
        <p><b>New indicators added following the first validation round.</b> In
        addition to the binary "within X&nbsp;km" access measures reviewed
        previously, this report also presents:</p>
        <ul>
        <li><b>Distance-to-nearest metrics.</b> The network distance to the nearest
        destination of each type (by both the low-stress and danger-weighted
        measures), reported alongside the binary indicators — so a neighbourhood
        that just misses a threshold is distinguishable from one that is far from
        any destination, and improvements can be tracked continuously rather than
        only as threshold crossings.</li>
        <li><b>Corrected public open space access.</b> Public open space is now
        reached at the <i>network entry points</i> of each open space (nodes within
        30&nbsp;m of the space), rather than a single centroid, with a strict
        variant (large public open space, &gt;1.5&nbsp;ha) and a lenient variant
        (any public open space). This addresses previous-round feedback that parks
        were being over- or under-counted depending on how a single access point was
        chosen.</li>
        <li><b>Access to activity centres.</b> An activity centre is a location whose
        short pedestrian walk-shed co-locates at least one destination of every
        category (food, public open space, public transport) — i.e. somewhere a
        resident can meet several everyday needs in one trip. Safe-cycling access is
        measured to the nearest <i>local</i> centre (everyday, lenient cluster) and
        <i>complete</i> centre (higher-amenity, strict cluster), giving a
        destination-bundle indicator rather than one isolated facility at a time.</li>
        </ul>

        <h3>How to read these indicators (in plain language)</h3>
        <p>Each indicator asks a simple question about a place: <b>starting from
        here, can a person on a bicycle reach a given kind of destination within a
        set distance, using streets that feel safe to ride?</b> "Distance" is measured
        along the street network (not straight-line), at 2&nbsp;km and 5&nbsp;km (with
        500&nbsp;m and 1&nbsp;km also reported where configured) — roughly a short and a
        longer everyday bike trip.</p>

        <p><b>Level of Traffic Stress (LTS).</b> Every street is graded 1–4 for how
        stressful it is to cycle on, from LTS&nbsp;1 (calm streets and separated paths,
        suitable for children and cautious riders) to LTS&nbsp;4 (busy, fast roads that
        only confident riders will use). The grade comes from the road type, speed limit,
        traffic and any cycling facility. This is the backbone of every accessibility
        result and the subject of the map in section&nbsp;2.</p>

        <p><b>The two access measures — and how to interpret them.</b> For each
        destination we report two figures:</p>
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
        help most.</li>
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
        stats = (
            edges.assign(km=edges['length'] / 1000)
            .groupby('lvl_traf_stress')
            .agg(edges=('ogc_fid', 'count'), km=('km', 'sum'))
        )
        rows = ''.join(
            f'<tr><td style="color:{LTS_COLORS[i]};font-weight:bold">{LTS_LABELS[i]}</td>'
            f'<td>{int(stats.loc[i, "edges"]) if i in stats.index else 0:,}</td>'
            f'<td>{stats.loc[i, "km"] if i in stats.index else 0:,.0f}</td>'
            f'<td>{(100 * stats.loc[i, "km"] / stats["km"].sum()) if i in stats.index else 0:.1f}%</td></tr>'
            for i in [1, 2, 3, 4]
        )
        dismount_km = edges.loc[edges['foot_dismount'].fillna(False), 'length'].sum() / 1000
        table = f"""
        <table><thead><tr><th>Level of Traffic Stress</th><th>Edges</th>
        <th>Length (km)</th><th>Share of network</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p>{n:,} network edges in total; {dismount_km:,.0f} km are walkable-only
        paths (footway/pedestrian/path where cycling is not permitted), routable by
        dismounting and walking the bicycle at a penalised cost.</p>
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
            + img_tag(fig, f'{r.name}: network coloured by LTS class (higher-stress roads drawn on top)')
        )
        self.parts.append(html)

    # ------------------------------------------------------------ destinations
    def destinations(self):
        if not self.has('destinations'):
            return
        r = self.r
        counts = r.get_df(
            'SELECT dest_name, count(*) AS n FROM destinations GROUP BY dest_name ORDER BY n DESC',
        )
        rows = ''.join(
            f'<tr><td>{d.dest_name}</td><td>{int(d.n):,}</td></tr>'
            for d in counts.itertuples()
        )
        pos_note = ''
        for layer, label in [
            ('aos_public_large_nodes_30m_line', 'large public open space entry points'),
            ('aos_public_any_nodes_30m_line', 'any public open space entry points'),
        ]:
            if layer in self.tables:
                n = self.r.get_df(f'SELECT count(*) AS n FROM {layer}')['n'][0]
                pos_note += f'<li>{label}: {int(n):,}</li>'

        dests = get_gdf_generic(
            r, 'SELECT dest_name, geom FROM destinations',
        )
        fig, ax = plt.subplots(figsize=(12, 12))
        palette = {
            'fresh_food_market': ('#d7191c', 14),
            'convenience': ('#fdae61', 5),
            'pt_any': ('#2b83ba', 6),
        }
        if self.boundary is not None:
            self.boundary.boundary.plot(ax=ax, color='white', linewidth=1.2, zorder=6)
        handles = []
        for name, (color, size) in palette.items():
            sub = dests[dests['dest_name'] == name]
            if len(sub):
                sub.plot(ax=ax, color=color, markersize=size, alpha=0.8, zorder=4)
                handles.append(
                    mlines.Line2D(
                        [], [], color=color, marker='o', ls='',
                        label=f'{name} ({len(sub):,})',
                    ),
                )
        others = dests[~dests['dest_name'].isin(palette)]
        if len(others):
            others.plot(ax=ax, color='#984ea3', markersize=4, alpha=0.5, zorder=3)
            handles.append(
                mlines.Line2D(
                    [], [], color='#984ea3', marker='o', ls='',
                    label=f'other ({len(others):,})',
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
            f'<table><thead><tr><th>Destination (OSM-derived)</th><th>Count</th></tr></thead><tbody>{rows}</tbody></table>'
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

        def fmt(v):
            return '—' if pd.isna(v) else f'{v:.1f}%'

        names = sorted(
            {
                c.replace('pop_pct_access_cycle_safe_', '')
                .replace('pop_pct_access_cycle_', '')
                .rsplit('_', 1)[0]
                for c in cols
            },
        )
        rows = ''
        for name in names:
            label = DEST_LABELS.get(name, name)
            cells = ''
            for d in self.distances:
                for measure in ['safe', '']:
                    col = (
                        f'pop_pct_access_cycle_safe_{name}_{d}m'
                        if measure == 'safe'
                        else f'pop_pct_access_cycle_{name}_{d}m'
                    )
                    if col in city.index and not pd.isna(city[col]):
                        val = float(city[col])
                        style = _batlow_cell_bg(val, 'pct')
                        cells += f'<td style="{style}">{val:.1f}%</td>'
                    else:
                        cells += '<td>—</td>'
            rows += f'<tr><td>{label}</td>{cells}</tr>'
        header_cells = ''.join(
            f'<th>{d / 1000:g} km<br/>low-stress route</th><th>{d / 1000:g} km<br/>danger-weighted</th>'
            for d in self.distances
        )
        dist_table = self._distance_table()
        html = f"""
        <h2>4. City-level results: population access and distance to destinations</h2>
        <p class="formlink">Supports form questions <b>1.1 and 1.2</b> (is the
        distribution of accessibility within {' and '.join(f'{d / 1000:g} km' for d in self.distances)}
        as expected?) and <b>1.3</b> (percent-of-population is the headline
        communication measure, as favoured by most collaborators in the previous
        round).</p>
        <p>Estimated share of the region's population with access to each
        destination type within the network distance thresholds, by the strict
        low-stress-route measure and the graduated danger-weighted measure.</p>
        <table><thead><tr><th>Destination</th>{header_cells}</tr></thead>
        <tbody>{rows}</tbody></table>
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

        def fmt(v):
            return '—' if pd.isna(v) else (
                f'{v / 1000:.2f} km' if v >= 1000 else f'{v:.0f} m'
            )

        names = sorted(
            {
                c.replace('pop_avg_cycle_dist_safe_', '')
                .replace('pop_avg_cycle_dist_', '')
                for c in dcols
            },
        )
        rows = ''
        for name in names:
            safe_col = f'pop_avg_cycle_dist_safe_{name}'
            dw_col = f'pop_avg_cycle_dist_{name}'
            cells = ''
            for col in (safe_col, dw_col):
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
            '<p><b>Average distance to the nearest destination</b> (new'
            ' post-validation metric): population-weighted mean network distance'
            ' among residents able to reach each destination type, by the'
            ' low-stress and danger-weighted routes.</p>'
            '<table><thead><tr><th>Destination</th>'
            '<th>Low-stress route</th><th>Danger-weighted route</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )

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
        # R strict-safe binary column template -> (GHSCI spec name, label)
        mapping = [
            ('fresh_food_market_safe_{}km', 'fresh_food_market', 'Fresh food market'),
            ('public_open_space_safe_{}km', 'public_open_space_large',
             'Large public open space'),
            ('pt_any_safe_{}km', 'pt_any', 'Public transport (any stop)'),
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
                cells += f'<td>{pct(R, tmpl.format(d))}</td>'
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
            ('public_open_space_safe',  'public_open_space_large', 'Large public open space'),
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
                g_grid, g_name, g_comp, measure='safe')
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
    def _isochrone_cat(self, grid, name, distances, measure='safe'):
        """Assign each grid cell to an isochrone band.

        The band is the *minimum* configured distance at which ≥ 50 % of the
        cell's sample points have access (majority threshold).  Band 0 = closest
        configured distance (best); band n_bands − 1 = no access within any
        configured distance.

        Returns ``(cat, n_bands, sorted_dists)``.
        """
        sorted_dists = sorted(distances)
        n_bands = len(sorted_dists) + 1
        prefix = (
            f'pct_access_cycle_safe_{name}_'
            if measure == 'safe'
            else f'pct_access_cycle_{name}_'
        )
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
        # Include every configured destination/indicator for which at least one
        # safe-access distance column exists in the grid summary table.
        wanted_names = [
            name for name in DEST_LABELS
            if any(
                f'pct_access_cycle_safe_{name}_{d}m' in cols
                for d in self.distances
            )
        ]
        if not wanted_names:
            self.missing.append('cycling columns on grid summary (run _12_aggregation)')
            return
        # Collect all needed columns (both measures, all distances) in one query
        all_grid_cols = [
            c
            for name in wanted_names
            for d in self.distances
            for c in (
                f'pct_access_cycle_safe_{name}_{d}m',
                f'pct_access_cycle_{name}_{d}m',
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
            fig, axes = plt.subplots(1, 2, figsize=(18, 9))
            caption_stats = []
            for ax, measure, meas_label in [
                (axes[0], 'safe', 'Low-stress route'),
                (axes[1], '',     'Danger-weighted'),
            ]:
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
                pfx = ('pop_pct_access_cycle_safe_' if measure == 'safe'
                       else 'pop_pct_access_cycle_')
                dist_stats = []
                for d in sorted_dists:
                    rv = region.get(f'{pfx}{name}_{d}m')
                    if rv is not None:
                        dist_stats.append(f'{d / 1000:g} km: {rv:.1f}%')
                if dist_stats:
                    caption_stats.append(
                        meas_label + ': ' + '; '.join(dist_stats))
            fig.suptitle(
                f'{self.r.name}: {label} — isochrone access bands',
                fontsize=12)
            fig.tight_layout()
            region_note = (' — region: ' + ' | '.join(caption_stats)
                           if caption_stats else '')
            imgs += img_tag(
                fig,
                f'{self.r.name}: {label} — isochrone bands (colour = minimum'
                ' distance with ≥ 50 % sample-point access; left: low-stress'
                f' route, right: danger-weighted; 100 m population grid){region_note}.')
        html = (
            '<h2>6. Spatial distribution of accessibility (population grid)</h2>'
            '<p class="formlink">Supports form questions <b>1.1</b> and <b>1.2</b>:'
            ' review whether the spatial pattern of cycling access looks plausible'
            ' for neighbourhoods you know. Each pair of maps shows all configured'
            ' distance bands as a single isochrone: the colour of each grid cell is'
            ' the <em>closest</em> configured distance at which the majority'
            ' (≥ 50 %) of the cell\'s sample points have access. Left panel:'
            ' strict low-stress (LTS 1–2) route; right panel: danger-weighted'
            ' (LTS 3–4 allowed but penalised). Destination markers are overlaid'
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
        cols = [
            c
            for c in self.r.get_df(
                'SELECT column_name FROM information_schema.columns '
                f"WHERE table_name = '{grid_table}'",
            )['column_name']
            if c.startswith('pct_access_cycle_safe_all_')
        ]
        if not cols:
            return
        grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, pop_est, {", ".join(chr(34) + c + chr(34) for c in cols)}, geom '
            f'FROM {grid_table}',
        )
        for agg, spec in aggs.items():
            table = f'agg_{agg}'
            if table not in self.tables:
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
            wdf = pd.DataFrame(weighted).sort_values(
                cols[0], ascending=False,
            )
            head = ''.join(
                f'<th>{c.replace("pct_access_cycle_safe_", "% access (safe): ").replace("_", " ")}</th>'
                for c in cols
            )
            body = ''.join(
                '<tr><td>{}</td><td>{:,.0f}</td>{}</tr>'.format(
                    row.get('name', row['id']),
                    row['pop_est'],
                    ''.join(
                        f'<td>{"—" if pd.isna(row[c]) else f"{row[c]:.1f}%"}</td>'
                        for c in cols
                    ),
                )
                for _, row in wdf.iterrows()
            )
            html = f"""
            <h2>7. Accessibility by local reporting geography: {agg}</h2>
            <p class="formlink">Supports question <b>1.3 (output communication)</b>:
            population-weighted low-stress cycling access summarised to the
            configured official areas ({agg}, {len(wdf)} areas), responding to
            previous-round feedback that sub-city summaries aid interpretation.</p>
            <table><thead><tr><th>{agg[:-1] if agg.endswith('s') else agg}</th>
            <th>Population (grid est.)</th>{head}</tr></thead>
            <tbody>{body}</tbody></table>
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
        """Destination-specific case studies of R-vs-GHSCI change.  For each comparable
        destination type, previous-R sample points are matched to the nearest GHSCI point
        (within 12 m) for the strict low-stress measure at 2 km; contiguous clusters that
        gained or lost access are found (DBSCAN) and a couple of local windows featured.
        Every gained/lost cluster in a window is enclosed in a numbered box, with a
        summary table beneath that map.  Returns False (fall back to generic) if no
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
            ('Large public open space', 'public_open_space_safe_2km',
             'sp_cycle_safe_access_public_open_space_large_2000m',
             'sp_cycle_safe_nearest_node_public_open_space_large',
             'SELECT geom FROM aos_public_large_nodes_30m_line'),
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
        m = gpd.sjoin_nearest(
            R, G[g_acc + g_dist + ['geometry']], how='inner', max_distance=12)
        m = m.dropna(subset=[g_acc[0]])
        if not len(m):
            return False
        self._DBSCAN = DBSCAN
        self._Point = Point
        self._edges = get_gdf_generic(
            r, 'SELECT highway, lvl_traf_stress, length, geom FROM edges')
        blocks = ''
        for label, r_col, g_col, g_dist_col, overlay_sql in DESTS:
            blocks += self._dest_case_block(
                m, label, r_col, g_col, g_dist_col, overlay_sql)
        if not blocks:
            return False
        self.parts.append(
            '<h2>8. Case studies of notable change vs the previous (R) results</h2>'
            '<p class="formlink">Supports questions <b>1.1/1.2</b> comments. For each'
            ' destination type, previous-R sample points are matched to the nearest GHSCI'
            ' point (within 12 m) for the strict low-stress measure at 2 km. Each map'
            ' below features a local area where access changed; every contiguous cluster'
            ' of change within it is enclosed in a numbered box (<span style="color:'
            '#08519c">blue = gained</span> under GHSCI, <span style="color:#c026a6">'
            'magenta = lost</span>), and the table beneath the map characterises each'
            ' box.</p>' + blocks)
        return True
    def _dest_case_block(self, m, label, r_col, g_col, g_dist_col, overlay_sql):
        cat = np.where((m[r_col] == 1) & (m[g_col] == 0), 'lost',
                       np.where((m[r_col] == 0) & (m[g_col] == 1), 'gained', 'same'))
        mm = m.assign(cat=cat, r_acc=m[r_col].astype(int), g_acc=m[g_col].astype(int))
        n_gain = int((cat == 'gained').sum())
        n_lost = int((cat == 'lost').sum())
        intro = (f'<h3>{label}</h3><p class="note">Comparing the strict low-stress 2 km'
                 f' measure point-by-point: <b>{n_gain:,}</b> locations gained access under'
                 f' GHSCI and <b>{n_lost:,}</b> lost it.</p>')
        if n_gain + n_lost < 5:
            return intro + '<p class="note">Too little change to feature clusters.</p>'
        clusters = []
        for direction in ['gained', 'lost']:
            cand = mm[mm.cat == direction]
            if len(cand) < 5:
                continue
            xy = np.c_[cand.geometry.x.to_numpy(), cand.geometry.y.to_numpy()]
            cand = cand.assign(_cl=self._DBSCAN(eps=70, min_samples=5).fit_predict(xy))
            for cl, sub in cand.groupby('_cl'):
                if cl == -1:
                    continue
                c = self._Point(sub.geometry.x.mean(), sub.geometry.y.mean())
                clusters.append((direction, sub, c, len(sub)))
        if not clusters:
            return intro + '<p class="note">No sufficiently contiguous clusters.</p>'
        clusters.sort(key=lambda t: t[3], reverse=True)
        centres = []
        for _, _, c, _sz in clusters:
            if all(c.distance(cc) > 1600 for cc in centres):
                centres.append(c)
            if len(centres) >= 2:
                break
        try:
            overlay = get_gdf_generic(self.r, overlay_sql).to_crs(mm.crs)
        except Exception:
            overlay = None
        content = ''
        for wc in centres:
            content += self._case_window(
                mm, clusters, wc, label, g_dist_col, overlay)
        return intro + content
    def _case_window(self, mm, clusters, wc, label, g_dist_col, overlay):
        half = 900
        xlim = (wc.x - half, wc.x + half)
        ylim = (wc.y - half, wc.y + half)
        in_win = [t for t in clusters
                  if xlim[0] <= t[2].x <= xlim[1] and ylim[0] <= t[2].y <= ylim[1]]
        in_win = sorted(in_win, key=lambda t: t[3], reverse=True)[:6]
        CAT = {'gained': '#08519c', 'lost': '#c026a6'}
        fig, ax = plt.subplots(figsize=(9.5, 9.5))
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        e = self._edges.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        for lts, c in LTS_COLORS.items():
            seg = e[e['lvl_traf_stress'] == lts]
            if len(seg):
                seg.plot(ax=ax, color=c, linewidth=1.0, alpha=0.85, zorder=3)
        win = mm.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
        s = win[win.cat == 'same']
        if len(s):
            s.plot(ax=ax, color='#bdbdbd', markersize=6, alpha=0.4, zorder=4)
        for direction in ['gained', 'lost']:
            s = win[win.cat == direction]
            if len(s):
                s.plot(ax=ax, color=CAT[direction], markersize=18, alpha=0.85,
                       zorder=5, edgecolor='white', linewidth=0.3)
        if overlay is not None:
            ov = overlay.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
            if len(ov):
                ov.plot(ax=ax, color='black', marker='^', markersize=20, zorder=6,
                        edgecolor='white', linewidth=0.4)
        summaries = []
        for bi, (direction, sub, c, sz) in enumerate(in_win, 1):
            x0, y0, x1, y1 = sub.total_bounds
            pad = 60
            x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
            ax.add_patch(mpatches.Rectangle(
                (x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor=CAT[direction],
                linewidth=2.5, zorder=8))
            ax.text(x0, y1, f' {bi} ', fontsize=12, fontweight='bold', color='white',
                    ha='left', va='bottom', zorder=9,
                    bbox=dict(boxstyle='square,pad=0.15', facecolor=CAT[direction],
                              edgecolor='none'))
            summaries.append(self._box_summary(
                bi, direction, sub, mm, g_dist_col, (x0, y0, x1, y1)))
        add_basemap(ax, mm.crs)
        add_scalebar(ax)
        ax.set_axis_off()
        ax.set_title(f'{label}: local change in low-stress access at 2 km', fontsize=10.5)
        legend = [
            mlines.Line2D([], [], color=c, lw=2, label=f'LTS {k}')
            for k, c in LTS_COLORS.items()
        ] + [
            mlines.Line2D([], [], color=CAT['gained'], marker='o', ls='',
                          markeredgecolor='white', label='gained (GHSCI)'),
            mlines.Line2D([], [], color=CAT['lost'], marker='o', ls='',
                          markeredgecolor='white', label='lost (R only)'),
            mlines.Line2D([], [], color='black', marker='^', ls='',
                          markeredgecolor='white', label=label.lower()),
        ]
        ax.legend(handles=legend, loc='upper right', fontsize=7.5, framealpha=0.9)
        img = img_tag(
            fig, f'{label}: a local area of change; numbered boxes are clusters that '
            'gained (blue) or lost (magenta) access, summarised in the table below.')
        return img + self._summary_table(summaries, label)
    def _box_summary(self, num, direction, cluster, mm, g_dist_col, bounds):
        x0, y0, x1, y1 = bounds
        m_in = mm.cx[x0:x1, y0:y1]
        r_pct = 100 * m_in['r_acc'].mean() if len(m_in) else np.nan
        g_pct = 100 * m_in['g_acc'].mean() if len(m_in) else np.nan
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
        if g_dist_col in m_in.columns:
            dd = pd.to_numeric(
                m_in.loc[m_in['g_acc'] == 1, g_dist_col], errors='coerce').dropna()
            if len(dd) >= 3:
                dist = (f'{dd.median():.0f} m '
                        f'(IQR {dd.quantile(.25):.0f}–{dd.quantile(.75):.0f})')
        return dict(num=num, direction=direction, n=len(cluster), r_pct=r_pct,
                    g_pct=g_pct, tags=tags, lts12=lts12, dist=dist)
    def _summary_table(self, summaries, label):
        if not summaries:
            return ''
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
            '<table><thead><tr><th>Box</th><th>Change</th><th>Focal points</th>'
            f'<th>{label} access in box (R &rarr; GHSCI)</th>'
            '<th>Network (predominant types; low-stress share)</th>'
            f'<th>Distance to {label.lower()} (GHSCI, reachable)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')

    def _difference_summary_table(self, summaries):
        rows = ''
        for s in summaries:
            change = 'gained' if s['direction'] == 'GHSCI only' else 'lost'
            lts = '—' if pd.isna(s['lts12']) else f"{s['lts12']:.0f}%"
            rp = '—' if pd.isna(s['r_pct']) else f"{s['r_pct']:.0f}%"
            gp = '—' if pd.isna(s['g_pct']) else f"{s['g_pct']:.0f}%"
            rows += (
                f'<tr><td><b>{s["num"]}</b></td><td>{change}</td><td>{s["n"]}</td>'
                f'<td>{rp} &rarr; {gp}</td><td>{s["tags"]} (low-stress {lts})</td>'
                f'<td>{s["dist"]}</td></tr>')
        return (
            '<p><b>Focal cluster summaries</b> (numbers match the boxes on the maps).'
            ' "Access in box" is the share of sample points inside the box with the'
            ' composite low-stress access, before (R) and after (GHSCI). "Network" gives'
            ' the predominant street types in the box and the share of network length'
            ' that is low-stress (LTS&nbsp;1–2). "Distance" is the median (and IQR)'
            ' low-stress network distance to reach all everyday categories, among'
            ' reachable points.</p>'
            '<table><thead><tr><th>Box</th><th>Change</th><th>Focal points</th>'
            '<th>Access in box (R &rarr; GHSCI)</th>'
            '<th>Network (predominant types; low-stress share)</th>'
            '<th>Distance to all categories (GHSCI)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>')

    def _generic_case_studies(self, n_cases=4):
        r = self.r
        d = self.distances[0]
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
        html = f"""
        <h2>9. Completing the validation form</h2>
        {prov_html}
        {lim_html}
        <table><thead><tr><th>CyclingValidation.xlsx item</th><th>Use</th></tr></thead>
        <tbody>
        <tr><td><b>1.1</b> Accessibility within 2 km (Yes/No/Unsure + comments)</td>
        <td>Sections 4, 6 and 8 (2 km results, maps and cases); section 5 vs previous results</td></tr>
        <tr><td><b>1.2</b> Accessibility within 5 km</td>
        <td>Sections 4 and 6 (5 km columns and maps); section 5 vs previous results</td></tr>
        <tr><td><b>1.3</b> Output communication</td>
        <td>Sections 4 and 7 — is % of population (city and ward level) the right
        headline? What else would help local policy audiences?</td></tr>
        <tr><td><b>1.4</b> Destination distribution</td>
        <td>Section 3 — flag missing/over-included destinations; note whether the
        strict or lenient variant better matches local reality.</td></tr>
        <tr><td><b>Part 2</b> LTS validation (MapRoulette)</td>
        <td>Section 2 — a MapRoulette challenge sampling street segments for local
        LTS review can be generated on request, as in the previous round.</td></tr>
        </tbody></table>
        """
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
</style></head><body>
{body}
{missing}
<p class="note">Generated by _validation_report.py (GHSCI cycling workflow).</p>
</body></html>"""
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Wrote {out_path}')
        # companion PDF for easy sharing (fpdf2)
        try:
            from _html2pdf import html_to_pdf

            pdf_path = out_path.rsplit('.', 1)[0] + '.pdf'
            pages = html_to_pdf(html, pdf_path)
            print(f'Wrote {pdf_path} ({pages} pages)')
        except Exception as e:
            print(f'  (PDF generation skipped: {e})')


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
    report.form_guide()
    out = f'{r.config["region_dir"]}/{r.codename}_cycling_validation_report.html'
    report.render(out)


if __name__ == '__main__':
    main()
