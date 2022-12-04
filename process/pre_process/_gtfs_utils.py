# Utility functions to support GTFS headway analysis for cities

import time
import pandas as pd
import os
import numpy as np
from datetime import datetime, timedelta

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


def get_calendar_range(loaded_feeds):
    """
    Check calendar and calendar dates dataframes to determine
    earliest and latest dates of services in loaded GTFS feed

    Parameters
    ----------
    loaded_feeds: gtfsfeeds_dataframe with GTFS objects

    Returns
    -------
    calendar_range: 2-tuple containing start and end date strings in yyyymmdd format
    """
    if  sum([x in dir(loaded_feeds) for x in ['calendar','calendar_dates']]) < 2:
        sys.exit("Invalid gtfsfeeds_dataframe supplied to get_calendar_range function")
    else:
        start_dates = []
        end_dates = []
        if len(loaded_feeds.calendar)!=0:
            start_dates.append(loaded_feeds.calendar.start_date.min())
            end_dates.append(loaded_feeds.calendar.end_date.max())
        if len(loaded_feeds.calendar_dates)!=0:
            start_dates.append(loaded_feeds.calendar.start_date.min())
            end_dates.append(loaded_feeds.calendar.end_date.max())
        return((min(start_dates),max(end_dates)))


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
    if len(loaded_feeds.calendar)!=0:
        calendar_range = get_calendar_range(loaded_feeds)
        
        # tabulate each date and weekday from the start to the end date in calendar
        dates = get_date_weekday_df(start=str(calendar_range[0]),end=str(calendar_range[1]))
        
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
        date_service_df = date_service_df.query('(date>=start_date) & (date<=end_date)')[['service_id','date', 'weekday']]
    else:
        date_service_df = pd.DataFrame({'service_id':[],'date':[],'weekday':[]})
    
    if len(loaded_feeds.calendar_dates) > 0:
        # add calendar_dates additions (1)
        # note that additional dates need not be within range of calendar.txt
        addition_dates = loaded_feeds.calendar_dates.query('exception_type==1')[['service_id', 'date']]
        addition_dates['date'] = pd.to_datetime(addition_dates['date'], format='%Y%m%d')
        addition_dates['weekday'] = addition_dates.date.dt.day_name().str.lower()
        date_service_df = pd.concat([addition_dates, date_service_df], ignore_index=True)
        
        # remove calendar_dates exceptions (2)
        exception_dates = loaded_feeds.calendar_dates.query('exception_type==2')[['service_id', 'date']]
        exception_dates['date'] = pd.to_datetime(exception_dates['date'], format='%Y%m%d')
        
        date_service_df = pd.merge(date_service_df,exception_dates,indicator=True,
                                how='outer').query('_merge=="left_only"').drop('_merge',axis=1)
    
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
        search_start_date = datetime.strptime(start_date, "%Y%m%d")
        search_end_date = datetime.strptime(end_date, "%Y%m%d")
        feed_min_date = search_start_date
        feed_max_date = search_end_date
    elif (isinstance(start_date, datetime) & isinstance(end_date, datetime)):
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
    
    assert (feed_max_date - feed_min_date >= timedelta(days=7)), \
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
    


def hours(time_str):
    """
    Get hours from time.
    time_str: str (hh:mm:ss)
    """
    h, m, s = [int(x) for x in time_str.split(':')]
    return(h + m/60.0 + s/3600.0)


def not_neg(x):
    if x < 0:
        return(0)
    else:
        return(x)


def weight_hours(start_time,end_time,start_hour,end_hour):
    """
    Get hour weights for frequencies with start_time and end_time given an analysis window (start_hour, end_hour)
    """
    #if (start_time>=start_hour) and (end_time<end_hour):
    #    weight = end_time-start_time
    #elif (start_time>=start_hour) and (end_time>=end_hour):
    #    weight = (end_time-start_time)-(end_time-end_hour)
    #elif (start_time<start_hour) and (end_time<end_hour):
    start_time = hours(start_time)
    end_time = hours(end_time)
    start_hour = hours(start_hour)
    end_hour = hours(end_hour)
    
    return(round(not_neg(not_neg(end_time-start_time) - not_neg(start_hour-start_time) - not_neg(end_time-end_hour)),1))


# revise based on tidytransit [get_stop_frequency function]
# https://github.com/r-transit/tidytransit/blob/master/R/frequencies.R

