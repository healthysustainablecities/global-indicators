################################################################################
# Script: gtfs_headway_analysis.py

# Description: This script contain functions and processes to retain public transit stops points with frequent services
# Outputs: 'frequent_transit_headway_2020May_python.gpkg' containing
# stop point layer with headway information for each study region

################################################################################
import pandas as pd
import geopandas as gpd
import os
import time
import networkx as nx
import osmnx as ox
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point, LineString, Polygon

import calendar
import datetime
from datetime import timedelta


import urbanaccess as ua
import ua_load
import gtfs_config



def get_date_weekday_df(start, end):
    """
    Create table to show weekday of all dates from start to end date

    Parameters
    ----------
    start: str or datetime

    end: str or datetime

    Returns
    -------
    date_weekday_df: pandas.DataFrame
    """
    date_range = pd.date_range(start=start, end=end)
    dates = pd.DataFrame(date_range, columns=['date'])
    # Return the day of the week as an integer, where Monday is 0 and Sunday is 6.
    weekdays = pd.DataFrame(date_range.weekday, columns=['weekday'])
    date_weekday_df = dates.join(weekdays)

    # replace weekday numeric to str values
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    date_weekday_df = date_weekday_df.replace([0, 1, 2, 3, 4, 5, 6], weekdays)
    return date_weekday_df


def set_date_service_table(loaded_feeds):
    """
    Summarize service that run on each date;
    Use it to summarise service. For example, get a count of the number of services for a date.

    Parameters
    ----------
    loaded_feeds: gtfsfeeds_dataframe with GTFS objects

    Returns
    -------
    date_service_df : pandas.DataFrame
    """
    # tabulate each date and weekday from the start to the end date in calendar
    dates = get_date_weekday_df(start=str(min(loaded_feeds.calendar['start_date'])),
                            end=str(max(loaded_feeds.calendar['end_date'])))

    # gather services by weekdays
    service_ids_weekdays = loaded_feeds.calendar[['service_id', 'start_date', 'end_date',
                           'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
                          ]].set_index(['service_id', 'start_date', 'end_date'
                                       ]).stack().to_frame().reset_index()

    service_ids_weekdays = service_ids_weekdays[(service_ids_weekdays[0] == 1)
                                               ].rename(columns={'level_3':'weekday'}).drop(columns=[0])
    # create table to connect every date to corresponding services (all dates from earliest to latest)
    # set services to dates according to weekdays and start/end date
    date_service_df = pd.merge(dates, service_ids_weekdays, on='weekday')

    date_service_df['start_date'] = pd.to_datetime(date_service_df['start_date'], format='%Y%m%d')
    date_service_df['end_date'] = pd.to_datetime(date_service_df['end_date'], format='%Y%m%d')


    #filter valid service date within start and end date
    date_service_df = date_service_df[(date_service_df['date'] >= date_service_df['start_date'])
                    & (date_service_df['date'] <= date_service_df['end_date'])][['date', 'weekday', 'service_id']]

    if len(loaded_feeds.calendar_dates) > 0:
        # add calendar_dates additions (1) if the additional dates are within the start and end date range
        addition_dates = loaded_feeds.calendar_dates[(loaded_feeds.calendar_dates['exception_type']==1)
                                                    ][['service_id', 'date']]

        min_start_datetime = pd.to_datetime(str(min(loaded_feeds.calendar['start_date'])), format='%Y%m%d')
        max_end_datetime = pd.to_datetime(str(max(loaded_feeds.calendar['end_date'])), format='%Y%m%d')
        addition_dates['date'] = pd.to_datetime(addition_dates['date'], format='%Y%m%d')

        addition_dates['within_range'] = addition_dates['date'].apply(
            lambda x: 1 if (x >= min_start_datetime
                           ) & (x <= max_end_datetime) else 0)

        addition_dates = addition_dates[addition_dates['within_range'] == 1][['service_id', 'date']]
        date_service_df = pd.concat([addition_dates, date_service_df], ignore_index=True)

        # remove calendar_dates exceptions (2)
        exception_dates = loaded_feeds.calendar_dates[(loaded_feeds.calendar_dates['exception_type']==2)
                                                     ][['service_id', 'date']]

        exception_dates['date'] = pd.to_datetime(exception_dates['date'], format='%Y%m%d')

        date_service_exception_df = pd.merge(exception_dates.set_index(['service_id', 'date']
                                          ), date_service_df.set_index(['service_id', 'date']),
                 left_index=True, right_index=True, indicator=True, how='outer').reset_index()

        date_service_df = date_service_exception_df[(date_service_exception_df['_merge']=='right_only')
                                                   ][['service_id', 'date', 'weekday']]

    if len(date_service_df) == 0:
        print('No start and end dates defined in feed')

    return date_service_df


