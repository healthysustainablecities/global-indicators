"""
Longitudinal (multi-timepoint) comparison of GHSCI study regions.

Supports analysis of change over time for a city analysed at two or more
time points as separate study region configurations (e.g. Melbourne 2016,
2021 and 2026, ideally sharing a common boundary and population grid).

A series may be defined at runtime from a list of region codenames or
paths, or using a dedicated series configuration file validated against
configuration/regions/series-json-schema.json.  Series configuration
files are preferentially located with their data (e.g.
data/AU/AU_Melbourne_series.yml), though they may also be placed in the
configuration/regions folder.

Alternatively, a single study region configuration may define its own
series in a 'series' block: timepoints (or sensitivity analysis
scenarios) keyed by a codename suffix, each overriding a subset of the
base configuration's parameters (see ghsci.merge_overrides).  Each
variant is analysed as its own study region, with the codename
'{base codename}_{key}', and the series is loaded using the base
codename, e.g. ghsci.Series('AU_Melbourne_1000m').  Variants and the
availability of their configured data can be reviewed before analysis
using describe_series().

Example usage:

    from subprocesses import ghsci
    s = ghsci.Series('AU_Melbourne_series')
    s = ghsci.Series(
        ['AU_Melbourne_2016', 'AU_Melbourne_2021', 'AU_Melbourne_2026'],
    )
    s.validate_alignment()
    panel = s.get_grid_panel()
    change = s.compute_change(panel)
    equity = s.equity_summary()
"""

import glob
import os

import numpy as np
import pandas as pd

# quantiles evaluated by default in distributional summaries
DEFAULT_QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)

# indicators not following the pct_ prefix convention may be classified
# explicitly here (or via the overrides argument of classify_indicator)
INDICATOR_CLASS_OVERRIDES = {}

# columns recognised as unit identifiers in long-format panels
UNIT_COLUMNS = ('grid_id', 'area_id', 'unit_id')


def _ghsci():
    """Return the ghsci module, however it has been imported."""
    try:
        import subprocesses.ghsci as ghsci
    except ImportError:
        import ghsci
    return ghsci


def _policy_report():
    """Return the policy_report module, however it has been imported."""
    try:
        import subprocesses.policy_report as policy_report
    except ImportError:
        import policy_report
    return policy_report


def classify_indicator(indicator: str, overrides: dict = None) -> str:
    """
    Classify an indicator as 'bounded_pct' or 'unbounded'.

    Indicators representing bounded 0-100 percentage shares (named with
    a 'pct_' prefix, or containing '_pct_') default to percentage-point
    change and have ratio-based statistics suppressed; other indicators
    (densities, scores) are treated as unbounded.
    """
    merged = dict(INDICATOR_CLASS_OVERRIDES)
    if overrides:
        merged.update(overrides)
    if indicator in merged:
        return merged[indicator]
    if indicator.startswith('pct_') or '_pct_' in indicator:
        return 'bounded_pct'
    return 'unbounded'


def _panel_unit_column(panel: pd.DataFrame) -> str:
    """Return the unit identifier column of a long-format panel."""
    for column in UNIT_COLUMNS:
        if column in panel.columns:
            return column
    raise ValueError(
        f'Panel does not contain a recognised unit identifier column '
        f'(one of {UNIT_COLUMNS}).',
    )


def _panel_timepoints(panel: pd.DataFrame) -> list:
    """Return ordered timepoint labels for a long-format panel."""
    timepoints = panel.attrs.get('timepoints')
    if timepoints is None:
        timepoints = list(pd.unique(panel['timepoint']))
    return list(timepoints)


def _resolve_pairs(timepoints: list, pairs: str, reference=None) -> list:
    """Return ordered (t0, t1) comparison pairs of timepoint labels."""
    if reference is None:
        reference = timepoints[0]
    if reference not in timepoints:
        raise ValueError(
            f"Reference timepoint '{reference}' not found among "
            f'{timepoints}.',
        )
    if pairs == 'reference':
        return [(reference, t) for t in timepoints if t != reference]
    elif pairs == 'consecutive':
        return list(zip(timepoints[:-1], timepoints[1:]))
    elif pairs == 'all':
        return [
            (timepoints[i], timepoints[j])
            for i in range(len(timepoints))
            for j in range(i + 1, len(timepoints))
        ]
    raise ValueError(
        f"Unknown pairs option '{pairs}'; expected 'reference', "
        "'consecutive' or 'all'.",
    )


def compute_change(
    panel: pd.DataFrame,
    pairs: str = 'reference',
    reference=None,
    metrics: tuple = None,
    overrides: dict = None,
) -> pd.DataFrame:
    """
    Compute change metrics between timepoints of a long-format panel.

    The panel requires columns for a unit identifier (grid_id, area_id
    or unit_id), 'timepoint', 'indicator' and 'value'.  Comparison pairs
    are formed against the reference timepoint ('reference', default),
    between consecutive timepoints ('consecutive'), or for all ordered
    pairs ('all').

    Metrics are indicator-aware unless explicitly requested: bounded
    percentage indicators (see classify_indicator) yield percentage
    point change ('pp_change'); unbounded indicators yield absolute
    difference ('diff') and relative percentage change ('pct_change',
    with infinite values from zero baselines masked as missing).

    Returns a tidy DataFrame with columns: unit identifier, indicator,
    t0, t1, value_t0, value_t1, metric, change.
    """
    unit = _panel_unit_column(panel)
    timepoints = _panel_timepoints(panel)
    comparison_pairs = _resolve_pairs(timepoints, pairs, reference)
    results = []
    for t0, t1 in comparison_pairs:
        baseline = panel.loc[
            panel['timepoint'] == t0,
            [unit, 'indicator', 'value'],
        ].rename(columns={'value': 'value_t0'})
        follow_up = panel.loc[
            panel['timepoint'] == t1,
            [unit, 'indicator', 'value'],
        ].rename(columns={'value': 'value_t1'})
        merged = baseline.merge(
            follow_up,
            on=[unit, 'indicator'],
            how='outer',
        )
        merged['t0'] = t0
        merged['t1'] = t1
        for indicator, group in merged.groupby('indicator', sort=False):
            indicator_class = classify_indicator(indicator, overrides)
            if metrics is not None:
                indicator_metrics = metrics
            elif indicator_class == 'bounded_pct':
                indicator_metrics = ('pp_change',)
            else:
                indicator_metrics = ('diff', 'pct_change')
            v0 = pd.to_numeric(group['value_t0'], errors='coerce')
            v1 = pd.to_numeric(group['value_t1'], errors='coerce')
            for metric in indicator_metrics:
                if metric in ('diff', 'pp_change'):
                    change = v1 - v0
                elif metric == 'pct_change':
                    change = 100 * (v1 - v0) / v0
                    change = change.replace([np.inf, -np.inf], np.nan)
                else:
                    raise ValueError(
                        f"Unknown change metric '{metric}'; expected "
                        "'diff', 'pp_change' or 'pct_change'.",
                    )
                result = group[[unit, 'indicator', 't0', 't1']].copy()
                result['value_t0'] = v0
                result['value_t1'] = v1
                result['metric'] = metric
                result['change'] = change
                results.append(result)
    if not results:
        return pd.DataFrame(
            columns=[
                unit,
                'indicator',
                't0',
                't1',
                'value_t0',
                'value_t1',
                'metric',
                'change',
            ],
        )
    change_df = pd.concat(results, ignore_index=True)
    change_df.attrs['timepoints'] = timepoints
    return change_df


def validate_grid_alignment(
    frames: dict,
    reference,
    centroid_tolerance_m: float = 10,
    min_shared_fraction: float = 0.95,
) -> dict:
    """
    Validate grid alignment of timepoint grid summaries by grid_id.

    Takes a dictionary of DataFrames keyed by timepoint label, each with
    a 'grid_id' column and optionally 'centroid_x'/'centroid_y' columns
    in a common projected (metre) coordinate reference system.

    For each non-reference timepoint the shared fraction of grid cells
    (shared count relative to the smaller grid, so genuine urban growth
    does not penalise alignment), the counts of new and retired cells
    (real change in urban extent, reported as signal rather than error),
    and centroid offsets among shared cells (misalignment, reported as
    error) are evaluated.

    Returns a dictionary keyed by timepoint label with alignment
    statistics and a 'status' of 'ok', 'warn' (shared fraction below
    min_shared_fraction, or centroid offsets above tolerance) or 'error'
    (shared fraction below 0.5, requiring a crosswalk or re-analysis of
    timepoints against a common population grid).
    """
    if reference not in frames:
        raise ValueError(
            f"Reference timepoint '{reference}' not found among "
            f'{list(frames)}.',
        )
    reference_frame = frames[reference].set_index('grid_id')
    report = {}
    for label, frame in frames.items():
        if label == reference:
            continue
        comparison = frame.set_index('grid_id')
        shared = reference_frame.index.intersection(comparison.index)
        n_reference = len(reference_frame)
        n_comparison = len(comparison)
        smaller = min(n_reference, n_comparison)
        shared_fraction = len(shared) / smaller if smaller else 0.0
        result = {
            'n_reference': n_reference,
            'n_timepoint': n_comparison,
            'n_shared': len(shared),
            'n_new': len(comparison.index.difference(reference_frame.index)),
            'n_retired': len(
                reference_frame.index.difference(comparison.index),
            ),
            'shared_fraction': shared_fraction,
            'max_offset_m': None,
            'p95_offset_m': None,
            'method': 'grid_id',
        }
        centroid_columns = {'centroid_x', 'centroid_y'}
        if centroid_columns.issubset(
            reference_frame.columns,
        ) and centroid_columns.issubset(comparison.columns):
            offsets = np.hypot(
                comparison.loc[shared, 'centroid_x'].astype(float)
                - reference_frame.loc[shared, 'centroid_x'].astype(float),
                comparison.loc[shared, 'centroid_y'].astype(float)
                - reference_frame.loc[shared, 'centroid_y'].astype(float),
            )
            if len(offsets):
                result['max_offset_m'] = float(np.max(offsets))
                result['p95_offset_m'] = float(np.percentile(offsets, 95))
        else:
            result['method'] = 'grid_id_only'
        if shared_fraction < 0.5:
            result['status'] = 'error'
        elif shared_fraction < min_shared_fraction:
            result['status'] = 'warn'
        elif (
            result['max_offset_m'] is not None
            and result['max_offset_m'] > centroid_tolerance_m
        ):
            result['status'] = 'warn'
        else:
            result['status'] = 'ok'
        report[label] = result
    return report


