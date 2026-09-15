"""
Figures for longitudinal (multi-timepoint) comparison of study regions.

Provides change-oriented figures for a longitudinal Series (see
subprocesses/longitudinal.py): small multiple choropleths, difference
choropleths on a diverging colour scale, dumbbell and slope charts of
sub-area change, distributional quantile bands and threshold trends, a
multi-timepoint access profile radar, and policy rating gauges marking
each assessed timepoint.

All figure functions return the saved path when a path is supplied, or
the matplotlib figure for interactive (e.g. notebook) use when path is
None.
"""

import os

import numpy as np
import pandas as pd

GREY12 = '#1f1f1f'


def _mm_scale(mm):
    """Scale millimetres for fpdf2 display (see _utils.fpdf2_mm_scale)."""
    return 2 * mm / 25.4


def _utils():
    """Return the _utils module, however it has been imported."""
    try:
        import subprocesses._utils as utils
    except ImportError:
        import _utils as utils
    return utils


def _longitudinal():
    """Return the longitudinal module, however it has been imported."""
    try:
        import subprocesses.longitudinal as longitudinal
    except ImportError:
        import longitudinal
    return longitudinal


def _batlow():
    """Return the batlow colormap."""
    try:
        from subprocesses.batlow import batlow_map
    except ImportError:
        from batlow import batlow_map
    return batlow_map


def _vik():
    """Return the vik diverging colormap (fallback: RdBu_r)."""
    try:
        try:
            from subprocesses.vik import vik_map
        except ImportError:
            from vik import vik_map
        return vik_map
    except ImportError:
        import matplotlib.pyplot as plt

        return plt.get_cmap('RdBu_r')


def _default_phrases(phrases: dict = None) -> dict:
    """Fill minimal phrase defaults for standalone figure generation."""
    defaults = {'north arrow': 'N', 'km': 'km'}
    if phrases:
        defaults.update(phrases)
    return defaults


def _save_or_return(fig, path, dpi=300, transparent=False):
    """Save a figure and return its path, or return the figure."""
    import matplotlib.pyplot as plt

    if path is None:
        return fig
    fig.savefig(path, dpi=dpi, transparent=transparent)
    plt.close(fig)
    return path


def _indicator_label(indicator: str, region=None, phrases=None) -> str:
    """
    Look up a display label for an indicator variable name.

    Prefers the descriptive label configured for the indicator's report
    figure in indicators.yml (localised via phrases where the label
    references a phrase key), then the output data dictionary, and
    finally the variable name itself.  Note that the report's own
    percentage phrases are deliberately not used here: they state a
    single city-wide percentage, which is not meaningful for a figure
    spanning several time points.
    """
    if region is not None:
        try:
            figures = region.indicators['report'][
                'spatial_distribution_figures'
            ]
            label = figures.get(indicator, {}).get('label')
        except (KeyError, TypeError, AttributeError):
            label = None
        if label:
            label = str(label)
            if phrases:
                try:
                    label = label.format(**phrases)
                except (KeyError, IndexError):
                    pass
            return label.strip('{}').strip()
    try:
        ghsci = _longitudinal()._ghsci()
        if indicator in ghsci.dictionary.index:
            return str(ghsci.dictionary.loc[indicator, 'Description']).strip()
    except Exception:
        pass
    # the reference dictionary describes permutable indicators once via
    # parameter placeholders, so resolve concrete variants directly
    try:
        try:
            from subprocesses.data_dictionary import describe_variable
        except ImportError:
            from data_dictionary import describe_variable
        category, description = describe_variable(str(indicator))
        if category != 'Other fields':
            return description
    except Exception:
        pass
    return indicator


def _grid_geometry(series):
    """Grid cell geometries of the series reference timepoint."""
    region = series.reference.region
    table = region.config['grid_summary']
    for geom_col in ('geom', 'geometry'):
        gdf = region.get_gdf(table, geom_col=geom_col)
        if gdf is not None:
            return gdf[['grid_id', geom_col]].set_geometry(geom_col)
    raise ValueError(
        f'Grid geometries for {region.codename} could not be retrieved; '
        'map figures require access to the study region database.',
    )


def _boundary_geometry(series):
    """Urban study region boundary of the series reference timepoint."""
    region = series.reference.region
    for table in (region.config['city_summary'], 'urban_study_region'):
        for geom_col in ('geom', 'geometry'):
            gdf = region.get_gdf(table, geom_col=geom_col)
            if gdf is not None:
                return gdf.set_geometry(geom_col)
    return None


def _map_axis_decorations(ax, gdf, phrases, locale, textsize=12):
    """Add scalebar and north arrow to a map axis."""
    import matplotlib.font_manager as fm

    utils = _utils()
    utils.add_scalebar(
        ax,
        length=int(
            (gdf.geometry.total_bounds[2] - gdf.geometry.total_bounds[0])
            / 3000,
        ),
        multiplier=1000,
        units='kilometer',
        locale=locale,
        fontproperties=fm.FontProperties(size=textsize),
    )
    utils.add_localised_north_arrow(ax, text=phrases['north arrow'])


