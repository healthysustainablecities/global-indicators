"""
Analyse GTFS feed data_dir.

This script contain functions and processes to retain public transit
stops points with regular services Outputs 'pt_stops_headway' table with
headway information for each study region.
"""

import os
import sys
import time

import _gtfs_utils

# Set up project and region parameters for GHSCIC analyses
import ghsci
import gtfslite
import numpy as np
import pandas as pd

# import urbanaccess as ua
from script_running_log import script_running_log
from sqlalchemy import text


def stop_id_na_check(loaded_feeds):
    na_check = loaded_feeds.stops.stop_id.isna().sum()
    if na_check == 0:
        return loaded_feeds
    elif na_check == 1:
        loaded_feeds.stops.stop_id = loaded_feeds.stops.stop_id.astype(str)
        loaded_feeds.stop_times.stop_id = loaded_feeds.stop_times.stop_id.astype(
            str,
        )
        return loaded_feeds
    elif na_check > 1:
        print(
            f"""\n  - Error: {na_check} null values found in stop_id column of stops.txt, meaning that stops cannot be uniquely identified.   Values of stop_id in the source data that may be problematic and result in multiple ambiguous null records include: [‘’, ‘#N/A’, ‘#N/A N/A’, ‘#NA’, ‘-1.#IND’, ‘-1.#QNAN’, ‘-NaN’, ‘-nan’, ‘1.#IND’, ‘1.#QNAN’, ‘<NA>’, ‘N/A’, ‘NA’, ‘NULL’, ‘NaN’, ‘None’, ‘n/a’, ‘nan’, ‘null’]. """,
        )
        return None


def check_and_load_stop_times(
    loaded_feeds, feed_config: dict = {}, feed_name: str = '',
):
    null_stop_times_stops = len(
        loaded_feeds.stop_times.loc[
            loaded_feeds.stop_times['departure_time'].isnull(), 'stop_id',
        ].unique(),
    )
    if null_stop_times_stops > 0:
        if (
            'interpolate_stop_times' in feed_config
            and feed_config['interpolate_stop_times']
        ):
            print(
                f'\n  - **Note**: {null_stop_times_stops} stops with null departure times found in stop_times.txt.\n    This GTFS feed has been configured to to fill null arrival and departure values.based on a linear interpolation according to the provided stop sequence start and end times within each trip_id.  This is an approximation based on the available information, but results may still differ from the actual service frequencies at these stops.',
            )
            loaded_feeds.stop_times = interpolate_stop_times(
                loaded_feeds.stop_times,
            )
        else:
            sys.exit(
                f'\n**WARNING**: {null_stop_times_stops} stops with null departure times found in stop_times.txt for this GTFS feed:\n{feed_name}: {feed_config}.\n\n  Use of this feed in analysis without specialised cleaning will result in inaccurate service frequencies.\n\nIt is recommended to interpolate stop_times values.  Optionally, this GTFS feed can be configured to have interpolation applied by adding an entry of "interpolate_stop_times: true" within its settings in the region configuration file.  This will attempt to fill null arrival and departure values using a linear interpolation according to the provided stop sequence start and end times within each trip_id.  This is an approximation based on the available information, but results may still differ from the actual service frequencies at these stops.  See documentation and the example configuration file for further details.',
            )
    loaded_feeds.stop_times = loaded_feeds.stop_times.query(
        f"stop_id in {list(loaded_feeds.stops['stop_id'].values)}",
    )
    return loaded_feeds


def interpolate_stop_times(df: pd.DataFrame):
    """Interpolates stop_times values based on a linear interpolation according to stop sequence start and end times within each trip_id.  This is an approximation based on the available information, but results may still differ from the actual service frequencies at these stops."""
    df = df.copy()
    columns = df.columns
    df[['td_a', 'td_d']] = df[['arrival_time', 'departure_time']].astype(
        'timedelta64[ns]',
    )
    interpolated = (
        df.groupby(['trip_id'])[['stop_sequence', 'td_a', 'td_d']]
        .apply(lambda trip: trip.interpolate())
        .reset_index('trip_id')
    )
    df = df.merge(
        interpolated,
        how='left',
        on=['trip_id', 'stop_sequence'],
        suffixes=['', '_interpolated'],
    )
    df['arrival_time'] = format_timedelta_hhmmss(df['td_a_interpolated'])
    df['departure_time'] = format_timedelta_hhmmss(df['td_d_interpolated'])
    return df[columns]


