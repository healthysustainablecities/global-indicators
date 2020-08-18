"""

List locales
~~~~~~~~~~~~~~~~~

::

    Script:  
    Purpose: List all study region locales names
    Authors: Carl Higgs 

"""

import os
import sys
import time
import pandas

def main():
    xls = pandas.ExcelFile('./_project_configuration.xlsx')
    df_local = pandas.read_excel(xls, 'region_settings',index_col=0)
    locales = ' '.join(list(df_local.columns.values)[2:])
    print(locales)

if __name__ == '__main__':
    main()