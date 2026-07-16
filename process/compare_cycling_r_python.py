"""
Compare the R cycling pipeline outputs against the native-GHSCI Python port.

The original R pipeline (``cyclingIndicators/``) and the Python port
(``_cycling_lts_network`` + ``_cycling_accessibility``) implement the same
manuscript methodology.  This utility quantifies how closely the Python results
reproduce the R results for a study region, producing a printed + Markdown report.

Three comparisons are made:

* **Sample-point access — city rates (distribution)** — each pipeline's overall
  access rate over *its own* sample points, per indicator, with the difference.
  This needs no ``point_id`` alignment, so it is valid even when a fresh Python run
  does not share sample points with an older R output (the usual case).  The
  indicator mapping adapts to the R-output vintage (older outputs tag transport
  ``pt_any`` → Python ``pt_any``; newer ``pt_20min_or_any`` → ``pt_frequent``) and
  the Python variant used is shown in the label.

* **Python-only indicators** — the access indicators the port produces that have no
  R counterpart (strict/lenient variants, activity centres, "all categories"
  composites, local-custom sets), documenting its broader scope.

* **Per-point agreement** (optional; skip with ``--distribution-only``) — joined on
  ``point_id``, the strongest comparison, but only meaningful when both runs share
  the same ``urban_sample_points``; otherwise it reports no matches.

* **Network Level of Traffic Stress** — compared *distributionally* (class shares by
  edge count and by length), because the R network is split into directed one-way
  edges (~2x) with identifiers that need not align.  An optional ``--spatial``
  per-edge LTS agreement is available when both networks are the same build.

The Python port is the newer, more comprehensive methodology, so differences from an
older R baseline are expected (and the point of the comparison is to confirm them).

Python outputs are read from the generated study-region GeoPackage when
``--python-gpkg`` is given, otherwise from PostGIS via ``ghsci.Region``.  The R
outputs are read from ``<City>_cyclingIndicators.gpkg``.

Usage::

    python compare_cycling_r_python.py <codename> \
        --r-gpkg  output/<City>/<City>_cyclingIndicators.gpkg \
        [--python-gpkg <region>_<buffer>m_buffer.gpkg] \
        [--distribution-only] [--spatial] [--out comparison.md]
"""

import argparse
import sys

import numpy as np
import pandas as pd

# R sample-point columns -> Python (strict-variant) columns, with a plain label.
# The Python pt column falls back to ``pt_any`` if ``pt_frequent`` is absent
# (region without a GTFS feed), mirroring the R ``pt_20min_or_any`` fallback.
DEFAULT_SP_MAPPING = [
    (
        'fresh_food_market_safe_2km',
        'sp_cycle_access_fresh_food_market_2000m',
        'Fresh food (market), 2 km',
    ),
    (
        'fresh_food_market_safe_5km',
        'sp_cycle_access_fresh_food_market_5000m',
        'Fresh food (market), 5 km',
    ),
    (
        'public_open_space_safe_2km',
        'sp_cycle_access_public_open_space_large_2000m',
        'Public open space (large), 2 km',
    ),
    (
        'public_open_space_safe_5km',
        'sp_cycle_access_public_open_space_large_5000m',
        'Public open space (large), 5 km',
    ),
    (
        'pt_20min_or_any_safe_2km',
        'sp_cycle_access_pt_frequent_2000m',
        'Public transport (frequent), 2 km',
    ),
    (
        'pt_20min_or_any_safe_5km',
        'sp_cycle_access_pt_frequent_5000m',
        'Public transport (frequent), 5 km',
    ),
    (
        'all_safe_access_2km',
        'sp_cycle_access_all_strict_2000m',
        'All categories (strict), 2 km',
    ),
    (
        'all_safe_access_5km',
        'sp_cycle_access_all_strict_5000m',
        'All categories (strict), 5 km',
    ),
]

PT_FALLBACK = {
    'sp_cycle_access_pt_frequent_2000m': 'sp_cycle_access_pt_any_2000m',
    'sp_cycle_access_pt_frequent_5000m': 'sp_cycle_access_pt_any_5000m',
}

LTS_LABELS = [1, 2, 3, 4]


