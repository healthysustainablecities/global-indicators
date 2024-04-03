"""Provides access to all the functions and variables for analysis and generating resources included within the GLobal Healthy and Sustainable City Indicators workflow.

It can be imported directly, rather than users having to import it from the subprocesses folder.

An example workflow can be conducted as follows:

import ghsci
r = ghsci.example()
r.analysis()
r.generate()

Users can get additional information through help functions:

ghsci.help()
r.help()
"""
from subprocesses.ghsci import *
