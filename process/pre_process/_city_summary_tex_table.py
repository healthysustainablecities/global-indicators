# OSM Audit  - Lancet series
import os
import sys
import time
import pandas
from sqlalchemy import create_engine,inspect

# Import custom variables for National Liveability indicator process
from _project_setup import *

from datetime import datetime

formatters=['%s','%9.0fc','%9.1fc','%9.1fc','%9.0fc','%9.0fc','%9.0fc']
column_formats = 'p{2cm}|p{2.2cm}|p{2cm}|p{1.5cm}|p{1.2cm}|p{1.3cm}|p{1.2cm}|p{1.2cm}|p{1.2cm}'
def tex_str(x):
    return(str(x))

def tex_int(x):
    return(f'{x:,.0f}')

def tex_float(x):
    return(f'{x:,.1f}')

def main():
    print("\nPreparing LaTeX summary table files for all cities defined in the project configuration file"\
          ", drawing onf results from the following databases:\n")
    key_stats = ['City','Country', 'Continent', 'Population estimate', 'Urban area (sqkm)','Pop. per sqkm']
    core_destinations = ['Fresh Food / Market','Convenience','Public transport stop (any)']
    formatters = [tex_int,tex_float,tex_float,tex_int,tex_int,tex_int]
    multi_index = pandas.MultiIndex.from_tuples([(x,'') for x in key_stats] + \
                        [('Destination Count',x) for x in core_destinations])
            
    # derived study region name (no need to change!)
    print(study_region)
    engine = create_engine(f"postgresql://{db_user}:{db_pwd}@{db_host}/{db}")
    db_contents = inspect(engine)
    try:
        df = pandas.read_sql_table('urban_dest_summary',engine)
        df.columns = [
            'City', 
            'dest_name_full', 
            'count', 
            'Population estimate', 
            'Urban area (sqkm)',
            'Pop. per sqkm', 
            'dest_per_sqkm', 'dest_per_sqkm_per_10kpop',
            ]
        df['Country'] = country
        df['Continent'] = continent
        df = df[[
            'City',
            'Country',
            'Continent',
            'Population estimate', 
            'Urban area (sqkm)',
            'Pop. per sqkm',
            'dest_name_full', 
            'count']]
        results = df.set_index('dest_name_full')\
            .loc[core_destinations]\
            .reset_index()\
            .pivot(
                index=key_stats,
                columns='dest_name_full',
                values='count')\
            .reset_index()\
            .copy()
        results.columns = multi_index
    except:
        raise
    finally:
        engine.dispose()
    
    results = results\
        .set_index(['Continent','Country','City'])\
        .sort_index()
    table_tex = results\
        .to_latex(
            multicolumn=True,
            sparsify=True,
            formatters=formatters,
            column_format=column_formats,
            multicolumn_format='c',
            caption = 'Destination counts by cities.',
            label = 'cities_table')\
        .replace(
            f"{core_destinations[0]}",
            f"{' '*20}&{' '*19}&{' '*15}& {core_destinations[0]}")\
        .replace(
            'Convenience',
            'Con-venience'
            )\
        .replace(
            'Public transport stop (any)',
            'Public transport (any)'
            )\
        .replace(
            '|p{',
            '|>{\\raggedleft\\arraybackslash}p{'
            )\
        .replace(
            '\\begin{table}','\\begin{table}\n\\small'
            )
    
    out_file = '../collaborator_report/_static/cities_data.tex'
    with open(out_file, 'w') as out_table:
        out_table.write(table_tex)
        print(f"\nSaved main city comparison table to {out_file}.\n")

if __name__ == '__main__':
    main()