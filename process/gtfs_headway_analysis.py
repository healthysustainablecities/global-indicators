################################################################################
# Script: gtfs_headway_analysis.py
# Description: This script contain functions and processes to retain public transit stops points with frequent services
# Outputs: 'frequent_transit_headway_2020April_python.gpkg' containing
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

import urbanaccess as ua
import ua_load

# set up study region GTFS config
GTFS = {
        'adelaide':{'gtfs_filename':'data/Transport/2019/gtfs_au_sa_adelaidemetro_20191004',
                    'gtfs_provider' : 'Adelaide Metro',
                    'gtfs_year' : '2019',
                    # define month and day for "representative period" ie. not in school time
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                    # get bounding box from study region boundary shapefile
                    # bounding box formatted as a 4 element tuple: (lng_max, lat_min, lng_min, lat_max)
                    # you can generate a bounding box by going to http://boundingbox.klokantech.com/ and selecting the CSV format.
                    'bbox' : (138.46098212857206, -35.15966609024628, 138.74830806651352, -34.71454282915053),
                    # define modes for GTFS feed(s) as per agency_id codes in agency.txt below
                    'modes' : {
                        'bus' : {'route_types': [3],
                                  'peak_time' : ['07:00:00', '09:00:00'],
                                  'day_time' : ['07:00:00', '19:00:00'],
                                  'intervals': 30,
                                 'agency_id': None},
                        'tram':{'route_types': [0],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None},
                        'train':{'route_types': [1,2],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None},

                        'ferry':{'route_types': [4],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None}
                    }
                   },
        'melbourne':{'gtfs_filename':'data/Transport/2019/gtfs_au_vic_ptv_20191004',
                    'gtfs_provider' : 'Public Transport Victoria',
                    'gtfs_year' : '2019',
                    # define month and day for "representative period" ie. not in school time
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                     'bbox' : (144.59067957842007, -38.21131973169178, 145.39847326519424, -37.61837232908795),
                    # define modes for GTFS feed(s) as per agency_id codes in agency.txt below
                    'modes' : {
                        'bus' : {'route_types': [3],
                                  'peak_time' : ['07:00:00', '09:00:00'],
                                  'day_time' : ['07:00:00', '19:00:00'],
                                  'intervals': 30,
                                 'agency_id': [4, 6]},
                        'tram':{'route_types': [0],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': [3]},
                        'train':{'route_types': [1,2],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': [1,2]}

                    }
                   },
        'sydney' : {'gtfs_filename':'data/Transport/2019/gtfs_au_nsw_tfnsw_complete_20190619',
                    'gtfs_provider' : 'Transport for NSW',
                    'gtfs_year' : '2019',
                    # define month and day for "representative period" ie. not in school time
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                    'bbox' : (150.6290606117829, -34.12321411958463, 151.3206735172292, -33.66275213092711),
                    # define modes for GTFS feed(s) as per agency_id codes in agency.txt below
                    'modes' : {
                        'bus' : {'route_types': [700,712,714],
                                  'peak_time' : ['07:00:00', '09:00:00'],
                                  'day_time' : ['07:00:00', '19:00:00'],
                                  'intervals': 30,
                                 'agency_id': None},
                        'tram':{'route_types': [0],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None},
                        'train':{'route_types': [2,401],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None},

                        'ferry':{'route_types': [4],
                                'peak_time' : ['07:00:00', '09:00:00'],
                                'day_time' : ['07:00:00', '19:00:00'],
                                'intervals': 30,
                                'agency_id': None}
                    }
                   }
       }


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
    return date_service_df


# revise based on tidytransit [get_stop_frequency function]
# https://github.com/r-transit/tidytransit/blob/master/R/frequencies.R

def get_hlc_stop_frequency(loaded_feeds, start_hour='7:00:00', end_hour= '19:00:00', start_date,
                           end_date, route_types, agency_ids=None,
                           dow=['monday','tuesday','wednesday','thursday','friday']):
    """
    Summarize dataframe of stops with average headway based on the number of daily departures within a given timeframe

    Parameters
    ----------
    loaded_feeds: gtfsfeeds_dataframe with GTFS objects

    start_hour: int
        optional, an integer indicating the start hour

    end_hour:  int
        optional, an integer indicating the end hour

    start_date: str or datetime

    end_date: str or datetime

    route_types: list

    agency_ids: list
        optional, default to none

    dow: list
        option, default to list of weekdays ['monday','tuesday','wednesday','thursday','friday']


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

    # filter valid service trips
    valid_service_trips = pd.merge(date_service_df, trips_routes, on='service_id', how='left')
    valid_service_trips = valid_service_trips[['trip_id', 'date', 'direction_id']].set_index('trip_id')

    # filter stops within valid service and time range
    stop_time_trips = pd.merge(valid_service_trips, selected_stop_times_df, left_index=True, right_index=True, how='inner').reset_index()

    # get counts of departure of each stop of each direction per day
    stop_time_trips_departure = stop_time_trips.groupby(['direction_id', 'stop_id', 'date'
                                                    ], sort=False)['trip_id'].count().to_frame('departure')

    # count sec. and min. within the timerange
    t1_min = (endtime_sec - starttime_sec)/60

    # for each stop we average headway over dates
    # We take the best (smallest) headway out of the two possible of the stop
    # this is because many stops have frequent service in one direction
    # and infrequent in the other (ie. inbound vs outbound differences)
    stop_time_trips_departure['headway'] = round(t1_min / stop_time_trips_departure['departure'])

    stops_headway = stop_time_trips_departure.reset_index().groupby([
    'stop_id', 'direction_id']).mean().groupby('stop_id').min()[['headway']]

    #print('     Time to complete average stop headway analysis with {} frequent stops is: {}'.format(len(stops_headway), time.time() - startTime))

    return stops_headway


if __name__ == '__main__':
    # get the work directory
    dirname = os.path.abspath('')

    # geopackage path where to save processing layers
    gpkgPath_output = os.path.join(dirname, 'data/Transport', 'frequent_transit_headway_2020April_python.gpkg')


    for city in GTFS.keys():
        #print(city)
        city_config = GTFS['{}'.format(city)]
        gtfsfeed_path = city_config['gtfs_filename']
        start_date = city_config['start_date_mmdd']
        end_date = city_config['end_date_mmdd']
        authority = city_config['gtfs_provider']
        hour = 'day_time'

        # load GTFS Feed
        loaded_feeds = ua_load.gtfsfeed_to_df(gtfsfeed_path=gtfsfeed_path)

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

            stops_headway = get_hlc_stop_frequency(loaded_feeds, start_hour, end_hour, start_date,
                               end_date, route_types, agency_ids,
                               dow=['monday','tuesday','wednesday','thursday','friday'])

            # select average departure headway less than or equal to maxi headway frequency intervals
            #stop_frequent_headway = stops_headway[stops_headway['headway'] <= headway_intervals]

            if len(stops_headway) > 0:
                stop_frequent_final = pd.merge(stops_headway, loaded_feeds.stops, how='left', on='stop_id')
                stop_frequent_final['authority'] = authority
                stop_frequent_final['mode'] = mode
                stop_frequent = stop_frequent.append(stop_frequent_final)
                print('     Complete {} ({}) {} analysis during {} with {} stop counts in {:,.2f} seconds'.format(
                    city, authority, mode, hour, len(stops_headway), time.time() - startTime))
            else:
                print('     {} {} feature is found in {} ({}) during {}'.format(
                    len(stops_headway), mode, city, authority, hour))
                continue

        # get spatial features for freqent stops
        # add stop id geometry
        stop_frequent['geometry'] = stop_frequent.apply(
            lambda row: Point(row['stop_lon'], row['stop_lat']), axis=1)
        stop_frequent_gdf = gpd.GeoDataFrame(stop_frequent)


        # save to output file
        # save the frequent stop by study region and modes to a new layer in geopackage
        stop_frequent_gdf.to_file(
            gpkgPath_output,
            layer='{}_{}min_stops_{}_{}_{}'.format(
                city, headway_intervals, hour, start_date, end_date),
            driver='GPKG')