# --------------------------------------------------------------------------- #
# Core metrics (pure; unit-tested in tests/tests.py)
# --------------------------------------------------------------------------- #
def binary_agreement(r_vals, py_vals):
    """Agreement statistics between two aligned binary (0/1) series.

    Rows where either value is missing are dropped before scoring.

    Returns a dict with the matched count ``n``, each pipeline's access share
    (``r_pct`` / ``py_pct``), point-level ``agreement_pct``, Cohen's
    ``kappa``, and the disagreement split ``py_only`` (Python=1, R=0) /
    ``r_only`` (R=1, Python=0).
    """
    r = pd.to_numeric(pd.Series(r_vals).reset_index(drop=True), errors='coerce')
    p = pd.to_numeric(pd.Series(py_vals).reset_index(drop=True), errors='coerce')
    keep = r.notna() & p.notna()
    r = r[keep].astype(int).to_numpy()
    p = p[keep].astype(int).to_numpy()
    n = int(len(r))
    if n == 0:
        return {
            'n': 0, 'r_pct': np.nan, 'py_pct': np.nan,
            'agreement_pct': np.nan, 'kappa': np.nan,
            'py_only': 0, 'r_only': 0,
        }
    both = int(np.sum((r == 1) & (p == 1)))
    py_only = int(np.sum((r == 0) & (p == 1)))
    r_only = int(np.sum((r == 1) & (p == 0)))
    neither = int(np.sum((r == 0) & (p == 0)))
    po = (both + neither) / n
    # expected agreement under independence (Cohen's kappa)
    p_r1 = (both + r_only) / n
    p_p1 = (both + py_only) / n
    pe = p_r1 * p_p1 + (1 - p_r1) * (1 - p_p1)
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 0 else np.nan
    return {
        'n': n,
        'r_pct': 100.0 * (both + r_only) / n,
        'py_pct': 100.0 * (both + py_only) / n,
        'agreement_pct': 100.0 * po,
        'kappa': kappa,
        'py_only': py_only,
        'r_only': r_only,
    }


def ordinal_confusion(r_vals, py_vals, labels=LTS_LABELS):
    """Per-edge ordinal agreement for matched LTS values.

    Returns a dict with matched count ``n``, ``exact_pct`` (equal class),
    ``within1_pct`` (differ by <= 1), ``mean_abs_diff``, and the ``confusion``
    cross-tabulation (R rows x Python columns) as a DataFrame.
    """
    r = pd.to_numeric(pd.Series(r_vals).reset_index(drop=True), errors='coerce')
    p = pd.to_numeric(pd.Series(py_vals).reset_index(drop=True), errors='coerce')
    keep = r.notna() & p.notna()
    r = r[keep].astype(int)
    p = p[keep].astype(int)
    n = int(len(r))
    confusion = pd.crosstab(r, p).reindex(
        index=labels, columns=labels, fill_value=0,
    )
    if n == 0:
        return {
            'n': 0, 'exact_pct': np.nan, 'within1_pct': np.nan,
            'mean_abs_diff': np.nan, 'confusion': confusion,
        }
    diff = (r.to_numpy() - p.to_numpy())
    return {
        'n': n,
        'exact_pct': 100.0 * np.mean(diff == 0),
        'within1_pct': 100.0 * np.mean(np.abs(diff) <= 1),
        'mean_abs_diff': float(np.mean(np.abs(diff))),
        'confusion': confusion,
    }


def class_shares(values, weights=None, labels=None):
    """Share (%) of each class, optionally weighted (e.g. by edge length)."""
    s = pd.Series(values).reset_index(drop=True)
    if weights is None:
        w = pd.Series(1.0, index=s.index)
    else:
        w = pd.to_numeric(
            pd.Series(weights).reset_index(drop=True), errors='coerce',
        ).fillna(0.0)
    keep = s.notna()
    s, w = s[keep], w[keep]
    total = w.sum()
    grouped = w.groupby(s).sum()
    shares = (100.0 * grouped / total) if total > 0 else grouped * np.nan
    if labels is not None:
        shares = shares.reindex(labels, fill_value=0.0)
    return shares


def _coerce_point_id(series):
    """Coerce a point_id series to a common joinable key (Int64 if possible)."""
    numeric = pd.to_numeric(series, errors='coerce')
    if numeric.notna().all():
        return numeric.astype('int64')
    return series.astype(str)