def small_multiple_maps(
    series,
    indicator: str,
    panel: pd.DataFrame = None,
    label: str = None,
    range: tuple = None,
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    phrases: dict = None,
    locale: str = 'en',
):
    """
    Small multiple choropleths of an indicator, one panel per timepoint.

    Values are mapped on the shared reference grid with a common colour
    scale and single shared colour bar, so change in the spatial
    distribution can be read across panels.
    """
    import matplotlib.pyplot as plt

    phrases = _default_phrases(phrases)
    if cmap is None:
        cmap = _batlow()
    if label is None:
        label = _indicator_label(
            indicator,
            series.reference.region,
            phrases,
        )
    if panel is None:
        panel = series.get_grid_panel(indicators=[indicator])
    subset = panel.loc[panel['indicator'] == indicator]
    geometry = _grid_geometry(series)
    boundary = _boundary_geometry(series)
    timepoints = panel.attrs.get('timepoints', series.labels)
    n = len(timepoints)
    if width is None:
        width = _mm_scale(60 * n)
    if height is None:
        height = _mm_scale(70)
    if range is None:
        values = pd.to_numeric(subset['value'], errors='coerce')
        if indicator.startswith('pct_') or '_pct_' in indicator:
            range = (0, 100)
        else:
            range = (
                float(np.nanmin(values)),
                float(np.nanmax(values)),
            )
    fig, axes = plt.subplots(
        1,
        n,
        figsize=(width, height),
        constrained_layout=True,
    )
    axes = np.atleast_1d(axes)
    textsize = 12
    for i, (ax, timepoint) in enumerate(zip(axes, timepoints)):
        ax.set_axis_off()
        values = subset.loc[
            subset['timepoint'] == timepoint,
            ['grid_id', 'value'],
        ]
        gdf = geometry.merge(values, on='grid_id', how='left')
        if boundary is not None:
            boundary.boundary.plot(
                ax=ax,
                color='black',
                linewidth=0.8,
                alpha=0.5,
            )
        gdf.plot(
            column='value',
            ax=ax,
            vmin=range[0],
            vmax=range[1],
            cmap=cmap,
            alpha=0.9,
            missing_kwds={
                'color': 'none',
                'edgecolor': 'lightgrey',
                'hatch': '///',
                'linewidth': 0.05,
            },
        )
        ax.set_title(str(timepoint), fontsize=textsize)
        if i == 0:
            _map_axis_decorations(ax, geometry, phrases, locale, textsize)
    import matplotlib.cm as mpl_cm
    import matplotlib.colors as mpl_colors

    norm = mpl_colors.Normalize(vmin=range[0], vmax=range[1])
    colorbar = fig.colorbar(
        mpl_cm.ScalarMappable(norm=norm, cmap=cmap),
        ax=axes,
        orientation='horizontal',
        fraction=0.05,
        pad=0.02,
        shrink=0.6,
    )
    colorbar.set_label(label, size=textsize)
    colorbar.ax.tick_params(labelsize=textsize)
    return _save_or_return(fig, path, dpi)


