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
            f"""\nError: {na_check} null values found in stop_id column of stops.txt, meaning that stops cannot be uniquely identified.   Values of stop_id in the source data that may be problematic and result in multiple ambiguous null records include: [‘’, ‘#N/A’, ‘#N/A N/A’, ‘#NA’, ‘-1.#IND’, ‘-1.#QNAN’, ‘-NaN’, ‘-nan’, ‘1.#IND’, ‘1.#QNAN’, ‘<NA>’, ‘N/A’, ‘NA’, ‘NULL’, ‘NaN’, ‘None’, ‘n/a’, ‘nan’, ‘null’]. """,
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
                f'\n**Note**: {null_stop_times_stops} stops with null departure times found in stop_times.txt.\nThis GTFS feed has been configured to to fill null arrival and departure values.based on a linear interpolation according to the provided stop sequence start and end times within each trip_id.  This is an approximation based on the available information, but results may still differ from the actual service frequencies at these stops.',
            )
            loaded_feeds.stop_times = interpolate_stop_times(
                loaded_feeds.stop_times,
            )
        else:
            sys.exit(
                f'\n**WARNING**: {null_stop_times_stops} stops with null departure times found in stop_times.txt for this GTFS feed:\n{feed_name}: {feed_config}.\n\n  Use of this feed in analysis without specialised cleaning will result in inaccurate service frequencies.\n\nIt is recommended to interpolate stop_times values.  Optionally, this GTFS feed can be configured to have interpolation applied by adding an entry of "interpolate_stop_times: true" within its settings in the region configuration file.  This will attempt to fill null arrival and departure values using a linear interpolation according to the provided stop sequence start and end times within each trip_id.  This is an approximation based on the available information, but results may still differ from the actual service frequencies at these stops.',
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


def gtfs_analysis(codename):
    # simple timer for log file
    start = time.time()
    script = '_10_gtfs_analysis'
    task = 'create study region boundary'
    r = ghsci.Region(codename)
    dow = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    analysis_period = ghsci.datasets['gtfs']['analysis_period']
    no_gtfs_folder_warning = 'GTFS folder not specified'
    out_table = ghsci.datasets['gtfs']['headway']
    if r.config['gtfs_feeds'] is not None:
        folder = r.config['gtfs_feeds'].pop('folder', no_gtfs_folder_warning)
        dissolve = r.config['gtfs_feeds'].pop('dissolve', None)
        if folder == no_gtfs_folder_warning:
            sys.exit(no_gtfs_folder_warning)

        if len(r.config['gtfs_feeds']) == 0:
            sys.exit('GTFS feeds not specified')

        sql = f"""
            SELECT
            ST_Xmax(geom_4326) xmax,
            ST_Ymin(geom_4326) ymin,
            ST_Xmin(geom_4326) xmin,
            ST_Ymax(geom_4326) ymax
            FROM (
            SELECT
                ST_Transform(geom, 4326) geom_4326
            FROM {r.config['buffered_urban_study_region']}
            ) t;
        """
        with r.engine.begin() as connection:
            bbox = connection.execute(text(sql)).all()[0]._asdict()

        stop_frequent = pd.DataFrame()
        # gtfs_feed = list(r.config['gtfs_feeds'].keys())[0]
        for gtfs_feed in r.config['gtfs_feeds']:
            feed = r.config['gtfs_feeds'][gtfs_feed]
            gtfsfeed_path = f'{ghsci.folder_path}/process/data/{ghsci.datasets["gtfs"]["data_dir"]}/{folder}/{gtfs_feed}'
            print(f'\n{gtfsfeed_path}')
            start_date = feed['start_date_mmdd']
            end_date = feed['end_date_mmdd']
            if 'modes' not in feed or feed['modes'] in [None, 'null', '']:
                feed['modes'] = ghsci.datasets['gtfs']['default_modes']

            # load GTFS Feed
            if gtfsfeed_path.endswith('zip'):
                loaded_feeds = gtfslite.GTFS.load_zip(gtfsfeed_path)
            else:
                loaded_feeds = gtfslite.GTFS.load_zip(f'{gtfsfeed_path}.zip')

            loaded_feeds = stop_id_na_check(loaded_feeds)
            if loaded_feeds is None:
                print('Skipping feed due to multiple null stop_id values')
                continue

            loaded_feeds.stops = loaded_feeds.stops.query(
                f"(stop_lat>={bbox['ymin']}) and (stop_lat<={bbox['ymax']}) and (stop_lon>={bbox['xmin']}) and (stop_lon<={bbox['xmax']})",
            )

            loaded_feeds.stop_times = check_and_load_stop_times(
                loaded_feeds=loaded_feeds,
                feed_config=feed,
                feed_name=gtfs_feed,
            ).stop_times
            loaded_feeds.routes['route_id'] = loaded_feeds.routes[
                'route_id'
            ].str.strip()
            loaded_feeds.trips['route_id'] = loaded_feeds.trips[
                'route_id'
            ].str.strip()
            loaded_feeds.trips['trip_id'] = loaded_feeds.trips[
                'trip_id'
            ].str.strip()
            loaded_feeds.stop_times['trip_id'] = loaded_feeds.stop_times[
                'trip_id'
            ].str.strip()
            # load frequencies if exists
            for root, dirs, files in os.walk(gtfsfeed_path):
                # naive assumption that only one frequencies.txt exists in feed path...
                for file in files:
                    if file == 'frequencies.txt':
                        frequencies_df = pd.read_csv(os.path.join(root, file))
                        frequencies_df.set_index('trip_id', inplace=True)

            if 'frequencies_df' not in locals():
                frequencies_df = ''

            print(
                f'\n{r.name} analysis:\n'
                f'  - {gtfsfeed_path})\n'
                f'  - {start_date} to {end_date})\n'
                f'  - {analysis_period}\n\n',
            )
            for mode in feed['modes'].keys():
                # print(mode)
                startTime = time.time()
                start_hour = analysis_period[0]
                end_hour = analysis_period[1]

                route_types = (
                    feed['modes'][f'{mode}'].copy().pop('route_types', None)
                )
                agency_ids = (
                    feed['modes'][f'{mode}'].copy().pop('agency_id', None)
                )

                stops_headway = _gtfs_utils.get_hlc_stop_frequency(
                    loaded_feeds,
                    start_hour,
                    end_hour,
                    start_date,
                    end_date,
                    route_types,
                    agency_ids,
                    dow=dow,
                    frequencies=frequencies_df,
                )

                stop_count = len(stops_headway)
                all_stop_count = len(loaded_feeds.stops['stop_id'].unique())
                duration = time.time() - startTime
                if stop_count > 0:
                    stop_frequent_final = pd.merge(
                        loaded_feeds.stops,
                        stops_headway,
                        how='left',
                        on='stop_id',
                    )
                    stop_frequent_final['authority'] = feed['gtfs_provider']
                    stop_frequent_final['mode'] = mode
                    stop_frequent_final['feed'] = gtfs_feed
                    stop_frequent = pd.concat(
                        [stop_frequent, stop_frequent_final],
                        ignore_index=True,
                    )

                print(
                    f'     {mode:13s} {stop_count:9.0f}/{all_stop_count:.0f} ({100*(stop_count/all_stop_count):.1f}%) stops identified with departure times ({duration:,.2f} seconds)',
                )

        if len(stop_frequent) > 0:
            # show frequent stop stats
            tot_df = (
                stop_frequent.groupby('mode')[['stop_id']]
                .count()
                .rename(columns={'stop_id': 'tot_stops'})
            )
            headway30_df = (
                stop_frequent[stop_frequent['headway'] <= 30]
                .groupby('mode')[['stop_id']]
                .count()
                .rename(columns={'stop_id': 'headway<=30'})
            )
            headway20_df = (
                stop_frequent[stop_frequent['headway'] <= 20]
                .groupby('mode')[['stop_id']]
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
            print(
                f'\n{r.name} summary (all feeds):\n{mode_freq_comparison}\n\n',
            )

            if dissolve:
                unique_feeds = [
                    os.path.basename(x) for x in stop_frequent.feed.unique()
                ]
                agg_feed_description = (
                    f'average headway for stops across feeds: {unique_feeds}'
                )
                stop_frequent = stop_frequent.groupby('stop_id').mean()
                stop_frequent['feeds'] = agg_feed_description

                # post-aggregation summary
                stop_frequent.reset_index(inplace=True)
                tot_df = (
                    stop_frequent.groupby('feeds')[['stop_id']]
                    .count()
                    .rename(columns={'stop_id': 'tot_stops'})
                )
                headway30_df = (
                    stop_frequent[stop_frequent['headway'] <= 30]
                    .groupby('feeds')[['stop_id']]
                    .count()
                    .rename(columns={'stop_id': 'headway<=30'})
                )
                headway20_df = (
                    stop_frequent[stop_frequent['headway'] <= 20]
                    .groupby('feeds')[['stop_id']]
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
                with pd.option_context('display.max_colwidth', 0):
                    print(
                        f'\n{r.name} summary (all feeds):\n{mode_freq_comparison}\n\n',
                    )

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
        else:
            print(
                f'Zero stop features identified in {r.name} during the analysis period\n',
            )
            print(f'(skipping export of {out_table} to SQL database)\n')
    else:
        print('GTFS feeds not configured for this city')
        print(f'(skipping export of {out_table} to SQL database)\n')

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