def weighted_quantile(values, weights, quantiles) -> np.ndarray:
    """
    Compute weighted quantiles by interpolation.

    Uses the standard weighted percentile estimator, interpolating
    between the cumulative weight midpoints of sorted values (each
    observation is centred within its weight share of the cumulative
    distribution).  Quantiles of 0 and 1 return the minimum and maximum
    observed value respectively.
    """
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    quantiles = np.atleast_1d(np.asarray(quantiles, dtype=float))
    valid = ~np.isnan(values) & ~np.isnan(weights) & (weights > 0)
    values = values[valid]
    weights = weights[valid]
    if len(values) == 0:
        return np.full(len(quantiles), np.nan)
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    midpoints = np.cumsum(weights) - 0.5 * weights
    midpoints = midpoints / np.sum(weights)
    return np.interp(quantiles, midpoints, values)


def gini(values, weights=None) -> float:
    """
    Compute the (population) weighted Gini coefficient.

    Uses the standard weighted estimator based on the covariance of
    values with their weighted midpoint ranks.  For bounded percentage
    indicators note that the Gini coefficient is mean-dependent, and
    attainment and shortfall inequality can diverge; report alongside
    the mean, and see the shortfall sensitivity in concentration_index.
    """
    values = np.asarray(values, dtype=float)
    if weights is None:
        weights = np.ones_like(values)
    weights = np.asarray(weights, dtype=float)
    valid = ~np.isnan(values) & ~np.isnan(weights) & (weights > 0)
    values = values[valid]
    weights = weights[valid]
    if len(values) == 0:
        return np.nan
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    total_weight = np.sum(weights)
    mean = np.sum(values * weights) / total_weight
    if mean == 0:
        return np.nan
    shares = weights / total_weight
    ranks = (np.cumsum(weights) - 0.5 * weights) / total_weight
    mean_rank = np.sum(shares * ranks)
    return float(
        2 / mean * np.sum(shares * values * (ranks - mean_rank)),
    )


def weighted_quantiles(
    panel: pd.DataFrame,
    quantiles=DEFAULT_QUANTILES,
    weight: str = 'pop_est',
) -> pd.DataFrame:
    """
    Population-weighted quantiles per indicator and timepoint.

    Takes a long-format panel with 'timepoint', 'indicator', 'value' and
    a weight column; returns a tidy DataFrame with columns: indicator,
    timepoint, q, value.  Unweighted quantiles are computed if the
    weight column is absent.
    """
    results = []
    for (indicator, timepoint), group in panel.groupby(
        ['indicator', 'timepoint'],
        sort=False,
    ):
        weights = (
            group[weight] if weight in group.columns else np.ones(len(group))
        )
        estimates = weighted_quantile(group['value'], weights, quantiles)
        for q, value in zip(np.atleast_1d(quantiles), estimates):
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'q': float(q),
                    'value': value,
                },
            )
    quantile_df = pd.DataFrame(results)
    quantile_df.attrs['timepoints'] = _panel_timepoints(panel)
    return quantile_df


def quantile_gaps(
    quantile_df: pd.DataFrame,
    overrides: dict = None,
) -> pd.DataFrame:
    """
    Distributional gap statistics per indicator and timepoint.

    From a weighted_quantiles result, computes the p90-p10 and p75-p25
    absolute gaps for each indicator and timepoint, the change in each
    gap relative to the first timepoint, and (for unbounded indicators
    only, as ratios of bounded percentage shares mislead near zero) the
    p90:p10 ratio.  Returns a tidy DataFrame with columns: indicator,
    timepoint, statistic, value.
    """
    timepoints = _panel_timepoints(quantile_df)
    results = []
    wide = quantile_df.pivot_table(
        index=['indicator', 'timepoint'],
        columns='q',
        values='value',
    )
    for (indicator, timepoint), row in wide.iterrows():
        gaps = {}
        if 0.9 in row.index and 0.1 in row.index:
            gaps['p90_p10_gap'] = row[0.9] - row[0.1]
            if (
                classify_indicator(indicator, overrides) == 'unbounded'
                and row[0.1] != 0
            ):
                gaps['p90_p10_ratio'] = row[0.9] / row[0.1]
        if 0.75 in row.index and 0.25 in row.index:
            gaps['p75_p25_gap'] = row[0.75] - row[0.25]
        for statistic, value in gaps.items():
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'statistic': statistic,
                    'value': value,
                },
            )
    gaps_df = pd.DataFrame(results)
    if len(gaps_df) == 0:
        return gaps_df
    # change in each gap statistic relative to the first timepoint
    reference = timepoints[0]
    changes = []
    for (indicator, statistic), group in gaps_df.groupby(
        ['indicator', 'statistic'],
        sort=False,
    ):
        if statistic.endswith('_ratio'):
            continue
        baseline = group.loc[group['timepoint'] == reference, 'value']
        if len(baseline) == 0:
            continue
        for _, row in group.iterrows():
            if row['timepoint'] == reference:
                continue
            changes.append(
                {
                    'indicator': indicator,
                    'timepoint': row['timepoint'],
                    'statistic': f'{statistic}_change',
                    'value': row['value'] - baseline.iloc[0],
                },
            )
    gaps_df = pd.concat(
        [gaps_df, pd.DataFrame(changes)],
        ignore_index=True,
    )
    gaps_df.attrs['timepoints'] = timepoints
    return gaps_df


def low_high_end_change(quantile_df: pd.DataFrame) -> pd.DataFrame:
    """
    Change at the low and high ends of the distribution over time.

    From a weighted_quantiles result, compares the change in the 10th
    percentile with the change in the 90th percentile (and p25 with
    p75) between the first and each later timepoint, classifying each
    indicator's trajectory: 'converging' if the low end gains on the
    high end, 'diverging' if it falls behind, combined with 'improving'
    or 'declining' overall direction (based on the median where
    available).  Directly answers whether the worst-served areas caught
    up.  Returns a tidy DataFrame with columns: indicator, t0, t1,
    low_q, high_q, low_change, high_change, median_change,
    classification.
    """
    timepoints = _panel_timepoints(quantile_df)
    reference = timepoints[0]
    wide = quantile_df.pivot_table(
        index=['indicator', 'timepoint'],
        columns='q',
        values='value',
    )
    results = []
    for pair in [(0.1, 0.9), (0.25, 0.75)]:
        low_q, high_q = pair
        if low_q not in wide.columns or high_q not in wide.columns:
            continue
        for indicator in wide.index.get_level_values(0).unique():
            block = wide.loc[indicator]
            if reference not in block.index:
                continue
            for timepoint in timepoints[1:]:
                if timepoint not in block.index:
                    continue
                low_change = (
                    block.loc[timepoint, low_q] - block.loc[reference, low_q]
                )
                high_change = (
                    block.loc[timepoint, high_q] - block.loc[reference, high_q]
                )
                median_change = (
                    block.loc[timepoint, 0.5] - block.loc[reference, 0.5]
                    if 0.5 in block.columns
                    else np.nan
                )
                trend = (
                    'improving'
                    if median_change > 0
                    else 'declining' if median_change < 0 else 'stable'
                )
                spread = (
                    'converging'
                    if low_change > high_change
                    else 'diverging' if low_change < high_change else 'stable'
                )
                results.append(
                    {
                        'indicator': indicator,
                        't0': reference,
                        't1': timepoint,
                        'low_q': low_q,
                        'high_q': high_q,
                        'low_change': low_change,
                        'high_change': high_change,
                        'median_change': median_change,
                        'classification': f'{spread}-{trend}',
                    },
                )
    ends_df = pd.DataFrame(results)
    ends_df.attrs['timepoints'] = timepoints
    return ends_df


def concentration_index(
    panel: pd.DataFrame,
    weight: str = 'pop_est',
    overrides: dict = None,
) -> pd.DataFrame:
    """
    Population-weighted concentration (Gini) per indicator and timepoint.

    For bounded percentage indicators the Gini coefficient of attainment
    is mean-dependent, so the shortfall Gini (of 100 - value) is also
    computed as a sensitivity, along with the weighted mean for context.
    Change in concentration relative to the first timepoint is included.
    Returns a tidy DataFrame with columns: indicator, timepoint,
    statistic, value.
    """
    timepoints = _panel_timepoints(panel)
    results = []
    for (indicator, timepoint), group in panel.groupby(
        ['indicator', 'timepoint'],
        sort=False,
    ):
        values = pd.to_numeric(group['value'], errors='coerce')
        weights = (
            group[weight] if weight in group.columns else np.ones(len(group))
        )
        weights = pd.to_numeric(weights, errors='coerce')
        total = np.nansum(weights)
        mean = np.nansum(values * weights) / total if total else np.nan
        statistics = {
            'weighted_mean': mean,
            'gini': gini(values, weights),
        }
        if classify_indicator(indicator, overrides) == 'bounded_pct':
            statistics['shortfall_gini'] = gini(100 - values, weights)
        for statistic, value in statistics.items():
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'statistic': statistic,
                    'value': value,
                },
            )
    concentration_df = pd.DataFrame(results)
    if len(concentration_df) == 0:
        return concentration_df
    reference = timepoints[0]
    changes = []
    for (indicator, statistic), group in concentration_df.groupby(
        ['indicator', 'statistic'],
        sort=False,
    ):
        baseline = group.loc[group['timepoint'] == reference, 'value']
        if len(baseline) == 0:
            continue
        for _, row in group.iterrows():
            if row['timepoint'] == reference:
                continue
            changes.append(
                {
                    'indicator': indicator,
                    'timepoint': row['timepoint'],
                    'statistic': f'{statistic}_change',
                    'value': row['value'] - baseline.iloc[0],
                },
            )
    concentration_df = pd.concat(
        [concentration_df, pd.DataFrame(changes)],
        ignore_index=True,
    )
    concentration_df.attrs['timepoints'] = timepoints
    return concentration_df


