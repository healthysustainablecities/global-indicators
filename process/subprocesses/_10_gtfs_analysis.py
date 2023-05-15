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
import numpy as np
import pandas as pd

# import urbanaccess as ua
import ua_load
from script_running_log import script_running_log
from sqlalchemy import text


def gtfs_analysis(codename):
    # simple timer for log file
    start = time.time()
    script = '_10_gtfs_analysis'
    task = 'create study region boundary'
    today = ghsci.time.strftime('%Y-%m-%d')
    r = ghsci.Region(codename)
    engine = r.get_engine()
    dow = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
    analysis_period = ghsci.datasets['gtfs']['analysis_period']
    # could loop over headway intervals, but not implemented
    headway_intervals = ghsci.datasets['gtfs']['headway_intervals']
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
            ST_Xmin(geom_4326) xmin,
            ST_Ymin(geom_4326) ymin,
            ST_Xmax(geom_4326) xmax,
            ST_Ymax(geom_4326) ymax
            FROM (
            SELECT
                ST_Transform(geom, 4326) geom_4326
            FROM {r.config['buffered_urban_study_region']}
            ) t;
        """
        with engine.begin() as connection:
            bbox = connection.execute(text(sql)).all()[0]

        stop_frequent = pd.DataFrame()
        # gtfs_feed = list(r.config['gtfs_feeds'].keys())[0]
        for gtfs_feed in r.config['gtfs_feeds']:
            feed = r.config['gtfs_feeds'][gtfs_feed]
            gtfsfeed_path = f'{ghsci.folder_path}/process/data/{ghsci.datasets["gtfs"]["data_dir"]}/{folder}/{gtfs_feed}'
            print(f'\n{gtfsfeed_path}')
            start_date = feed['start_date_mmdd']
            end_date = feed['end_date_mmdd']
            if feed['modes'] is None:
                feed['modes'] = ghsci.datasets['gtfs']['default_modes']

            # load GTFS Feed
            loaded_feeds = ua_load.gtfsfeed_to_df(
                gtfsfeed_path=gtfsfeed_path,
                bbox=bbox,
                remove_stops_outsidebbox=True,
            )
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

                route_types = feed['modes'][f'{mode}']['route_types']
                agency_ids = feed['modes'][f'{mode}']['agency_id']

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
                duration = time.time() - startTime
                if stop_count > 0:
                    stop_frequent_final = pd.merge(
                        stops_headway,
                        loaded_feeds.stops,
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
                    f'     {mode:13s} {stop_count:9.0f} stops identified ({duration:,.2f} seconds)',
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
            with engine.begin() as connection:
                connection.execute(text(f'DROP TABLE IF EXISTS {out_table}'))
            stop_frequent.set_index('stop_id').to_sql(
                out_table, con=engine, index=True,
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
            with engine.begin() as connection:
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
    engine.dispose()


def main():
    try:
        codename = sys.argv[1]
    except IndexError:
        codename = None
    gtfs_analysis(codename)


if __name__ == '__main__':
    main()
