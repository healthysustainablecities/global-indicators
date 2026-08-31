"""Summarise a region's indicators as a tidy, labelled table.

Presents output variables as rows, described in plain language using the
data dictionary and grouped by category, with one column per area: the
region summary first, followed by each area of any additional scales
requested (custom aggregations such as suburbs or meshblocks, or the
grid and sample point summaries).

This differs from compare(), which contrasts the city-scale summaries of
two or more study regions using raw variable names: this describes a
single region at whatever scales it was aggregated to, rounds each value
according to what it measures, prints the result, and can emit markdown.

The region is duck typed (as in data_dictionary), so only get_tables(),
get_df(), config and codename are required.  Called as:

    r.indicator_summary()
    r.indicator_summary('region', ['suburbs', 'meshblocks'])
    r.indicator_summary('suburbs', markdown=True, save=True)

It may also be run on the commandline from the process folder, e.g.
    /env/bin/python subprocesses/indicator_summary.py <codename> suburbs
"""

import os
import re
import sys
import textwrap
from datetime import datetime

import data_dictionary
import pandas as pd

# Aliases for the standard output scales, mapped to the region
# configuration key naming each table.
SCALE_ALIASES = {
    'region': 'city_summary',
    'city': 'city_summary',
    'city_summary': 'city_summary',
    'region_summary': 'city_summary',
    'grid': 'grid_summary',
    'grid_summary': 'grid_summary',
    'population_grid': 'grid_summary',
    'sample_points': 'point_summary',
    'sample_point': 'point_summary',
    'points': 'point_summary',
    'point': 'point_summary',
    'point_summary': 'point_summary',
}

# The names that identify the region summary, whichever way it is asked
# for; a raw table name is included, as that is the name it is exported
# and reported under.
CITY_ALIASES = {
    alias for alias, key in SCALE_ALIASES.items() if key == 'city_summary'
} | {'indicators_region'}

# Identifiers that number rows without naming them; unusable as column
# headings, and skipped when looking for a label field.
SURROGATE_IDS = {
    'fid',
    'gid',
    'grid_id',
    'id',
    'index',
    'ogc_fid',
    'osm_id',
    'point_id',
}

# The region summary inherits quoted, display-style column names from
# the urban covariates, where every other scale uses the lower case
# name for the same measure.  Reported as one row each, so that a
# region and its areas can be read across; the data dictionary lists
# both spellings of each of these against identical units.
VARIABLE_SYNONYMS = {
    'Area (sqkm)': 'area_sqkm',
    'Population estimate': 'pop_est',
    'Population per sqkm': 'pop_per_sqkm',
    'Intersections': 'intersection_count',
    'Intersections per sqkm': 'intersections_per_sqkm',
}

# Codes and identifiers retained from boundary data are numbers that
# are not quantities: a postcode must not be grouped into thousands.
CODE_PATTERN = re.compile(
    r'(^|_)(id|ids|cod|codigo|code\d*|postal|postcode|zip|fid|uid)(\d*)(_|$)',
    re.IGNORECASE,
)

# Columns preferred for ordering areas when a scale must be capped,
# with the short phrase used to report the ordering that was applied.
WEIGHT_COLUMNS = {
    'pop_est': 'population estimate',
    'urban_sample_point_count': 'sample point count',
    'grid_count': 'grid cell count',
    'area_count': 'area count',
}


def _norm(name) -> str:
    """Normalise a scale name for case and separator insensitive matching."""
    return re.sub(r'[\s\-]+', '_', str(name).strip().lower())


def normalise_scales(scales, by=None, include_region=True) -> list:
    """Flatten scale arguments to an ordered, de-duplicated list of names.

    Accepts a string, a list, or a list containing lists, so that a
    primary scale and a list of additional scales may be given
    positionally, as in
    indicator_summary('region', ['suburbs', 'meshblocks']).

    The region summary is the reference every area is read against, so
    it heads the columns unless it was named in some other position, or
    include_region is False.
    """
    names = []
    for argument in (scales, by):
        if argument is None:
            continue
        if isinstance(argument, (str, bytes)):
            names.append(argument)
            continue
        try:
            items = list(argument)
        except TypeError:
            names.append(argument)
            continue
        for item in items:
            if isinstance(item, (str, bytes)) or not hasattr(item, '__iter__'):
                names.append(item)
            else:
                names.extend(item)
    ordered = []
    for name in names:
        if str(name).strip() and name not in ordered:
            ordered.append(name)
    if not ordered:
        return ['region']
    if include_region and not any(
        _norm(name) in CITY_ALIASES for name in ordered
    ):
        ordered.insert(0, 'region')
    return ordered


