"""Compare a reference city to a comparison city, and save the comparison as a CSV file."""
import sys

import pandas as pd
from subprocesses._project_setup import *

if len(sys.argv) != 3:
    sys.exit(
        """Usage: python compare.py <reference codename> <comparison codename>""",
    )
else:
    comparison_codename = sys.argv[2]

if comparison_codename not in region_names:
    sys.exit(
        f'Specified city ({comparison_codename}) does not appear to be in the list of configured cities ({region_names})',
    )

if comparison_codename == codename:
    sys.exit('Attempted to compare against self; no point!')

files = {
    'reference': f"{region_config['region_dir']}/{city_summary}.csv",
    'comparison': f"{region_config['region_dir']}/{city_summary}.csv".replace(
        codename, comparison_codename,
    ),
}
dfs = {}

for file in files:
    dfs[file] = pd.read_csv(files[file])

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