def change_map(
    series,
    indicator: str,
    t0=None,
    t1=None,
    panel: pd.DataFrame = None,
    label: str = None,
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    phrases: dict = None,
    locale: str = 'en',
):
    """
    Difference choropleth of indicator change between two timepoints.

    Change (percentage point change for bounded percentage indicators,
    absolute difference otherwise) is mapped on the shared reference
    grid using a diverging colour scale centred on zero with symmetric
    robust limits (98th percentile of absolute change).  Cells present
    at only one timepoint (change in urban extent) are hatched.
    """
    import matplotlib.pyplot as plt

    longitudinal = _longitudinal()
    phrases = _default_phrases(phrases)
    if cmap is None:
        cmap = _vik()
    if panel is None:
        panel = series.get_grid_panel(indicators=[indicator])
    timepoints = panel.attrs.get('timepoints', series.labels)
    if t0 is None:
        t0 = timepoints[0]
    if t1 is None:
        t1 = timepoints[-1]
    metric = (
        'pp_change'
        if longitudinal.classify_indicator(indicator) == 'bounded_pct'
        else 'diff'
    )
    if label is None:
        unit_label = phrases.get(
            'percentage point change' if metric == 'pp_change' else 'change',
            'percentage point change' if metric == 'pp_change' else 'change',
        )
        indicator_label = _indicator_label(
            indicator,
            series.reference.region,
            phrases,
        )
        label = f'{indicator_label} ({unit_label}, {t0}-{t1})'
    subset = panel.loc[
        panel['indicator'] == indicator,
        ['grid_id', 'timepoint', 'value'],
    ]
    baseline = subset.loc[subset['timepoint'] == t0].set_index('grid_id')[
        'value'
    ]
    follow_up = subset.loc[subset['timepoint'] == t1].set_index('grid_id')[
        'value'
    ]
    change = (
        pd.DataFrame({'value_t0': baseline, 'value_t1': follow_up})
        .astype(float)
        .assign(change=lambda df: df['value_t1'] - df['value_t0'])
        .reset_index()
    )
    geometry = _grid_geometry(series)
    boundary = _boundary_geometry(series)
    gdf = geometry.merge(change, on='grid_id', how='left')
    absolute = gdf['change'].abs()
    limit = (
        float(np.nanpercentile(absolute, 98))
        if absolute.notna().any()
        else 1.0
    )
    limit = limit if limit > 0 else 1.0
    if width is None:
        width = _mm_scale(88)
    if height is None:
        height = _mm_scale(80)
    textsize = 12
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_axis_off()
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    divider = make_axes_locatable(ax)
    cax = divider.append_axes('bottom', size='5%', pad=0.1)
    if boundary is not None:
        boundary.boundary.plot(
            ax=ax,
            color='black',
            linewidth=1,
            alpha=0.5,
        )
    from textwrap import wrap

    gdf.plot(
        column='change',
        ax=ax,
        legend=True,
        vmin=-limit,
        vmax=limit,
        legend_kwds={
            'label': '\n'.join(wrap(label, 60, break_long_words=False)),
            'orientation': 'horizontal',
        },
        cax=cax,
        cmap=cmap,
        alpha=0.9,
        missing_kwds={
            'color': 'none',
            'edgecolor': 'lightgrey',
            'hatch': '///',
            'linewidth': 0.05,
        },
    )
    _map_axis_decorations(ax, geometry, phrases, locale, textsize)
    cax.tick_params(labelsize=textsize)
    cax.xaxis.label.set_size(textsize)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def dumbbell_chart(
    change_df: pd.DataFrame,
    indicator: str,
    t0=None,
    t1=None,
    metric: str = None,
    names: pd.Series = None,
    top_n: int = None,
    label: str = None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    region=None,
    phrases: dict = None,
):
    """
    Dumbbell chart of sub-area change between two timepoints.

    Takes a compute_change result for an area panel; each area is drawn
    as a line from its baseline to its follow-up value, sorted by
    baseline value.  When the change result contains several comparison
    pairs, the pair may be selected with t0/t1 (default: the pair
    spanning the longest period).  Optionally map area identifiers to
    display names (a Series indexed by area identifier) and restrict to
    the top_n areas by absolute change.
    """
    import matplotlib.pyplot as plt

    longitudinal = _longitudinal()
    unit = longitudinal._panel_unit_column(change_df)
    subset = change_df.loc[change_df['indicator'] == indicator]
    if metric is None:
        metric = subset['metric'].iloc[0]
    subset = subset.loc[subset['metric'] == metric].dropna(
        subset=['value_t0', 'value_t1'],
    )
    # restrict to a single comparison pair
    pairs = list(
        subset[['t0', 't1']].drop_duplicates().itertuples(index=False),
    )
    if t0 is None and t1 is None and len(pairs) > 1:
        timepoints = change_df.attrs.get('timepoints')
        if timepoints:
            span = {
                pair: abs(
                    timepoints.index(pair.t1) - timepoints.index(pair.t0),
                )
                for pair in pairs
                if pair.t0 in timepoints and pair.t1 in timepoints
            }
            t0, t1 = max(span, key=span.get) if span else pairs[0]
        else:
            t0, t1 = pairs[0]
    if t0 is not None:
        subset = subset.loc[subset['t0'] == t0]
    if t1 is not None:
        subset = subset.loc[subset['t1'] == t1]
    if len(subset) == 0:
        raise ValueError(
            f'No change results for {indicator} between the requested '
            'timepoints.',
        )
    if top_n is not None and len(subset) > top_n:
        subset = subset.reindex(
            subset['change'].abs().sort_values(ascending=False).index,
        ).head(top_n)
    subset = subset.sort_values('value_t0')
    if label is None:
        label = _indicator_label(indicator, region, phrases)
    t0 = subset['t0'].iloc[0]
    t1 = subset['t1'].iloc[0]
    display = subset[unit].astype(str)
    if names is not None:
        display = subset[unit].map(names).fillna(display)
    if width is None:
        width = _mm_scale(88)
    if height is None:
        height = _mm_scale(max(60, 5 * len(subset)))
    fig, ax = plt.subplots(figsize=(width, height))
    y = np.arange(len(subset))
    ax.hlines(
        y,
        subset['value_t0'],
        subset['value_t1'],
        color='lightgrey',
        linewidth=2,
        zorder=1,
    )
    baseline_dots = ax.scatter(
        subset['value_t0'],
        y,
        color='lightgrey',
        edgecolor=GREY12,
        s=40,
        zorder=2,
        label=str(t0),
    )
    follow_up_dots = ax.scatter(
        subset['value_t1'],
        y,
        color=GREY12,
        s=40,
        zorder=3,
        label=str(t1),
    )
    ax.set_yticks(y)
    ax.set_yticklabels(display)
    ax.set_xlabel(label)
    ax.legend(
        handles=[baseline_dots, follow_up_dots],
        frameon=False,
        loc='lower right',
    )
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def slope_chart(
    df: pd.DataFrame,
    y: str = 'value',
    x: str = 'timepoint',
    group: str = 'stratum',
    timepoints: list = None,
    label: str = None,
    group_label: str = None,
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
):
    """
    Slope chart of values per group across timepoints.

    Suitable for stratified trends (e.g. weighted mean access by
    disadvantage quintile over time, from stratified_summary rows with
    statistic 'weighted_mean') or for individual sub-areas.
    """
    import matplotlib.pyplot as plt

    if cmap is None:
        cmap = _batlow()
    if timepoints is None:
        timepoints = df.attrs.get('timepoints') or list(pd.unique(df[x]))
    timepoints = [t for t in timepoints if t in set(df[x])]
    if width is None:
        width = _mm_scale(88)
    if height is None:
        height = _mm_scale(70)
    fig, ax = plt.subplots(figsize=(width, height))
    groups = list(pd.unique(df[group]))
    positions = {t: i for i, t in enumerate(timepoints)}
    for i, member in enumerate(groups):
        series = (
            df.loc[df[group] == member].set_index(x)[y].reindex(timepoints)
        )
        colour = cmap(i / max(len(groups) - 1, 1))
        ax.plot(
            [positions[t] for t in timepoints],
            series.values,
            marker='o',
            color=colour,
            label=str(member),
        )
    ax.set_xticks(list(positions.values()))
    ax.set_xticklabels([str(t) for t in timepoints])
    if label:
        ax.set_ylabel(label)
    ax.legend(
        title=group_label or group,
        frameon=False,
        bbox_to_anchor=(1.02, 1),
        loc='upper left',
    )
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def quantile_band_plot(
    quantile_df: pd.DataFrame,
    indicator: str,
    label: str = None,
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    region=None,
    phrases: dict = None,
):
    """
    Distribution of an indicator over time as quantile bands.

    Plots the population-weighted median as a line with p25-p75 and
    p10-p90 bands per timepoint, summarising distributional change
    (narrowing bands indicate convergence).
    """
    import matplotlib.pyplot as plt

    if cmap is None:
        cmap = _batlow()
    if label is None:
        label = _indicator_label(indicator, region, phrases)
    timepoints = quantile_df.attrs.get('timepoints') or list(
        pd.unique(quantile_df['timepoint']),
    )
    wide = (
        quantile_df.loc[quantile_df['indicator'] == indicator]
        .pivot_table(index='timepoint', columns='q', values='value')
        .reindex(timepoints)
    )
    if width is None:
        width = _mm_scale(88)
    if height is None:
        height = _mm_scale(60)
    fig, ax = plt.subplots(figsize=(width, height))
    x = np.arange(len(wide))
    band_colour = cmap(0.35)
    if 0.1 in wide.columns and 0.9 in wide.columns:
        ax.fill_between(
            x,
            wide[0.1],
            wide[0.9],
            color=band_colour,
            alpha=0.25,
            label='p10-p90',
        )
    if 0.25 in wide.columns and 0.75 in wide.columns:
        ax.fill_between(
            x,
            wide[0.25],
            wide[0.75],
            color=band_colour,
            alpha=0.45,
            label='p25-p75',
        )
    if 0.5 in wide.columns:
        ax.plot(
            x,
            wide[0.5],
            color=GREY12,
            marker='o',
            label='median',
        )
    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in wide.index])
    ax.set_ylabel(label)
    ax.legend(frameon=False)
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def threshold_trend_plot(
    threshold_df: pd.DataFrame,
    labels: dict = None,
    ylabel: str = 'Population share (%)',
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    region=None,
    phrases: dict = None,
):
    """
    Population share meeting indicator thresholds over time.

    Takes a population_below_threshold result and plots one line per
    indicator (statistic 'pop_share_pct').
    """
    import matplotlib.pyplot as plt

    if cmap is None:
        cmap = _batlow()
    subset = threshold_df.loc[threshold_df['statistic'] == 'pop_share_pct']
    timepoints = threshold_df.attrs.get('timepoints') or list(
        pd.unique(subset['timepoint']),
    )
    if width is None:
        width = _mm_scale(110)
    if height is None:
        height = _mm_scale(70)
    fig, ax = plt.subplots(figsize=(width, height))
    indicators = list(pd.unique(subset['indicator']))
    positions = {t: i for i, t in enumerate(timepoints)}
    for i, indicator in enumerate(indicators):
        series = (
            subset.loc[subset['indicator'] == indicator]
            .set_index('timepoint')['value']
            .reindex(timepoints)
        )
        display = (
            labels.get(indicator, indicator)
            if labels
            else _indicator_label(indicator, region, phrases)
        )
        ax.plot(
            [positions[t] for t in timepoints],
            series.values,
            marker='o',
            color=cmap(i / max(len(indicators) - 1, 1)),
            label=display,
        )
    ax.set_xticks(list(positions.values()))
    ax.set_xticklabels([str(t) for t in timepoints])
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 100)
    ax.legend(
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(1.02, 1),
        loc='upper left',
    )
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def _format_point_change(change: float, phrases: dict = None) -> str:
    """Format a percentage point change with an explicit sign (e.g. +4.2 pp)."""
    phrases = phrases or {}
    unit = phrases.get('percentage points abbreviation', 'pp')
    try:
        from babel.numbers import format_decimal

        magnitude = format_decimal(
            abs(change),
            format='#,##0.0',
            locale=phrases.get('locale', 'en'),
        )
    except Exception:
        magnitude = f'{abs(change):.1f}'
    if round(change, 1) > 0:
        sign = '+'
    elif round(change, 1) < 0:
        sign = '−'
    else:
        sign = '±'
    return f'{sign}{magnitude} {unit}'