def scale_options(config, tables) -> list:
    """List the scale names that could be requested for a region."""
    options = ['region', 'grid', 'sample points']
    options.extend(list((config.get('custom_aggregations') or {}).keys()))
    options.extend(
        [
            t
            for t in tables
            if t.startswith('indicators_') and t not in options
        ],
    )
    return options


def resolve_scales(config, tables, names) -> list:
    """Resolve requested scale names to output tables.

    Returns one descriptor per resolved scale, in the order requested,
    de-duplicated by table: a custom aggregation may also be the
    configured population grid, in which case 'grid' and that
    aggregation's own name identify the same table.
    """
    custom = {}
    for aggregation in (config.get('custom_aggregations') or {}).keys():
        table = f"indicators_{aggregation.replace(' ', '_').lower()}"
        for key in {_norm(aggregation), _norm(table)}:
            custom[key] = (aggregation, table)
    resolved = []
    seen = set()
    for name in names:
        key = _norm(name)
        aggregation = None
        if key in SCALE_ALIASES:
            table = config.get(SCALE_ALIASES[key])
            kind = SCALE_ALIASES[key].split('_')[0]
        elif key in custom:
            aggregation, table = custom[key]
            kind = 'custom'
        elif str(name) in tables or key in tables:
            table = str(name) if str(name) in tables else key
            kind = 'table'
        else:
            print(
                f"\nNote: the scale '{name}' was not recognised, and has been "
                'skipped.  Scales may be named by alias, by custom '
                'aggregation name, or by table name; this region has: '
                f'{", ".join(scale_options(config, tables))}',
            )
            continue
        if table is None or table in seen:
            continue
        seen.add(table)
        resolved.append(
            {
                'name': str(name),
                'table': table,
                'kind': kind,
                'aggregation': aggregation,
            },
        )
    return resolved


def resolve_label_column(columns, id_column=None, keep_columns=None):
    """Return the column whose values best name each area.

    The aggregation SQL selects the configured identifier unquoted, so
    PostgreSQL folds it to lower case (a configured 'SAL_NAME21' is the
    column 'sal_name21'); matching is therefore case insensitive.
    Surrogate identifiers number rows rather than naming them, so a
    retained boundary attribute is preferred where one is available.
    """
    columns = list(columns)
    lookup = {str(column).lower(): column for column in columns}
    candidates = []
    if id_column:
        candidates.append(str(id_column))
    candidates.extend(
        [c.strip() for c in str(keep_columns or '').split(',') if c.strip()],
    )
    for candidate in candidates:
        key = candidate.lower()
        if key in lookup and key not in SURROGATE_IDS:
            return lookup[key]
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    for key in lookup:
        if key in SURROGATE_IDS:
            return lookup[key]
    return columns[0] if columns else None


def disambiguate(labels, unnamed='(unnamed)') -> list:
    """Return unique, printable text labels, numbering any duplicates."""
    seen = {}
    unique = []
    for label in labels:
        try:
            missing = label is None or pd.isna(label)
        except (TypeError, ValueError):
            missing = False
        text = unnamed if missing else str(label).strip()
        if text == '':
            text = unnamed
        seen[text] = seen.get(text, 0) + 1
        unique.append(text if seen[text] == 1 else f'{text} ({seen[text]})')
    return unique


def _adaptive_decimals(magnitude):
    """Decimal places for a quantity whose units could not be resolved."""
    if magnitude >= 1000:
        return (0, True)
    if magnitude >= 100:
        return (1, False)
    if magnitude >= 0.01 or magnitude == 0:
        return (2, False)
    return (4, False)


