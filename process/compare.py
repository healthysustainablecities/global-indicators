"""Compare a reference city to a comparison city, and save the comparison as a CSV file."""

import sys

import pandas as pd
from subprocesses.ghsci import Region, date_hhmm, get_region_names


def check_arguments():
    if len(sys.argv) != 3:
        sys.exit(
            f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThis process is run by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, the process can be run by entering the shortcut command:\ncompare <reference> <comparison>
            """,
        )


def check_codenames(codename, comparison_codename):
    if str(comparison_codename) == str(codename):
        raise ValueError(
            """Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe same codename was provided as reference and comparison.  This process is designed to summarise differences, and there would be none in this case.\n\nPlease try again by entering the name of a city configuration file located in the process/configuration/regions folder, or entering a path to a configuration file relative to the process folder. Configured cities that have been fully analysed with resources generated may be compared:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
        )


def compare(a, b, save=True):
    """Given a codename and a comparison codename (or path to configuration file relative to process directory) for two cities with generated resources, compare the two cities and save the comparison as a CSV file."""
    regions = {}
    if type(a) == str:
        regions['a'] = Region(a)
    elif type(a) == Region:
        regions['a'] = a
    else:
        raise ValueError(
            f"Invalid type for argument 'a': {type(a)}. Expected str or Region.",
        )
    if type(b) == str:
        regions['b'] = Region(b)
    elif type(b) == Region:
        regions['b'] = b
    else:
        raise ValueError(
            f"Invalid type for argument 'b': {type(b)}. Expected str or Region.",
        )
    check_codenames(regions['a'].yaml, regions['b'].yaml)
    print(regions['a'].header)
    dfs = {}
    for region in ['a', 'b']:
        if regions[region].config is None:
            raise ValueError(
                f"Could not successfully retrieve configuration {regions[region].yaml}. Please ensure the codename and file path provided is correct.",
            )
        df = regions[region].get_df('indicators_region')
        if df is None:
            raise ValueError(
                f"Could not retrieve 'indicators_region' for {regions[region].codename}. "
                f"Please ensure analysis has been fully run for this region.",
            )
        dfs[regions[region].codename] = df
    # ordered set of columns shared between dataframes
    shared_columns = [
        x for x in dfs[regions['a'].codename].columns if x in dfs[regions['b'].codename].columns
    ]
    # store unshared columns from each dataframe
    unshared_columns = {
        regions['a'].codename: [
            x
            for x in dfs[regions['a'].codename].columns
            if x not in dfs[regions['b'].codename].columns
        ],
        regions['b'].codename: [
            x
            for x in dfs[regions['b'].codename].columns
            if x not in dfs[regions['a'].codename].columns
        ],
    }
    print(f'\nColumns shared across both datasets: {shared_columns}')
    for name in unshared_columns:
        print(f'\nColumns unique to {name}: {unshared_columns[name]}')
    # print(pd.concat(dfs).transpose())
    comparison = (
        dfs[regions['a'].codename][shared_columns]
        .compare(
            dfs[regions['b'].codename][shared_columns],
            align_axis=0,
            keep_shape=True,
            keep_equal=True,
            result_names=(regions['a'].codename, regions['b'].codename),
        )
        .droplevel(0)
        .transpose()
    )
    if len(comparison) == 0:
        sys.exit(
            f'The results contained in the generated summaries for {regions["a"].codename} and {regions["b"].codename} are identical.',
        )
    else:
        if save:
            comparison.to_csv(
                f"{regions['a'].config['region_dir']}/compare_{regions['a'].codename}_{regions['b'].codename}_{date_hhmm}.csv",
            )
            print(
                f'\nComparison saved as compare_{regions['a'].codename}_{regions['b'].codename}_{date_hhmm}.csv\n',
            )
    return comparison
    # except Exception as e:
    #     sys.exit(f"Error occurred while processing the reference city: {e}")


def main():
    check_arguments()
    codename = sys.argv[1]
    comparison_codename = sys.argv[2]
    r = Region(codename)
    r.compare(comparison_codename)


if __name__ == '__main__':
    main()