def population_below_threshold(
    panel: pd.DataFrame,
    thresholds: dict,
    weight: str = 'pop_est',
) -> pd.DataFrame:
    """
    Population share meeting indicator thresholds per timepoint.

    Thresholds map indicator names to a numeric threshold (interpreted
    as 'greater_equal': the share of population in units meeting or
    exceeding the threshold) or to a dictionary with 'threshold' and
    'relationship' ('greater', 'greater_equal', 'less', 'less_equal').
    The percentage point change relative to the first timepoint is also
    computed.  Returns a tidy DataFrame with columns: indicator,
    timepoint, threshold, relationship, pop_share_pct (and matching
    pop_share_pct_change rows identified by the statistic column).
    """
    comparisons = {
        'greater': np.greater,
        'greater_equal': np.greater_equal,
        'less': np.less,
        'less_equal': np.less_equal,
    }
    timepoints = _panel_timepoints(panel)
    results = []
    for indicator, criterion in thresholds.items():
        if isinstance(criterion, dict):
            threshold = criterion['threshold']
            relationship = criterion.get('relationship', 'greater_equal')
        else:
            threshold = criterion
            relationship = 'greater_equal'
        comparison = comparisons[relationship]
        subset = panel.loc[panel['indicator'] == indicator]
        for timepoint, group in subset.groupby('timepoint', sort=False):
            values = pd.to_numeric(group['value'], errors='coerce')
            weights = (
                pd.to_numeric(group[weight], errors='coerce')
                if weight in group.columns
                else pd.Series(np.ones(len(group)), index=group.index)
            )
            valid = ~values.isna() & ~weights.isna()
            total = weights[valid].sum()
            share = (
                100
                * weights[valid & comparison(values, threshold)].sum()
                / total
                if total
                else np.nan
            )
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'threshold': threshold,
                    'relationship': relationship,
                    'statistic': 'pop_share_pct',
                    'value': share,
                },
            )
    threshold_df = pd.DataFrame(results)
    if len(threshold_df) == 0:
        return threshold_df
    reference = timepoints[0]
    changes = []
    for indicator, group in threshold_df.groupby('indicator', sort=False):
        baseline = group.loc[group['timepoint'] == reference, 'value']
        if len(baseline) == 0:
            continue
        for _, row in group.iterrows():
            if row['timepoint'] == reference:
                continue
            changes.append(
                {
                    'indicator': indicator,
                    'timepoint': row['timepoint'],
                    'threshold': row['threshold'],
                    'relationship': row['relationship'],
                    'statistic': 'pop_share_pct_change',
                    'value': row['value'] - baseline.iloc[0],
                },
            )
    threshold_df = pd.concat(
        [threshold_df, pd.DataFrame(changes)],
        ignore_index=True,
    )
    threshold_df.attrs['timepoints'] = timepoints
    return threshold_df


def inequality_indices(
    means: pd.DataFrame,
    stratum_weights: dict,
    reference=None,
) -> pd.DataFrame:
    """
    Slope and relative indices of inequality across ordered strata.

    For each indicator and timepoint, strata (ordered from lowest to
    highest, e.g. IRSD decile 1, most disadvantaged, to 10) are assigned
    the midpoint of their cumulative population share (their ridit
    score), and stratum means are regressed on those ranks weighted by
    population share.  The slope index of inequality (SII) is the fitted
    difference between the highest (rank 1) and lowest (rank 0) ends of
    the distribution, in the indicator's units; the relative index of
    inequality (RII) is the ratio of those fitted values.  Positive SII
    (RII above 1) indicates higher values towards the upper strata.  The
    change in SII from the reference timepoint is also reported.

    Takes weighted mean rows (indicator, timepoint, stratum, value) and a
    dictionary of population weight totals keyed by (indicator,
    timepoint, stratum).  Returns rows with stratum 'all' and statistics
    'sii', 'rii' and 'sii_change'.
    """
    results = []
    for (indicator, timepoint), group in means.groupby(
        ['indicator', 'timepoint'],
        sort=False,
    ):
        group = group.sort_values('stratum')
        weights = np.array(
            [
                stratum_weights.get((indicator, timepoint, s), 0)
                for s in group['stratum']
            ],
            dtype=float,
        )
        values = pd.to_numeric(group['value'], errors='coerce').to_numpy()
        valid = ~np.isnan(values) & (weights > 0)
        if valid.sum() < 2:
            continue
        values, weights = values[valid], weights[valid]
        shares = weights / weights.sum()
        ranks = np.cumsum(shares) - shares / 2
        mean_rank = (shares * ranks).sum()
        mean_value = (shares * values).sum()
        denominator = (shares * (ranks - mean_rank) ** 2).sum()
        if denominator == 0:
            continue
        slope = (shares * (ranks - mean_rank) * (values - mean_value)).sum()
        slope = slope / denominator
        intercept = mean_value - slope * mean_rank
        rii = (intercept + slope) / intercept if intercept > 0 else np.nan
        for statistic, value in (('sii', slope), ('rii', rii)):
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'stratum': 'all',
                    'statistic': statistic,
                    'value': value,
                },
            )
    indices = pd.DataFrame(
        results,
        columns=['indicator', 'timepoint', 'stratum', 'statistic', 'value'],
    )
    if reference is None or len(indices) == 0:
        return indices
    changes = []
    sii = indices.loc[indices['statistic'] == 'sii']
    for indicator, group in sii.groupby('indicator', sort=False):
        baseline = group.loc[group['timepoint'] == reference, 'value']
        if len(baseline) == 0:
            continue
        for _, row in group.loc[group['timepoint'] != reference].iterrows():
            changes.append(
                {
                    'indicator': indicator,
                    'timepoint': row['timepoint'],
                    'stratum': 'all',
                    'statistic': 'sii_change',
                    'value': row['value'] - baseline.iloc[0],
                },
            )
    return pd.concat([indices, pd.DataFrame(changes)], ignore_index=True)


def stratified_summary(
    panel: pd.DataFrame,
    stratifier: pd.DataFrame,
    stratifier_column: str,
    weight: str = 'pop_est',
    quantiles=(0.1, 0.5, 0.9),
) -> pd.DataFrame:
    """
    Weighted summaries per stratum, indicator and timepoint.

    The stratifier DataFrame maps the panel's unit identifier column to
    a stratum assignment (e.g. a disadvantage index quintile) held fixed
    over time.  Computes the weighted mean and requested quantiles per
    stratum for each indicator and timepoint, the gap between the top
    and bottom strata and its change relative to the first timepoint,
    and (when three or more timepoints have a numeric 'year' column) a
    simple per-stratum linear trend in the weighted mean (slope per
    year).  Returns a tidy DataFrame with columns: indicator, timepoint,
    stratum, statistic, value.
    """
    unit = _panel_unit_column(panel)
    if unit not in stratifier.columns:
        raise ValueError(
            f"Stratifier must include the panel unit column '{unit}'.",
        )
    timepoints = _panel_timepoints(panel)
    # a time-matched stratifier assigns strata per timepoint
    keys = [unit]
    if 'timepoint' in stratifier.columns:
        keys.append('timepoint')
    left = panel.copy()
    right = stratifier[keys + [stratifier_column]].copy()
    for frame in (left, right):
        frame[unit] = _as_id(frame[unit])
        if 'timepoint' in keys:
            frame['timepoint'] = frame['timepoint'].astype(str)
    merged = left.merge(right, on=keys, how='inner')
    unmatched = len(panel) - len(merged)
    if unmatched:
        print(
            f'Note: {unmatched} panel rows had no stratum assignment '
            'and were excluded from stratified summaries.',
        )
    results = []
    stratum_weights = {}
    for (indicator, timepoint, stratum), group in merged.groupby(
        ['indicator', 'timepoint', stratifier_column],
        sort=False,
    ):
        values = pd.to_numeric(group['value'], errors='coerce')
        weights = (
            pd.to_numeric(group[weight], errors='coerce')
            if weight in group.columns
            else pd.Series(np.ones(len(group)), index=group.index)
        )
        valid = ~values.isna() & ~weights.isna()
        total = weights[valid].sum()
        stratum_weights[(indicator, timepoint, stratum)] = total
        mean = (
            (values[valid] * weights[valid]).sum() / total if total else np.nan
        )
        results.append(
            {
                'indicator': indicator,
                'timepoint': timepoint,
                'stratum': stratum,
                'statistic': 'weighted_mean',
                'value': mean,
            },
        )
        estimates = weighted_quantile(values, weights, quantiles)
        for q, value in zip(np.atleast_1d(quantiles), estimates):
            results.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'stratum': stratum,
                    'statistic': f'p{round(q * 100):d}',
                    'value': value,
                },
            )
    summary = pd.DataFrame(results)
    if len(summary) == 0:
        return summary
    # gap between top and bottom strata, and its change over time
    strata = sorted(summary['stratum'].unique())
    bottom, top = strata[0], strata[-1]
    means = summary.loc[summary['statistic'] == 'weighted_mean']
    gaps = []
    for (indicator, timepoint), group in means.groupby(
        ['indicator', 'timepoint'],
        sort=False,
    ):
        by_stratum = group.set_index('stratum')['value']
        if bottom in by_stratum.index and top in by_stratum.index:
            gaps.append(
                {
                    'indicator': indicator,
                    'timepoint': timepoint,
                    'stratum': f'{top}-{bottom}',
                    'statistic': 'stratum_gap',
                    'value': by_stratum[top] - by_stratum[bottom],
                },
            )
    gaps_df = pd.DataFrame(gaps)
    reference = timepoints[0]
    changes = []
    for indicator, group in gaps_df.groupby('indicator', sort=False):
        baseline = group.loc[group['timepoint'] == reference, 'value']
        if len(baseline) == 0:
            continue
        for _, row in group.iterrows():
            if row['timepoint'] == reference:
                continue
            changes.append(
                {
                    'indicator': indicator,
                    'timepoint': row['timepoint'],
                    'stratum': row['stratum'],
                    'statistic': 'stratum_gap_change',
                    'value': row['value'] - baseline.iloc[0],
                },
            )
    inequality = inequality_indices(means, stratum_weights, reference)
    summary = pd.concat(
        [summary, gaps_df, pd.DataFrame(changes), inequality],
        ignore_index=True,
    )
    # per-stratum linear trend when three or more timepoints have distinct
    # years (not so for the scenarios of a sensitivity analysis)
    years = None
    if 'year' in merged.columns:
        years = (
            merged[['timepoint', 'year']]
            .drop_duplicates()
            .set_index('timepoint')['year']
        )
        years = pd.to_numeric(years, errors='coerce').dropna()
    if years is not None and years.nunique() >= 3:
        trends = []
        for (indicator, stratum), group in means.groupby(
            ['indicator', 'stratum'],
            sort=False,
        ):
            observed = group.set_index('timepoint')['value'].reindex(
                years.index,
            )
            valid = ~observed.isna()
            if valid.sum() >= 3:
                slope = np.polyfit(
                    years[valid].astype(float),
                    observed[valid].astype(float),
                    1,
                )[0]
                trends.append(
                    {
                        'indicator': indicator,
                        'timepoint': 'all',
                        'stratum': stratum,
                        'statistic': 'trend_per_year',
                        'value': slope,
                    },
                )
        summary = pd.concat(
            [summary, pd.DataFrame(trends)],
            ignore_index=True,
        )
    summary.attrs['timepoints'] = timepoints
    return summary