# Get trip counts per day between the start and end day of the feed.
def get_trip_counts_per_day(loaded_feeds):
    """
    Get trip counts per day between the start and end day of the feed.

    Parameters
    ----------
    loaded_feeds: gtfsfeeds_dataframe with GTFS objects

   Returns
    -------
    daily_trip_counts : pandas.DataFrame
        Has columns "date" and "trip_counts"
    """
    date_service_df = set_date_service_table(loaded_feeds)
    daily_trip_counts = pd.merge(date_service_df, loaded_feeds.trips, on='service_id').groupby(['date'
                                                    ], sort=False)['trip_id'].count().to_frame('trip_counts')
    daily_trip_counts = daily_trip_counts.sort_index().reset_index()
    return daily_trip_counts


# function revised from gtfspy (reference:https://www.nature.com/articles/sdata201889#Sec21):
# https://github.com/CxAalto/gtfspy/blob/47f1526fee43b83b396c7e75b64a4b9de3b467a0/gtfspy/gtfs.py#L679
# function revised from gtfspy (reference:https://www.nature.com/articles/sdata201889#Sec21):
# https://github.com/CxAalto/gtfspy/blob/47f1526fee43b83b396c7e75b64a4b9de3b467a0/gtfspy/gtfs.py#L679
def get_weekly_extract_start_date(daily_trip_counts, weekdays_at_least_of_max=0.9,
                                start_date=None, end_date=None):
    """
    Find a suitable weekly extract start date (monday).
    The goal is to obtain as 'usual' week as possible.
    The weekdays of the weekly extract week should contain
    at least 0.9 (default) of the total maximum of trips.

    Parameters
    ----------
    daily_trip_counts: pandas.DataFrame
        Has columns "date" and "trip_counts"

    weekdays_at_least_of_max: float

    start_date: str or datetime, semi-optional
        if given, overrides the recorded start date in the feed

    end_date: str or datetime, semi-optional
        if given, overrides the recorded end date in the feed,
        must given if start_date is specified

    Returns
    -------
    row['date']: int or str or Timestamp

    """

    # make sure the daily trip count is sorted by date
    daily_trip_counts = daily_trip_counts.sort_values('date').reset_index()
    # search start date, defaults to the smallest date in the feed
    if (isinstance(start_date, str) & isinstance(end_date, str)):
        search_start_date = datetime.datetime.strptime(start_date, "%Y%m%d")
        search_end_date = datetime.datetime.strptime(end_date, "%Y%m%d")
        feed_min_date = search_start_date
        feed_max_date = search_end_date
    elif (isinstance(start_date, datetime.datetime) & isinstance(end_date, datetime.datetime)):
        search_start_date = start_date
        search_end_date = end_date
        feed_min_date = search_end_date
        feed_max_date = search_end_date
    else:
        assert start_date is None
        warnings.warn("Start and end date is not given or in wrong formats, defaults to the smallest date when any operations take place.")
        search_start_date = daily_trip_counts['date'].min()
        feed_min_date = search_start_date
        feed_max_date = daily_trip_counts['date'].max()

    assert (feed_max_date - feed_min_date >= datetime.timedelta(days=7)), \
    "Dataset is not long enough for providing week long extracts"

    # get first a valid monday where the search for the week can be started:
    next_monday_from_search_start_date = search_start_date + timedelta(days=(7 - search_start_date.weekday()))

    if not (feed_min_date <= next_monday_from_search_start_date <= feed_max_date):
        warnings.warn("The next monday after the (possibly user) specified download date is not present in the database."
                  "Resorting to first monday after the beginning of operations instead.")
        search_start_date = daily_trip_counts['date'].min()
        feed_min_date = daily_trip_counts['date'].min()
        feed_max_date = daily_trip_counts['date'].max()
        next_monday_from_search_start_date = feed_min_date + timedelta(days=(7 - feed_min_date.weekday()))

    # limit feeds within start and end date
    daily_trip_counts = daily_trip_counts[(feed_min_date <= daily_trip_counts['date']) &  (daily_trip_counts['date']<=feed_max_date)]
    daily_trip_counts = daily_trip_counts.sort_values('date').reset_index()

    # Take 95th percentile to omit special days, if any exist.
    max_trip_count = daily_trip_counts['trip_counts'].quantile(0.95)

    threshold = weekdays_at_least_of_max * max_trip_count
    threshold_fulfilling_days = daily_trip_counts['trip_counts'] > threshold

    # look forward first
    # get the index of the trip:
    search_start_monday_index = daily_trip_counts[daily_trip_counts['date'] == next_monday_from_search_start_date].index[0]

         # get starting point
    while_loop_monday_index = search_start_monday_index
    while len(daily_trip_counts.index) >= while_loop_monday_index + 7:
        if all(threshold_fulfilling_days[while_loop_monday_index:while_loop_monday_index + 5]):
            row = daily_trip_counts.iloc[while_loop_monday_index]
            #return row['date']
        while_loop_monday_index += 7

    while_loop_monday_index = search_start_monday_index - 7
    # then backwards
    while while_loop_monday_index >= 0:
        if all(threshold_fulfilling_days[while_loop_monday_index:while_loop_monday_index + 5]):
            row = daily_trip_counts.iloc[while_loop_monday_index]
            #return row['date']
        while_loop_monday_index -= 7

    return row['date']

