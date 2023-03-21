"""
Aggregation.

This script aggreates sample point indicators to a gridal grid of small area
'neighbourhood summaries, and overall summaries for cities. To run it, supply a
study region code name.  The list of configured codenames is displayed if run
with no region name as an argument. It is  to be run after
01_study_region_setup.py and 02_neighbourhood_analysis.py.

The following outputs are generated for the city, which can support within- and between-city comparisons
and mapping and will be located in the city's study region folder.
1. {city}_{country code}_{year}_grid_{resolution}m_yyyymmdd.csv
2. {city}_{country code}_{year}_city_yyyymmdd.csv
1. {city}_{country code}_{year}_grid_{resolution}m_yyyymmdd
2. {city}_{country code}_{year}_city__yyyymmdd
"""

# Set up project and region parameters for GHSCIC analyses
from _project_setup import *
from setup_aggr import (
    calc_cities_pop_pct_indicators,
    calc_grid_pct_sp_indicators,
)


def main():
    startTime = time.time()

    print('Calculating small area neighbourhood grid indicators... '),
    # calculate within-city indicators weighted by sample points for each city
    # calc_grid_pct_sp_indicators take sample point stats within each city as
    # input and aggregate up to grid cell indicators by calculating the mean of
    # sample points stats within each hex
    calc_grid_pct_sp_indicators(region_config, indicators)
    print('Done.')

    print('Calculating city summary indicators... '),
    # Calculate city-level indicators weighted by population
    # calc_cities_pop_pct_indicators function take grid cell indicators and
    # pop estimates of each city as input then aggregate grid cell to city-level
    # indicator by summing all the population weighted grid cell indicators

    # in addition to the population weighted averages, unweighted averages are
    # also included to reflect the spatial distribution of key walkability
    # measures (regardless of population distribution)
    calc_cities_pop_pct_indicators(region_config, indicators)
    print('Done.')
    print(
        f'\nAggregation completed: {(time.time() - startTime)/60.0:.02f} mins',
    )


if __name__ == '__main__':
    main()
