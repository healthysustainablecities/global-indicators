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

LTS_COLORS = {1: '#1a9850', 2: '#a6d96a', 3: '#fdae61', 4: '#d7191c'}
LTS_LABELS = {
    1: 'LTS 1 — lowest stress (suitable for all ages and abilities)',
    2: 'LTS 2 — low stress (most adults)',
    3: 'LTS 3 — moderate stress (confident cyclists)',
    4: 'LTS 4 — high stress (strong and fearless)',
}
ACCESS_CMAP = 'RdYlGn'
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
    """Satellite basemap; degrade gracefully when offline."""
    try:
        cx.add_basemap(
            ax, crs=crs, source=cx.providers.Esri.WorldImagery,
            attribution_size=5,
        )
    except Exception as e:
        print(f'  (basemap unavailable: {e})')


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
                    wanted.append(
                        (col, f'{DEST_LABELS[name]} — low-stress route, {d / 1000:g} km'),
                    )
        if not wanted:
            self.missing.append('cycling columns on grid summary (run _12_aggregation)')
            return
        grid = get_gdf_generic(
            self.r,
            f'SELECT grid_id, pop_est, {", ".join(chr(34) + c + chr(34) for c, _ in wanted)}, geom '
            f'FROM {grid_table}',
        )
        imgs = ''
        for col, label in wanted:
            fig, ax = plt.subplots(figsize=(11, 11))
            grid.plot(
                column=col, cmap=ACCESS_CMAP, vmin=0, vmax=100, ax=ax,
                legend=True, legend_kwds={'shrink': 0.6, 'label': '% of sample points with access'},
                missing_kwds={'color': '#00000000'},
                alpha=0.85, linewidth=0,
            )
            if self.boundary is not None:
                self.boundary.boundary.plot(ax=ax, color='black', linewidth=1.0)
            add_basemap(ax, grid.crs)
            add_scalebar(ax)
            ax.set_axis_off()
            ax.set_title(f'{self.r.name}: {label}')
            imgs += img_tag(fig, f'{self.r.name}: {label} (100 m population grid)')
        html = (
            '<h2>5. Spatial distribution of accessibility (population grid)</h2>'
            '<p class="formlink">Supports form questions <b>1.1</b> and <b>1.2</b>:'
            ' review whether the spatial pattern of low-stress cycling access looks'
            ' plausible for neighbourhoods you know. The composite maps require'
            ' <i>all</i> destination categories to be reachable (the strictest view);'
            ' the corrected large public open space and complete activity centre maps'
            ' show two of the new post-validation indicators. Any single-destination'
            ' map can be produced the same way.</p>'
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
            <h2>6. Accessibility by local reporting geography: {agg}</h2>
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
                '<h2>7. Case studies</h2>'
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
        <h2>8. Completing the validation form</h2>
        {prov_html}
        {lim_html}
        <table><thead><tr><th>CyclingValidation.xlsx item</th><th>Use</th></tr></thead>
        <tbody>
        <tr><td><b>1.1</b> Accessibility within 2 km (Yes/No/Unsure + comments)</td>
        <td>Sections 4, 5 and 7 (2 km results, maps and cases)</td></tr>
        <tr><td><b>1.2</b> Accessibility within 5 km</td>
        <td>Sections 4 and 5 (5 km columns and maps)</td></tr>
        <tr><td><b>1.3</b> Output communication</td>
        <td>Sections 4 and 6 — is % of population (city and ward level) the right
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


def main():
    codename = sys.argv[1] if len(sys.argv) > 1 else None
    r = ghsci.Region(codename)
    report = Report(r)
    report.header()
    report.enhancements()
    report.lts_network()
    report.destinations()
    report.city_summary()
    report.grid_maps()
    report.custom_area_summary()
    report.case_studies()
    report.form_guide()
    out = f'{r.config["region_dir"]}/{r.codename}_cycling_validation_report.html'
    report.render(out)


if __name__ == '__main__':
    main()
