################################################################################
# Script: gtfs_config.py

# Description: This script contain GTFS parameters defined for each study regions
# for importing to conduct stop frequency analysis
################################################################################

# set up study region GTFS config
GTFS = {'adelaide':{'gtfs_filename':'gtfs_input_data/gtfs_au_sa_adelaidemetro_20191004',
                    'gtfs_provider' : 'Adelaide Metro',
                    'gtfs_year' : '2019',
                    # define month and day for feeds start and end date
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                    # get bounding box from study region boundary shapefile
                    # bounding box formatted as a 4 element tuple: (lng_max, lat_min, lng_min, lat_max)
                    # you can generate a bounding box by going to http://boundingbox.klokantech.com/ and selecting the CSV format.
                    # this parameters is optional, for use if wanting remove features outside the bbox when loading feeds
                    'bbox' : (138.46098212857206, -35.15966609024628, 138.74830806651352, -34.71454282915053),
                    'crs': 'epsg:7845',
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
        'melbourne':{'gtfs_filename':'gtfs_input_data/gtfs_au_vic_ptv_20191004',
                    'gtfs_provider' : 'Public Transport Victoria',
                    'gtfs_year' : '2019',
                    # define month and day for "representative period" ie. not in school time
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                     'bbox' : (144.59067957842007, -38.21131973169178, 145.39847326519424, -37.61837232908795),
                     'crs': 'epsg:7845',
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
        'sydney' : {'gtfs_filename':'gtfs_input_data/gtfs_au_nsw_tfnsw_complete_20190619',
                    'gtfs_provider' : 'Transport for NSW',
                    'gtfs_year' : '2019',
                    # define month and day for "representative period" ie. not in school time
                    'start_date_mmdd' : '20191008',
                    'end_date_mmdd' : '20191205',
                    'bbox' : (150.6290606117829, -34.12321411958463, 151.3206735172292, -33.66275213092711),
                    'crs': 'epsg:7845',
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
                   },
       'phoenix' : {'gtfs_filename':'gtfs_input_data/gtfs_us_phoenix_valleymetro_20190403',
                   'gtfs_provider' : 'Valley metro',
                   'gtfs_year' : '2019',
                   # define month and day for "representative period" ie. not in school time
                   'start_date_mmdd' : '20190415',
                   'end_date_mmdd' : '20190621',
                   'bbox' : (-112.32944760645097, 33.28617148327744, -111.9200170423412, 33.71516047286253),
                   'crs': 'epsg:32612',
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
                               'agency_id': None}
                   }
                  },
       'mexico_city' : {'gtfs_filename':'gtfs_input_data/gtfs_mexico_mexico_city_fdg_20180101',
                   'gtfs_provider' : 'Federal District Government',
                   'gtfs_year' : '2019',
                   # define month and day for "representative period" ie. not in school time
                   'start_date_mmdd' : '20190415',
                   'end_date_mmdd' : '20190621',
                   'bbox' : (-99.33472129581168, 19.1632356281967, -98.93554618620378, 19.585767134392107),
                   'crs': 'epsg:32614',
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
                               'agency_id': None}
                   }
                  },
       'baltimore' : {'gtfs_filename':'gtfs_input_data/gtfs_us_baltimore_MarylandMTA_20180101',
                   'gtfs_provider' : 'Maryland MTA',
                   'gtfs_year' : '2019',
                   # define month and day for "representative period" ie. not in school time
                   'start_date_mmdd' : '20190415',
                   'end_date_mmdd' : '20190621',
                   'bbox' : (-76.71732081546881, 39.197419266639976, -76.5236521818912, 39.376708110613045),
                   'crs': 'epsg:32618',
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
                               'agency_id': None}
                   }
                  },
       'sao_paulo' : {'gtfs_filename':'gtfs_input_data/gtfs_brazil_sao_paulo_SPTrans_20080101',
                   'gtfs_provider' : 'SPTrans',
                   'gtfs_year' : '2019',
                   # define month and day for "representative period" ie. not in school time
                   'start_date_mmdd' : '20191008',
                   'end_date_mmdd' : '20191205',
                   'bbox' : (-46.830230353747325, -23.819961957892033, -46.36030177462541, -23.392833498544647),
                   'crs': 'epsg:32723',
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
       'auckland' : {'gtfs_filename':'gtfs_input_data/gtfs_newzealand_auckland_AucklandTransport_20190928',
                   'gtfs_provider' : 'Auckland Transport',
                   'gtfs_year' : '2019',
                   # define month and day for "representative period" ie. not in school time
                   'start_date_mmdd' : '20191008',
                   'end_date_mmdd' : '20191205',
                   'bbox' :  (174.57726564925753, -37.089137447205424, 174.98796590474333, -36.68399669533544),
                   'crs': 'epsg:2193',
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
                               }
                               }