def access_profile_longitudinal(
    series,
    language: str = 'English',
    phrases: dict = None,
    title: str = None,
    cmap=None,
    width: int = 80,
    height: int = 100,
    dpi: int = 300,
    path: str = None,
    style: str = 'auto',
    timepoints: list = None,
    show_reference: bool = False,
    locale_profile=None,
):
    """
    Multi-timepoint access profile radar chart.

    Follows the layout of the single region access profile (see
    Region.access_profile), in one of the following styles:

    - 'change': the later of two timepoints is drawn as bars and the
      earlier as dashed bar outlines, with the difference between them
      shaded by direction of change and labelled in percentage points.
      Where more than two timepoints are selected, the reference and
      latest timepoints are compared;
    - 'grouped': each indicator arm is divided into a bar per timepoint,
      ordered clockwise in time and coloured by timepoint, to show trends;
    - 'markers': the latest timepoint is drawn as bars, with earlier
      timepoints overlaid as markers;
    - 'auto' (default): 'change' for two timepoints, otherwise 'grouped'.

    Optionally, 'timepoints' restricts the figure to a list of timepoint
    labels, and 'show_reference' adds the 25 city comparison medians and
    interquartile ranges.  Indicator labels report the latest timepoint's
    percentage (or the later timepoint's, for 'change').
    """
    import matplotlib.colors as mpl_colors
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    ghsci = _longitudinal()._ghsci()
    if cmap is None:
        cmap = _batlow()
    members = list(series.timepoints)
    if timepoints is not None:
        selected = [str(t) for t in timepoints]
        members = [tp for tp in members if tp.label in selected]
    if len(members) == 0:
        raise ValueError('No timepoints were selected for the access profile.')
    if style == 'auto':
        style = 'change' if len(members) == 2 else 'grouped'
    if style not in ('change', 'grouped', 'markers'):
        raise ValueError(
            f"Unknown access profile style '{style}'; expected 'auto', "
            "'change', 'grouped' or 'markers'.",
        )
    if style == 'change' and len(members) > 2:
        first = (
            series.reference
            if timepoints is None and series.reference in members[:-1]
            else members[0]
        )
        members = [first, members[-1]]
    latest = members[-1]
    if phrases is None:
        phrases = latest.region.get_phrases(language)
    if title is None:
        title = phrases['Population % with access within 500m to...']
    stats = {}
    latest_stats = None
    for tp in members:
        city_stats = tp.region.get_city_stats(phrases=phrases)
        if city_stats is not None:
            stats[tp.label] = city_stats['access']
            if tp is latest:
                latest_stats = city_stats
    if latest_stats is None:
        raise ValueError(
            'City statistics for the latest timepoint could not be '
            'retrieved; please confirm analysis has been run.',
        )
    index = stats[latest.label].index
    values = {
        label: pd.to_numeric(access.reindex(index), errors='coerce').values
        for label, access in stats.items()
    }
    labels_present = [tp.label for tp in members if tp.label in stats]
    angles = np.linspace(0.15, 2 * np.pi - 0.05, len(index), endpoint=False)
    bar_width = 0.52
    textsize = 10
    norm = mpl_colors.Normalize(vmin=0, vmax=100)
    fig, ax = plt.subplots(
        figsize=(_mm_scale(width), _mm_scale(height)),
        subplot_kw={'projection': 'polar'},
    )
    ax.set_theta_offset(1.2 * np.pi / 2)
    ax.set_ylim(-50, 125)
    handles = []
    label_values = values[latest.label]
    if style == 'change':
        if len(labels_present) < 2:
            raise ValueError(
                'The change style requires city statistics for two '
                'timepoints.',
            )
        earlier, later = labels_present[0], labels_present[-1]
        v0, v1 = values[earlier], values[later]
        change = v1 - v0
        diverging = _vik()
        increase, decrease = diverging(0.85), diverging(0.15)
        ax.bar(
            angles,
            v1,
            color=cmap(list(norm(v1))),
            alpha=0.9,
            width=bar_width,
            zorder=10,
        )
        ax.bar(
            angles,
            np.abs(change),
            bottom=np.minimum(v0, v1),
            width=bar_width,
            color=[increase if c > 0 else decrease for c in change],
            alpha=0.6,
            zorder=11,
        )
        ax.bar(
            angles,
            v0,
            width=bar_width,
            facecolor='none',
            edgecolor=GREY12,
            linewidth=1,
            linestyle=(0, (3, 2)),
            zorder=12,
        )
        for angle, top, difference in zip(
            angles,
            np.fmax(v0, v1),
            change,
        ):
            if np.isnan(difference):
                continue
            ax.text(
                angle,
                top + 10,
                _format_point_change(difference, phrases),
                ha='center',
                va='center',
                size=textsize - 2,
                zorder=13,
                bbox=dict(
                    facecolor='white',
                    edgecolor='none',
                    alpha=0.6,
                    pad=0.1,
                ),
            )
        handles = [
            Patch(
                facecolor='none',
                edgecolor=GREY12,
                linestyle='--',
                label=str(earlier),
            ),
            Patch(facecolor=cmap(0.55), alpha=0.9, label=str(later)),
            Patch(
                color=increase,
                alpha=0.6,
                label=phrases.get('Increase', 'Increase'),
            ),
            Patch(
                color=decrease,
                alpha=0.6,
                label=phrases.get('Decrease', 'Decrease'),
            ),
        ]
        label_values = v1
    elif style == 'grouped':
        n = len(labels_present)
        sub_width = bar_width / n
        positions = np.linspace(0.1, 0.8, n) if n > 1 else [0.5]
        for i, label in enumerate(labels_present):
            # decreasing angle runs clockwise on the polar axis
            offset = bar_width / 2 - sub_width * (i + 0.5)
            colour = cmap(positions[i])
            ax.bar(
                angles + offset,
                values[label],
                width=sub_width * 0.92,
                color=colour,
                alpha=0.9,
                zorder=10,
            )
            handles.append(Patch(color=colour, alpha=0.9, label=str(label)))
    else:
        ax.bar(
            angles,
            label_values,
            color=cmap(list(norm(label_values))),
            alpha=0.9,
            width=bar_width,
            zorder=10,
        )
        handles.append(Patch(facecolor=cmap(0.55), label=str(latest.label)))
        markers = ['o', 's', 'D', 'v', 'P']
        for i, label in enumerate(labels_present[:-1]):
            marker = markers[i % len(markers)]
            ax.scatter(
                angles,
                values[label],
                s=45,
                marker=marker,
                facecolor='white',
                edgecolor=GREY12,
                linewidth=1.2,
                zorder=11,
            )
            handles.append(
                Line2D(
                    [],
                    [],
                    marker=marker,
                    linestyle='none',
                    markerfacecolor='white',
                    markeredgecolor=GREY12,
                    label=str(label),
                ),
            )
    if show_reference:
        percentiles = latest_stats['percentiles']
        if all(v is not None for v in percentiles['p50']):
            ax.scatter(
                angles,
                percentiles['p50'],
                s=30,
                color=GREY12,
                zorder=14,
            )
            ax.vlines(
                angles,
                percentiles['p25'],
                percentiles['p75'],
                color=GREY12,
                zorder=14,
            )
            handles.append(
                Line2D(
                    [],
                    [],
                    marker='o',
                    color=GREY12,
                    label=phrases.get(
                        '25 city comparison',
                        '25 city comparison',
                    ),
                ),
            )
    tick_labels = ghsci.access_profile_labels(
        index,
        label_values,
        phrases,
        locale_profile,
    )
    ghsci.style_access_profile_axes(
        ax,
        angles,
        tick_labels,
        title,
        phrases,
        locale_profile,
        textsize=textsize,
    )
    ax.legend(
        handles=handles,
        loc='upper center',
        bbox_to_anchor=(0.5, -0.15),
        ncol=2 if style == 'change' else min(len(handles), 3),
        frameon=False,
    )
    return _save_or_return(fig, path, dpi, transparent=True)