# revise based on tidytransit [get_stop_frequency function]
# https://github.com/r-transit/tidytransit/blob/master/R/frequencies.R

def get_hlc_stop_frequency(loaded_feeds, start_hour, end_hour, start_date,
                           end_date, route_types, agency_ids=None,
                           dow=['monday','tuesday','wednesday','thursday','friday']):
    """
    Summarize dataframe of stops with average headway based on the number of daily departures within a given timeframe

    Parameters
    ----------
    loaded_feeds: gtfsfeeds_dataframe with GTFS objects

    start_hour: str
        a str indicating the start hour, for example: '07:00:00'

    end_hour: str
        a str indicating the end hour, for example: '19:00:00'

    start_date: str or datetime

    end_date: str or datetime

    route_types: list

    agency_ids: list
        optional, default to none

    dow: list
        optional, default to list of weekdays ['monday','tuesday','wednesday','thursday','friday']


    Returns
    -------
    date_service_df : pandas.DataFrame
    """

    startTime = time.time()
    # set service date
    date_service_df = set_date_service_table(loaded_feeds)

    # limit within specified start and end date, and within weekdays
    start_date_mmdd = pd.to_datetime(start_date, format='%Y%m%d')
    end_date_mmdd = pd.to_datetime(end_date, format='%Y%m%d')

    date_service_df = date_service_df[date_service_df['weekday'].isin(dow)
                                     ][(date_service_df['date'] >= start_date_mmdd)
                                       & (date_service_df['date'] <= end_date_mmdd)].drop_duplicates()
    #print('     ', len(date_service_df), ' unique service dates are identified within',
          #dow, ' from ', start_date, ' to ', end_date)


    trips_routes = pd.merge(loaded_feeds.trips, loaded_feeds.routes, on='route_id', how='left')
    # filter route trips based on valid services
    valid_service_ids = date_service_df.service_id.unique()
    trips_routes = trips_routes[trips_routes['service_id'].isin(valid_service_ids)]

    # filter trips within route types and agency id
    if (route_types != None) & (agency_ids == None):
        trips_routes = trips_routes[(trips_routes['route_type'].isin(route_types))]
        date_service_df = date_service_df[date_service_df['service_id'].isin(trips_routes.service_id.unique())]
    elif (route_types != None) & (agency_ids != None):
        trips_routes = trips_routes[(trips_routes['agency_id'].isin(agency_ids)) & (trips_routes['route_type'].isin(route_types))]
        date_service_df = date_service_df[date_service_df['service_id'].isin(trips_routes.service_id.unique())]
    elif (route_types == None) & (agency_ids != None):
        trips_routes = trips_routes[(trips_routes['agency_id'].isin(agency_ids))]
        date_service_df = date_service_df[date_service_df['service_id'].isin(trips_routes.service_id.unique())]

    # takes input start and end time range from 24 hour clock and converts
    # it to seconds past midnight
    # in order to select times that may be after midnight

    # convert string time components to integer and then calculate seconds
    # past midnight
    # convert starttime 24 hour to seconds past midnight
    start_h = int(str(start_hour[0:2]))
    start_m = int(str(start_hour[3:5]))
    start_s = int(str(start_hour[6:8]))
    starttime_sec = (start_h * 60 * 60) + (start_m * 60) + start_s

    # convert endtime 24 hour to seconds past midnight
    end_h = int(str(end_hour[0:2]))
    end_m = int(str(end_hour[3:5]))
    end_s = int(str(end_hour[6:8]))
    endtime_sec = (end_h * 60 * 60) + (end_m * 60) + end_s

    stop_times = loaded_feeds.stop_times[loaded_feeds.stop_times.trip_id.isin(trips_routes.trip_id.unique())]

    # filter stop times within the timerange
    selected_stop_times_df = stop_times[((starttime_sec < stop_times[
        'departure_time_sec'])  & (stop_times["departure_time_sec"] < endtime_sec))]
    selected_stop_times_df = selected_stop_times_df[['trip_id', 'stop_id']].set_index('trip_id')

    if len(selected_stop_times_df) == 0:
        print('     Zero trip is found within the specified start and end hours')

    # count sec. and min. within the timerange
    t1_min = (endtime_sec - starttime_sec)/60

    # some feeds do not contain direction_id field in the trip file or have null values
    if 'direction_id' not in trips_routes.columns:
        # filter valid service trips
        valid_service_trips = pd.merge(date_service_df, trips_routes, on='service_id', how='left')
        valid_service_trips = valid_service_trips[['trip_id', 'date']].set_index('trip_id')

        # filter stops within valid service and time range
        stop_time_trips = pd.merge(valid_service_trips, selected_stop_times_df, left_index=True, right_index=True, how='inner').reset_index()

        # get counts of departure of each stop per day
        stop_time_trips_departure = stop_time_trips.groupby(['stop_id', 'date'
                                                        ], sort=False)['trip_id'].count().to_frame('departure')

        # for each stop we average headway over dates
        # We take the best (smallest) headway out of the two possible of the stop
        stop_time_trips_departure['headway'] = round(t1_min / stop_time_trips_departure['departure'])

        stops_headway = stop_time_trips_departure.reset_index().groupby('stop_id').min()[['headway']]

    elif trips_routes['direction_id'].isnull().values.any() == False:
        # filter valid service trips
        valid_service_trips = pd.merge(date_service_df, trips_routes, on='service_id', how='left')
        valid_service_trips = valid_service_trips[['trip_id', 'date', 'direction_id']].set_index('trip_id')

        # filter stops within valid service and time range
        stop_time_trips = pd.merge(valid_service_trips, selected_stop_times_df, left_index=True, right_index=True, how='inner').reset_index()

        # get counts of departure of each stop of each direction per day
        stop_time_trips_departure = stop_time_trips.groupby(['direction_id', 'stop_id', 'date'
                                                        ], sort=False)['trip_id'].count().to_frame('departure')

        stop_time_trips_departure['headway'] = round(t1_min / stop_time_trips_departure['departure'])

        stops_headway = stop_time_trips_departure.reset_index().groupby([
        'stop_id', 'direction_id']).mean().groupby('stop_id').min()[['headway']]

    else:
        # filter valid service trips
        valid_service_trips = pd.merge(date_service_df, trips_routes, on='service_id', how='left')
        valid_service_trips = valid_service_trips[['trip_id', 'date']].set_index('trip_id')

        # filter stops within valid service and time range
        stop_time_trips = pd.merge(valid_service_trips, selected_stop_times_df, left_index=True, right_index=True, how='inner').reset_index()

        # get counts of departure of each stop per day
        stop_time_trips_departure = stop_time_trips.groupby(['stop_id', 'date'
                                                        ], sort=False)['trip_id'].count().to_frame('departure')
        # for each stop we average headway over dates
        # We take the best (smallest) headway out of the two possible of the stop
        stop_time_trips_departure['headway'] = round(t1_min / stop_time_trips_departure['departure'])

        stops_headway = stop_time_trips_departure.reset_index().groupby('stop_id').min()[['headway']]

    #print('     Time to complete average stop headway analysis with {} frequent stops is: {}'.format(len(stops_headway), time.time() - startTime))
    if len(stops_headway) == 0:
        print('     Zero stop is found within the specified timerange')

    return stops_headway