class Timepoint:
    """A study region member of a longitudinal series."""

    def __init__(self, region, label=None, year=None, policy_review=None):
        self.region = region
        self.codename = region.codename
        if year is not None:
            self.year = year
        else:
            self.year = region.config.get('year')
        if label is not None:
            self.label = str(label)
        else:
            self.label = str(self.year)
        if policy_review is not None:
            self.has_policy = bool(policy_review)
        else:
            configured = region.config.get('policy_review')
            self.has_policy = bool(configured) and os.path.isfile(
                str(configured),
            )

    def __repr__(self):
        return (
            f'Timepoint({self.label}: {self.codename}, year={self.year}, '
            f'policy={self.has_policy})'
        )


def load_series_config(series: str) -> dict:
    """
    Load and validate a series configuration file.

    A name containing a path separator or ending in .yml is resolved as
    a path (absolute, or relative to the process directory); a bare name
    is looked up in configuration/regions, then within subfolders of the
    data directory (the preferred location, e.g.
    data/AU/AU_Melbourne_series.yml).
    """
    ghsci = _ghsci()
    from validate_config import validate_yaml_schema

    name_stem = str(series).replace('.yml', '')
    candidates = []
    if os.path.dirname(name_stem):
        if os.path.isabs(name_stem):
            candidates = [f'{name_stem}.yml']
        else:
            candidates = [f'{ghsci.folder_path}/process/{name_stem}.yml']
    else:
        configured = f'{ghsci.config_path}/regions/{name_stem}.yml'
        if os.path.isfile(configured):
            candidates = [configured]
        else:
            candidates = sorted(
                glob.glob(f'{ghsci.data_path}/*/{name_stem}.yml')
                + glob.glob(f'{ghsci.data_path}/*/*/{name_stem}.yml'),
            )
        if len(candidates) == 0:
            # a study region configuration defining its own series,
            # located wherever region configurations are discovered
            candidates = ghsci.get_region_configs().get(name_stem, [])
    if len(candidates) == 0:
        raise FileNotFoundError(
            f"Series configuration '{series}' could not be located in "
            f'{ghsci.config_path}/regions or subfolders of '
            f'{ghsci.data_path}.',
        )
    if len(candidates) > 1:
        raise ValueError(
            f"Series name '{series}' is ambiguous; candidates found: "
            f'{candidates}.  Please supply a path relative to the '
            'process directory.',
        )
    yaml_path = candidates[0]
    schema = f'{ghsci.config_path}/regions/series-json-schema.json'
    config = ghsci.load_yaml(yaml_path)
    if (
        isinstance(config, dict)
        and 'timepoints' not in config
        and ghsci.get_series_timepoints(config)
    ):
        from validate_config import validate_config_dict

        base_codename = os.path.basename(name_stem)
        codename = (config.get('series') or {}).get('codename')
        config = series_config_from_region(config, yaml_path)
        if not validate_config_dict(config, schema):
            raise ValueError(
                f"The 'series' block of {yaml_path} failed schema "
                'validation; please address the errors reported above.',
            )
        config['yaml'] = yaml_path
        config['codename'] = codename or f'{base_codename}_series'
        return config
    if not isinstance(config, dict) or 'timepoints' not in config:
        raise ValueError(
            f'{yaml_path} does not appear to be a series configuration '
            "(no top-level 'timepoints' key, or 'series' block).  Study "
            'region configurations are loaded using ghsci.Region().',
        )
    if not validate_yaml_schema(yaml_path, schema):
        raise ValueError(
            f'Series configuration {yaml_path} failed schema '
            'validation; please address the errors reported above.',
        )
    config['yaml'] = yaml_path
    config['codename'] = os.path.basename(name_stem)
    return config


def series_config_from_region(region_config: dict, yaml_path: str) -> dict:
    """
    Express a region configuration's 'series' block as a series configuration.

    Each timepoint becomes a member region referenced as
    '{yaml_path}::{key}' (a series variant, see ghsci.Region), labelled by
    its configured label or key.  The returned dictionary follows the
    series configuration schema.
    """
    ghsci = _ghsci()
    series = region_config.get('series') or {}
    timepoints = []
    labels = {}
    for key, spec in ghsci.get_series_timepoints(region_config).items():
        label = str(spec.get('label', key))
        labels[key] = label
        timepoint = {
            'region': f'{yaml_path}{ghsci.SERIES_VARIANT_SEPARATOR}{key}',
            'label': label,
        }
        if spec.get('year') is not None:
            timepoint['year'] = spec['year']
        if spec.get('policy_review') is not None:
            timepoint['policy_review'] = spec['policy_review']
        timepoints.append(timepoint)
    config = {
        'name': series.get('name') or region_config.get('name'),
        'country': region_config.get('country'),
        'timepoints': timepoints,
    }
    for key in (
        'description',
        'type',
        'reference',
        'alignment',
        'equity',
        'reporting',
        'composite',
    ):
        if series.get(key) is not None:
            config[key] = series[key]
    # a reference may be given by timepoint key; series refer to labels
    if 'reference' in config and str(config['reference']) in labels:
        config['reference'] = labels[str(config['reference'])]
    return config


def read_lookup(lookup) -> pd.DataFrame:
    """
    Read a stratifier lookup table.

    A string is a path to a CSV file relative to the process directory.
    An object reads a CSV or Excel file ('data', relative to the project
    data directory) with optional reading options ('sheet', 'header',
    'skiprows', 'skipfooter', 'usecols', 'names'), so that an original
    release (e.g. an ABS SEIFA workbook) can be used directly.
    """
    ghsci = _ghsci()
    if isinstance(lookup, str):
        path = (
            lookup
            if os.path.isabs(lookup)
            else f'{ghsci.folder_path}/process/{lookup}'
        )
        options = {}
    else:
        options = dict(lookup)
        data = options.pop('data')
        path = data if os.path.isabs(data) else f'{ghsci.data_path}/{data}'
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f'The stratifier lookup table {path} could not be located.',
        )
    extension = os.path.splitext(path)[1].lower()
    if extension == '.xls':
        try:
            import xlrd  # noqa: F401
        except ImportError:
            raise ImportError(
                f'{os.path.basename(path)} is a legacy Excel (.xls) '
                'workbook, which cannot be read in this environment; '
                'please open and re-save it in .xlsx format, and update '
                'the configured lookup path.',
            )
    if extension in ('.xls', '.xlsx', '.xlsm'):
        if 'sheet' in options:
            options['sheet_name'] = options.pop('sheet')
        table = pd.read_excel(path, **options)
    else:
        options.pop('sheet', None)
        if options.get('skipfooter'):
            options['engine'] = 'python'
        table = pd.read_csv(path, **options)
    return table.dropna(how='all')


def _as_id(values: pd.Series) -> pd.Series:
    """Normalise identifiers to strings for joining (e.g. 2.0 and '2')."""
    numeric = pd.to_numeric(values, errors='coerce')
    if numeric.notna().all() and (numeric % 1 == 0).all():
        return numeric.astype('int64').astype(str)
    return (
        values.astype(str)
        .str.strip()
        .str.replace(
            r'\.0$',
            '',
            regex=True,
        )
    )