def decile_gradient_plot(
    stratified: pd.DataFrame,
    indicator: str,
    timepoints: list = None,
    stratum_label: str = None,
    label: str = None,
    region=None,
    phrases: dict = None,
    cmap=None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
    path: str = None,
):
    """
    Weighted mean of an indicator across ordered strata, per timepoint.

    Plots rows of a stratified_summary (statistic 'weighted_mean') with
    strata on the x axis (e.g. IRSD deciles, most disadvantaged first) and
    a line per timepoint, labelled with the slope index of inequality
    where available, to show social gradients and how they have changed.
    """
    import matplotlib.pyplot as plt

    if cmap is None:
        cmap = _batlow()
    subset = stratified.loc[
        (stratified['statistic'] == 'weighted_mean')
        & (stratified['indicator'] == indicator)
    ].copy()
    if len(subset) == 0:
        raise ValueError(
            f'No stratified weighted means are available for {indicator}.',
        )
    if timepoints is None:
        timepoints = stratified.attrs.get('timepoints') or list(
            pd.unique(subset['timepoint']),
        )
    timepoints = [t for t in timepoints if t in set(subset['timepoint'])]
    sii = (
        stratified.loc[
            (stratified['statistic'] == 'sii')
            & (stratified['indicator'] == indicator)
        ]
        .set_index('timepoint')['value']
        .to_dict()
    )
    numeric = pd.to_numeric(subset['stratum'], errors='coerce')
    subset['position'] = (
        numeric if numeric.notna().all() else subset['stratum']
    )
    if width is None:
        width = _mm_scale(88)
    if height is None:
        height = _mm_scale(70)
    fig, ax = plt.subplots(figsize=(width, height))
    positions = np.linspace(0.1, 0.8, len(timepoints))
    for i, timepoint in enumerate(timepoints):
        rows = subset.loc[subset['timepoint'] == timepoint].sort_values(
            'position',
        )
        legend = str(timepoint)
        if timepoint in sii and not pd.isna(sii[timepoint]):
            legend = f'{timepoint} (SII {sii[timepoint]:+.1f})'
        ax.plot(
            rows['position'],
            rows['value'],
            marker='o',
            color=cmap(positions[i]),
            label=legend,
        )
    if numeric.notna().all():
        ax.set_xticks(sorted(numeric.unique()))
    ax.set_xlabel(stratum_label or 'Stratum')
    ax.set_ylabel(label or _indicator_label(indicator, region, phrases))
    ax.legend(frameon=False, fontsize='small')
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def policy_rating_longitudinal(
    policy_panel: pd.DataFrame,
    measure: str = 'presence',
    label: str = None,
    cmap=None,
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
):
    """
    Policy rating gauge marking each assessed timepoint.

    Draws the presence or quality score (as a percentage of the maximum)
    on a horizontal colour bar with one labelled marker per assessed
    timepoint, so change in policy ratings can be read along the gauge.
    Timepoints without a policy review are omitted (unequal policy and
    spatial coverage is expected).
    """
    import matplotlib.cm as mpl_cm
    import matplotlib.colors as mpl_colors
    import matplotlib.pyplot as plt

    if cmap is None:
        cmap = _batlow()
    if label is None:
        label = measure.capitalize()
    assessed = policy_panel.loc[policy_panel['assessed'].astype(bool)]
    scores = assessed[f'{measure}_pct'].dropna()
    if len(scores) == 0:
        raise ValueError(
            f'No assessed timepoints with {measure} scores are available.',
        )
    if width is None:
        width = _mm_scale(70)
    if height is None:
        height = _mm_scale(18)
    textsize = 12
    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(bottom=0.4, top=0.7)
    norm = mpl_colors.Normalize(vmin=0, vmax=100)
    fig.colorbar(
        mpl_cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=ax,
        orientation='horizontal',
    )
    ax.set_xlabel(label, labelpad=2, fontsize=textsize)
    ax.tick_params(labelsize=textsize)
    for timepoint, score in scores.items():
        ax.plot(
            score,
            1,
            marker='v',
            color='black',
            markersize=9,
            zorder=10,
            clip_on=False,
            transform=ax.get_xaxis_transform(),
        )
        ax.annotate(
            str(timepoint),
            xy=(score, 1),
            xycoords=ax.get_xaxis_transform(),
            xytext=(0, 8),
            textcoords='offset points',
            ha='center',
            va='bottom',
            fontsize=textsize,
        )
    return _save_or_return(fig, path, dpi)