# --------------------------------------------------------------------------- #
# Comparison drivers
# --------------------------------------------------------------------------- #
def compare_sample_points(r_sp, py_sp, mapping=DEFAULT_SP_MAPPING):
    """Join R and Python sample points on point_id and score each indicator."""
    r_sp = r_sp.copy()
    py_sp = py_sp.copy()
    r_sp['_pid'] = _coerce_point_id(r_sp['point_id'])
    py_sp['_pid'] = _coerce_point_id(py_sp['point_id'])
    joined = pd.merge(
        r_sp.set_index('_pid'),
        py_sp.set_index('_pid'),
        left_index=True, right_index=True,
        how='inner', suffixes=('_r', '_py'),
    )
    rows = []
    for r_col, py_col, label in mapping:
        # fall back to pt_any where pt_frequent is not present (no GTFS feed)
        if py_col not in joined.columns and py_col in PT_FALLBACK:
            alt = PT_FALLBACK[py_col]
            if alt in joined.columns:
                py_col = alt
                label += ' [pt_any fallback]'
        if r_col not in joined.columns or py_col not in joined.columns:
            rows.append({'indicator': label, 'n': 0, 'note': 'column absent'})
            continue
        stats = binary_agreement(joined[r_col], joined[py_col])
        stats['indicator'] = label
        rows.append(stats)
    return pd.DataFrame(rows), len(joined)


# Indicator resolution across R-output vintages and Python variants.  Each indicator
# lists ``(r_template, [py_templates])`` pairs in priority order: the first pair whose R
# column is present fixes both the R column and the candidate Python columns (first
# present wins).  This couples the choice, so an *older* R output (PT tagged ``pt_any``)
# maps to Python ``pt_any``, while a newer one (``pt_20min_or_any``) maps to
# ``pt_frequent``.  ``{rk}`` is the R distance in km (2 / 5); ``{d}`` the Python metres.
SP_INDICATOR_TEMPLATES = [
    ('Fresh food (market)', [
        ('fresh_food_market_safe_{rk}km', ['sp_cycle_access_fresh_food_market_{d}m']),
    ]),
    ('Public open space', [
        ('public_open_space_safe_{rk}km', [
            'sp_cycle_access_public_open_space_large_{d}m',
            'sp_cycle_access_public_open_space_any_{d}m',
        ]),
    ]),
    ('Public transport', [
        ('pt_20min_or_any_safe_{rk}km', [
            'sp_cycle_access_pt_frequent_{d}m', 'sp_cycle_access_pt_any_{d}m',
        ]),
        ('pt_any_safe_{rk}km', ['sp_cycle_access_pt_any_{d}m']),
    ]),
    ('All categories', [
        ('all_safe_access_{rk}km', [
            'sp_cycle_access_all_strict_{d}m', 'sp_cycle_access_all_lenient_{d}m',
        ]),
    ]),
]


def resolve_sp_mapping(r_cols, py_cols, distances=(2000, 5000)):
    """Resolve ``(r_col, py_col, label)`` triples present in both outputs.

    Adapts to the R-output vintage (``pt_any`` vs ``pt_20min_or_any``) and to whichever
    Python variant column exists; the label notes the Python column actually used so the
    (sometimes approximate) cross-methodology mapping is explicit in the report.
    """
    r_cols, py_cols = set(r_cols), set(py_cols)
    mapping = []
    for d in distances:
        rk = int(d) // 1000
        for label, pairs in SP_INDICATOR_TEMPLATES:
            for r_template, py_templates in pairs:
                r_col = r_template.format(rk=rk)
                if r_col not in r_cols:
                    continue
                py_col = next(
                    (t.format(d=int(d)) for t in py_templates
                     if t.format(d=int(d)) in py_cols),
                    None,
                )
                if py_col is None:
                    continue
                variant = py_col.replace('sp_cycle_access_', '').replace(f'_{int(d)}m', '')
                mapping.append((r_col, py_col, f'{label} [{variant}], {rk} km'))
                break  # first matching pair wins for this indicator + distance
    return mapping


def compare_sample_point_distributions(r_sp, py_sp, mapping):
    """City-level access-rate comparison that needs no ``point_id`` alignment.

    Each pipeline's access share is the mean of its binary column over *its own* sample
    points, so this is valid even when a fresh Python run does not share sample points
    with an older R output.  Returns a DataFrame of R % / Python % / difference / counts.
    """
    rows = []
    for r_col, py_col, label in mapping:
        r = pd.to_numeric(r_sp[r_col], errors='coerce') if r_col in r_sp else None
        p = pd.to_numeric(py_sp[py_col], errors='coerce') if py_col in py_sp else None
        r_pct = 100.0 * r.mean() if r is not None and r.notna().any() else np.nan
        p_pct = 100.0 * p.mean() if p is not None and p.notna().any() else np.nan
        delta = (
            p_pct - r_pct
            if not (np.isnan(r_pct) or np.isnan(p_pct)) else np.nan
        )
        rows.append({
            'indicator': label,
            'R %': r_pct, 'Python %': p_pct, 'delta_py_minus_r': delta,
            'R n': int(r.notna().sum()) if r is not None else 0,
            'Py n': int(p.notna().sum()) if p is not None else 0,
        })
    return pd.DataFrame(rows)