def decimals_for(units, statistic, number) -> tuple:
    """Return (decimal places, thousands separator) for a measurement.

    Driven by the units and statistic the data dictionary reports for a
    variable, so that regionally customised variables round correctly
    without curated entries.  Trailing zeros are deliberately retained,
    so that values in a column align on the decimal point.
    """
    units = str(units or '')
    statistic = str(statistic or '')
    magnitude = abs(number)
    if statistic == 'category' or units in ('year', 'class 1-5'):
        return (0, False)
    if units.startswith('ordered class'):
        return (0, False)
    if units == 'percent':
        return (1, False)
    if units == 'metres':
        return (0, True)
    if 'per km' in units:
        return (0, True) if magnitude >= 1000 else (1, True)
    # area, tested before the count and sum statistics below: an area is
    # summed over an aggregation, but is not a whole number
    if units.startswith('km'):
        return (1, True) if magnitude >= 100 else (2, True)
    if units.startswith(('index', 'score', 'proportion', 'ratio')):
        return (2, False)
    if units.startswith(('degrees', 'deaths')):
        return (1, False)
    if units in ('persons', 'count') or statistic in ('count', 'sum'):
        # a counted total is whole; an average of counts is not
        return (0, True) if statistic in ('count', 'sum') else (1, True)
    return _adaptive_decimals(magnitude)


def format_value(variable, value, na_rep='', decimals=None) -> str:
    """Format one value for display, rounded according to what it measures.

    Missing values are reported as na_rep.  Values arrive from a
    pyarrow backed frame, where a null is pd.NA rather than a float
    nan: pd.NA is not an instance of float, and truth testing it
    raises, so nullity is tested with pd.isna alone.
    """
    if value is None:
        return na_rep
    try:
        if pd.isna(value):
            return na_rep
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, str):
        return value.strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals is None:
        units, statistic = data_dictionary.describe_units(variable)
        if (
            units == ''
            and statistic == ''
            and CODE_PATTERN.search(
                str(variable),
            )
        ):
            return f'{number:.0f}'
        digits, separator = decimals_for(units, statistic, number)
    else:
        digits, separator = int(decimals), abs(number) >= 1000
    if separator:
        return f'{number:,.{digits}f}'
    return f'{number:.{digits}f}'


def canonical(column):
    """Return the name a variable is reported under across scales."""
    return VARIABLE_SYNONYMS.get(column, column)


def select_variables(frames, variables=None, identifiers=False) -> list:
    """Return the ordered rows of the summary.

    Rows are the union of the variables of each requested scale, so
    that nothing a scale reports is silently dropped: a weighted
    aggregation reports pop_pct_ variables where an unweighted one
    reports pct_, and the region summary carries covariates the areas
    do not.  Ordering follows the data dictionary's category order and
    then first appearance, so that a summary and the region's data
    dictionary present variables in the same sequence.
    """
    excluded = set(data_dictionary.SKIP_COLUMNS)
    if not identifiers:
        excluded |= set(data_dictionary.IDENTIFIERS)
    entries = {}
    order = 0
    for frame in frames:
        label_column = frame.get('label_column')
        for column in frame['df'].columns:
            if column in excluded or str(column).startswith('_'):
                continue
            if label_column is not None and column == label_column:
                continue
            name = canonical(column)
            if name in entries:
                continue
            category, description = data_dictionary.describe_variable(name)
            entries[name] = {
                'Category': category,
                'Indicator': description,
                'Variable': name,
                'order': order,
            }
            order += 1
    if isinstance(variables, str) and variables.lower() == 'shared':
        shared = None
        for frame in frames:
            columns = {canonical(c) for c in frame['df'].columns}
            shared = columns if shared is None else shared & columns
        entries = {k: v for k, v in entries.items() if k in (shared or set())}
    elif variables is not None:
        requested = [_norm(v) for v in variables]
        lookup = {_norm(k): k for k in entries}
        entries = {
            lookup[v]: entries[lookup[v]] for v in requested if v in lookup
        }
        for position, key in enumerate(entries):
            entries[key]['order'] = position
    rank = {
        category: i
        for i, category in enumerate(data_dictionary.CATEGORY_ORDER)
    }
    rows = sorted(
        entries.values(),
        key=lambda row: (
            rank.get(row['Category'], len(data_dictionary.CATEGORY_ORDER)),
            row['order'],
        ),
    )
    # Two variables can share a description (an area's average of a
    # sample point measure, for example); name them so rows stay
    # distinguishable.
    counts = {}
    for row in rows:
        counts[row['Indicator']] = counts.get(row['Indicator'], 0) + 1
    for row in rows:
        if counts[row['Indicator']] > 1:
            row['Indicator'] = f"{row['Indicator']} ({row['Variable']})"
    return rows