class Series:
    """
    An ordered longitudinal series of study region timepoints.

    Initialise with the name or path of a series configuration file, or
    with a list of region codenames, paths or Region objects for a
    runtime series with default settings.
    """

    def __init__(self, series, labels: list = None, reference=None):
        ghsci = _ghsci()
        if isinstance(series, (list, tuple)):
            self.config = {}
            self.codename = None
            timepoints = []
            for i, member in enumerate(series):
                region = (
                    member
                    if isinstance(member, ghsci.Region)
                    else ghsci.Region(member)
                )
                label = (
                    labels[i]
                    if labels is not None and i < len(labels)
                    else None
                )
                timepoints.append(Timepoint(region, label=label))
        else:
            self.config = load_series_config(series)
            self.codename = self.config['codename']
            timepoints = []
            for spec in self.config['timepoints']:
                region = ghsci.Region(spec['region'])
                timepoints.append(
                    Timepoint(
                        region,
                        label=spec.get('label'),
                        year=spec.get('year'),
                        policy_review=spec.get('policy_review'),
                    ),
                )
            if reference is None:
                reference = self.config.get('reference')
        codenames = [tp.codename for tp in timepoints]
        if len(set(codenames)) != len(codenames):
            raise ValueError(
                f'Series timepoints must have unique codenames; '
                f'received {codenames}.',
            )
        self.type = self.config.get('type', 'longitudinal')
        # order by year (retaining input order for ties); the scenarios of a
        # sensitivity analysis retain their configured order
        if self.type == 'sensitivity':
            order = list(range(len(timepoints)))
        else:
            order = sorted(
                range(len(timepoints)),
                key=lambda i: (
                    (
                        timepoints[i].year
                        if timepoints[i].year is not None
                        else float('inf')
                    ),
                    i,
                ),
            )
        self.timepoints = [timepoints[i] for i in order]
        # de-duplicate labels using codenames where required
        labels_seen = {}
        for tp in self.timepoints:
            if tp.label in labels_seen:
                tp.label = f'{tp.label} ({tp.codename})'
            labels_seen[tp.label] = tp
        if self.codename is None:
            self.codename = self._derive_codename()
        self.reference = self._resolve_reference(reference)
        self.output_dir = self._resolve_output_dir()
        self._alignment = None
        self._crosswalks = {}

    def __repr__(self):
        members = ', '.join(
            f'{tp.label} ({tp.codename})' for tp in self.timepoints
        )
        return f'Series({self.codename}: {members})'

    @property
    def labels(self) -> list:
        """Ordered timepoint labels."""
        return [tp.label for tp in self.timepoints]

    def _derive_codename(self) -> str:
        """Derive a series codename from member codenames."""
        codenames = [tp.codename for tp in self.timepoints]
        prefix = os.path.commonprefix(codenames).rstrip('_-')
        if len(prefix) >= 3:
            return f'{prefix}_series'
        return f'{codenames[0]}_series'

    def _resolve_reference(self, reference) -> Timepoint:
        """Resolve the reference timepoint by label or codename."""
        if reference is None:
            return self.timepoints[0]
        for tp in self.timepoints:
            if str(reference) in (tp.label, tp.codename):
                return tp
        raise ValueError(
            f"Reference '{reference}' does not match a timepoint label "
            f'or codename among {self.labels}.',
        )

    def _resolve_output_dir(self) -> str:
        """Resolve the series output directory (not yet created)."""
        ghsci = _ghsci()
        configured = (self.config.get('reporting') or {}).get('output_dir')
        if configured:
            if os.path.isabs(configured):
                return configured
            return f'{ghsci.folder_path}/process/{configured}'
        return f'{ghsci.data_path}/_study_region_outputs/{self.codename}'

    def _ensure_output_dir(self) -> str:
        """Create and return the series output directory."""
        os.makedirs(self.output_dir, exist_ok=True)
        return self.output_dir

    def _timepoint(self, label) -> Timepoint:
        """Return the timepoint with the given label or codename."""
        for tp in self.timepoints:
            if str(label) in (tp.label, tp.codename):
                return tp
        raise ValueError(
            f"Timepoint '{label}' not found among {self.labels}.",
        )

    def _alignment_settings(self) -> dict:
        """Alignment settings with configuration overrides applied."""
        settings = {
            'expect_shared_grid': True,
            'method': 'grid_id',
            'centroid_tolerance_m': 10,
            'min_shared_fraction': 0.95,
        }
        settings.update(self.config.get('alignment') or {})
        return settings

    def _get_columns(self, region, table) -> list:
        """List available columns of a region table (or its CSV export)."""
        df = region.get_df(f'SELECT * FROM {table} LIMIT 0')
        if df is not None:
            return list(df.columns)
        csv_path = (
            f"{region.config['region_dir']}/{region.codename}_{table}.csv"
        )
        if os.path.isfile(csv_path):
            return list(pd.read_csv(csv_path, nrows=0).columns)
        return []

    def _get_table_df(self, region, table, columns=None) -> pd.DataFrame:
        """Retrieve a region table (or its CSV export) as a DataFrame."""
        if columns:
            sql = f'SELECT {", ".join(columns)} FROM {table}'
        else:
            sql = f'SELECT * FROM {table}'
        df = region.get_df(sql)
        if df is None:
            csv_path = (
                f"{region.config['region_dir']}/"
                f'{region.codename}_{table}.csv'
            )
            if os.path.isfile(csv_path):
                df = pd.read_csv(csv_path)
                if columns:
                    df = df[[c for c in columns if c in df.columns]]
        if df is None:
            raise ValueError(
                f"Could not retrieve '{table}' for {region.codename} "
                'from its database or CSV output.  Please ensure '
                'analysis has been fully run for this region.',
            )
        return df

    def _fetch_grid_reference(self, timepoint: Timepoint) -> pd.DataFrame:
        """Fetch grid_id, population and centroid coordinates for a
        timepoint's grid summary (centroids omitted when only the CSV
        export is available)."""
        region = timepoint.region
        table = region.config['grid_summary']
        for geom in ('geom', 'geometry'):
            df = region.get_df(
                f'SELECT grid_id, pop_est, '
                f'ST_X(ST_Centroid({geom})) AS centroid_x, '
                f'ST_Y(ST_Centroid({geom})) AS centroid_y '
                f'FROM {table}',
            )
            if df is not None:
                return df
        df = self._get_table_df(region, table, columns=None)
        available = [c for c in ('grid_id', 'pop_est') if c in df.columns]
        return df[available]

    def validate_alignment(self, save: bool = False) -> dict:
        """
        Validate grid alignment across timepoints.

        Compares each timepoint's grid summary against the reference by
        grid_id and centroid position (see validate_grid_alignment),
        printing a summary and caching the result.  If centroids
        disagree beyond tolerance, a nearest-centroid crosswalk is
        constructed and applied by subsequent panel assembly, with a
        warning.  Set save=True to export the alignment report as CSV.
        """
        settings = self._alignment_settings()
        frames = {
            tp.label: self._fetch_grid_reference(tp) for tp in self.timepoints
        }
        report = validate_grid_alignment(
            frames,
            self.reference.label,
            centroid_tolerance_m=settings['centroid_tolerance_m'],
            min_shared_fraction=settings['min_shared_fraction'],
        )
        for label, result in report.items():
            print(
                f"\n{label} vs {self.reference.label} (reference): "
                f"{result['n_shared']} shared cells "
                f"({result['shared_fraction']:.1%}), "
                f"{result['n_new']} new, {result['n_retired']} retired"
                + (
                    f", max centroid offset {result['max_offset_m']:.1f} m"
                    if result['max_offset_m'] is not None
                    else ''
                )
                + f" [{result['status']}]",
            )
            if result['status'] == 'error':
                raise ValueError(
                    f'Fewer than half of grid cells are shared between '
                    f'{label} and the reference timepoint.  These '
                    'regions do not appear to share a population grid; '
                    'please re-analyse timepoints against a common '
                    'population data source and boundary, or configure '
                    "alignment method 'spatial' to construct a "
                    'crosswalk.',
                )
        needs_crosswalk = settings['method'] == 'spatial' or any(
            result['max_offset_m'] is not None
            and result['max_offset_m'] > settings['centroid_tolerance_m']
            for result in report.values()
        )
        if needs_crosswalk:
            print(
                '\nWarning: grid centroids differ beyond tolerance; '
                'constructing nearest-centroid crosswalks.  Grid '
                'identifiers of comparison timepoints will be mapped to '
                'the nearest reference cell; results should be '
                'interpreted with care.',
            )
            for tp in self.timepoints:
                if tp.label == self.reference.label:
                    continue
                self._crosswalks[tp.label] = self._build_crosswalk(
                    frames[self.reference.label],
                    frames[tp.label],
                )
        self._alignment = report
        if save:
            self._ensure_output_dir()
            ghsci = _ghsci()
            path = (
                f'{self.output_dir}/{self.codename}_alignment_report_'
                f'{ghsci.date_hhmm}.csv'
            )
            pd.DataFrame(report).T.to_csv(path, index_label='timepoint')
            print(f'\nAlignment report saved as {path}')
        return report

    def _build_crosswalk(
        self,
        reference_frame: pd.DataFrame,
        frame: pd.DataFrame,
    ) -> pd.Series:
        """Map a timepoint's grid_id values to the nearest reference
        grid_id by centroid, within half the typical cell size."""
        import geopandas as gpd

        centroid_columns = {'centroid_x', 'centroid_y'}
        if not centroid_columns.issubset(
            reference_frame.columns,
        ) or not centroid_columns.issubset(frame.columns):
            raise ValueError(
                'Centroid coordinates are required to build a grid '
                'crosswalk; these are only available while the study '
                'region databases are accessible.',
            )
        crs = self.reference.region.config['crs_srid']
        reference_points = gpd.GeoDataFrame(
            reference_frame[['grid_id']],
            geometry=gpd.points_from_xy(
                reference_frame['centroid_x'],
                reference_frame['centroid_y'],
            ),
            crs=crs,
        )
        points = gpd.GeoDataFrame(
            frame[['grid_id']],
            geometry=gpd.points_from_xy(
                frame['centroid_x'],
                frame['centroid_y'],
            ),
            crs=crs,
        )
        # estimate cell size from typical nearest-neighbour spacing of
        # reference centroids
        xs = np.sort(reference_frame['centroid_x'].astype(float).unique())
        spacing = np.median(np.diff(xs)) if len(xs) > 1 else 100
        matched = gpd.sjoin_nearest(
            points,
            reference_points,
            how='inner',
            max_distance=spacing / 2,
            lsuffix='t',
            rsuffix='ref',
        )
        return matched.set_index('grid_id_t')['grid_id_ref']

    def _apply_crosswalk(
        self,
        df: pd.DataFrame,
        label: str,
        unit: str = 'grid_id',
    ) -> pd.DataFrame:
        """Apply a cached crosswalk to a timepoint's unit identifiers."""
        crosswalk = self._crosswalks.get(label)
        if crosswalk is None:
            return df
        df = df.copy()
        df[unit] = df[unit].map(crosswalk)
        return df.loc[~df[unit].isna()]

    def get_grid_panel(
        self,
        indicators: list = None,
        how: str = 'long',
    ) -> pd.DataFrame:
        """
        Assemble a grid indicator panel across timepoints.

        By default includes the neighbourhood indicator variables shared
        by all timepoints (reporting any dropped from individual
        timepoints); pass an explicit indicators list to keep indicators
        with partial coverage (missing values where unavailable).

        Returns a tidy long-format DataFrame with columns grid_id,
        timepoint, year, indicator, value and pop_est ('long', default),
        or a wide DataFrame indexed by grid_id with (indicator,
        timepoint) columns ('wide').
        """
        candidates = indicators
        if candidates is None:
            candidates = self.reference.region.indicators['output'][
                'neighbourhood_variables'
            ]
        return self._assemble_panel(
            candidates,
            table_for=lambda tp: tp.region.config['grid_summary'],
            unit_for=lambda tp: 'grid_id',
            unit='grid_id',
            intersect=indicators is None,
            how=how,
        )

    def get_area_panel(
        self,
        aggregation: str,
        indicators: list = None,
        how: str = 'long',
        timepoints: list = None,
    ) -> pd.DataFrame:
        """
        Assemble a custom aggregation area panel across timepoints.

        Reads the indicators_{aggregation} tables produced by each
        timepoint's custom aggregation configuration.  The aggregation's
        configured 'id' column provides the stable area identifier for
        joining across timepoints (a warning is issued if this defaults
        to the load-order dependent ogc_fid).  Output columns follow
        get_grid_panel with area_id in place of grid_id.  Optionally,
        the panel may be restricted to a list of timepoint labels (e.g.
        those for which an aggregation is configured).
        """

        def unit_for(tp):
            config = tp.region.config.get('custom_aggregations') or {}
            if aggregation not in config:
                raise ValueError(
                    f"Custom aggregation '{aggregation}' is not "
                    f'configured for {tp.codename}.',
                )
            id_column = config[aggregation].get('id') or 'ogc_fid'
            if id_column == 'ogc_fid':
                print(
                    f'Warning: the {aggregation} aggregation for '
                    f'{tp.codename} does not configure a stable id '
                    'column, defaulting to ogc_fid which is load-order '
                    'dependent; joins across timepoints may be '
                    'unreliable.',
                )
            return id_column

        candidates = indicators
        if candidates is None:
            candidates = self.reference.region.indicators['output'][
                'neighbourhood_variables'
            ]
        return self._assemble_panel(
            candidates,
            table_for=lambda tp: f'indicators_{aggregation}',
            unit_for=unit_for,
            unit='area_id',
            intersect=indicators is None,
            how=how,
            timepoints=timepoints,
        )

    def _assemble_panel(
        self,
        candidates: list,
        table_for,
        unit_for,
        unit: str,
        intersect: bool,
        how: str,
        timepoints: list = None,
    ) -> pd.DataFrame:
        """Assemble a long- or wide-format indicator panel."""
        if timepoints is None:
            members = self.timepoints
        else:
            selected = {str(label) for label in timepoints}
            members = [tp for tp in self.timepoints if tp.label in selected]
        labels = [tp.label for tp in members]
        available = {}
        for tp in members:
            columns = self._get_columns(tp.region, table_for(tp))
            available[tp.label] = [c for c in candidates if c in columns]
        if intersect:
            used = [
                c
                for c in candidates
                if all(c in cols for cols in available.values())
            ]
            for label, columns in available.items():
                dropped = [c for c in columns if c not in used]
                if dropped:
                    print(
                        f'Note: indicators not shared by all timepoints '
                        f'were excluded from the panel ({label}: '
                        f'{dropped}).',
                    )
        else:
            used = [
                c
                for c in candidates
                if any(c in cols for cols in available.values())
            ]
        if not used:
            raise ValueError(
                'None of the requested indicators are available across '
                'the series timepoints.',
            )
        frames = []
        for tp in members:
            source_unit = unit_for(tp)
            columns = [source_unit] + [
                c
                for c in ['pop_est'] + used
                if c in self._get_columns(tp.region, table_for(tp))
            ]
            df = self._get_table_df(
                tp.region,
                table_for(tp),
                columns=columns,
            )
            df = df.rename(columns={source_unit: unit})
            if unit == 'grid_id':
                df = self._apply_crosswalk(df, tp.label, unit)
            id_vars = [unit] + (['pop_est'] if 'pop_est' in df.columns else [])
            long = df.melt(
                id_vars=id_vars,
                value_vars=[c for c in used if c in df.columns],
                var_name='indicator',
                value_name='value',
            )
            long['timepoint'] = tp.label
            long['year'] = tp.year
            frames.append(long)
        panel = pd.concat(frames, ignore_index=True)
        ordered_columns = [unit, 'timepoint', 'year', 'indicator', 'value']
        if 'pop_est' in panel.columns:
            ordered_columns.append('pop_est')
        panel = panel[ordered_columns]
        panel.attrs['timepoints'] = labels
        panel.attrs['alignment'] = self._alignment
        if how == 'wide':
            wide = panel.pivot_table(
                index=unit,
                columns=['indicator', 'timepoint'],
                values='value',
            )
            wide.attrs['timepoints'] = labels
            return wide
        return panel

    def get_city_panel(self) -> pd.DataFrame:
        """
        Assemble the city summary panel: one row per timepoint.

        Returns a DataFrame indexed by timepoint label with the columns
        shared across all timepoints' city summaries (indicators_region)
        plus year and codename.
        """
        frames = {}
        for tp in self.timepoints:
            df = self._get_table_df(
                tp.region,
                tp.region.config['city_summary'],
            )
            frames[tp.label] = df.iloc[0]
        shared = [
            column
            for column in frames[self.timepoints[0].label].index
            if all(column in frame.index for frame in frames.values())
        ]
        panel = pd.DataFrame(
            {label: frame[shared] for label, frame in frames.items()},
        ).T
        panel.insert(0, 'codename', [tp.codename for tp in self.timepoints])
        panel.insert(1, 'year', [tp.year for tp in self.timepoints])
        panel.index.name = 'timepoint'
        return panel

    def get_policy_panel(self) -> pd.DataFrame:
        """
        Assemble the policy score panel: one row per timepoint.

        Presence and quality scores are derived from each covered
        timepoint's configured policy review checklist; timepoints
        without a policy review are retained with missing scores and
        assessed=False, supporting series with unequal policy coverage.
        """
        policy_report = _policy_report()
        rows = []
        for tp in self.timepoints:
            row = {
                'timepoint': tp.label,
                'codename': tp.codename,
                'year': tp.year,
                'assessed': tp.has_policy,
                'checklist_version': None,
                'presence_numerator': np.nan,
                'presence_denominator': np.nan,
                'presence_pct': np.nan,
                'quality_numerator': np.nan,
                'quality_denominator': np.nan,
                'quality_pct': np.nan,
            }
            if tp.has_policy:
                checklist = tp.region.config['policy_review']
                setting = policy_report.get_policy_setting(checklist)
                if setting is not None:
                    row['checklist_version'] = setting.get(
                        'Checklist version',
                    )
                scores = (
                    policy_report.get_policy_presence_quality_score_dictionary(
                        checklist,
                    )
                )
                if scores is not None:
                    for measure in ('presence', 'quality'):
                        numerator = scores[measure]['numerator']
                        denominator = scores[measure]['denominator']
                        row[f'{measure}_numerator'] = numerator
                        row[f'{measure}_denominator'] = denominator
                        row[f'{measure}_pct'] = (
                            100 * numerator / denominator
                            if denominator
                            else np.nan
                        )
                else:
                    row['assessed'] = False
            rows.append(row)
        return pd.DataFrame(rows).set_index('timepoint')

    def compute_change(
        self,
        panel: pd.DataFrame = None,
        pairs: str = 'reference',
        metrics: tuple = None,
    ) -> pd.DataFrame:
        """
        Compute change metrics for a panel (grid panel by default).

        See the module-level compute_change for details; the series
        reference timepoint anchors 'reference' pairing.
        """
        if panel is None:
            panel = self.get_grid_panel()
        return compute_change(
            panel,
            pairs=pairs,
            reference=self.reference.label,
            metrics=metrics,
        )

    def _equity_settings(self) -> dict:
        """Equity settings with configuration overrides applied."""
        settings = {
            'thresholds': 'default',
            'quantiles': list(DEFAULT_QUANTILES),
            'stratification': [],
        }
        settings.update(self.config.get('equity') or {})
        return settings

    def _default_thresholds(self, panel: pd.DataFrame) -> dict:
        """Default thresholds: 100% access within bounded indicators."""
        return {
            indicator: {'threshold': 100, 'relationship': 'greater_equal'}
            for indicator in panel['indicator'].unique()
            if classify_indicator(indicator) == 'bounded_pct'
        }

    def _stratification_for_timepoint(
        self,
        stratification: dict,
        label: str,
    ) -> dict:
        """
        Resolve a time-matched stratification's settings for a timepoint.

        Settings given for the timepoint under 'by_timepoint' override the
        stratification's defaults.  Returns None where no aggregation is
        configured for the timepoint (it is then excluded).
        """
        configured = stratification.get('by_timepoint') or {}
        by_timepoint = {str(key): value for key, value in configured.items()}
        settings = {
            key: value
            for key, value in stratification.items()
            if key not in ('by_timepoint', 'reference_timepoint')
        }
        settings.update(by_timepoint.get(str(label)) or {})
        if not settings.get('aggregation'):
            return None
        return settings

    def _load_stratifier(self, stratification: dict) -> pd.DataFrame:
        """
        Load a stratifier table for stratified equity summaries.

        Reads the stratifier from the configured lookup table (joined by
        lookup_id) or directly from the aggregation table of the
        stratification's reference timepoint, whose stratum assignments
        are held fixed across the series.  Continuous stratifier values
        are cut into n_groups groups.  Returns a DataFrame with area_id
        and the stratifier column.

        A time-matched stratification ('by_timepoint') instead reads each
        timepoint's own stratifier (e.g. the disadvantage index of the
        nearest census, for that census's areas), and the returned
        DataFrame also has a timepoint column.
        """
        if stratification.get('by_timepoint'):
            column = stratification.get('stratifier_column') or 'stratum'
            frames = []
            for tp in self.timepoints:
                settings = self._stratification_for_timepoint(
                    stratification,
                    tp.label,
                )
                if settings is None:
                    print(
                        f'Note: no aggregation is configured for timepoint '
                        f'{tp.label} of the stratification '
                        f"'{stratification.get('name')}'; it is excluded.",
                    )
                    continue
                stratifier = self._read_stratifier(settings, tp)
                stratifier = stratifier.rename(
                    columns={settings.get('stratifier_column'): column},
                )
                stratifier['timepoint'] = tp.label
                frames.append(stratifier)
            if not frames:
                raise ValueError(
                    'No timepoints could be stratified for '
                    f"'{stratification.get('name')}'.",
                )
            return pd.concat(frames, ignore_index=True)
        reference_label = stratification.get(
            'reference_timepoint',
            self.reference.label,
        )
        return self._read_stratifier(
            stratification,
            self._timepoint(reference_label),
        )

    def _read_stratifier(self, stratification: dict, tp) -> pd.DataFrame:
        """Read one stratifier source for a timepoint (see _load_stratifier)."""
        aggregation = stratification['aggregation']
        column = stratification.get('stratifier_column')
        config = (tp.region.config.get('custom_aggregations') or {}).get(
            aggregation,
        ) or {}
        id_column = (
            stratification.get('lookup_id') or config.get('id') or 'ogc_fid'
        )
        lookup = stratification.get('lookup')
        if lookup:
            stratifier = read_lookup(lookup)
        else:
            stratifier = self._get_table_df(
                tp.region,
                f'indicators_{aggregation}',
            )
            # column names are lower cased on import to the database
            lowered = {c.lower(): c for c in stratifier.columns}
            id_column = lowered.get(str(id_column).lower(), id_column)
            column = lowered.get(str(column).lower(), column)
        if id_column not in stratifier.columns:
            raise ValueError(
                f"Stratifier id column '{id_column}' not found in "
                f"columns {list(stratifier.columns)} for "
                f"stratification '{stratification.get('name')}'.",
            )
        if column is None or column not in stratifier.columns:
            raise ValueError(
                f"Stratifier column '{column}' not found for "
                f"stratification '{stratification.get('name')}'; "
                f'available columns: {list(stratifier.columns)}.',
            )
        stratifier = (
            stratifier[[id_column, column]]
            .rename(columns={id_column: 'area_id'})
            .dropna()
        )
        stratifier['area_id'] = _as_id(stratifier['area_id'])
        numeric = pd.to_numeric(stratifier[column], errors='coerce')
        if numeric.notna().mean() > 0.5:
            # a numeric stratifier; rows without a value (e.g. areas
            # excluded from an index, or notes at the foot of a published
            # table) are omitted
            stratifier[column] = numeric
            stratifier = stratifier.dropna(subset=[column])
        if stratification.get('stratifier_column') != column:
            stratifier = stratifier.rename(
                columns={column: stratification.get('stratifier_column')},
            )
            column = stratification.get('stratifier_column')
        n_groups = stratification.get('n_groups')
        if (
            n_groups
            and pd.api.types.is_numeric_dtype(
                stratifier[column],
            )
            and stratifier[column].nunique() > n_groups
        ):
            stratifier[column] = (
                pd.qcut(
                    stratifier[column],
                    n_groups,
                    labels=False,
                    duplicates='drop',
                )
                + 1
            )
        return stratifier

    def stratified_equity(
        self,
        stratification: dict,
        indicators: list = None,
    ) -> pd.DataFrame:
        """
        Stratified summary of area indicators for one stratification.

        For a fixed stratification, the area panel of its aggregation is
        joined with the stratum assignments of its reference timepoint.
        For a time-matched stratification ('by_timepoint'), each
        timepoint's panel is drawn from its own aggregation and joined with
        its own stratum assignments.  See stratified_summary for the
        statistics returned (including slope and relative indices of
        inequality).
        """
        if isinstance(stratification, str):
            matches = [
                s
                for s in self._equity_settings()['stratification']
                if s.get('name') == stratification
            ]
            if not matches:
                raise ValueError(
                    f"No stratification named '{stratification}' is "
                    'configured for this series.',
                )
            stratification = matches[0]
        stratifier = self._load_stratifier(stratification)
        column = stratification.get('stratifier_column') or 'stratum'
        if 'timepoint' not in stratifier.columns:
            area_panel = self.get_area_panel(
                stratification['aggregation'],
                indicators=indicators,
            )
        else:
            panels = []
            for tp in self.timepoints:
                settings = self._stratification_for_timepoint(
                    stratification,
                    tp.label,
                )
                if settings is None:
                    continue
                panels.append(
                    self.get_area_panel(
                        settings['aggregation'],
                        indicators=indicators,
                        timepoints=[tp.label],
                    ),
                )
            labels = [label for p in panels for label in p.attrs['timepoints']]
            area_panel = pd.concat(panels, ignore_index=True)
            area_panel.attrs['timepoints'] = labels
        return stratified_summary(area_panel, stratifier, column)

    def analysis(self) -> None:
        """Run analysis for each timepoint (see also series_analysis)."""
        for tp in self.timepoints:
            print(f'\n{tp.label}: {tp.codename}')
            tp.region.analysis()

    def generate(self) -> None:
        """Generate outputs for each timepoint (see also series_analysis)."""
        for tp in self.timepoints:
            print(f'\n{tp.label}: {tp.codename}')
            tp.region.generate()

    def equity_summary(
        self,
        level: str = 'grid',
        indicators: list = None,
        save: bool = True,
    ) -> dict:
        """
        Distributional and stratified equity summary of change.

        Computes population-weighted quantiles, quantile gaps, low- and
        high-end change, concentration indices and threshold population
        shares for the grid panel (level='grid', default) or a custom
        aggregation area panel (level=<aggregation name>), plus
        stratified summaries for any configured stratifications.

        Returns a dictionary of tidy DataFrames ('quantiles', 'gaps',
        'ends', 'concentration', 'thresholds' and 'stratified'), each
        exported as CSV to the series output directory when save=True.
        """
        ghsci = _ghsci()
        settings = self._equity_settings()
        if level == 'grid':
            panel = self.get_grid_panel(indicators=indicators)
        else:
            panel = self.get_area_panel(level, indicators=indicators)
        quantile_df = weighted_quantiles(
            panel,
            quantiles=settings['quantiles'],
        )
        thresholds = settings['thresholds']
        if thresholds == 'default' or thresholds is None:
            thresholds = self._default_thresholds(panel)
        summary = {
            'quantiles': quantile_df,
            'gaps': quantile_gaps(quantile_df),
            'ends': low_high_end_change(quantile_df),
            'concentration': concentration_index(panel),
            'thresholds': population_below_threshold(panel, thresholds),
            'stratified': {},
        }
        for stratification in settings['stratification']:
            name = stratification.get('name') or stratification.get(
                'aggregation',
            )
            summary['stratified'][name] = self.stratified_equity(
                stratification,
                indicators=indicators,
            )
        if save:
            self._ensure_output_dir()
            exports = {
                'quantiles': (
                    f'{self.codename}_equity_quantiles_{ghsci.date_hhmm}.csv'
                ),
                'gaps': (f'{self.codename}_equity_gaps_{ghsci.date_hhmm}.csv'),
                'ends': (
                    f'{self.codename}_equity_low_high_end_'
                    f'{ghsci.date_hhmm}.csv'
                ),
                'concentration': (
                    f'{self.codename}_equity_concentration_'
                    f'{ghsci.date_hhmm}.csv'
                ),
                'thresholds': (
                    f'{self.codename}_equity_thresholds_'
                    f'{ghsci.date_hhmm}.csv'
                ),
            }
            for key, filename in exports.items():
                if len(summary[key]) > 0:
                    summary[key].to_csv(
                        f'{self.output_dir}/{filename}',
                        index=False,
                    )
                    print(f'Saved {filename}')
            for name, stratified in summary['stratified'].items():
                filename = (
                    f'{self.codename}_equity_stratified_{name}_'
                    f'{ghsci.date_hhmm}.csv'
                )
                stratified.to_csv(
                    f'{self.output_dir}/{filename}',
                    index=False,
                )
                print(f'Saved {filename}')
        return summary

    def compare(self, save: bool = False) -> pd.DataFrame:
        """City summary comparison table (delegates to compare.py)."""
        from compare import compare as compare_regions

        regions = [tp.region for tp in self.timepoints]
        if len(regions) == 2:
            return compare_regions(regions[0], regions[1], save=save)
        return compare_regions(regions[:-1], regions[-1], save=save)

    def _composite_settings(self) -> dict:
        """Composite index settings with configuration overrides applied."""
        settings = {'goalposts': 'pooled'}
        settings.update(self.config.get('composite') or {})
        return settings

    def composite_index(
        self,
        names: list = None,
        goalposts: str = None,
        write: bool = True,
        save: bool = True,
    ) -> pd.DataFrame:
        """
        Score the timepoints' composite indices against shared goalposts.

        Each timepoint's composite indices (its 'composite_indices'
        configuration) are otherwise scored against goalposts resolved from
        that timepoint's own data, which describes a timepoint but cannot
        compare timepoints: the same score could mean different things.
        Here the goalposts are resolved once for the series and every
        timepoint is re-scored against them.  By default ('pooled') they span
        every timepoint and are centred on the reference timepoint, the
        Adjusted Mazziotta-Pareto Index approach to absolute comparisons over
        time; 'reference' takes both from the reference timepoint alone.

        With write (default), each timepoint's scores are re-written at every
        scale; with save (default), the shared goalposts are written to the
        series output folder, from where they can be supplied to score a
        further timepoint consistently.  Returns the grid panel of index and
        domain scores, for compute_change() and the equity summaries.
        """
        try:
            from subprocesses import _composite_index as ci
        except ImportError:
            import _composite_index as ci
        import yaml

        mode = goalposts or self._composite_settings()['goalposts']
        specs = ci.composite_index_config(self.reference.region)
        if specs is None:
            raise ValueError(
                'No composite indices are configured for the reference '
                f'timepoint ({self.reference.codename}).',
            )
        if names is not None:
            specs = {name: specs[name] for name in names}
        for tp in self.timepoints:
            configured = ci.composite_index_config(tp.region) or {}
            for name, spec in specs.items():
                if configured.get(name) != spec:
                    print(
                        f"Note: composite index '{name}' is configured "
                        f'differently for {tp.label}; the reference '
                        f'timepoint definition ({self.reference.label}) is '
                        'used throughout.',
                    )
        frames = [
            ci.load_indicator_frame(tp.region, specs.values())
            for tp in self.timepoints
        ]
        reference = self.timepoints.index(self.reference)
        parameters = {}
        for name, spec in specs.items():
            prepared = [ci.prepare(frame, spec) for frame in frames]
            parameters[name] = ci.series_parameters(
                prepared,
                spec,
                reference=reference,
                goalposts=mode,
            )
            parameters[name]['series'] = {
                'codename': self.codename,
                'goalposts': mode,
                'reference': self.reference.label,
                'timepoints': self.labels,
            }
        if save:
            self._ensure_output_dir()
            path = os.path.join(
                self.output_dir,
                f'{self.codename}_composite_goalposts.yml',
            )
            with open(path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    {'indices': parameters},
                    f,
                    sort_keys=False,
                    allow_unicode=True,
                )
            print(f'Shared composite index goalposts: {path}')
        if write:
            for tp in self.timepoints:
                print(f'\n{tp.label} ({tp.codename}):')
                tp.region.composite_index(goalposts=parameters)
        return self.get_grid_panel(
            indicators=[
                column
                for spec in specs.values()
                for column in ci.index_columns(spec)
            ],
        )

    def save_panels(self, pairs: str = 'reference') -> dict:
        """
        Export grid, city, policy and change panels as CSV files.

        Returns a dictionary of the saved paths.
        """
        ghsci = _ghsci()
        self._ensure_output_dir()
        paths = {}
        grid_panel = self.get_grid_panel()
        exports = {
            'grid_panel': (
                grid_panel,
                f'{self.codename}_longitudinal_grid_panel_'
                f'{ghsci.date_hhmm}.csv',
            ),
            'change': (
                self.compute_change(grid_panel, pairs=pairs),
                f'{self.codename}_longitudinal_change_{pairs}_'
                f'{ghsci.date_hhmm}.csv',
            ),
            'city_panel': (
                self.get_city_panel(),
                f'{self.codename}_longitudinal_city_panel_'
                f'{ghsci.date_hhmm}.csv',
            ),
            'policy_panel': (
                self.get_policy_panel(),
                f'{self.codename}_policy_panel_{ghsci.date_hhmm}.csv',
            ),
        }
        for key, (df, filename) in exports.items():
            path = f'{self.output_dir}/{filename}'
            df.to_csv(
                path,
                index=key in ('city_panel', 'policy_panel'),
            )
            paths[key] = path
            print(f'Saved {filename}')
        # data dictionary describing the panel schema and the indicators
        # observed across the series' timepoints
        try:
            try:
                from subprocesses.data_dictionary import save_series_dictionary
            except ImportError:
                from data_dictionary import save_series_dictionary

            indicators = list(
                dict.fromkeys(
                    list(grid_panel['indicator'].unique())
                    + [
                        column
                        for column in exports['city_panel'][0].columns
                        if column not in ('codename', 'year')
                    ],
                ),
            )
            dictionary_paths = save_series_dictionary(self, indicators)
            for key, path in dictionary_paths.items():
                paths[f'data_dictionary_{key}'] = path
                print(f'Saved {os.path.basename(path)}')
        except Exception as e:
            print(f'Data dictionary generation skipped ({e}).')
        return paths

    def generate_figures(self, language: str = 'English') -> dict:
        """Generate longitudinal figures (see longitudinal_plots)."""
        try:
            from subprocesses.longitudinal_plots import (
                generate_longitudinal_figures,
            )
        except ImportError:
            from longitudinal_plots import generate_longitudinal_figures
        return generate_longitudinal_figures(self, language=language)

    def generate_report(
        self,
        language: str = 'English',
        template=None,
        validate_language: bool = True,
    ) -> None:
        """Generate longitudinal reports (see longitudinal_report)."""
        try:
            from subprocesses.longitudinal_report import (
                generate_longitudinal_report,
            )
        except ImportError:
            from longitudinal_report import generate_longitudinal_report
        return generate_longitudinal_report(
            self,
            language=language,
            template=template,
            validate_language=validate_language,
        )


