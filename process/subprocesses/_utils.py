"""
Utility functions.

Purpose: These functions may be used in other scripts to undertake specific tasks.
"""
import shutil
import textwrap


# 'pretty' text wrapping as per https://stackoverflow.com/questions/37572837/how-can-i-make-python-3s-print-fit-the-size-of-the-command-prompt
def get_terminal_columns():
    return shutil.get_terminal_size().columns


def print_autobreak(*args, sep=' '):
    width = (
        get_terminal_columns()
    )  # Check size once to avoid rechecks per "paragraph"
    # Convert all args to strings, join with separator, then split on any newlines,
    # preserving line endings, so each "paragraph" wrapped separately
    for line in sep.join(map(str, args)).splitlines(True):
        # Py3's print function makes it easy to print textwrap.wrap's result as one-liner
        print(*textwrap.wrap(line, width), sep='\n')


def wrap_autobreak(*args, sep=' '):
    width = (
        get_terminal_columns()
    )  # Check size once to avoid rechecks per "paragraph"
    # Convert all args to strings, join with separator, then split on any newlines,
    # preserving line endings, so each "paragraph" wrapped separately
    for line in sep.join(map(str, args)).splitlines(True):
        # Py3's print function makes it easy to print textwrap.wrap's result as one-liner
        return '\n'.join(textwrap.wrap(line, width))


def reproject_raster(inpath, outpath, new_crs):
    import rasterio
    from rasterio.warp import (
        Resampling,
        calculate_default_transform,
        reproject,
    )

    dst_crs = new_crs  # CRS for web meractor
    with rasterio.open(inpath) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds,
        )
        kwargs = src.meta.copy()
        kwargs.update(
            {
                'crs': dst_crs,
                'transform': transform,
                'width': width,
                'height': height,
            },
        )
        with rasterio.open(outpath, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                )