def format_timedelta_hhmmss(pd_timedelta_series: pd.Series):
    """Formats a pandas timedelta series as HH:MM:SS string, allowing for relative times later than 24 hours."""
    return pd_timedelta_series.apply(
        lambda x: f'{(x.components.days*24)+x.components.hours:02d}:{x.components.minutes:02d}:{x.components.seconds:02d}'
        if not pd.isnull(x)
        else '',
    )


def stops_by_mode(loaded_feeds, route_types, agency_ids) -> set:
    routes = loaded_feeds.routes[
        [
            c
            for c in ['route_id', 'agency_id', 'route_type']
            if c in loaded_feeds.routes
        ]
    ]
    # filter trips within route types and agency id
    if (route_types is not None) & (agency_ids is None):
        routes = routes[(routes['route_type'].isin(route_types))]
    elif (route_types is not None) & (agency_ids is not None):
        routes = routes[
            (routes['agency_id'].isin(agency_ids))
            & (routes['route_type'].isin(route_types))
        ]
    elif (route_types is None) & (agency_ids is not None):
        routes = routes[(routes['agency_id'].isin(agency_ids))]
    mode_stops = set(
        loaded_feeds.stop_times[['trip_id', 'stop_id']]
        .merge(
            loaded_feeds.trips[['trip_id', 'route_id']],
            how='left',
            on='trip_id',
        )
        .merge(routes, how='right', on='route_id')['stop_id']
        .dropna(),
    )
    return mode_stops


def get_frequent_stop_stats(
    stop_frequent: pd.DataFrame, group_by: str,
) -> pd.DataFrame:
    """Get mode frequency comparison by either 'mode' or 'feed'."""
    tot_df = (
        stop_frequent.groupby(group_by)[['stop_id']]
        .count()
        .rename(columns={'stop_id': 'tot_stops'})
    )
    headway30_df = (
        stop_frequent[stop_frequent['headway'] <= 30]
        .groupby(group_by)[['stop_id']]
        .count()
        .rename(columns={'stop_id': 'headway<=30'})
    )
    headway20_df = (
        stop_frequent[stop_frequent['headway'] <= 20]
        .groupby(group_by)[['stop_id']]
        .count()
        .rename(columns={'stop_id': 'headway<=20'})
    )
    mode_freq_comparison = pd.concat(
        [tot_df, headway30_df, headway20_df], axis=1,
    )
    mode_freq_comparison.loc['total'] = mode_freq_comparison.sum()
    mode_freq_comparison['pct_headway<=30'] = (
        mode_freq_comparison['headway<=30']
        * 100
        / mode_freq_comparison['tot_stops']
    ).round(2)
    mode_freq_comparison['pct_headway<=20'] = (
        mode_freq_comparison['headway<=20']
        * 100
        / mode_freq_comparison['tot_stops']
    ).round(2)
    return mode_freq_comparison


def get_average_headway(stop_frequent: pd.DataFrame) -> pd.DataFrame:
    """Get average headway for stops across feeds."""
    stop_frequent = stop_frequent.copy()
    unique_feeds = [os.path.basename(x) for x in stop_frequent.feed.unique()]
    agg_feed_description = (
        f'average headway for stops across feeds: {unique_feeds}'
    )
    stop_frequent = stop_frequent.groupby('stop_id').mean()
    stop_frequent['feeds'] = agg_feed_description
    stop_frequent.reset_index(inplace=True)
    return stop_frequent


def gtfs_to_db(r, stop_frequent: pd.DataFrame):
    out_table = ghsci.datasets['gtfs']['headway']
    # save to output file
    # save the frequent stop by study region and modes to SQL database
    with r.engine.begin() as connection:
        connection.execute(text(f'DROP TABLE IF EXISTS {out_table}'))
    with r.engine.begin() as connection:
        stop_frequent.set_index('stop_id').to_sql(
            out_table, con=connection, index=True,
        )
    sql = f"""
                ALTER TABLE {out_table} ADD COLUMN geom geometry(Point, {r.config['crs']['srid']});
                UPDATE {out_table}
                    SET geom = ST_Transform(
                        ST_SetSRID(
                            ST_MakePoint(
                                stop_lon,
                                stop_lat
                                ),
                            4326),
                    {r.config['crs']['srid']})
                """
    with r.engine.begin() as connection:
        connection.execute(text(sql))
    print(f'{out_table} exported to SQL database\n')


