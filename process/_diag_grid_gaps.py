"""Read-only diagnostic: why does a population grid cell have no access value?

Written for round 2 validation feedback (Shirley Shiqin Liu, Minneapolis, Sep 2026):
"I do notice some grids have missing access that I was not sure why it is the case ...
access to public open space within 5000m through stress penalized networks. There are
open space entry points near the area, but why do some of the grids have missing
access even though we see destinations nearby?"

There are three distinct mechanisms, and they look different on the dashboard:

  1. The cell is not in the grid summary at all, so no polygon is drawn and clicking
     it gives nothing.  Sample points are deleted where they fall inside an open space
     polygon (_07_locate_origins_destinations) or in a cell below pop_min_threshold,
     and _12_aggregation then joins the grid to the sample point counts with
     how='inner' -- so a cell with no sample points is dropped outright.  A park, and
     the unpopulated land around it, is exactly this case, which is why the holes
     appear next to the destinations.
  2. The cell is present but the value is NULL.  In 'avg' (distance) mode the viewer
     renders NULL fully transparent -- indistinguishable from case 1 -- whereas in
     'iso' (% access) mode NULL is drawn the same as zero.  So "missing rather than
     zero" means the distance layer.
  3. The cell is present in the grid summary but absent from sample_points_cycling,
     so _12_aggregation's UPDATE never touched it and the column kept its NULL
     default.  In a clean single run this should be empty; it appears when the two
     tables are out of step, e.g. _12 re-run after the sample points changed.

This reports the size of each, per indicator, so a validator's example can be placed.

Writes nothing.  Usage, inside the container:

    /env/bin/python _diag_grid_gaps.py "data/Cycling/Minneapolis/Minneapolis-Urban.yml"
"""
import sys

import ghsci


def scalar(r, sql):
    df = r.get_df(sql)
    if df is None or df.empty:
        return None
    return df.iloc[0, 0]


def main():
    r = ghsci.Region(sys.argv[1])
    grid = r.config['population_grid']
    summary = r.config['grid_summary']
    tables = r.get_tables()

    print(f'\n{r.name} ({r.codename}) -- grid cells without an access value\n')

    n_grid = scalar(r, f'SELECT count(*) FROM {grid}')
    print(f'  population grid ({grid}): {n_grid:,} cells')
    if summary not in tables:
        print(f'  grid summary ({summary}) does not exist: _12_aggregation has not run.')
        return
    n_summary = scalar(r, f'SELECT count(*) FROM {summary}')
    print(f'  grid summary  ({summary}): {n_summary:,} cells')
    print(
        f'  -> {n_grid - n_summary:,} cells ({100 * (n_grid - n_summary) / n_grid:.1f}%) '
        'are not in the summary at all, so no polygon is drawn for them (case 1).\n',
    )

    # why those cells have no sample points.  urban_sample_points has no index on
    # grid_id and over a million rows here, so a correlated NOT EXISTS plans as a
    # nested loop and runs for tens of minutes; pull the distinct ids and difference
    # the sets in memory instead.
    cells = r.get_df(f'SELECT grid_id, pop_est FROM {grid}').set_index('grid_id')
    if 'urban_sample_points' in tables:
        sampled = set(
            r.get_df('SELECT DISTINCT grid_id FROM urban_sample_points')['grid_id'],
        )
        unsampled = cells.index.difference(list(sampled))
        n_unsampled = len(unsampled)
        print(f'  cells with no sample point: {n_unsampled:,}')
        if n_unsampled:
            threshold = r.config['population']['pop_min_threshold']
            below = int((cells.loc[unsampled, 'pop_est'] < threshold).sum())
            print(
                f'    of which below pop_min_threshold ({threshold}): {below:,} '
                f'({100 * below / n_unsampled:.1f}%)',
            )
            if 'open_space_areas' in tables:
                # one indexed spatial join over the whole grid, then intersect the
                # id sets in memory: passing the unsampled ids back as an IN list
                # builds a query with tens of thousands of literals and is far slower
                os_cells = set(
                    r.get_df(
                        f'SELECT DISTINCT g.grid_id FROM {grid} g '
                        'JOIN open_space_areas o ON ST_Intersects(o.geom, g.geom)',
                    )['grid_id'],
                )
                in_os = len(set(unsampled) & os_cells)
                print(
                    f'    of which intersect an open space polygon: {in_os:,} '
                    f'({100 * in_os / n_unsampled:.1f}%)',
                )
        print()

    # case 3: in the summary, but never seen by the cycling aggregation
    if 'sample_points_cycling' in tables:
        summary_ids = set(r.get_df(f'SELECT grid_id FROM {summary}')['grid_id'])
        cycling_ids = set(
            r.get_df('SELECT DISTINCT grid_id FROM sample_points_cycling')['grid_id'],
        )
        orphan = len(summary_ids - cycling_ids)
        print(
            f'  cells in the summary with no cycling sample point: {orphan:,} '
            '(case 3; expected 0 for a clean single run)\n',
        )

    # case 2: per-column nulls
    cols = r.get_df(
        'SELECT column_name FROM information_schema.columns WHERE table_name = '
        f"'{summary}' AND (column_name LIKE 'pct_access_cycle_%%' "
        "OR column_name LIKE 'avg_cycle_%%') ORDER BY column_name",
    )
    if cols is None or cols.empty:
        print('  no cycling indicator columns on the grid summary.')
        return
    print(f'  NULLs per cycling indicator column (case 2), of {n_summary:,} cells:\n')
    print(f'    {"column":<58}{"null":>10}{"share":>9}')
    print('    ' + '-' * 77)
    for col in cols['column_name']:
        n_null = scalar(r, f'SELECT count(*) FROM {summary} WHERE "{col}" IS NULL')
        if n_null:
            print(
                f'    {col:<58}{n_null:>10,}{100 * n_null / n_summary:>8.1f}%',
            )
    print(
        '\n  A pct_access_ column can only be NULL for every cell at once '
        '(binary_access_score\n  turns an unreachable destination into 0, not NULL), '
        'so a partial count there means\n  case 3.  An avg_cycle_dist_ NULL is honest: '
        'no sample point in that cell reached\n  any destination of that type within '
        'the maximum band.\n',
    )


if __name__ == '__main__':
    main()
