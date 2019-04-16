# Script:  calculate_employment_diversity.py
# Purpose: Calculate an employment diversity measure akin to land use mix, but using ANZIC codes, for DZNs
# Author:  Carl Higgs (for Rebecca Roberts and Hannah Badland, who conceived the measure)
# Date:    20190329

import os
import sys
import time
import pandas as pd
import numpy as np
from scipy.stats import entropy

# The SciPy library includes an entropy function which gets us part way there:
# "If only probabilities pk are given, the entropy is calculated as S = -sum(pk * log(pk), axis=0)
# ... This routine will normalize pk and qk if they don't sum to 1."
# In other words, this completes the top part of the LUM function described by Hannah:
# LUM=-(sum_(i=1)^n p_i*ln(p_i)) / ln(n)
# So we just have to do the second standardisation part --- divide by ln(n)

for year in [2011,2016]:
  # import data, with DZN as index
  df = pd.read_csv(os.path.join(sys.path[0],
                                '../data/employment/DZN_IndustryEmployment_{year}/AUST_DZN_EmploymentIndustry_{year}.csv'.format(year = year)),
                   index_col=0)
  
  # list fields present in data which are not industries
  not_industries = ['Inadequately described','Not stated','Not applicable','Total']
  
  # list industry fields
  industries = [i for i in df.columns.tolist() if i not in not_industries]
  
  # Calculate basic entropy
  df['entropy_basic'] = df[industries].apply(entropy,axis=1)
  
  # Calculate employment diversity
  df['employment_diversity'] = df['entropy_basic']/np.log(len(industries))
   
  # Write result to csv file 
  df.to_csv (os.path.join(sys.path[0],
                          '../data/employment/DZN_IndustryEmployment_{year}/employment_diversity_{year}.csv'.format(year = year)), 
            index = True, 
            header=True) 