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


def compare(a, b, save=False):
    """Compare reference region 'a' against one or more regions 'b'.

    'a' is the reference region; 'b' is a comparison region or a list of comparison regions.
    Results show 'a' first, followed by the 'b' region(s).  For a single comparison region,
    absolute difference (b - a) and relative percentage change 100*(b - a)/a are also shown.
    """
    import numpy as np

    # Resolve reference region
    a_region = load_comparison_region(a)

    # Normalise b to a list
    if not isinstance(b, list):
        b = [b]

    b_regions = []
    for item in b:
        b_regions.append(load_comparison_region(item))

    for b_region in b_regions:
        check_codenames(a_region.yaml, b_region.yaml)

    print(a_region.header)

    # Retrieve indicator data for the reference region
    if a_region.config is None:
        raise ValueError(
            f"Could not successfully retrieve configuration {a_region.yaml}. Please ensure the codename and file path provided is correct.",
        )
    a_df = a_region.get_df('indicators_region')
    if a_df is None:
        raise ValueError(
            f"Could not retrieve 'indicators_region' for {a_region.codename}. "
            f"Please ensure analysis has been fully run for this region.",
        )

    # Retrieve indicator data for each comparison region
    b_dfs = []
    for b_region in b_regions:
        if b_region.config is None:
            raise ValueError(
                f"Could not successfully retrieve configuration {b_region.yaml}. Please ensure the codename and file path provided is correct.",
            )
        df = b_region.get_df('indicators_region')
        if df is None:
            raise ValueError(
                f"Could not retrieve 'indicators_region' for {b_region.codename}. "
                f"Please ensure analysis has been fully run for this region.",
            )
        b_dfs.append(df)

    # Ordered set of columns shared across all regions
    shared_columns = [
        col for col in a_df.columns if all(col in df.columns for df in b_dfs)
    ]

    # Report on column coverage
    unshared_a = [col for col in a_df.columns if col not in shared_columns]
    if unshared_a:
        print(f'\nColumns unique to {a_region.codename}: {unshared_a}')
    for b_region, b_df in zip(b_regions, b_dfs):
        unshared_b = [col for col in b_df.columns if col not in shared_columns]
        if unshared_b:
            print(f'\nColumns unique to {b_region.codename}: {unshared_b}')
    print(f'\nColumns shared across all datasets: {shared_columns}')

    # Build comparison table: rows = indicators, reference region (a) first
    comparison = pd.DataFrame(
        {a_region.codename: a_df[shared_columns].iloc[0]},
    )
    for b_region, b_df in zip(b_regions, b_dfs):
        comparison[b_region.codename] = b_df[shared_columns].iloc[0].values

    # For a single comparison region, append difference and % change columns
    if len(b_regions) == 1:
        a_vals = pd.to_numeric(comparison[a_region.codename], errors='coerce')
        b_vals = pd.to_numeric(
            comparison[b_regions[0].codename],
            errors='coerce',
        )
        comparison['difference'] = b_vals - a_vals
        comparison.replace([np.inf, -np.inf], np.nan, inplace=True)
        comparison['% change'] = 100 * (b_vals - a_vals) / a_vals

    if len(comparison) == 0:
        b_names = ', '.join(br.codename for br in b_regions)
        sys.exit(
            f'The results contained in the generated summaries for {a_region.codename} and {b_names} are identical.',
        )

    if save:
        b_names = '_'.join(br.codename for br in b_regions)
        save_name = f'compare_{a_region.codename}_{b_names}_{date_hhmm}.csv'
        comparison.to_csv(f"{b_regions[0].config['region_dir']}/{save_name}")
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