def table_columns(r, table) -> list:
    """List a table's columns in their defined order."""
    df = r.get_df(
        'SELECT column_name FROM information_schema.columns '
        f"WHERE table_name = '{table}' ORDER BY ordinal_position",
    )
    if df is None or len(df) == 0:
        return []
    return df['column_name'].tolist()


def count_rows(r, table):
    """Count a table's rows, returning None where this is not possible."""
    df = r.get_df(f'SELECT COUNT(*) AS n FROM "{table}"')
    if df is None or len(df) == 0:
        return None
    try:
        return int(df['n'].iloc[0])
    except (TypeError, ValueError):
        return None


def _exported_csv(r, table):
    """Read a scale from its exported CSV, where one has been generated.

    Retrieval can fail with the database unavailable or the analysis
    incomplete; the CSVs written by generate() carry the same results,
    so a summary remains possible, as it is for compare().
    """
    region_dir = (r.config or {}).get('region_dir')
    if not region_dir:
        return None
    path = f'{region_dir}/{r.codename}_{table}.csv'
    if os.path.isfile(path):
        try:
            return pd.read_csv(path)
        except Exception as e:
            print(f'\nNote: {path} could not be read: {e}')
    return None


def _aggregation_settings(config, scale) -> tuple:
    """Return the (id column, keep_columns) configured for a scale."""
    aggregation = (config.get('custom_aggregations') or {}).get(
        scale['aggregation'] or '',
    )
    if not aggregation:
        return (None, None)
    if str(aggregation.get('data', '')).startswith('OSM:'):
        return ('osm_id', aggregation.get('keep_columns', ''))
    return (
        aggregation.get('id') or 'ogc_fid',
        aggregation.get('keep_columns', ''),
    )


def _order_clause(columns, label_column, capped):
    """Order areas by size when capped, and by name when not."""
    if capped:
        for column in WEIGHT_COLUMNS:
            if column in columns:
                return (f'"{column}" DESC NULLS LAST', column)
    if label_column is not None:
        return (f'"{label_column}" ASC NULLS LAST', None)
    return (None, None)


def _label_preference(scale, labels):
    """Return a column named to head this scale's areas, where given."""
    if isinstance(labels, str):
        return labels
    if isinstance(labels, dict):
        return labels.get(scale['name']) or labels.get(scale['aggregation'])
    return None


def load_scale(r, scale, max_columns=12, tables=None, labels=None):
    """Retrieve one scale, as the areas that will become its columns."""
    tables = r.get_tables() if tables is None else tables
    config = r.config or {}
    table = scale['table']
    id_column, keep_columns = _aggregation_settings(config, scale)
    id_column = _label_preference(scale, labels) or id_column
    note = None
    df = None
    label_column = None
    if table in tables:
        columns = [
            c
            for c in table_columns(r, table)
            if c not in data_dictionary.SKIP_COLUMNS
            and not str(c).startswith('_')
        ]
        if columns:
            if scale['kind'] != 'city':
                label_column = resolve_label_column(
                    columns,
                    id_column,
                    keep_columns,
                )
            total = count_rows(r, table)
            capped = total is None or total > max_columns
            order_by, weight = _order_clause(columns, label_column, capped)
            # The grid and sample point summaries can hold hundreds of
            # thousands of rows; project the columns explicitly and
            # limit in SQL, as get_df drops geometry only once the whole
            # result has crossed the wire.
            projection = ', '.join(f'"{c}"' for c in columns)
            sql = f'SELECT {projection} FROM "{table}"'
            if order_by:
                sql = f'{sql} ORDER BY {order_by}'
            if capped:
                sql = f'{sql} LIMIT {max_columns}'
            df = r.get_df(sql)
            if df is not None and capped and total is not None:
                ordering = (
                    f'the {max_columns} largest by {WEIGHT_COLUMNS[weight]}'
                    if weight
                    else f'the first {max_columns}'
                )
                note = (
                    f"'{scale['name']}' contains {total:,} areas; showing "
                    f'{ordering}.  Increase max_columns to show more.'
                )
    if df is None:
        df = _exported_csv(r, table)
        if df is None:
            print(
                f"\nNote: no results were found for the scale "
                f"'{scale['name']}' ({table}); it has been skipped.  Please "
                'confirm that analysis and generation have been run.',
            )
            return None
        if scale['kind'] != 'city':
            label_column = resolve_label_column(
                df.columns,
                id_column,
                keep_columns,
            )
            if label_column is not None:
                df = df.sort_values(label_column, kind='stable')
        if len(df) > max_columns:
            note = (
                f"'{scale['name']}' contains {len(df):,} areas; showing the "
                f'first {max_columns}.  Increase max_columns to show more.'
            )
            df = df.head(max_columns)
    if len(df) == 0:
        print(f"\nNote: the scale '{scale['name']}' held no areas.")
        return None
    return {
        'name': scale['name'],
        'table': table,
        'kind': scale['kind'],
        'df': df.reset_index(drop=True),
        'label_column': label_column,
        'note': note,
    }