def python_only_access_indicators(py_sp, mapping):
    """Python binary-access indicators with no R counterpart in the mapping.

    Documents the port's broader scope (strict/lenient variants, activity centres,
    'all categories' composites, local-custom sets) that the older R outputs lack.
    """
    mapped = {py_col for _, py_col, _ in mapping}
    return sorted(
        c for c in py_sp.columns
        if c.startswith('sp_cycle_access_') and c not in mapped
    )


def compare_edges(r_edges, py_edges):
    """Distributional comparison of LTS / facility / speed / impedance."""
    out = {}
    out['lts_count'] = pd.DataFrame({
        'R %': class_shares(r_edges['lvl_traf_stress'], labels=LTS_LABELS),
        'Python %': class_shares(py_edges['lvl_traf_stress'], labels=LTS_LABELS),
    })
    out['lts_length'] = pd.DataFrame({
        'R %': class_shares(
            r_edges['lvl_traf_stress'], r_edges.get('length'), LTS_LABELS,
        ),
        'Python %': class_shares(
            py_edges['lvl_traf_stress'], py_edges.get('length'), LTS_LABELS,
        ),
    })
    r_fac = r_edges['cycleway'] if 'cycleway' in r_edges else pd.Series(dtype=object)
    py_fac = (
        py_edges['bike_facility']
        if 'bike_facility' in py_edges else pd.Series(dtype=object)
    )
    facilities = sorted(
        set(r_fac.dropna().unique()) | set(py_fac.dropna().unique()),
    )
    out['facility'] = pd.DataFrame({
        'R %': class_shares(r_fac, labels=facilities),
        'Python %': class_shares(py_fac, labels=facilities),
    })
    # speed: a missing value is genuinely missing -> drop it.  impedance: a missing
    # value means *no* impedance -> treat as 0, so both pipelines are summarised over
    # their full edge set (R stores LTS_imped only on penalty-bearing edges; Python
    # populates lts_imped on every edge).
    out['speed'] = _summary_stats(
        r_edges.get('maxspeed'), py_edges.get('maxspeed_kmh'),
    )
    out['impedance'] = _summary_stats(
        r_edges.get('LTS_imped'), py_edges.get('lts_imped'), fillna=0.0,
    )
    return out


def _summary_stats(r_series, py_series, fillna=None):
    """Mean / median / 90th-pct summary of two numeric series for a report.

    Missing values are dropped by default; pass ``fillna`` to replace them instead
    (e.g. ``0`` for impedance, where a null means no impedance rather than missing).
    """
    def describe(s):
        if s is None:
            return {'n': 0, 'mean': np.nan, 'median': np.nan, 'p90': np.nan}
        v = pd.to_numeric(pd.Series(s), errors='coerce')
        v = v.fillna(fillna) if fillna is not None else v.dropna()
        return {
            'n': int(len(v)),
            'mean': float(v.mean()) if len(v) else np.nan,
            'median': float(v.median()) if len(v) else np.nan,
            'p90': float(v.quantile(0.9)) if len(v) else np.nan,
        }
    return pd.DataFrame({'R': describe(r_series), 'Python': describe(py_series)}).T


def spatial_lts_agreement(r_edges, py_edges, tolerance=20):
    """Optional per-edge LTS agreement via nearest-edge spatial match.

    For each Python edge, the nearest R edge within ``tolerance`` metres of its
    representative point is matched, then ``ordinal_confusion`` is scored.  Both
    inputs must be GeoDataFrames in the same projected CRS.
    """
    import geopandas as gpd

    py = py_edges[['lvl_traf_stress', 'geometry']].copy()
    r = r_edges[['lvl_traf_stress', 'geometry']].copy()
    py['geometry'] = py.geometry.representative_point()
    matched = gpd.sjoin_nearest(
        py, r, how='left', max_distance=tolerance,
        distance_col='_match_dist', lsuffix='py', rsuffix='r',
    ).dropna(subset=['lvl_traf_stress_r'])
    return ordinal_confusion(
        matched['lvl_traf_stress_r'], matched['lvl_traf_stress_py'],
    )


