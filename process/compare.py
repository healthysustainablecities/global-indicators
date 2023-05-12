"""Compare a reference city to a comparison city, and save the comparison as a CSV file."""
import os
import sys

import pandas as pd
from subprocesses.ghsci import Region, date_hhmm, region_names


def check_arguments():
    if len(sys.argv) != 3:
        sys.exit(
            f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThis process is run by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, the process can be run by entering the shortcut command:\ncompare <reference> <comparison>
            """,
        )


def check_codenames(codename, comparison_codename):
    for name in [codename, comparison_codename]:
        if name not in region_names:
            sys.exit(
                f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nSpecified city ({name}) does not appear to be in the list of configured cities.\n\nPlease try again by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
            )
    if comparison_codename == codename:
        sys.exit(
            f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe same codename was provided as reference and comparison.  This process is designed to summarise differences, and there would be none in this case.\n\nPlease try again by selecting two different codenames from the list of configured cities {region_names}, where these are study regions that have been fully analysed with resources generated.\n\nThe command can be run by entering:\ncompare  <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
        )


def compare(codename, comparison_codename):
    """Given a codename and a comparison codename for two cities with generated resources, compare the two cities and save the comparison as a CSV file."""
    r = Region(codename)
    files = {
        'reference': f"{r.config['region_dir']}/{r.config['city_summary']}.csv",
        'comparison': f"{r.config['region_dir']}/{r.config['city_summary']}.csv".replace(
            r.codename, comparison_codename,
        ),
    }
    dfs = {}
    for file in files:
        if os.path.exists(files[file]):
            dfs[file] = pd.read_csv(files[file])
        else:
            sys.exit(
                f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe summary results file ({files[file]}) could not be located.\n\nPlease try again by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
            )
    if all(dfs['reference'] == dfs['comparison']):
        sys.exit(
            f'The results contained in the generated summaries for {codename} and {comparison_codename} are identical.',
        )
    else:
        comparison = (
            dfs['reference']
            .compare(dfs['comparison'], align_axis=0)
            .droplevel(0)
            .transpose()
        )
    comparison.columns = [r.codename, comparison_codename]
    print(comparison)
    comparison.to_csv(
        f"{r.config['region_dir']}/compare_{r.codename}_{comparison_codename}_{date_hhmm}.csv",
    )
    print(
        f'\nComparison saved as compare_{r.codename}_{comparison_codename}_{date_hhmm}.csv\n',
    )


def main():
    check_arguments()
    codename = sys.argv[1]
    comparison_codename = sys.argv[2]
    check_codenames(codename, comparison_codename)
    compare(codename, comparison_codename)


if __name__ == '__main__':
    main()