def build_summary(
    r,
    scales='region',
    by=None,
    variables=None,
    max_columns=12,
    identifiers=False,
    labels=None,
    include_region=True,
) -> tuple:
    """Return the summary as (values DataFrame, notes).

    Rows are indexed by category, plain-language indicator and variable
    name; columns are one per area, in the order the scales were
    requested.  Values are returned unformatted, so that they remain
    available for further calculation.
    """
    config = r.config
    if config is None:
        raise ValueError(
            'Could not retrieve the configuration for '
            f'{getattr(r, "yaml", r.codename)}.  Please ensure the codename '
            'and file path provided is correct.',
        )
    tables = r.get_tables()
    resolved = resolve_scales(
        config,
        tables,
        normalise_scales(scales, by, include_region),
    )
    if not resolved:
        print(
            f'\nNo output scales could be resolved for {r.codename}.  Please '
            'ensure that analysis has been run for this region.',
        )
        return (None, [])
    frames = []
    notes = []
    for scale in resolved:
        frame = load_scale(r, scale, max_columns, tables, labels)
        if frame is None:
            continue
        frames.append(frame)
        if frame['note']:
            notes.append(frame['note'])
    if not frames:
        return (None, notes)
    rows = select_variables(frames, variables, identifiers)
    if not rows:
        print(f'\nNo summarisable variables were found for {r.codename}.')
        return (None, notes)
    keys = []
    data = {}
    columns_of = {
        frame['name']: {canonical(c): c for c in frame['df'].columns}
        for frame in frames
    }
    for frame in frames:
        df = frame['df']
        if frame['label_column'] is None:
            labels = [config.get('name') or r.codename]
        else:
            labels = disambiguate(df[frame['label_column']].tolist())
        for position, label in enumerate(labels):
            key = (frame['name'], label)
            keys.append(key)
            record = df.iloc[position]
            # a field naming this scale's areas is its column heading; it
            # may still be a row where another scale reports it as data
            # (a meshblock's suburb, say), but must not repeat the
            # heading back beneath it
            label = canonical(frame['label_column'])
            data[key] = {
                entry['Variable']: record.get(
                    columns_of[frame['name']].get(entry['Variable']),
                )
                for entry in rows
                if entry['Variable'] != label
                and entry['Variable'] in columns_of[frame['name']]
            }
    # An area label can recur across scales (two aggregations may share
    # an identifier field), so a repeated label is qualified by its scale.
    counts = {}
    for _, label in keys:
        counts[label] = counts.get(label, 0) + 1
    headers = disambiguate(
        [
            label if counts[label] == 1 else f'{label} [{scale_name}]'
            for scale_name, label in keys
        ],
    )
    index = pd.MultiIndex.from_tuples(
        [(e['Category'], e['Indicator'], e['Variable']) for e in rows],
        names=['Category', 'Indicator', 'Variable'],
    )
    values = pd.DataFrame(
        [[data[key].get(entry['Variable']) for key in keys] for entry in rows],
        index=index,
        columns=headers,
    )
    return (values, notes)


