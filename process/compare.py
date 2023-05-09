"""Compare a reference city to a comparison city, and save the comparison as a CSV file."""
import os
import sys

import pandas as pd
from subprocesses._project_setup import (
    city_summary,
    codename,
    region_config,
    region_names,
)

if len(sys.argv) != 3:
    sys.exit(
        f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThis process is run by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, the process can be run by entering the shortcut command:\ncompare <reference> <comparison>
        """,
    )
else:
    comparison_codename = sys.argv[2]

if comparison_codename not in region_names:
    sys.exit(
        f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nSpecified city ({comparison_codename}) does not appear to be in the list of configured cities.\n\nPlease try again by entering codenames from the list of configured cities {region_names} that have been fully analysed with resources generated:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
    )

if comparison_codename == codename:
    sys.exit(
        f"""Compare a reference city to a comparison city, and save the comparison as a CSV file.\n\nThe same codename was provided as reference and comparison.  This process is designed to summarise differences, and there would be none in this case.\n\nPlease try again by selecting two different codenames from the list of configured cities {region_names}, where these are study regions that have been fully analysed and generated.\n\nThe command can be run by entering:\npython 4_compare.py <reference> <comparison>\n\nAlternatively, enter the shortcut command:\ncompare <reference> <comparison>""",
    )

files = {
    'reference': f"{region_config['region_dir']}/{city_summary}.csv",
    'comparison': f"{region_config['region_dir']}/{city_summary}.csv".replace(
        codename, comparison_codename,
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

comparison = (
    dfs['reference']
    .compare(dfs['comparison'], align_axis=0)
    .droplevel(0)
    .transpose()
)
comparison.columns = [codename, comparison_codename]
print(comparison)

comparison.to_csv(
    f"{region_config['region_dir']}/compare_{codename}_{comparison_codename}_{date_hhmm}.csv",
)
print(
    f'\nComparison saved as compare_{codename}_{comparison_codename}_{date_hhmm}.csv\n',
)
