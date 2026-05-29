"""Compare a reference city to one or more comparison cities, and save the comparison as a CSV file."""

import sys

import pandas as pd
from subprocesses.ghsci import Region, date_hhmm, get_region_names


def check_arguments():
    if len(sys.argv) < 3:
        sys.exit(
            f"""Compare a reference city to one or more comparison cities, and save the comparison as a CSV file.\n\nThis process is run by entering codenames from the list of configured cities {get_region_names()} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison> [comparison2 ...]\n\nAlternatively, the process can be run by entering the shortcut command:\ncompare <reference> <comparison> [comparison2 ...]
            """,
        )


def check_codenames(codename, comparison_codename):
    if str(comparison_codename) == str(codename):
        raise ValueError(
            """Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe same codename was provided as reference and comparison.  This process is designed to summarise differences, and there would be none in this case.\n\nPlease try again by entering the name of a city configuration file located in the process/configuration/regions folder, or entering a path to a configuration file relative to the process folder. Configured cities that have been fully analysed with resources generated may be compared:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
        )


def load_comparison_region(comparison):
    if isinstance(comparison, str):
        return Region(comparison)
    elif isinstance(comparison, Region):
        return comparison
    else:
        raise ValueError(
            f"Invalid type for comparison region: {type(comparison)}. Expected str or Region.",
        )


def resolve_regions(a, b):
    """Normalise inputs to (reference Region, [comparison Regions]).

    When 'a' is a list, a[0] is the reference and a[1:] are prepended to b
    so that b (the calling region) is always displayed last.
    """
    if isinstance(a, list):
        if not a:
            raise ValueError('List must contain at least one region.')
        b = a[1:] + (b if isinstance(b, list) else [b])
        a = a[0]
    a_region = load_comparison_region(a)
    b_list = b if isinstance(b, list) else [b]
    b_regions = [load_comparison_region(item) for item in b_list]
    for b_region in b_regions:
        check_codenames(a_region.yaml, b_region.yaml)
    return a_region, b_regions


def get_indicator_df(region):
    """Return the indicators_region DataFrame for a region, raising on failure."""
    if region.config is None:
        raise ValueError(
            f"Could not successfully retrieve configuration {region.yaml}. "
            'Please ensure the codename and file path provided is correct.',
        )
    df = region.get_df('indicators_region')
    if df is None:
        raise ValueError(
            f"Could not retrieve 'indicators_region' for {region.codename}. "
            'Please ensure analysis has been fully run for this region.',
        )
    return df


def build_comparison_table(a_region, a_df, b_regions, b_dfs):
    """Build and return a comparison DataFrame, reporting on column coverage."""
    import numpy as np

    shared_columns = [
        col for col in a_df.columns if all(col in df.columns for df in b_dfs)
    ]
    for b_region, b_df in zip(b_regions, b_dfs):
        unshared = [col for col in b_df.columns if col not in shared_columns]
        if unshared:
            print(f'\nColumns unique to {b_region.codename}: {unshared}')
    unshared_a = [col for col in a_df.columns if col not in shared_columns]
    if unshared_a:
        print(
            f'\nColumns unique to {a_region.codename} (reference): {unshared_a}',
        )
    print(f'\nColumns shared across all datasets: {shared_columns}')

    table = pd.DataFrame({a_region.codename: a_df[shared_columns].iloc[0]})
    for b_region, b_df in zip(b_regions, b_dfs):
        table[b_region.codename] = b_df[shared_columns].iloc[0].values

    if len(b_regions) == 1:
        a_vals = pd.to_numeric(table[a_region.codename], errors='coerce')
        b_vals = pd.to_numeric(table[b_regions[0].codename], errors='coerce')
        table['difference'] = b_vals - a_vals
        table.replace([np.inf, -np.inf], np.nan, inplace=True)
        table['% change'] = 100 * (b_vals - a_vals) / a_vals

    return table


def compare(a, b, save=False):
    """Compare reference region 'a' against one or more regions 'b'.

    'a' is the reference region (or a list where a[0] is the reference and
    a[1:] are additional comparisons); 'b' is the calling/final region.
    Results show 'a' first, followed by any middle regions, then 'b' last.
    For a single comparison region, absolute difference and relative
    percentage change 100*(b - a)/a are also shown.
    """
    a_region, b_regions = resolve_regions(a, b)
    print(b_regions[-1].header)

    a_df = get_indicator_df(a_region)
    b_dfs = [get_indicator_df(region) for region in b_regions]

    comparison = build_comparison_table(a_region, a_df, b_regions, b_dfs)
    b_names = '_'.join(br.codename for br in b_regions)
    print(
        f'\nComparison of {b_names} against {a_region.codename} (reference):',
    )

    if len(comparison) == 0:
        sys.exit(
            f'The results contained in the generated summaries for {a_region.codename} and {b_names} are identical.',
        )

    if save:
        save_name = f'compare_{a_region.codename}_{b_names}_{date_hhmm}.csv'
        comparison.to_csv(f"{b_regions[-1].config['region_dir']}/{save_name}")
        print(f'\nComparison saved as {save_name}\n')

    return comparison


def main():
    check_arguments()
    reference_codename = sys.argv[1]
    comparison_codenames = sys.argv[2:]
    b = (
        comparison_codenames[0]
        if len(comparison_codenames) == 1
        else list(comparison_codenames)
    )
    import pandas as pd

    compare(reference_codename, b)


if __name__ == '__main__':
    main()
