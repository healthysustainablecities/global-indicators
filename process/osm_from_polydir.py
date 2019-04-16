# Author:  Carl Higgs
# Date:    20180911
# Project: miscellaneous raster processing
# Purpose: A wrapper function for osmosis which extracts OSM portions based on any .poly files located
#          in paths stemming from a supplied directory.  
#
#          Note that OSM output format will match input format; ie. if supplied a .osm file it will output
#          the series of .osm files corresponding to encountered intersecting .poly regions; likewise for 
#          .pbf files (which are probably preferable as they are notably more manageable file size wise!)
#
#          Read about OSM convert here: 
#          https://wiki.openstreetmap.org/wiki/Osmosis/Examples#Breaking_out_just_one_polygon

import os
import sys

import argparse
import subprocess as sp
from datetime import datetime

print("For help. run the script as: python osmosis_from_polydir.py --help")
search_dir = os.path.dirname(sys.argv[0])

# Start timing the code
start_time = datetime.now()

def valid_path(arg):
    if not os.path.exists(arg):
        msg = "The path %s does not exist!" % arg
        raise argparse.ArgumentTypeError(msg)
    else:
        return arg
  
# Parse input arguments
parser = argparse.ArgumentParser(description='Generate origin destination matrix')
parser.add_argument('--dir',
                    help='parent directory (by default, the directory in which the script is run)',
                    default=search_dir,
                    type=valid_path)
parser.add_argument('--osmconvert',
                    help='location of the osmconvert executable',
                    default='D:\osm\osmconvert64-0.8.8p.exe',
                    type=str)
parser.add_argument('--source',
                    help='Source OpenStreetMap file (.osm or .pbf)',
                    default='',
                    required=True,
                    type=str)
parser.add_argument('--suffix',
                    help='A suffix to append to the outfile name (which is based on the encountered .poly file name)')
parser.add_argument('--out_format',
                   help='Specify the required output format (by default, the format of the source OSM file will be used (e.g. osm or pbf)',
                   default='',
                   type=str)
args = parser.parse_args()

exe = os.path.basename(args.osmconvert)
exepath = os.path.dirname(args.osmconvert)
osm_format = os.path.splitext(args.source)[1]
if args.out_format!= '':
  osm_format = args.out_format
suffix = args.suffix
if suffix != '':
  suffix = '_{}'.format(suffix)


# iterate of files within root or otherwise specified directory, noting all poly files
count = 0
for root, dirs, files in os.walk(args.dir):
    for file in files:
        if file.endswith(".poly"):
           fullfile = os.path.join(root,file)
           filename = os.path.splitext(file)[0]
           command = '{osmconvert} {osm} -B={poly} -o={root}/{filename}{suffix}.{osm_format}'.format(osmconvert = exe, 
                                                         osm = args.source,
                                                         poly = fullfile,
                                                         root = root,
                                                         filename = filename,
                                                         suffix = suffix,
                                                         osm_format = osm_format)
                                                         
           print('\nRunning {time}: {command}...'.format(time = datetime.now().isoformat(),command = command)),
           sp.call(command, shell=True, cwd=exepath)
           print(' Done.')
           count += 1
            
print('\nExtracted (or attempted to extract) {} OSM portions.'.format(count))            
print("Elapsed time was {:.1f} minutes".format((datetime.now() - start_time).total_seconds()/60.0))