def compare_longitudinal(
    regions: list,
    labels: list = None,
    reference=None,
) -> Series:
    """
    Convenience constructor for a runtime longitudinal series.

    Takes a list of region codenames, paths or Region objects, returns
    the Series (ordered by year) and prints its city summary panel.
    """
    series = Series(regions, labels=labels, reference=reference)
    panel = series.get_city_panel()
    with pd.option_context(
        'display.max_rows',
        None,
        'display.max_columns',
        None,
        'display.width',
        None,
    ):
        print(panel.T)
    return series


def _timepoint_configuration(region: str) -> tuple:
    """
    Resolve a series member's configuration without loading it as a Region.

    Returns a tuple of (codename, configuration dictionary, list of
    overridden parameters).
    """
    ghsci = _ghsci()
    variant = ghsci.resolve_series_variant(region)
    if variant is not None:
        path, base, key = variant
        base_config = ghsci._read_yaml_quietly(path)
        spec = ghsci.get_series_timepoints(base_config).get(key) or {}
        return (
            ghsci.series_variant_codename(base, key),
            ghsci.build_series_variant_config(path, key, base_config),
            sorted((spec.get('overrides') or {}).keys()),
        )
    stem = str(region).replace('.yml', '')
    codename = os.path.basename(stem)
    if os.path.dirname(stem):
        path = (
            f'{stem}.yml'
            if os.path.isabs(stem)
            else f'{ghsci.folder_path}/process/{stem}.yml'
        )
    else:
        path = ghsci.get_region_config_path(codename)
    return codename, ghsci._read_yaml_quietly(path), []


