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
                    cells += f'<td>{fmt(city[col]) if col in city.index else "—"}</td>'
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
            safe = fmt(city[safe_col]) if safe_col in city.index else '—'
            dw = fmt(city[dw_col]) if dw_col in city.index else '—'
            rows += (
                f'<tr><td>{DEST_LABELS.get(name, name)}</td>'
                f'<td>{safe}</td><td>{dw}</td></tr>'
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
        """Side-by-side previous-R vs GHSCI grid maps for the comparable strict-safe
        indicators at 2 km (each on its own population grid; shared colour scale)."""
        try:
            r_grid = gpd.read_file(gpkg, layer='grid_accessibility').to_crs(epsg=self.srid)
        except Exception as e:
            print(f'  (R comparison maps unavailable: {e})')
            return ''
        grid_table = self.r.config['grid_summary']
        gcols = set(self.r.get_df(
            'SELECT column_name FROM information_schema.columns '
            f"WHERE table_name = '{grid_table}'")['column_name'])
        pairs = [
            ('all_safe_access_2km',
             'pct_access_cycle_safe_all_strict_2000m', 'All categories'),
            ('fresh_food_market_safe_2km',
             'pct_access_cycle_safe_fresh_food_market_2000m', 'Fresh food market'),
            ('public_open_space_safe_2km',
             'pct_access_cycle_safe_public_open_space_large_2000m',
             'Large public open space'),
            ('pt_any_safe_2km',
             'pct_access_cycle_safe_pt_any_2000m', 'Public transport'),
        ]
        pairs = [(rc, gc, lbl) for rc, gc, lbl in pairs
                 if rc in r_grid.columns and gc in gcols]
        if not pairs:
            return ''
        gsel = sorted({gc for _, gc, _ in pairs})
        g_grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, {", ".join(chr(34) + c + chr(34) for c in gsel)}, geom '
            f'FROM {grid_table}')
        imgs = ''
        for rc, gc, lbl in pairs:
            r_grid['_rv'] = pd.to_numeric(r_grid[rc], errors='coerce') * 100
            fig, axes = plt.subplots(1, 2, figsize=(15, 7.5))
            for ax, gdf, vcol, tag in [
                (axes[0], r_grid, '_rv', 'Previous (R)'),
                (axes[1], g_grid, gc, 'GHSCI (this analysis)'),
            ]:
                gdf.plot(
                    column=vcol, cmap=ACCESS_CMAP, vmin=0, vmax=100, ax=ax,
                    legend=True, legend_kwds={'shrink': 0.5, 'label': '% access'},
                    missing_kwds={'color': '#00000000'}, alpha=0.7, linewidth=0)
                if self.boundary is not None:
                    self.boundary.boundary.plot(ax=ax, color='black', linewidth=0.8)
                add_basemap(ax, gdf.crs)
                add_scalebar(ax)
                ax.set_axis_off()
                ax.set_title(tag, fontsize=11)
            fig.suptitle(f'{self.r.name}: {lbl} — low-stress route, 2 km', fontsize=12)
            fig.tight_layout()
            imgs += img_tag(
                fig,
                f'{self.r.name}: {lbl} at 2 km — previous R (left) vs GHSCI (right), '
                'same colour scale.')
        return (
            '<p class="note">Side-by-side maps (each on its own sample grid, shared'
            ' colour scale) show where the two analyses agree and differ spatially.</p>'
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
        # composite "all categories" maps, plus the headline new/corrected
        # single-category indicators (corrected large public open space; complete
        # activity centre) so their spatial pattern can be reviewed directly
        wanted = []
        for d in self.distances:
            for name in [
                'all_lenient', 'all_strict',
                'public_open_space_large', 'activity_centre_complete',
            ]:
                col = f'pct_access_cycle_safe_{name}_{d}m'
                if col in cols:
                    wanted.append((col, name, d, DEST_LABELS[name]))
        if not wanted:
            self.missing.append('cycling columns on grid summary (run _12_aggregation)')
            return
        grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, pop_est, {", ".join(chr(34) + c + chr(34) for c, _, _, _ in wanted)}, geom '
            f'FROM {grid_table}',
        )
        region = self._region_pct()
        imgs = ''
        for col, name, d, label in wanted:
            fig, ax = plt.subplots(figsize=(11, 11))
            grid.plot(
                column=col, cmap=ACCESS_CMAP, vmin=0, vmax=100, ax=ax,
                legend=True, legend_kwds={'shrink': 0.6, 'label': '% of sample points with access'},
                missing_kwds={'color': '#00000000'},
                alpha=0.7, linewidth=0,
            )
            if self.boundary is not None:
                self.boundary.boundary.plot(ax=ax, color='black', linewidth=1.0)
            handle = self.overlay_destinations(ax, grid.crs, name)
            add_basemap(ax, grid.crs)
            add_scalebar(ax)
            if handle is not None:
                ax.legend(handles=[handle], loc='upper right', fontsize=8, framealpha=0.9)
            ax.set_axis_off()
            regval = region.get(f'pop_pct_access_cycle_safe_{name}_{d}m')
            reg = f' — region overall: {regval:.1f}% of population' if regval is not None else ''
            title = f'{self.r.name}: {label} — low-stress route, {d / 1000:g} km'
            ax.set_title(title)
            imgs += img_tag(
                fig,
                f'{title}.{reg}. Coloured cells: share of sample points with access; '
                'markers: the reference destinations measured (100 m population grid).')
        html = (
            '<h2>6. Spatial distribution of accessibility (population grid)</h2>'
            '<p class="formlink">Supports form questions <b>1.1</b> and <b>1.2</b>:'
            ' review whether the spatial pattern of low-stress cycling access looks'
            ' plausible for neighbourhoods you know. Each map overlays the reference'
            ' destinations it measures access to (except the composite "all categories"'
            ' maps, which require every category at once), and its caption gives the'
            ' region-wide population estimate. The corrected large public open space and'
            ' complete activity centre maps show two of the new post-validation indicators.</p>'
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
        """Case studies of notable R-vs-GHSCI difference: spatially spread clusters of
        sample-point locations whose composite all-categories low-stress access at 2 km
        changed between the analyses (gained under GHSCI, or lost).  R points are matched
        to the nearest GHSCI point within 12 m.  Returns False (fall back to generic) if
        the comparison cannot be built."""
        r = self.r
        srid = self.srid
        rcol, gcol = 'all_safe_access_2km', 'sp_cycle_safe_access_all_strict_2000m'
        gcols = {
            c for c in r.get_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'sample_points_cycling'")['column_name']
        }
        if gcol not in gcols:
            return False
        try:
            R = gpd.read_file(r_gpkg, layer='sample_points_accessibility')
        except Exception:
            return False
        if rcol not in R.columns:
            return False
        R = R[[rcol, 'geometry']].to_crs(epsg=srid)
        R['r_acc'] = pd.to_numeric(R[rcol], errors='coerce').fillna(0).astype(int)
        # GHSCI points: composite access + per-category safe distances (for box summaries)
        self._dist_cols = [
            c for c in (
                'sp_cycle_safe_nearest_node_fresh_food_market',
                'sp_cycle_safe_nearest_node_public_open_space_large',
                'sp_cycle_safe_nearest_node_pt_any')
            if c in gcols]
        gsel = [f'"{gcol}" AS g_acc'] + [f'"{c}"' for c in self._dist_cols]
        G = get_gdf_generic(
            r, f'SELECT {", ".join(gsel)}, geom FROM sample_points_cycling',
        ).rename_geometry('geometry')
        G['g_acc'] = pd.to_numeric(G['g_acc'], errors='coerce').fillna(0).astype(int)
        self._G = G
        m = gpd.sjoin_nearest(
            R[['r_acc', 'geometry']], G[['g_acc', 'geometry']],
            how='inner', max_distance=12)
        if 'g_acc' not in m.columns:
            return False
        m = m.dropna(subset=['g_acc'])
        if not len(m):
            return False
        m['g_acc'] = m['g_acc'].astype(int)
        m = m.assign(cat=np.where(
            (m.r_acc == 1) & (m.g_acc == 0), 'R only',
            np.where((m.r_acc == 0) & (m.g_acc == 1), 'GHSCI only',
                     np.where((m.r_acc == 1) & (m.g_acc == 1), 'both', 'neither'))))
        n_ronly = int((m.cat == 'R only').sum())
        n_gonly = int((m.cat == 'GHSCI only').sum())
        # DBSCAN the difference points of each direction; feature the largest, spatially
        # spread clusters (the most notable, contiguous areas of change)
        from sklearn.cluster import DBSCAN

        cases = []
        per = max(1, n_cases // 2)
        for direction in ['GHSCI only', 'R only']:
            cand = m[m.cat == direction]
            if len(cand) < 5:
                continue
            xy = np.c_[cand.geometry.x.to_numpy(), cand.geometry.y.to_numpy()]
            cand = cand.assign(_cl=DBSCAN(eps=70, min_samples=5).fit_predict(xy))
            groups = sorted(
                ((cl, sub) for cl, sub in cand.groupby('_cl') if cl != -1),
                key=lambda t: len(t[1]), reverse=True)
            from shapely.geometry import Point

            picked, centroids = [], []
            for _, sub in groups:
                c = Point(sub.geometry.x.mean(), sub.geometry.y.mean())
                if all(c.distance(pc) > 900 for pc in centroids):
                    picked.append(sub)
                    centroids.append(c)
                if len(picked) >= per:
                    break
            cases += [(direction, sub) for sub in picked]
        if not cases:
            return False
        edges = get_gdf_generic(
            r, 'SELECT highway, lvl_traf_stress, length, geom FROM edges')
        dests = (
            get_gdf_generic(r, 'SELECT dest_name, geom FROM destinations')
            if 'destinations' in self.tables else None)
        CAT = {'GHSCI only': '#08519c', 'R only': '#f032e6',
               'both': '#969696', 'neither': '#dedede'}
        legend = [
            mlines.Line2D([], [], color=c, lw=2, label=f'LTS {k}')
            for k, c in LTS_COLORS.items()
        ] + [
            mlines.Line2D([], [], color=CAT['GHSCI only'], marker='o', ls='',
                          markeredgecolor='white', label='access: GHSCI only (gained)'),
            mlines.Line2D([], [], color=CAT['R only'], marker='o', ls='',
                          markeredgecolor='white', label='access: R only (lost)'),
            mlines.Line2D([], [], color=CAT['both'], marker='o', ls='', label='both'),
            mlines.Line2D([], [], color='black', marker='^', ls='',
                          markeredgecolor='white', label='fresh food / PT'),
        ]
        imgs = ''
        summaries = []
        for i, (direction, cluster) in enumerate(cases, 1):
            cx0, cy0, cx1, cy1 = cluster.total_bounds
            ccx, ccy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
            half = max(700, max(cx1 - cx0, cy1 - cy0) / 2 + 450)
            xlim, ylim = (ccx - half, ccx + half), (ccy - half, ccy + half)
            fig, ax = plt.subplots(figsize=(10, 10))
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            e = edges.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
            for lts, c in LTS_COLORS.items():
                seg = e[e['lvl_traf_stress'] == lts]
                if len(seg):
                    seg.plot(ax=ax, color=c, linewidth=1.0, alpha=0.85, zorder=3)
            mm = m.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
            for c in ['neither', 'both']:
                s = mm[mm.cat == c]
                if len(s):
                    s.plot(ax=ax, color=CAT[c], markersize=8, alpha=0.5, zorder=4)
            for c in ['GHSCI only', 'R only']:
                s = mm[mm.cat == c]
                if len(s):
                    s.plot(ax=ax, color=CAT[c], markersize=22, alpha=0.9, zorder=5,
                           edgecolor='white', linewidth=0.4)
            if dests is not None:
                dd = dests.cx[xlim[0]:xlim[1], ylim[0]:ylim[1]]
                sub = dd[dd['dest_name'].isin(['fresh_food_market', 'pt_any'])]
                if len(sub):
                    sub.plot(ax=ax, color='black', marker='^', markersize=24,
                             zorder=6, edgecolor='white', linewidth=0.5)
            # numbered box enclosing the focal cluster
            pad = 70
            bx0, by0, bx1, by1 = cx0 - pad, cy0 - pad, cx1 + pad, cy1 + pad
            ax.add_patch(mpatches.Rectangle(
                (bx0, by0), bx1 - bx0, by1 - by0, fill=False,
                edgecolor='black', linewidth=2.5, zorder=8))
            ax.text(bx0, by1, f' {i} ', fontsize=13, fontweight='bold', color='white',
                    ha='left', va='bottom', zorder=9,
                    bbox=dict(boxstyle='square,pad=0.15', facecolor='black',
                              edgecolor='none'))
            add_basemap(ax, m.crs)
            add_scalebar(ax)
            ax.set_axis_off()
            change = ('gained under GHSCI (was inaccessible under R)'
                      if direction == 'GHSCI only'
                      else 'lost under GHSCI (was accessible under R)')
            ax.set_title(
                f'Case {i}: focal cluster (box {i}) where all-categories low-stress '
                f'access at 2 km {change}', fontsize=10.5)
            ax.legend(handles=legend, loc='upper right', fontsize=7.5, framealpha=0.9)
            imgs += img_tag(
                fig, f'Case {i}: {change}. Box {i} encloses the focal cluster '
                '(summarised in the table below).')
            summaries.append(self._box_summary(
                i, direction, cluster, m, edges, bx0, by0, bx1, by1))
        html = (
            '<h2>8. Case studies of notable change vs the previous (R) results</h2>'
            '<p class="formlink">Supports questions <b>1.1/1.2</b> comments. Matching each'
            ' previous-R sample point to the nearest GHSCI point (within 12 m) for the'
            ' composite all-categories low-stress measure at 2 km: '
            f'<b>{n_gonly:,}</b> locations <b>gained</b> access under GHSCI and'
            f' <b>{n_ronly:,}</b> <b>lost</b> it. Each map below features one contiguous'
            ' cluster of change, enclosed in a numbered box; the table underneath'
            ' characterises each box (network make-up, access change and distance).</p>'
            + imgs + self._difference_summary_table(summaries)
        )
        self.parts.append(html)
        return True

    def _box_summary(self, num, direction, cluster, m, edges, bx0, by0, bx1, by1):
        """Characterise a focal-cluster box: sample-point access (R vs GHSCI), the
        predominant network tags and low-stress share, and the distribution of the
        low-stress distance needed to reach all categories."""
        from shapely.geometry import box as _box

        b = _box(bx0, by0, bx1, by1)
        m_in = m[m.geometry.within(b)]
        r_pct = 100 * m_in['r_acc'].mean() if len(m_in) else np.nan
        g_pct = 100 * m_in['g_acc'].mean() if len(m_in) else np.nan
        e_in = edges[edges.geometry.intersects(b)]
        tags, lts12 = '—', np.nan
        if len(e_in) and e_in['length'].sum() > 0:
            hw = (
                e_in['highway'].fillna('unknown').astype(str)
                .str.replace(r"[\[\]']", '', regex=True).str.split(',').str[0].str.strip())
            top = e_in.assign(h=hw).groupby('h')['length'].sum().sort_values(
                ascending=False).head(3)
            tags = ', '.join(top.index)
            lts12 = 100 * e_in[e_in['lvl_traf_stress'].isin([1, 2])]['length'].sum() \
                / e_in['length'].sum()
        dist = 'n/a (few reachable)'
        if self._dist_cols:
            g_in = self._G.cx[bx0:bx1, by0:by1]
            if len(g_in):
                dd = g_in[self._dist_cols].apply(pd.to_numeric, errors='coerce')
                binding = dd.max(axis=1).dropna()
                if len(binding) >= 3:
                    dist = (f'{binding.median():.0f} m '
                            f'(IQR {binding.quantile(.25):.0f}–{binding.quantile(.75):.0f})')
        return dict(num=num, direction=direction, n=len(cluster), r_pct=r_pct,
                    g_pct=g_pct, tags=tags, lts12=lts12, dist=dist)

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
