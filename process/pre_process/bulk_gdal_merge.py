"""Bulk merge tif files using GDAL."""

import argparse
import datetime
import os
import subprocess as sp
import sys

cwd = os.path.dirname(sys.argv[0])
print(cwd)


def valid_path(arg):
    """Check if this is a valid path."""
    if not os.path.exists(arg):
        msg = "The path %s does not exist!" % arg
        raise argparse.ArgumentTypeError(msg)
    else:
        return arg


# Parse input arguments
parser = argparse.ArgumentParser(
    description="Generate origin destination matrix"
)
parser.add_argument(
    "-dir", help="parent directory", default=cwd, type=valid_path
)
parser.add_argument(
    "-outfile", help="outfile name", default="gdal_merged.tif", type=str
)
parser.add_argument(
    "-gdal_loc",
    help="location of the gdal_merge.py script",
    default="C:/OSGeo4W64/bin/gdal_merge.py",
    type=str,
)
args = parser.parse_args()

# initialise tif list file
tif_list_name = "tif_list_{date:%Y-%m-%d}.txt".format(
    date=datetime.datetime.now()
)
tif_list_path = os.path.join(args.dir, tif_list_name)
tif_list = open(tif_list_path, "w")

# iterate of files within root or otherwise specified directory, noting all tifs
count = 0
for root, dirs, files in os.walk(args.dir):
    for file in files:
        if file.endswith(".tif"):
            tif_list.write(f"{os.path.join(root, file)}\n")
            count += 1
tif_list.close()
print(f"Compiled a list of {count} tifs.")
# merge tifs
command = (
    f"python {args.gdal_loc} -v -o {args.outfile} --optfile {tif_list_name}"
)
sp.call(command, shell=True, cwd=cwd)