if __name__ == '__main__':
    # get the work directory
    dirname = os.path.abspath('')

    # geopackage path where to save processing layers
    gpkgPath_output = os.path.join(dirname, 'gtfs_frequent_transit_headway_202006_python.gpkg')


    # get study region GTFS frequent stop parameters config
    GTFS = gtfs_config.GTFS
    for city in GTFS.keys():
        city_config = GTFS['{}'.format(city)]
        gtfsfeed_path = city_config['gtfs_filename']
        start_date = city_config['start_date_mmdd']
        end_date = city_config['end_date_mmdd']
        authority = city_config['gtfs_provider']
        bbox = GTFS['{}'.format(city)]['bbox']
        crs = GTFS['{}'.format(city)]['crs']
        gtfs_provider = GTFS['{}'.format(city)]['gtfs_provider']
        hour = 'day_time'

        # load GTFS Feed
        loaded_feeds = ua_load.gtfsfeed_to_df(gtfsfeed_path=gtfsfeed_path, validation=True, bbox=bbox, remove_stops_outsidebbox=True)

        stop_frequent = pd.DataFrame()
        for mode in city_config['modes'].keys():
            #print(mode)
            startTime = time.time()
            print('Start to process {} {} analysis during {}'.format(city, mode, hour))

            hour_1 = city_config['modes']['{}'.format(mode)]['{}'.format(hour)]
            start_hour = hour_1[0]
            end_hour = hour_1[1]

            headway_intervals = city_config['modes']['{}'.format(mode)]['intervals']
            route_types = city_config['modes']['{}'.format(mode)]['route_types']
            agency_ids = city_config['modes']['{}'.format(mode)]['agency_id']

            #count trips per day
            daily_trip_counts = get_trip_counts_per_day(loaded_feeds)
            # derive a usual/representative week for frequency analysis
            usual_start_date = get_weekly_extract_start_date(daily_trip_counts, weekdays_at_least_of_max=0.9,
                                                             start_date=start_date, end_date=end_date)

            # set the start and end date to usual week of weekday operation (Monday to Friday)
            start_date_usual = usual_start_date
            end_date_usual = usual_start_date + timedelta(4)

            stops_headway = get_hlc_stop_frequency(loaded_feeds, start_hour, end_hour, start_date_usual,
                               end_date_usual, route_types, agency_ids,
                               dow=['monday','tuesday','wednesday','thursday','friday'])


            if len(stops_headway) > 0:
                stop_frequent_final = pd.merge(stops_headway, loaded_feeds.stops, how='left', on='stop_id')
                stop_frequent_final['authority'] = authority
                stop_frequent_final['mode'] = mode
                stop_frequent = stop_frequent.append(stop_frequent_final)
                print('     Complete {} ({}) {} analysis during {} with {} stop counts in {:,.2f} seconds  \n'.format(
                    city, authority, mode, hour, len(stops_headway), time.time() - startTime))
            else:
                print('     {} {} feature is found in {} ({}) during {} \n'.format(
                    len(stops_headway), mode, city, authority, hour))
                continue

        if len(stop_frequent) > 0:
            # get spatial features for freqent stops
            # add stop id geometry
            stop_frequent['geometry'] = stop_frequent.apply(
                lambda row: Point(row['stop_lon'], row['stop_lat']), axis=1)
            stop_frequent_gdf = gpd.GeoDataFrame(stop_frequent)

            # define projection, same as study region projection
            default_crs = 'epsg:4326'
            stop_frequent_gdf.crs = {'init' :'{}'.format(default_crs)}
            stop_frequent_gdf = ox.projection.project_gdf(stop_frequent_gdf, to_crs=crs, to_latlong=False)

            # save to output file
            # save the frequent stop by study region and modes to a new layer in geopackage

            stop_frequent_gdf.to_file(
                gpkgPath_output,
                layer='{}_stops_headway_{}_{}_{}'.format(
                    city, gtfs_provider, start_date, end_date),
                driver='GPKG')

            # show frequent stop stats
            tot_df = stop_frequent_gdf.groupby('mode')[['stop_id']].count().rename(columns = {'stop_id':'tot_stops'})
            headway30_df = stop_frequent_gdf[stop_frequent_gdf['headway']<=30].groupby('mode')[['stop_id']].count().rename(columns = {'stop_id':'headway<=30'})
            headway20_df = stop_frequent_gdf[stop_frequent_gdf['headway']<=20].groupby('mode')[['stop_id']].count().rename(columns = {'stop_id':'headway<=20'})

            mode_freq_comparison = pd.concat([tot_df, headway30_df, headway20_df], axis=1)
            mode_freq_comparison.loc["total"] = mode_freq_comparison.sum()

            mode_freq_comparison['pct_headway<=30'] = (mode_freq_comparison['headway<=30']*100 / mode_freq_comparison['tot_stops']).round(2)
            mode_freq_comparison['pct_headway<=20'] = (mode_freq_comparison['headway<=20']*100 / mode_freq_comparison['tot_stops']).round(2)
            print(mode_freq_comparison)
        else:
            print('     Zero stop feature is found in {} ({}) during {} \n'.format(
            city, authority, hour))
            continue