def policy_comparison_table(
    comparison: pd.DataFrame,
    not_assessed: str = '',
    path: str = None,
    width: float = None,
    height: float = None,
    dpi: int = 300,
):
    """
    Render a policy checklist comparison as a table figure.

    Takes a DataFrame indexed by (topic, measure) with one column per
    reviewed timepoint holding identification marks (e.g. ✔, ✘,
    ✔/✘ or '-'); missing values indicate the measure was not
    assessed at that timepoint and are shown with the not_assessed
    symbol ('–' by default).  Topics are rendered as shaded
    separator rows.
    """
    from textwrap import wrap

    import matplotlib.pyplot as plt

    if not_assessed == '':
        not_assessed = '–'
    if width is None:
        width = _mm_scale(182)
    if height is None:
        height = _mm_scale(222)
    timepoints = list(comparison.columns)
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_axis_off()
    # assemble display rows: topic separators followed by measures
    rows = []
    for topic in comparison.index.get_level_values(0).unique():
        rows.append(('topic', topic, [''] * len(timepoints)))
        block = comparison.loc[topic]
        for measure in block.index:
            marks = [
                (
                    not_assessed
                    if pd.isna(value) or str(value) in ('', 'nan')
                    else str(value)
                )
                for value in block.loc[measure]
            ]
            rows.append(('measure', measure, marks))
    n_rows = len(rows)
    textsize = max(5, min(9, int(240 / max(n_rows, 1))))
    row_height = 1.0 / (n_rows + 2)
    text_right = 0.62
    mark_width = (1.0 - text_right) / len(timepoints)
    # header
    y = 1.0 - row_height / 2
    for j, timepoint in enumerate(timepoints):
        ax.text(
            text_right + (j + 0.5) * mark_width,
            y,
            str(timepoint),
            ha='center',
            va='center',
            fontsize=textsize + 1,
            fontweight='bold',
        )
    for i, (kind, label, marks) in enumerate(rows):
        y = 1.0 - (i + 1.5) * row_height
        if kind == 'topic':
            ax.axhspan(
                y - row_height / 2,
                y + row_height / 2,
                color='#e6e6e6',
                zorder=0,
            )
            ax.text(
                0.0,
                y,
                '\n'.join(wrap(str(label), 90, break_long_words=False)),
                ha='left',
                va='center',
                fontsize=textsize,
                fontweight='bold',
            )
        else:
            ax.text(
                0.01,
                y,
                '\n'.join(wrap(str(label), 90, break_long_words=False)),
                ha='left',
                va='center',
                fontsize=textsize,
            )
            for j, mark in enumerate(marks):
                ax.text(
                    text_right + (j + 0.5) * mark_width,
                    y,
                    mark,
                    ha='center',
                    va='center',
                    fontsize=textsize,
                )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    plt.tight_layout()
    return _save_or_return(fig, path, dpi)


