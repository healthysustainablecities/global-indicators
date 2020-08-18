# OSM Audit  - Lancet series

import time
import psycopg2
import pandas
from sqlalchemy import create_engine
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Import custom variables for National Liveability indicator process
from _project_setup import *
from datetime import datetime
today = datetime.today().strftime('%Y-%m-%d')

def find(name, path):
    for root, dirs, files in os.walk(path):
        print(files)
        if name in files:
            return os.path.join(root, name)

cities = ['maiduguri','mexico_city','baltimore','phoenix','seattle','sao_paulo','hong_kong','chennai','bangkok','hanoi','graz','ghent','bern','olomouc','cologne','odense','barcelona','valencia','vic','belfast','lisbon','adelaide','melbourne','sydney','auckland']
# connect to the PostgreSQL server
for locale in cities:
    # prepare and clean configuration entries
    for var in [x for x in  df_global.index.values]:
        globals()[var] = df_global.loc[var]['parameters']
    
    df_local[locale] = df_local[locale].fillna('')
    for var in [x for x in  df_local.index.values]:
        globals()[var] = df_local.loc[var][locale]
    
    # derived study region name (no need to change!)
    study_region = '{}_{}_{}'.format(locale,region,year).lower()
    print(study_region)
    path = f'./../data/study_region/{study_region}/'
    try:
        file =  [f for f in [files for root,dirs,files in os.walk(path)][0]  if f'{f}'.endswith('csv')][0]
        df = pandas.read_csv(os.path.join(path,file))
        t1 = df.iloc[0:3,[1,4,5,6]]
        t2 = df.iloc[0:3,1:].transpose().iloc[[2,6,7],:]
        t1['key']=1
        t2['key']=1
        df = (t1.merge(t2.reset_index(),how='outer').drop_duplicates()).drop(columns='key')
        df.iloc[1:3,0:4] = ''
        df.columns = ['Study region','Population estimate','Urban area','Pop. per sqkm', 'Measure','Fresh food','Convenience','Public transport']
        df['Measure']= df['Measure'].str.replace('dest_','').str.replace('_',' ').str.replace('10kpop','10,000 Pop.').str.replace('per ','/').str.title().str.replace('Sqkm','km²')
        if cities.index(locale)==0:
            results = df
        else:
            results  = results.append(df)
    except:
        print(f"{study_region} does not have an OSM summary CSV file produced...")
        continue

# print(results.to_html(index=False))
results.to_csv(f'osm_audit_{today}.csv')
#https://stackoverflow.com/questions/32137396/how-do-i-plot-only-a-table-in-matplotlib
fig, ax =plt.subplots(figsize=(12,4))
ax.axis('tight')
ax.axis('off')
the_table = ax.table(cellText=results.values,colLabels=results.columns,loc='center')

#https://stackoverflow.com/questions/4042192/reduce-left-and-right-margins-in-matplotlib-plot
pp = PdfPages("foo.pdf")
pp.savefig(fig, bbox_inches='tight')
pp.close()