def get_frequencies_df(gtfs_feed, gtfsfeed_path):
    # load frequencies if exists
    for root, dirs, files in os.walk(gtfsfeed_path):
        # naive assumption that only one frequencies.txt exists in feed path...
        for file in files:
            if file == 'frequencies.txt':
                frequencies_df = pd.read_csv(os.path.join(root, file))
                frequencies_df.set_index('trip_id', inplace=True)
    if 'frequencies_df' not in locals():
        frequencies_df = ''
    return frequencies_df


def load_gtfs_feed(r, gtfs_feed: dict, gtfsfeed_path) -> gtfslite.GTFS:
    feed = r.config['gtfs_feeds'][gtfs_feed]
    print(f'\n{gtfs_feed}')
    if 'modes' not in feed or feed['modes'] in [None, 'null', '']:
        feed['modes'] = ghsci.datasets['gtfs']['default_modes']
    if gtfsfeed_path.endswith('zip'):
        loaded_feeds = gtfslite.GTFS.load_zip(gtfsfeed_path)
    else:
        loaded_feeds = gtfslite.GTFS.load_zip(f'{gtfsfeed_path}.zip')
    loaded_feeds = stop_id_na_check(loaded_feeds)
    if loaded_feeds is None:
        print('Skipping feed due to multiple null stop_id values')
        return None
    loaded_feeds.stops = loaded_feeds.stops.query(
        f"(stop_lat>={r.bbox['ymin']}) and (stop_lat<={r.bbox['ymax']}) and (stop_lon>={r.bbox['xmin']}) and (stop_lon<={r.bbox['xmax']})",
    )
    loaded_feeds.stop_times = check_and_load_stop_times(
        loaded_feeds=loaded_feeds, feed_config=feed, feed_name=gtfs_feed,
    ).stop_times
    loaded_feeds.routes['route_id'] = loaded_feeds.routes[
        'route_id'
    ].str.strip()
    loaded_feeds.trips['route_id'] = loaded_feeds.trips['route_id'].str.strip()
    loaded_feeds.trips['trip_id'] = loaded_feeds.trips['trip_id'].str.strip()
    loaded_feeds.stop_times['trip_id'] = loaded_feeds.stop_times[
        'trip_id'
    ].str.strip()
    return loaded_feeds


