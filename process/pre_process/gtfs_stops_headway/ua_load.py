################################################################################
# Script: ua_load.py

# Description: This script contain functions to load study region gtfs data
# into a UrbanAccess transit data object
# the load functions have been revised based on origional function from UrbanAccess,
# take out the add agency and route type features
# https://github.com/UDST/urbanaccess/blob/9c0f64faf63bae6f5a73ae23409ca68b28113026/urbanaccess/gtfs/load.py
################################################################################

import os
import codecs
import re
import time
import pandas as pd
import six

from urbanaccess import config
from urbanaccess.utils import log
from urbanaccess.gtfs.gtfsfeeds_dataframe import gtfsfeeds_dfs
from urbanaccess.gtfs import utils_validation
from urbanaccess.gtfs import utils_format


def _standardize_txt(csv_rootpath=os.path.join(config.settings.data_folder,
                                               'gtfsfeed_text')):
    """
    Standardize all text files inside a GTFS feed for machine readability

    Parameters
    ----------
    csv_rootpath : str, optional
        root path where all gtfs feeds that make up a contiguous metropolitan
        area are stored

    Returns
    -------
    None
    """

    gtfsfiles_to_use = ['stops.txt', 'routes.txt', 'trips.txt',
                        'stop_times.txt', 'calendar.txt',
                        'agency.txt', 'calendar_dates.txt']

    if six.PY2:
        _txt_encoder_check(gtfsfiles_to_use, csv_rootpath)
    _txt_header_whitespace_check(gtfsfiles_to_use, csv_rootpath)


def _txt_encoder_check(gtfsfiles_to_use,
                       csv_rootpath=os.path.join(
                           config.settings.data_folder,
                           'gtfsfeed_text')):
    """
    Standardize all text files inside a GTFS feed for encoding problems.
    Has not been updated for Python 3.

    Parameters
    ----------
    gtfsfiles_to_use : list
        list of gtfs feed txt files to utilize
    csv_rootpath : str, optional
        root path where all gtfs feeds that make up a contiguous metropolitan
        area are stored

    Returns
    -------
    None
    """
    # UnicodeDecodeError
    start_time = time.time()

    folderlist = [foldername for foldername in os.listdir(csv_rootpath) if
                  os.path.isdir(os.path.join(csv_rootpath, foldername))]

    if not folderlist:
        folderlist = [csv_rootpath]

    for folder in folderlist:
        textfilelist = [textfilename for textfilename in
                        os.listdir(os.path.join(csv_rootpath, folder)) if
                        textfilename.endswith(".txt")]

        for textfile in textfilelist:
            if textfile in gtfsfiles_to_use:
                # Read from file
                file_open = open(os.path.join(csv_rootpath, folder, textfile))
                raw = file_open.read()
                file_open.close()
                if raw.startswith(codecs.BOM_UTF8):
                    raw = raw.replace(codecs.BOM_UTF8, '', 1)
                    # Write to file
                    file_open = open(
                        os.path.join(csv_rootpath, folder, textfile), 'w')
                    file_open.write(raw)
                    file_open.close()

    log('GTFS text file encoding check completed. Took {:,.2f} seconds'.format(
        time.time() - start_time))