def generate_longitudinal_figures(
    series,
    language: str = 'English',
    indicators: list = None,
    cmap=None,
    locale: str = 'en',
) -> dict:
    """
    Generate the standard set of longitudinal figures for a series.

    Produces small multiple and change maps per indicator, quantile band
    plots, a threshold trend plot, the multi-timepoint access profile
    and (when policy reviews are configured) policy rating gauges,
    saving them under {series.output_dir}/figures and returning a
    dictionary of paths.
    """
    longitudinal = _longitudinal()
    figure_dir = f'{series._ensure_output_dir()}/figures'
    os.makedirs(figure_dir, exist_ok=True)
    paths = {}
    panel = series.get_grid_panel(indicators=indicators)
    panel_indicators = list(pd.unique(panel['indicator']))
    for indicator in panel_indicators:
        try:
            paths[f'{indicator}_small_multiples'] = small_multiple_maps(
                series,
                indicator,
                panel=panel,
                cmap=cmap,
                locale=locale,
                path=f'{figure_dir}/{indicator}_small_multiples.png',
            )
            paths[f'{indicator}_change_map'] = change_map(
                series,
                indicator,
                panel=panel,
                locale=locale,
                path=f'{figure_dir}/{indicator}_change_map.png',
            )
        except ValueError as e:
            print(f'Skipping maps for {indicator}: {e}')
    quantile_df = longitudinal.weighted_quantiles(panel)
    region = series.reference.region
    for indicator in panel_indicators:
        paths[f'{indicator}_quantile_bands'] = quantile_band_plot(
            quantile_df,
            indicator,
            cmap=cmap,
            region=region,
            path=f'{figure_dir}/{indicator}_quantile_bands.png',
        )
    thresholds = series._default_thresholds(panel)
    if thresholds:
        threshold_df = longitudinal.population_below_threshold(
            panel,
            thresholds,
        )
        paths['threshold_trends'] = threshold_trend_plot(
            threshold_df,
            cmap=cmap,
            region=region,
            path=f'{figure_dir}/threshold_trends.png',
        )
    configured_style = (series.config.get('reporting') or {}).get(
        'access_profile',
        'auto',
    )
    for key, style, filename in (
        ('access_profile', configured_style, 'access_profile_longitudinal'),
        ('access_profile_change', 'change', 'access_profile_change'),
        ('access_profile_grouped', 'grouped', 'access_profile_grouped'),
    ):
        try:
            paths[key] = access_profile_longitudinal(
                series,
                language=language,
                cmap=cmap,
                style=style,
                path=f'{figure_dir}/{filename}_{language}.png',
            )
        except Exception as e:
            print(f'Skipping longitudinal access profile ({style}): {e}')
    for stratification in series._equity_settings()['stratification']:
        name = stratification.get('name') or stratification.get('aggregation')
        try:
            stratified = series.stratified_equity(
                stratification,
                indicators=indicators,
            )
            for indicator in pd.unique(stratified['indicator']):
                paths[f'{name}_{indicator}_gradient'] = decile_gradient_plot(
                    stratified,
                    indicator,
                    stratum_label=name,
                    region=region,
                    cmap=cmap,
                    path=f'{figure_dir}/{name}_{indicator}_gradient.png',
                )
        except Exception as e:
            print(f'Skipping stratified equity figures for {name}: {e}')
    if any(tp.has_policy for tp in series.timepoints):
        policy_panel = series.get_policy_panel()
        for measure in ('presence', 'quality'):
            try:
                paths[f'policy_{measure}'] = policy_rating_longitudinal(
                    policy_panel,
                    measure=measure,
                    cmap=cmap,
                    path=f'{figure_dir}/policy_{measure}_longitudinal.png',
                )
            except ValueError as e:
                print(f'Skipping policy {measure} gauge: {e}')
    print(f'Longitudinal figures saved to {figure_dir}')
    return paths