# --------------------------------------------------------------------------- #
# I/O + report
# --------------------------------------------------------------------------- #
def _load_layer(gpkg, layer):
    import geopandas as gpd

    return gpd.read_file(gpkg, layer=layer)


def load_python_outputs(codename, python_gpkg=None):
    """Return (edges, sample_points) for the Python pipeline."""
    if python_gpkg:
        edges = _load_layer(python_gpkg, 'edges')
        sp = _load_layer(python_gpkg, 'sample_points_cycling')
        return edges, sp
    import ghsci

    r = ghsci.Region(codename)
    edges = r.get_gdf('edges')
    sp = r.get_gdf('sample_points_cycling')
    return edges, sp


def _fmt(value, spec='.1f'):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return '—'
    return format(value, spec)


def build_report(
    codename, dist_table, sp_table, n_points, py_only, edge_cmp, spatial=None,
):
    """Assemble the Markdown comparison report as a string."""
    lines = [f'# Cycling indicators: R vs Python comparison — {codename}', '']

    # 1. Distribution-level access (always valid; no point_id alignment needed)
    lines.append('## Sample-point safe-route access — city rates (distribution)')
    lines.append('')
    lines.append('| Indicator | R access % | Python access % | Δ (Py−R) | R n | Py n |')
    lines.append('|---|---|---|---|---|---|')
    for _, row in dist_table.iterrows():
        lines.append(
            f"| {row['indicator']} | {_fmt(row['R %'])} | {_fmt(row['Python %'])} | "
            f"{_fmt(row['delta_py_minus_r'], '+.1f')} | {int(row['R n'])} | "
            f"{int(row['Py n'])} |",
        )
    lines.append('')
    lines.append(
        '> Compares each pipeline\'s overall access rate over its *own* sample points, '
        'so it is valid even when the runs do not share sample points (e.g. comparing a '
        'fresh Python run to an older R output). The mapping is approximate where the '
        'methodologies differ — the Python variant used is shown in [brackets].',
    )
    lines.append('')

    # 2. Python's broader scope (the 'more comprehensive' improvement)
    if py_only:
        lines.append(f'## Python-only access indicators ({len(py_only)})')
        lines.append('')
        lines.append(
            'Indicators the Python port produces that have no equivalent in the R '
            'output (strict/lenient variants, activity centres, "all categories" '
            'composites, local-custom sets), with each one\'s access rate — e.g. '
            'compare R "public open space" against Python `public_open_space_any` '
            '(the closest match to an older "any open space" definition):')
        lines.append('')
        lines.append('| Indicator | Python access % |')
        lines.append('|---|---|')
        for c, rate in py_only.items():
            lines.append(f'| `{c}` | {_fmt(rate)} |')
        lines.append('')

    # 3. Per-point agreement (only meaningful when sample points are shared)
    if sp_table is not None:
        lines.append(
            f'## Per-point agreement ({n_points} points matched on `point_id`)',
        )
        lines.append('')
        if n_points == 0:
            lines.append(
                '> No sample points matched on `point_id` — the runs do not share '
                'sample points, so per-point agreement is not applicable here; rely on '
                'the city-rate distribution above. (Re-run Python on the R run\'s '
                'origins for a per-point comparison.)')
            lines.append('')
        else:
            lines.append(
                '| Indicator | R access % | Python access % | Agreement % | '
                'Kappa | Python-only | R-only |',
            )
            lines.append('|---|---|---|---|---|---|---|')
            for _, row in sp_table.iterrows():
                if row.get('n', 0) == 0:
                    lines.append(
                        f"| {row['indicator']} | — | — | — | — | — | — |",
                    )
                    continue
                lines.append(
                    f"| {row['indicator']} | {_fmt(row['r_pct'])} | "
                    f"{_fmt(row['py_pct'])} | {_fmt(row['agreement_pct'])} | "
                    f"{_fmt(row['kappa'], '.3f')} | {int(row['py_only'])} | "
                    f"{int(row['r_only'])} |",
                )
            lines.append('')
    lines.append('## Network Level of Traffic Stress (distributional)')
    lines.append('')
    lines.append('By edge count:')
    lines.append('')
    lines.append(edge_cmp['lts_count'].round(1).to_markdown())
    lines.append('')
    lines.append('By edge length:')
    lines.append('')
    lines.append(edge_cmp['lts_length'].round(1).to_markdown())
    lines.append('')
    lines.append('## Cycling facility class (distributional)')
    lines.append('')
    lines.append(edge_cmp['facility'].round(1).to_markdown())
    lines.append('')
    lines.append('## Speed and impedance summary')
    lines.append('')
    lines.append('Speed (km/h):')
    lines.append('')
    lines.append(edge_cmp['speed'].round(2).to_markdown())
    lines.append('')
    lines.append('LTS impedance (m):')
    lines.append('')
    lines.append(edge_cmp['impedance'].round(3).to_markdown())
    lines.append('')
    if spatial is not None:
        lines.append('## Spatial per-edge LTS agreement (nearest-edge match)')
        lines.append('')
        lines.append(
            f"Matched {spatial['n']} edges — exact "
            f"{_fmt(spatial['exact_pct'])}%, within ±1 "
            f"{_fmt(spatial['within1_pct'])}%, mean |Δ| "
            f"{_fmt(spatial['mean_abs_diff'], '.2f')}.",
        )
        lines.append('')
        lines.append('Confusion (R rows × Python columns):')
        lines.append('')
        lines.append(spatial['confusion'].to_markdown())
        lines.append('')
    lines.append(
        '> Notes: routing is undirected in Python and the R network is one-way split, '
        'so LTS is compared distributionally. PT maps R `pt_20min_or_any` → Python '
        '`pt_frequent`, or (older R outputs) R `pt_any` → Python `pt_any`. The Python '
        'port is the newer, more comprehensive methodology, so differences from an '
        'older R baseline are expected. Distances are LTS-impedance-weighted in both.',
    )
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('codename', help='GHSCI study-region codename')
    parser.add_argument(
        '--r-gpkg', required=True,
        help='Path to the R <City>_cyclingIndicators.gpkg',
    )
    parser.add_argument(
        '--python-gpkg',
        help='Path to the generated Python region GeoPackage '
        '(default: read from PostGIS via ghsci.Region)',
    )
    parser.add_argument(
        '--spatial', action='store_true',
        help='Also compute per-edge spatial LTS agreement (same-build networks)',
    )
    parser.add_argument(
        '--distribution-only', action='store_true',
        help='Skip the per-point (point_id) agreement; only compare city-level rates '
        '(use when the runs do not share sample points, e.g. an older R output)',
    )
    parser.add_argument('--out', help='Write the Markdown report to this path')
    args = parser.parse_args()

    r_sp = _load_layer(args.r_gpkg, 'sample_points_accessibility')
    r_edges = _load_layer(args.r_gpkg, 'edges')
    py_edges, py_sp = load_python_outputs(args.codename, args.python_gpkg)

    # fail clearly if a required layer could not be loaded (e.g. the cycling
    # accessibility step has not been run, or the codename/db is wrong)
    for name, gdf in [('R sample_points_accessibility', r_sp), ('R edges', r_edges)]:
        if gdf is None:
            sys.exit(f'Could not read {name} from {args.r_gpkg}.')
    if py_sp is None or py_edges is None:
        src = args.python_gpkg or f"PostGIS for region '{args.codename}'"
        missing = 'sample_points_cycling' if py_sp is None else 'edges'
        sys.exit(
            f"Could not read Python '{missing}' from {src}.\n"
            'If reading from PostGIS, ensure the cycling steps have run for this '
            'region, e.g.:\n'
            "  python -c \"import _cycling_lts_network as n; n.cycling_lts_network"
            f"('{args.codename}')\"\n"
            "  python -c \"import _cycling_accessibility as a; a.cycling_accessibility"
            f"('{args.codename}')\"\n"
            'Or pass --python-gpkg pointing at a generated GeoPackage that contains '
            'sample_points_cycling and the LTS edges.',
        )

    mapping = resolve_sp_mapping(r_sp.columns, py_sp.columns)
    dist_table = compare_sample_point_distributions(r_sp, py_sp, mapping)
    py_only_cols = python_only_access_indicators(py_sp, mapping)
    py_only = {
        c: float(100.0 * pd.to_numeric(py_sp[c], errors='coerce').mean())
        for c in py_only_cols
    }
    if args.distribution_only:
        sp_table, n_points = None, 0
    else:
        sp_table, n_points = compare_sample_points(r_sp, py_sp, mapping)
    edge_cmp = compare_edges(r_edges, py_edges)
    spatial = (
        spatial_lts_agreement(r_edges, py_edges) if args.spatial else None
    )

    report = build_report(
        args.codename, dist_table, sp_table, n_points, py_only, edge_cmp, spatial,
    )
    print(report)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(report + '\n')
        print(f'\nReport written to {args.out}')


if __name__ == '__main__':
    sys.exit(main())