def _configured_data(config: dict) -> list:
    """List (parameter, data path) pairs configured for a study region."""
    ghsci = _ghsci()
    entries = []

    def add(parameter, data):
        if isinstance(data, str) and data.strip():
            entries.append((parameter, data.strip()))

    add(
        'study_region_boundary',
        (config.get('study_region_boundary') or {}).get('data'),
    )
    for block in ('urban_region', 'population', 'OpenStreetMap'):
        value = config.get(block)
        if isinstance(value, str):
            value = (ghsci.datasets.get(block) or {}).get(value) or {}
        if isinstance(value, dict):
            add(block, value.get('data') or value.get('data_dir'))
    intersections = (config.get('network') or {}).get('intersections') or {}
    add('network: intersections', intersections.get('data'))
    for name, aggregation in (config.get('custom_aggregations') or {}).items():
        data = (aggregation or {}).get('data')
        if isinstance(data, str) and not data.startswith('OSM:'):
            add(f'custom_aggregations: {name}', data)
    gtfs = config.get('gtfs_feeds') or {}
    if gtfs.get('folder'):
        root = ghsci.get_gtfs_folder_path(gtfs['folder'])
        feeds = [feed for feed in gtfs if feed != 'folder']
        for feed in feeds:
            entries.append((f'gtfs_feeds: {feed}', f'{root}/{feed}'))
        if not feeds:
            entries.append(('gtfs_feeds: folder', root))
    add('policy_review', config.get('policy_review'))
    return entries