def gtfs_analysis(codename):
    # simple timer for log file
    start = time.time()
    script = '_10_gtfs_analysis'
    task = 'GTFS analysis for identification of public transport stops with frequent service'
    r = ghsci.Region(codename)
    dow = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    analysis_period = ghsci.datasets['gtfs']['analysis_period']
    no_gtfs_folder_warning = 'GTFS folder not specified'
    if ('gtfs_feeds' in r.config) and (r.config['gtfs_feeds'] is not None):
        folder = r.config['gtfs_feeds'].pop('folder', no_gtfs_folder_warning)
        dissolve = r.config['gtfs_feeds'].pop('dissolve', None)
        if folder == no_gtfs_folder_warning:
            sys.exit(no_gtfs_folder_warning)

        if len(r.config['gtfs_feeds']) == 0:
            sys.exit('GTFS feeds not specified')

        stop_frequent = pd.DataFrame()
        print(
            '\nCommencing GTFS analysis.  GTFS analysis can be complex.  For details on expected data structures, including default route type codes, consult the GTFS Schedule Reference (https://gtfs.org/schedule/reference/).  Correct identification of transport modes may require custom configuration if GTFS feeds do not match the standard route_type codes defined in routes.txt.  Analysis will only be undertaken for stops aligned with trips in stop_times.txt, allowing mode of transport to be identified.  Service frequency analysis will only be undertaken for stops with scheduled services.  Where stop times are not defined but a stop sequence is defined, interpolation of stop times may be configured to support service frequency analysis.',
        )
        for gtfs_feed in r.config['gtfs_feeds']:
            # load GTFS Feed
            feed = r.config['gtfs_feeds'][gtfs_feed]
            start_date = r.config['gtfs_feeds'][gtfs_feed]['start_date_mmdd']
            end_date = r.config['gtfs_feeds'][gtfs_feed]['end_date_mmdd']
            gtfsfeed_path = f'{ghsci.folder_path}/process/data/{ghsci.datasets["gtfs"]["data_dir"]}/{folder}/{gtfs_feed}'
            loaded_feeds = load_gtfs_feed(r, gtfs_feed, gtfsfeed_path)
            if loaded_feeds is None:
                pass
            all_stops_in_feed = loaded_feeds.stops['stop_id'].nunique()
            print(
                f'  - analysis dates: {start_date} to {end_date}\n'
                f'  - analysis times: {ghsci.datasets["gtfs"]["analysis_period"]}\n'
                f'  - {all_stops_in_feed} unique stops in stops.txt\n',
            )
            # initialise a counter for stops aligned with mode
            stops_aligned_with_mode = 0
            for mode in feed['modes'].keys():
                # print(mode)
                start_date = feed['start_date_mmdd']
                end_date = feed['end_date_mmdd']
                start_hour = analysis_period[0]
                end_hour = analysis_period[1]

                route_types = (
                    feed['modes'][f'{mode}'].copy().pop('route_types', None)
                )
                agency_ids = (
                    feed['modes'][f'{mode}'].copy().pop('agency_id', None)
                )
                mode_stops = stops_by_mode(
                    loaded_feeds, route_types, agency_ids,
                )
                mode_stops_count = len(mode_stops)
                stops_aligned_with_mode += mode_stops_count
                if mode_stops_count > 0:
                    if route_types is not None:
                        print(
                            f'  - configured {mode} route type codes: {route_types}',
                        ),
                    if agency_ids is not None:
                        print(
                            f'  - configured {mode} agency id numbers: {agency_ids}',
                        ),
                    stops_headway = _gtfs_utils.get_hlc_stop_frequency(
                        loaded_feeds,
                        start_hour,
                        end_hour,
                        start_date,
                        end_date,
                        route_types,
                        agency_ids,
                        dow=dow,
                    )

                    stop_count = len(stops_headway)
                    all_stop_count = len(mode_stops)
                    if stop_count > 0:
                        stop_frequent_final = pd.merge(
                            loaded_feeds.stops[
                                (
                                    loaded_feeds.stops['stop_id'].isin(
                                        mode_stops,
                                    )
                                )
                            ],
                            stops_headway,
                            how='left',
                            on='stop_id',
                        )
                        stop_frequent_final['authority'] = feed[
                            'gtfs_provider'
                        ]
                        stop_frequent_final['mode'] = mode
                        stop_frequent_final['feed'] = gtfs_feed
                        stop_frequent = pd.concat(
                            [stop_frequent, stop_frequent_final],
                            ignore_index=True,
                        )
                    print(
                        f'  - {mode:13s} {stop_count:9.0f}/{mode_stops_count:.0f} ({100*(stop_count/mode_stops_count):.1f}%) {mode.lower()} stops aligned with departure times.',
                    )
            stops_without_mode = all_stops_in_feed - stops_aligned_with_mode
            if stops_without_mode > 0:
                print(
                    f'\n  - {stops_without_mode} stops in this feed were not aligned with a transport mode.  If GTFS feed uses non-standard route_types or agency_ids to identify transport modes, these can be defined in the region configuration file GTFS section.',
                )

        if len(stop_frequent) > 0:
            mode_freq_comparison = get_frequent_stop_stats(
                stop_frequent, group_by='mode',
            )
            print(
                f'\n{r.name} summary (all feeds):\n{mode_freq_comparison}\n\n',
            )
            if dissolve:
                stop_frequent = get_average_headway(stop_frequent)
                mode_freq_comparison = get_frequent_stop_stats(
                    stop_frequent, group_by='feed',
                )
                with pd.option_context('display.max_colwidth', 0):
                    print(
                        f'\n{r.name} summary (all feeds):\n{mode_freq_comparison}\n\n',
                    )
            gtfs_to_db(r, stop_frequent)
        else:
            print(
                f'Zero stop features identified in {r.name} during the analysis period\n',
            )
            print(
                f'(skipping export of {ghsci.datasets["gtfs"]["headway"]} to SQL database)\n',
            )
    else:
        print('GTFS feeds not configured for this city')
        print(
            f'(skipping export of {ghsci.datasets["gtfs"]["headway"]} to SQL database)\n',
        )

    # output to completion log
    script_running_log(r.config, script, task, start)
    r.engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    gtfs_analysis(codename)


if __name__ == '__main__':
    main()
