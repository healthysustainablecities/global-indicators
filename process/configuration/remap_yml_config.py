"""
Convert older (pre 16 Feb 2023) config files to updated config format.

Changes include: nested keys, clearer names (eg not_urban_intersection=False becomes 'study_region'>'ghsl_urban_intersection'=True).
"""

import os
import pprint
import shutil
import sys
import time

import yaml

date = time.strftime('%Y-%m-%d')

if os.path.exists(f'{os.getcwd()}/../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../')
    sys.path.append(os.path.abspath('./subprocesses'))
elif os.path.exists(f'{os.getcwd()}/../../global-indicators.sh'):
    folder_path = os.path.abspath(f'{os.getcwd()}/../../')
    sys.path.append(os.path.abspath('.'))
else:
    folder_path = os.getcwd()

config_path = f'{folder_path}/process/configuration'

with open(f'{config_path}/regions.yml') as f:
    regions = yaml.safe_load(f)

# check to see if an old value is in the regions description
if 'network_not_using_buffered_region' in regions[list(regions.keys())[0]]:
    proceed = input(
        f"Region configuration template schema requires updating.  Would you like a copy to be made of your old file to '{config_path}/_obsolete_regions_{date}.yml', and convert the original file 'regions.yml' to use the updated schema (nested keys, clearer names, rephrased double negatives)?  This is required to run the current version of the software.  Type 'y' and hit enter to proceed, or another letter and enter to exit: ",
    )
    if proceed != 'y':
        sys.exit()
    shutil.copyfile(
        f'{config_path}/regions.yml',
        f'{config_path}/_obsolete_regions_{date}.yml',
    )
    new = {}
    for r in regions:
        new[r] = {
            'name': regions[r]['full_locale'],
            'year': regions[r]['year'],
            'country': regions[r]['country'],
            'country_code': regions[r]['region'],
            'continent': regions[r]['continent'],
            'crs': {
                'name': regions[r]['crs_name'],
                'standard': regions[r]['crs_standard'],
                'srid': regions[r]['crs_srid'],
                'utm': regions[r]['utm'],
            },
            'study_region_boundary': {
                'data': regions[r]['area_data'],
                'source': regions[r]['area_data_source'],
                'publication_date': None,
                'url': regions[r]['area_data_source_url'],
                'licence': regions[r]['area_data_licence'],
                'licence_url': regions[r]['area_data_licence_url'],
                'ghsl_urban_intersection': regions[r]['not_urban_intersection']
                is False,
            },
            'population': regions[r]['population'],
            'OpenStreetMap': regions[r]['OpenStreetMap'],
            'network': {
                'osmnx_retain_all': regions[r]['osmnx_retain_all'],
                'buffered_region': regions[r][
                    'network_not_using_buffered_region'
                ]
                is None,
                'polygon_iteration': regions[r]['network_polygon_iteration'],
                'connection_threshold': regions[r][
                    'network_connection_threshold'
                ],
                'intersection_tolerance': regions[r]['intersection_tolerance'],
            },
            'urban_region': 'GHS-URBAN',
            'urban_query': regions[r]['covariate_data'],
            'country_gdp': regions[r]['country_gdp'],
            'custom_destinations': regions[r]['custom_destinations'],
            'gtfs_feeds': regions[r]['gtfs_feeds'],
            'policy_review': None,
            'notes': regions[r]['note'],
        }
        if 'area_data_date' in regions[r]:
            new[r]['study_region_boundary']['publication_date']: regions[r][
                'area_data_date'
            ]
        if 'policy_review' in regions[r]:
            new[r]['policy_review'] = regions[r]['policy_review']

    if 'description' in new:
        new['description']['crs'][
            'utm'
        ] = 'UTM grid if EPSG code is not known (used to manually derive EPSG code= 326** is for Northern Hemisphere, 327** is for Southern Hemisphere)'
        new['description']['study_region_boundary'][
            'publication_date'
        ] = 'Publication date for study region area data source, or date of currency'
        new['description']['network'][
            'polygon_iteration'
        ] = 'Iterate over and combine polygons (e.g. islands)'
        new['description']['network'][
            'connection_threshold'
        ] = 'Minimum distance to retain'
        new['description']['network'][
            'intersection_tolerance'
        ] = 'Tolerance in metres for cleaning intersections.  This is an important methodological choice, and the chosen parameter should be robust to a variety of network topologies in the city being studied.  See https://github.com/gboeing/osmnx-examples/blob/main/notebooks/04-simplify-graph-consolidate-nodes.ipynb.'
        for key in new['description']:
            if type(new['description'][key]) is str:
                new['description'][key] = (
                    new['description'][key]
                    .replace('\n', '')
                    .replace("'''", '')
                )
            elif type(new['description'][key]) is dict:
                for skey in new['description'][key]:
                    if type(new['description'][key][skey]) is str:
                        new['description'][key][skey] = (
                            new['description'][key][skey]
                            .replace('\n', '')
                            .replace("'''", '')
                        )
                    elif type(new['description'][key][skey]) is dict:
                        for sskey in new['description'][key][skey]:
                            if (
                                type(new['description'][key][skey][sskey])
                                is str
                            ):
                                new['description'][key][skey][sskey] = (
                                    new['description'][key][skey][sskey]
                                    .replace('\n', '')
                                    .replace("'''", '')
                                )
    with open(f'{config_path}/regions.yml', 'w') as f:
        yaml.safe_dump(
            new,
            f,
            default_style=None,
            default_flow_style=False,
            sort_keys=False,
            width=float('inf'),
        )
else:
    print(
        "The current regions.yml file doesn't appear to contain the key 'network_not_using_buffered_region', at least not for the first record (which is usually 'description').  No conversion has been undertaken, as it does not seem to be required.",
    )