def _configured_data_exists(data: str) -> bool:
    """Whether a configured data path (as used in configuration) exists."""
    ghsci = _ghsci()
    path = data.split('-where')[0].strip()
    if '.gpkg:' in path:
        path = path.split('.gpkg:')[0] + '.gpkg'
    if '.zip' in path and not path.endswith('.zip'):
        path = path.split('.zip')[0] + '.zip'
    if os.path.isabs(path):
        return os.path.exists(path)
    return any(
        os.path.exists(f'{root}/{path}')
        for root in (
            ghsci.data_path,
            ghsci.folder_path,
            f'{ghsci.folder_path}/process',
        )
    )


def describe_series(series) -> pd.DataFrame:
    """
    Describe the timepoints of a series without loading their regions.

    For each timepoint, prints its codename, year, overridden parameters
    and each configured input dataset, flagging data not yet located.  No
    database is accessed, so a series may be checked before its data are
    in place.  Returns a DataFrame with a row per configured dataset.
    """
    ghsci = _ghsci()
    config = load_series_config(series)
    print(
        f"\nSeries: {config.get('name')} ({config['codename']}; "
        f"{config.get('type', 'longitudinal')})",
    )
    rows = []
    for spec in config['timepoints']:
        try:
            codename, tp_config, overrides = _timepoint_configuration(
                spec['region'],
            )
        except Exception as e:
            print(f"\n  {spec.get('label', spec['region'])}: {e}")
            continue
        if not isinstance(tp_config, dict):
            print(
                f"\n  {spec.get('label', spec['region'])}: configuration "
                'could not be read.',
            )
            continue
        year = spec.get('year', tp_config.get('year'))
        label = str(spec.get('label', year))
        outputs = os.path.isdir(
            f'{ghsci.data_path}/_study_region_outputs/{codename}',
        )
        details = [f'year {year}']
        if overrides:
            details.append(f"overrides: {', '.join(overrides)}")
        if outputs:
            details.append('output folder exists')
        print(f"\n  {label}: {codename} ({'; '.join(details)})")
        for parameter, data in _configured_data(tp_config):
            exists = _configured_data_exists(data)
            print(
                f"    [{'found' if exists else 'MISSING':>7}] "
                f"{parameter}: {data.replace(ghsci.folder_path + '/', '')}",
            )
            rows.append(
                {
                    'timepoint': label,
                    'codename': codename,
                    'year': year,
                    'overrides': ', '.join(overrides),
                    'parameter': parameter,
                    'data': data,
                    'exists': exists,
                },
            )
    print()
    return pd.DataFrame(rows)


def series_analysis(series, generate: bool = False) -> dict:
    """
    Run analysis (and optionally generate outputs) for each series timepoint.

    Each timepoint is loaded and processed in turn; any whose
    configuration or data checks fail, or whose analysis fails, is
    reported and skipped so that the remaining timepoints are processed.
    Returns a dictionary of the outcome for each timepoint.
    """
    ghsci = _ghsci()
    config = load_series_config(series)
    outcomes = {}
    for spec in config['timepoints']:
        name = spec['region']
        label = str(spec.get('label', name))
        try:
            region = ghsci.Region(name)
            if region.config is None:
                raise ValueError('configuration could not be loaded')
            print(f'\n{label}: {region.codename}')
            region.analysis()
            if generate:
                region.generate()
            outcomes[label] = 'completed'
        except (Exception, SystemExit) as e:
            print(f'\nTimepoint {label} ({name}) was skipped: {e}\n')
            outcomes[label] = f'skipped: {e}'
    print('\nSeries processing summary:')
    for label, outcome in outcomes.items():
        print(f'  {label}: {outcome}')
    return outcomes