def _txt_header_whitespace_check(gtfsfiles_to_use,
                                 csv_rootpath=os.path.join(
                                     config.settings.data_folder,
                                     'gtfsfeed_text')):
    """
    Standardize all text files inside a GTFS feed to remove whitespace
    in headers

    Parameters
    ----------
    gtfsfiles_to_use : list
        list of gtfs feed txt files to utilize
    csv_rootpath : str, optional
        root path where all gtfs feeds that make up a contiguous metropolitan
        area are stored

    Returns
    -------
    None
    """
    start_time = time.time()

    folderlist = [foldername for foldername in os.listdir(csv_rootpath) if
                  os.path.isdir(os.path.join(csv_rootpath, foldername))]

    if not folderlist:
        folderlist = [csv_rootpath]

    for folder in folderlist:
        textfilelist = [textfilename for textfilename in
                        os.listdir(os.path.join(csv_rootpath, folder)) if
                        textfilename.endswith(".txt")]

        for textfile in textfilelist:
            if textfile in gtfsfiles_to_use:
                # Read from file
                with open(os.path.join(csv_rootpath, folder, textfile)) as f:
                    lines = f.readlines()
                lines[0] = re.sub(r'\s+', '', lines[0]) + '\n'
                # Write to file
                try:
                    with open(os.path.join(csv_rootpath, folder, textfile),
                              'w') as f:
                        f.writelines(lines)
                except Exception:
                    log('Unable to read {}. Check that file is not currently'
                        'being read or is not already in memory as this is '
                        'likely the cause of the error.'
                        ''.format(os.path.join(csv_rootpath,
                                               folder, textfile)))
    log('--------------------------------')
    log(
        'GTFS text file header whitespace check completed. Took {:,'
        '.2f} seconds'.format(
            time.time() - start_time))