def format_frame(values, na_rep='', decimals=None):
    """Format every value of a summary for display, as text."""
    variables = values.index.get_level_values('Variable')
    formatted = [
        [
            format_value(variables[position], value, na_rep, decimals)
            for value in values.iloc[position]
        ]
        for position in range(len(values))
    ]
    return pd.DataFrame(
        formatted,
        index=values.index,
        columns=values.columns,
    )


def _terminal_width(width=None) -> int:
    """Return the width to render a text table within."""
    if width is None:
        try:
            from _utils import get_terminal_columns

            width = get_terminal_columns()
        except Exception:
            width = 80
    return max(int(width), 40)


def _panel(headers, widths, available) -> list:
    """Group columns into panels that each fit the available width."""
    panels = []
    current = []
    used = 0
    for header, size in zip(headers, widths):
        cost = size + 2
        if current and used + cost > available:
            panels.append(current)
            current = []
            used = 0
        current.append(header)
        used += cost
    if current:
        panels.append(current)
    return panels


def render_text(formatted, width=None, notes=(), title=None) -> str:
    """Render the summary as a fixed width table of labelled rows.

    Columns are rendered in panels where they exceed the width
    available, repeating the indicator labels for each, rather than
    wrapping mid-row.  Note that print_autobreak() cannot be used for
    the table itself: it word wraps, which would destroy the alignment.
    """
    width = _terminal_width(width)
    indicators = [
        str(label) for label in formatted.index.get_level_values('Indicator')
    ]
    categories = [
        str(label) for label in formatted.index.get_level_values('Category')
    ]
    limit = 22
    shortened = []
    legend = []
    for header in [str(column) for column in formatted.columns]:
        if len(header) > limit:
            short = f'{header[: limit - 1]}.'
            legend.append(f'{short}  {header}')
        else:
            short = header
        shortened.append(short)
    shortened = disambiguate(shortened)
    widths = {
        header: max(
            len(header),
            max(
                (len(str(v)) for v in formatted[column]),
                default=0,
            ),
        )
        for header, column in zip(shortened, formatted.columns)
    }
    label_width = min(
        max((len(label) for label in indicators), default=20),
        max(24, int(width * 0.45)),
    )
    panels = _panel(
        shortened,
        [widths[h] for h in shortened],
        max(width - label_width - 2, 20),
    )
    lines = []
    if title:
        lines.extend([title, '=' * min(len(title), width)])
    for position, panel in enumerate(panels):
        if position > 0:
            lines.append('')
            lines.append('(continued)')
        header_line = (
            ' ' * label_width
            + '  '
            + '  '.join(header.rjust(widths[header]) for header in panel)
        )
        lines.append('')
        lines.append(header_line)
        lines.append('-' * min(len(header_line), width))
        category = None
        for row in range(len(formatted)):
            if categories[row] != category:
                category = categories[row]
                lines.append('')
                lines.append(category)
            cells = [
                str(formatted.iloc[row][formatted.columns[shortened.index(h)]])
                for h in panel
            ]
            wrapped = textwrap.wrap(indicators[row], label_width) or ['']
            lines.append(
                wrapped[0].ljust(label_width)
                + '  '
                + '  '.join(
                    cell.rjust(widths[header])
                    for cell, header in zip(cells, panel)
                ),
            )
            for continuation in wrapped[1:]:
                lines.append(continuation.ljust(label_width))
    for note in list(notes) + legend:
        lines.append('')
        lines.extend(textwrap.wrap(note, width))
    return '\n'.join(lines)


def _escape(text) -> str:
    """Escape a value for inclusion in a markdown table cell."""
    return (
        str(text)
        .replace('|', '\\|')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .strip()
    )


def to_markdown(formatted, title=None, notes=(), group=True) -> str:
    """Render the summary as a markdown table.

    Written directly rather than with DataFrame.to_markdown(), which
    requires tabulate; that is present in the Earth Engine image but not
    the standard one, so relying on it would fail for most users.
    """
    columns = [str(column) for column in formatted.columns]
    lines = []
    if title:
        lines.extend([f'## {title}', ''])
    lines.append('| ' + ' | '.join(['Indicator'] + columns) + ' |')
    lines.append('| ' + ' | '.join([':---'] + ['---:'] * len(columns)) + ' |')
    category = None
    for row in range(len(formatted)):
        row_category, indicator, _ = formatted.index[row]
        if group and row_category != category:
            category = row_category
            lines.append(
                '| '
                + ' | '.join(
                    [f'**{_escape(category)}**'] + [''] * len(columns),
                )
                + ' |',
            )
        lines.append(
            '| '
            + ' | '.join(
                [_escape(indicator)]
                + [_escape(value) for value in formatted.iloc[row]],
            )
            + ' |',
        )
    for note in notes:
        lines.extend(['', f'*{note}*'])
    return '\n'.join(lines)


