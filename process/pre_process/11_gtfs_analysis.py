################################################################################
# Script: gtfs_headway_analysis.py

# Description: This script contain functions and processes to retain public transit stops points with regular services
# Outputs: 'pt_stops_headway' table with headway information for each study region

################################################################################
import pandas as pd
import os
import time
import numpy as np
from sqlalchemy import create_engine,inspect

# import urbanaccess as ua
import ua_load

from script_running_log import script_running_log

# Import custom variables for National Liveability indicator process
from _project_setup import *
from _gtfs_utils import *

def main():
    today = time.strftime('%Y-%m-%d')
    # simple timer for log file
    start = time.time()
    script = os.path.basename(sys.argv[0])
    task = 'create study region boundary'
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    dow=['monday','tuesday','wednesday','thursday','friday']
    analysis_period   = gtfs['analysis_period']
    # could loop over headway intervals, but not implemented
    headway_intervals = gtfs['headway_intervals'] 
    no_gtfs_folder_warning = "GTFS folder not specified"
    out_table = gtfs['headway']
    if gtfs_feeds is not None:
        folder = gtfs_feeds.pop('folder',no_gtfs_folder_warning)
        dissolve = gtfs_feeds.pop('dissolve',None)
        if folder==no_gtfs_folder_warning:
            sys.exit(no_gtfs_folder_warning)
        
        if len(gtfs_feeds)==0:
            sys.exit( "GTFS feeds not specified")
        
        stop_frequent = pd.DataFrame()
        # gtfs_feed = list(gtfs_feeds.keys())[0]
        for gtfs_feed in gtfs_feeds:
            feed = gtfs_feeds[gtfs_feed]
            gtfsfeed_path = f'{gtfs["data_dir"]}/{folder}/{gtfs_feed}'
            print(f'\n{gtfsfeed_path}')
            start_date = feed['start_date_mmdd']
            end_date = feed['end_date_mmdd']
            if feed['modes'] is None:
                feed['modes'] = gtfs['default_modes']
            
            sql = f'''
             SELECT 
                ST_Xmin(geom_4326) xmin,
                ST_Ymin(geom_4326) ymin,
                ST_Xmax(geom_4326) xmax,
                ST_Ymax(geom_4326) ymax
             FROM {study_region}_1600m;
            '''
            bbox = engine.execute(sql).all()[0]
            
            # load GTFS Feed
            loaded_feeds = ua_load.gtfsfeed_to_df(
                gtfsfeed_path=gtfsfeed_path, 
                bbox=bbox, 
                remove_stops_outsidebbox=True)
            
            # load frequencies if exists
            for root, dirs, files in os.walk(gtfsfeed_path):
                # naive assumption that only one frequencies.txt exists in feed path...
                for file in files:
                    if file == 'frequencies.txt':
                        frequencies_df = pd.read_csv(os.path.join(root, file))
                        frequencies_df.set_index('trip_id',inplace=True)
            
            if 'frequencies_df' not in locals():
                frequencies_df = ''
            
            print(
                f'\n{full_locale} analysis:\n'
                f'  - {gtfsfeed_path})\n'
                f'  - {start_date} to {end_date})\n'
                f'  - {analysis_period}\n\n')
            for mode in feed['modes'].keys():
                #print(mode)
                startTime = time.time()
                start_hour = analysis_period[0]
                end_hour = analysis_period[1]
                
                route_types = feed['modes'][f'{mode}']['route_types']
                agency_ids = feed['modes'][f'{mode}']['agency_id']
                
                stops_headway = get_hlc_stop_frequency(loaded_feeds, start_hour, end_hour, start_date,
                                   end_date, route_types, agency_ids,
                                   dow=dow,
                                   frequencies = frequencies_df)
                
                stop_count = len(stops_headway)
                duration = time.time() - startTime
                if stop_count > 0:
                    stop_frequent_final = pd.merge(stops_headway, loaded_feeds.stops, how='left', on='stop_id')
                    stop_frequent_final['authority'] = feed['gtfs_provider']
                    stop_frequent_final['mode'] = mode
                    stop_frequent_final['feed'] = gtfs_feed
                    stop_frequent = stop_frequent.append(stop_frequent_final)
                
                print(f'     {mode:13s} {stop_count:9.0f} stops identified ({duration:,.2f} seconds)')
        
        if len(stop_frequent) > 0:        
            # show frequent stop stats
            tot_df = stop_frequent\
                .groupby('mode')[['stop_id']]\
                .count()\
                .rename(columns = {'stop_id':'tot_stops'})
            headway30_df = stop_frequent[stop_frequent['headway']<=30]\
                .groupby('mode')[['stop_id']]\
                .count()\
                .rename(columns = {'stop_id':'headway<=30'})
            headway20_df = stop_frequent[stop_frequent['headway']<=20]\
                .groupby('mode')[['stop_id']]\
                .count()\
                .rename(columns = {'stop_id':'headway<=20'})
            
            mode_freq_comparison = pd.concat([tot_df, headway30_df, headway20_df], axis=1)
            mode_freq_comparison.loc["total"] = mode_freq_comparison.sum()
            
            mode_freq_comparison['pct_headway<=30'] = (mode_freq_comparison['headway<=30']*100 \
                                                        / mode_freq_comparison['tot_stops']).round(2)
            mode_freq_comparison['pct_headway<=20'] = (mode_freq_comparison['headway<=20']*100 \
                                                        / mode_freq_comparison['tot_stops']).round(2)
            print(f'\n{full_locale} summary (all feeds):\n{mode_freq_comparison}\n\n')
            
            if dissolve:
                unique_feeds = [os.path.basename(x) for x in stop_frequent.feed.unique()]
                agg_feed_description = f'average headway for stops across feeds: {unique_feeds}'
                stop_frequent = stop_frequent.groupby('stop_id').mean()
                stop_frequent['feeds'] = agg_feed_description
                
                # post-aggregation summary
                stop_frequent.reset_index(inplace=True)
                tot_df = stop_frequent.groupby('feeds')[['stop_id']].count()\
                    .rename(columns = {'stop_id':'tot_stops'})
                headway30_df = stop_frequent[stop_frequent['headway']<=30]\
                    .groupby('feeds')[['stop_id']].count().rename(columns = {'stop_id':'headway<=30'})
                headway20_df = stop_frequent[stop_frequent['headway']<=20]\
                    .groupby('feeds')[['stop_id']].count().rename(columns = {'stop_id':'headway<=20'})
                
                mode_freq_comparison = pd.concat([tot_df, headway30_df, headway20_df], axis=1)
                mode_freq_comparison.loc["total"] = mode_freq_comparison.sum()
                
                mode_freq_comparison['pct_headway<=30'] = (mode_freq_comparison['headway<=30']*100 \
                                                            / mode_freq_comparison['tot_stops']).round(2)
                mode_freq_comparison['pct_headway<=20'] = (mode_freq_comparison['headway<=20']*100 \
                                                            / mode_freq_comparison['tot_stops']).round(2)
                with pd.option_context('display.max_colwidth', 0):
                    print(f'\n{full_locale} summary (all feeds):\n{mode_freq_comparison}\n\n')
           
            # save to output file
            # save the frequent stop by study region and modes to SQL database
            engine.execute(f'DROP TABLE IF EXISTS {out_table}')
            stop_frequent.set_index('stop_id').to_sql(
                out_table,
                con=engine, 
                index=True)
            sql = f'''
            ALTER TABLE {out_table} ADD COLUMN geom geometry(Point, {srid});
            UPDATE {out_table}
                SET geom = ST_Transform(
                    ST_SetSRID(
                        ST_MakePoint(
                            stop_lon, 
                            stop_lat
                            ), 
                        4326), 
                {srid})
            '''
            engine.execute(sql)
            print(f'{out_table} exported to SQL database\n')
        else:
            print(f'Zero stop features identified in {full_locale} during the analysis period\n')
            print(f'(skipping export of {out_table} to SQL database)\n')
    else:
        print('GTFS feeds not configured for this city')
        print(f'(skipping export of {out_table} to SQL database)\n')
    script_running_log(script, task, start, locale)
    engine.dispose()

if __name__ == '__main__':   
    main() 