def gtfsfeed_to_df(gtfsfeed_path=None, validation=False, verbose=True,
                   bbox=None, remove_stops_outsidebbox=None):
    """
    Read all GTFS feed components as a dataframe in a gtfsfeeds_dfs object and
    merge all individual GTFS feeds into a regional metropolitan data table.
    Optionally, data can also be validated before its use.

    Parameters
    ----------
    gtfsfeed_path : str, optional
        root path where all gtfs feeds that make up a contiguous metropolitan
        area are stored
    validation : bool
        if true, the validation check on stops checking for stops outside
        of a bounding box and stop coordinate
        hemisphere will be run. this is required to remove stops outside of
        a bbox
    verbose : bool
        if true and stops are found outside of the bbox, the stops that are
        outside will be printed for your reference
    bbox : tuple
        Bounding box formatted as a 4 element tuple:
        (lng_max, lat_min, lng_min, lat_max)
        example: (-122.304611,37.798933,-122.263412,37.822802)
        a bbox can be extracted for an area using: the CSV format bbox
        from http://boundingbox.klokantech.com/
    remove_stops_outsidebbox : bool
        if true stops that are outside the bbox will be removed
    append_definitions : bool
        if true, columns that use the GTFS data schema for their attribute
        codes will have the corresponding GTFS definition information of
        that code appended to the resulting dataframes for reference

    Returns
    -------
    gtfsfeeds_dfs : object
        processed dataframes of corresponding GTFS feed text files
    gtfsfeeds_dfs.stops : pandas.DataFrame
    gtfsfeeds_dfs.routes : pandas.DataFrame
    gtfsfeeds_dfs.trips : pandas.DataFrame
    gtfsfeeds_dfs.stop_times : pandas.DataFrame
    gtfsfeeds_dfs.calendar : pandas.DataFrame
    gtfsfeeds_dfs.calendar_dates : pandas.DataFrame
    """


    start_time = time.time()

    if gtfsfeed_path is None:
        gtfsfeed_path = os.path.join(config.settings.data_folder,
                                     'gtfsfeed_text')
        if not os.path.exists(gtfsfeed_path):
            raise ValueError('{} does not exist'.format(gtfsfeed_path))
    else:
        if not os.path.exists(gtfsfeed_path):
            raise ValueError('{} does not exist'.format(gtfsfeed_path))
    if not isinstance(gtfsfeed_path, str):
        raise ValueError('gtfsfeed_path must be a string')

    if validation:
        if bbox is None or remove_stops_outsidebbox is None or verbose is \
                None:
            raise ValueError(
                'Attempted to run validation but bbox, verbose, and or '
                'remove_stops_outsidebbox were set to None. These parameters '
                'must be specified for validation.')

    _standardize_txt(csv_rootpath=gtfsfeed_path)

    folderlist = [foldername for foldername in os.listdir(gtfsfeed_path) if
                  os.path.isdir(os.path.join(gtfsfeed_path, foldername))]
    if not folderlist:
        folderlist = [gtfsfeed_path]

    for index, folder in enumerate(folderlist):

        # print break to visually separate each gtfs feed log
        log('--------------------------------')
        log('Processing GTFS feed: {!s}'.format(os.path.split(folder)[1]))

        textfilelist = [textfilename for textfilename in
                        os.listdir(os.path.join(gtfsfeed_path, folder)) if
                        textfilename.endswith(".txt")]
        required_gtfsfiles = ['stops.txt', 'routes.txt', 'trips.txt',
                              'stop_times.txt', 'calendar.txt']
        optional_gtfsfiles = ['agency.txt', 'calendar_dates.txt']
        for required_file in required_gtfsfiles:
            if required_file not in textfilelist:
                raise ValueError(
                    '{} is a required GTFS text file and was not found in '
                    'folder {}'.format(
                        required_file,
                        os.path.join(gtfsfeed_path, folder)))

        for textfile in required_gtfsfiles:
            if textfile == 'stops.txt':
                stops_df = utils_format._read_gtfs_stops(
                    textfile_path=os.path.join(gtfsfeed_path, folder),
                    textfile=textfile)
            if textfile == 'routes.txt':
                routes_df = utils_format._read_gtfs_routes(
                    textfile_path=os.path.join(gtfsfeed_path, folder),
                    textfile=textfile)
            if textfile == 'trips.txt':
                trips_df = utils_format._read_gtfs_trips(
                    textfile_path=os.path.join(gtfsfeed_path, folder),
                    textfile=textfile)
            if textfile == 'stop_times.txt':
                stop_times_df = utils_format._read_gtfs_stop_times(
                    textfile_path=os.path.join(gtfsfeed_path, folder),
                    textfile=textfile)
            if textfile == 'calendar.txt':
                calendar_df = utils_format._read_gtfs_calendar(
                    textfile_path=os.path.join(gtfsfeed_path, folder),
                    textfile=textfile)

        for textfile in optional_gtfsfiles:
            if textfile == 'agency.txt':
                if textfile in textfilelist:
                    agency_df = utils_format._read_gtfs_agency(
                        textfile_path=os.path.join(gtfsfeed_path, folder),
                        textfile=textfile)
                else:
                    agency_df = pd.DataFrame()
            if textfile == 'calendar_dates.txt':
                if textfile in textfilelist:
                    calendar_dates_df = utils_format._read_gtfs_calendar_dates(
                        textfile_path=os.path.join(gtfsfeed_path, folder),
                        textfile=textfile)
                else:
                    calendar_dates_df = pd.DataFrame()


        if validation:
            stops_df = (utils_validation
                        ._validate_gtfs(
                            stops_df=stops_df,
                            feed_folder=os.path.join(gtfsfeed_path, folder),
                            verbose=verbose,
                            bbox=bbox,
                            remove_stops_outsidebbox=remove_stops_outsidebbox))
            if remove_stops_outsidebbox:
                stops_inside_bbox = list(stops_df['stop_id'])
                stop_times_df = stop_times_df[stop_times_df['stop_id'].isin(
                    stops_inside_bbox)]

    stop_times_df = utils_format._timetoseconds(
        df=stop_times_df, time_cols=['departure_time'])

    # set gtfsfeeds_dfs object to merged GTFS dfs
    gtfsfeeds_dfs.stops = stops_df
    gtfsfeeds_dfs.routes = routes_df
    gtfsfeeds_dfs.trips = trips_df
    gtfsfeeds_dfs.stop_times = stop_times_df
    gtfsfeeds_dfs.calendar = calendar_df
    gtfsfeeds_dfs.calendar_dates = calendar_dates_df

    # TODO: add to print the list of gtfs feed txt files read in for each feed
    log('{:,} GTFS feed file(s) successfully read as dataframes:'.format(
        len(folderlist)))
    for folder in folderlist:
        log('     {}'.format(os.path.split(folder)[1]))
    log('     Took {:,.2f} seconds'.format(time.time() - start_time))

    return gtfsfeeds_dfs