def get_hlc_stop_frequency(loaded_feeds, start_hour, end_hour, start_date,
                           end_date, route_types, agency_ids=None,
                           dow=['monday','tuesday','wednesday','thursday','friday'],
                           frequencies=''):
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
    frequencies: dataframe
        optional, default to an empty string which means that frequencies.txt is not accounted for

    Returns
    -------
    date_service_df : pandas.DataFrame
    """
    
    startTime = time.time()
    # set service date
    date_service_df = set_date_service_table(loaded_feeds)
    
    # using query to avoid boolean series key warning message
    date_service_df = date_service_df.query(f'''
        (weekday in {dow}) and ('{start_date}' <= date) and (date < '{end_date}')
        ''').drop_duplicates()
    
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
    
    if len(frequencies)!=0:
        # if true, the assumption is that a valid frequencies.txt dataframe has been defined and passed as an argument
        frequencies = frequencies[frequencies.index.astype(str).isin(trips_routes.trip_id.unique().astype(str))]
        if len(frequencies)!=0:
            # Weight for hours within analysis window, rounded to one decimal place.
            # Often, the frequencies are defined in 59 minute increments e.g. 07:00:00 to 07:59:00 (weight of 1).
            # However, by defining a rounded weight we allow for possibility that some feeds could possibly
            # have larger frequency windows - e.g. 07:00:00 to 08:59:00 (weight of 2).
            # hours of frequencies outside of the analysis window are weighted zero.
            # This is important to note, as some services may have a window 07:00: to 23:00:00
            # That shouldn't be excluded (because it ends too late); rather it is limited to a weight of 12, rather than a weight of 16
            frequencies['weight'] = frequencies.apply(lambda x: weight_hours(x.start_time,x.end_time,start_hour,end_hour),axis=1)
            frequencies = frequencies[frequencies.weight>0]
    
    stop_times = loaded_feeds.stop_times[loaded_feeds.stop_times.trip_id.isin(trips_routes.trip_id.unique())]
    
    # filter stop times within the timerange
    selected_stop_times_df = stop_times.query(f"('{start_hour}' <= departure_time) and (departure_time < '{end_hour}')")
    selected_stop_times_df = selected_stop_times_df[['trip_id', 'stop_id']].set_index('trip_id')
    
    if (len(selected_stop_times_df)==0) and (len(frequencies) == 0):
        # no journeys were found for this mode, so return empty dataframe
        # print('     Zero trip is found within the specified start and end hours')
        null_headway =  pd.DataFrame({'stop_id':[],'headway' : []})
        null_headway = null_headway.set_index('stop_id')
        return(null_headway)
    
    # count sec. and min. within the tierange
    t1_min = ((datetime.strptime(end_hour, '%H:%M:%S') - datetime.strptime(start_hour, '%H:%M:%S'))/60).seconds
    
    # Ensure that direction_id exists and does not have nulls, so we can use it for grouping
    if 'direction_id' not in trips_routes.columns:
        trips_routes['direction_id'] = 0
    
    trips_routes.direction_id.fillna(-1,inplace=True)
    
    # filter valid service trips
    valid_service_trips = pd.merge(date_service_df, trips_routes, on='service_id', how='left')
    valid_service_trips = valid_service_trips[['trip_id', 'date', 'direction_id']].set_index('trip_id')
    
    # filter stops within valid service and time range
    stop_time_trips = pd.merge(valid_service_trips, selected_stop_times_df, left_index=True, right_index=True, how='inner').reset_index()
    
    # get counts of departure of each stop of each direction per day
    stop_time_trips_departure = stop_time_trips.groupby(['direction_id', 'stop_id', 'date'
                                                    ], sort=False)['trip_id'].count().to_frame('departure')
    
    stop_time_trips_departure['headway'] = round(t1_min / stop_time_trips_departure['departure'])
    
    # average headway over dates
    stops_headway = stop_time_trips_departure.reset_index().groupby(['stop_id', 'direction_id']).mean().reset_index()
    
    # take lowest headway for each stop out of each direction
    # (some stops have many services in one direction, but few in the other, and so it is not fair to average these)
    stops_headway = stops_headway.groupby('stop_id').min()[['headway']]
    
    if len(frequencies)!=0:
        # if true, assumption is that any stops existing as result of pre-defined headways should
        # have results based on this data, not stops_headway
        # So, restrict frequencies to those with valid trips
        
        # Ensure valid_service_trips and frequencies indexes have some dtype (frequencies could be either int64 or object (str), for example
        frequencies.index = frequencies.index.astype(type(valid_service_trips.index[0]))
        
        freq_headway = pd.merge(valid_service_trips, frequencies, left_index=True, right_index=True, how='inner')
        # and retrieve all stops for these trips
        freq_headway = pd.merge(freq_headway, stop_times.set_index('trip_id')['stop_id'], left_index=True, right_index=True, how='left').reset_index()
        if len(frequencies)!=0:
            # and take a weighted average (which if all weights = 1, is equivalent to straight average).
            # The rational for taking an average across trips at stops and directions is that
            # trips represent journeys to distinct destinations, and one direction is not equivalent to another
            # so the average across these represents the average time between services heading in a direction you may want to go.
            # there may be more services in between which if accounted for (ie. leave for anywhere) may mean a shorter wait,
            # but rather than measure service frequency to 'get me out of here' kind of headway, we are measuring something closer to the
            # more real world service frequency of 'get me somewhere where i might want to go'.
            # Worth noting that service frequency isn't equivalent to theoretical average wait time (which is service frequency / 2).
            freq_headway = freq_headway.groupby(['stop_id','direction_id']).apply(lambda x: np.average(x['headway_secs'],
                                                                                                       weights=x['weight']))
            # taking best of each direction, and converting headway from seconds to minutes
            freq_headway = freq_headway.reset_index().groupby('stop_id').min()[0]/60
            freq_headway.name = 'headway'
            freq_headway = pd.DataFrame(freq_headway)
            # Combine freq_headway with any stops in stops_headway which aren't otherwise mentioned
            # Assumption is that these are distinct sets of stops, and if some have headway estimates in
            # freq_headway, this is the preferable estimate (e.g. as per advice such as of tidytransit)
            if len(stops_headway)!= 0:
                stops_headway = freq_headway.append(stops_headway.loc[list(set(stops_headway.index) - set(freq_headway.index))]).sort_index()
            else:
                stops_headway = freq_headway    
    return(stops_headway)