def _in_notebook() -> bool:
    """Report whether this is running in a notebook."""
    try:
        from IPython import get_ipython

        shell = get_ipython()
        return (
            shell is not None
            and shell.__class__.__name__ == 'ZMQInteractiveShell'
        )
    except Exception:
        return False


def _display_markdown(text) -> None:
    """Display markdown, rendered where a notebook can render it."""
    if _in_notebook():
        try:
            from IPython.display import Markdown, display

            display(Markdown(text))
            return
        except Exception:
            pass
    print(text)


def save_summary(r, values, markdown_text, save, title=None, notes=()):
    """Save the summary, as markdown or (with a .csv path) as values."""
    if isinstance(save, str):
        path = save
    else:
        stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
        region_dir = (r.config or {}).get('region_dir', '.')
        path = f'{region_dir}/{r.codename}_indicator_summary_{stamp}.md'
    if path.lower().endswith('.csv'):
        values.to_csv(path)
    else:
        with open(path, 'w', encoding='utf-8') as file:
            file.write(markdown_text)
            file.write('\n')
    print(f'\nIndicator summary saved as {os.path.basename(path)}')
    return path


def indicator_summary(
    r,
    scales='region',
    by=None,
    variables=None,
    max_columns=12,
    decimals=None,
    identifiers=False,
    labels=None,
    include_region=True,
    markdown=False,
    save=False,
    display=True,
    na_rep='',
):
    """Summarise a region's indicators as a tidy, labelled table.

    Returns the formatted table, or the markdown text where markdown is
    requested.  build_summary() returns the same table unformatted,
    where the values are wanted for further calculation.
    """
    values, notes = build_summary(
        r,
        scales=scales,
        by=by,
        variables=variables,
        max_columns=max_columns,
        identifiers=identifiers,
        labels=labels,
        include_region=include_region,
    )
    if values is None:
        return None
    formatted = format_frame(values, na_rep=na_rep, decimals=decimals)
    name = (r.config or {}).get('name') or r.codename
    title = f'Indicator summary: {name} ({r.codename})'
    markdown_text = None
    if markdown or (
        isinstance(save, str) and not save.lower().endswith('.csv')
    ):
        markdown_text = to_markdown(formatted, title=title, notes=notes)
    elif save is True:
        markdown_text = to_markdown(formatted, title=title, notes=notes)
    if display:
        if markdown:
            _display_markdown(markdown_text)
        elif _in_notebook():
            # the returned table is rendered by the notebook itself
            for note in notes:
                print(note)
        else:
            print(render_text(formatted, notes=notes, title=title))
    if save:
        save_summary(r, values, markdown_text, save, title, notes)
    return markdown_text if markdown else formatted


def main():
    """Summarise indicators for a region named on the commandline."""
    if len(sys.argv) < 2:
        sys.exit(
            'Summarise a study region\'s indicators as a tidy table of '
            'plain-language rows, with a column per area.\n\nUsage:\n  '
            'python subprocesses/indicator_summary.py <codename> [scale ...] '
            '[--markdown] [--save]\n\nFor example:\n  python '
            'subprocesses/indicator_summary.py ES_Las_Palmas_2025 region '
            'school_districts_grid_pop --markdown',
        )
    import ghsci

    arguments = sys.argv[1:]
    options = [a for a in arguments if a.startswith('--')]
    positional = [a for a in arguments if not a.startswith('--')]
    r = ghsci.Region(positional[0])
    scales = positional[1:] or ['region']
    return indicator_summary(
        r,
        scales=scales,
        markdown='--markdown' in options,
        save='--save' in options,
    )


if __name__ == '__main__':
    # allow for running from the process folder or subprocesses
    if os.path.basename(os.getcwd()) == 'subprocesses':
        os.chdir('..')
    sys.path.append(os.path.abspath('./subprocesses'))
    main()
