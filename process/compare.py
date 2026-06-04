"""Compare a reference city to a comparison city, and save the comparison as a CSV file."""

import os
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
    if type(a) == str:
        a = Region(a)
        a_codename = a.codename
    else:
        a_codename = a.codename
    if type(b) == str:
        b = Region(b)
        b_codename = b.codename
    else:
        b_codename = b.codename
    check_codenames(a.yaml, b.yaml)
    print(a.header)
    files = {
        a_codename: f"{a.config['region_dir']}/{a.codename}_{a.config['city_summary']}.csv",
        b_codename: f"{b.config['region_dir']}/{b.codename}_{b.config['city_summary']}.csv",
    }
    dfs = {}
    for file in files:
        if os.path.exists(files[file]):
            dfs[file] = pd.read_csv(files[file])
        else:
            sys.exit(
                f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe summary results file ({files[file]}) could not be located.\n\nPlease try again by entering codenames from the list of configured cities {get_region_names()} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
            )
    # ordered set of columns shared between dataframes
    shared_columns = [
        x for x in dfs[a_codename].columns if x in dfs[b_codename].columns
    ]
    # store unshared columns from each dataframe
    unshared_columns = {
        a_codename: [
            x
            for x in dfs[a_codename].columns
            if x not in dfs[b_codename].columns
        ],
        b_codename: [
            x
            for x in dfs[b_codename].columns
            if x not in dfs[a_codename].columns
        ],
    }
    print(f'\nColumns shared across both datasets: {shared_columns}')
    for name in unshared_columns:
        print(f'\nColumns unique to {name}: {unshared_columns[name]}')
    # print(pd.concat(dfs).transpose())
    comparison = (
        dfs[a_codename][shared_columns]
        .compare(
            dfs[b_codename][shared_columns],
            align_axis=0,
            keep_shape=True,
            keep_equal=True,
            result_names=(a_codename, b_codename),
        )
        .droplevel(0)
        .transpose()
    )
    if len(comparison) == 0:
        sys.exit(
            f'The results contained in the generated summaries for {a_codename} and {b_codename} are identical.',
        )
    else:
        if save:
            comparison.to_csv(
                f"{a.config['region_dir']}/compare_{a_codename}_{b_codename}_{date_hhmm}.csv",
            )
            print(
                f'\nComparison saved as compare_{a_codename}_{b_codename}_{date_hhmm}.csv\n',
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
