"""
Longitudinal comparison of study region timepoints.

Provides commandline access to the longitudinal series functionality in
subprocesses/longitudinal.py, and re-exports it so that 'import
longitudinal' behaves consistently with the subprocesses module.

Usage:

    python longitudinal.py <series>            # series config name/path
    python longitudinal.py <codename> <codename> [...]  # runtime series
    ... [--save] [--report] [--language English] [--template T]

Alternatively, use the shortcut command:

    longitudinal <series-or-codenames...> [options]
"""

import argparse
import sys

from subprocesses.longitudinal import *  # noqa: F401,F403
from subprocesses.longitudinal import (  # noqa: F401
    Series,
    _ghsci,
    _panel_timepoints,
    _panel_unit_column,
    _policy_report,
    _resolve_pairs,
    compare_longitudinal,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Compare a series of study region timepoints (longitudinal '
            'analysis), optionally generating equity summaries and '
            'longitudinal reports.'
        ),
        epilog=(
            'A single argument is treated as a series configuration '
            'name or path (e.g. AU_Melbourne_series, or '
            'data/AU/AU_Melbourne_series.yml); multiple arguments are '
            'treated as an ordered runtime series of study region '
            'codenames or configuration paths.'
        ),
    )
    parser.add_argument(
        'series',
        nargs='+',
        help='series configuration name/path, or two or more codenames',
    )
    parser.add_argument(
        '--save',
        action='store_true',
        help='export panels, change metrics and equity summaries as CSV',
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='generate longitudinal report(s)',
    )
    parser.add_argument(
        '--language',
        default='English',
        help='report language (default: English)',
    )
    parser.add_argument(
        '--template',
        default=None,
        help=(
            'report template (spatial_longitudinal, '
            'policy_longitudinal or policy_spatial_longitudinal); '
            'defaults to the series configuration or policy coverage'
        ),
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='generate reports without language validation checks',
    )
    args = parser.parse_args()
    if len(args.series) == 1:
        series = Series(args.series[0])
    else:
        series = Series(args.series)
    print(series)
    series.validate_alignment(save=args.save)
    panel = series.get_city_panel()
    import pandas as pd

    with pd.option_context(
        'display.max_rows',
        None,
        'display.max_columns',
        None,
        'display.width',
        None,
    ):
        print(f'\nCity summary by timepoint:\n{panel.T}')
    if args.save:
        series.save_panels()
        series.equity_summary(save=True)
    if args.report:
        series.generate_report(
            language=args.language,
            template=args.template,
            validate_language=not args.force,
        )
    return series


if __name__ == '__main__':
    main()
