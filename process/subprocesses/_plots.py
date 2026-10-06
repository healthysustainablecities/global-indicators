import matplotlib.colors as mpl_colors
import matplotlib.pyplot as plt
import numpy as np
from _utils import fpdf2_mm_scale, wrap


## access profile radar chart
def access_profile(
    self,
    city_stats: dict = None,
    title: str = None,
    phrases: dict = None,
    cmap=None,
    width: int = 100,
    height: int = 80,
    dpi: int = 300,
    legend_xy: tuple = (0.85, 0.25),
    legend_anchor: str = 'upper left',
    legend_width: int = 23,
    legend_pos: int = 130,
    path: str = None,
):
    """
    Generates a radar chart for city liveability profiles.

    Expands on https://www.python-graph-gallery.com/web-circular-barplot-with-matplotlib
    -- A python code blog post by Yan Holtz, in turn expanding on work of Tomás Capretto and Tobias Stadler.
    Height and width are given in milimeters.
    """
    if phrases is None:
        phrases = self.get_phrases()
    if city_stats is None:
        city_stats = self.get_city_stats(phrases=phrases)
    if title is None:
        title = phrases['Population % with access within 500m to...']
    if cmap is None:
        from subprocesses.batlow import batlow_map as cmap
    if path is None:
        figure_path = f'{self.config["region_dir"]}/figures'
        if not os.path.exists(figure_path):
            os.mkdir(figure_path)
        path = f'{figure_path}/access_profile_{phrases['language']}.png'
    width = fpdf2_mm_scale(width)
    height = fpdf2_mm_scale(height)
    figsize = (width, height)
    # Values for the x axis
    ANGLES = np.linspace(
        0.15,
        2 * np.pi - 0.05,
        len(city_stats['access']),
        endpoint=False,
    )
    VALUES = city_stats['access'].values
    COMPARISON = city_stats['percentiles']['p50']
    INDICATORS = city_stats['access'].index
    # Colours
    GREY12 = '#1f1f1f'
    norm = mpl_colors.Normalize(vmin=0, vmax=100)
    COLORS = cmap(list(norm(VALUES)))
    # Initialize layout in polar coordinates
    textsize = 11
    fig, ax = plt.subplots(
        figsize=figsize,
        subplot_kw={'projection': 'polar'},
    )
    # Set background color to white, both axis and figure.
    # fig.patch.set_facecolor('white')
    # ax.set_facecolor('white')
    ax.set_theta_offset(1.2 * np.pi / 2)
    ax.set_ylim(-50, 125)
    # Add geometries to the plot -------------------------------------
    # Add bars to represent the cumulative track lengths
    ax.bar(ANGLES, VALUES, color=COLORS, alpha=0.9, width=0.52, zorder=10)
    # Add dots to represent the mean gain
    comparison_text = '\n'.join(
        wrap(
            phrases['25 city comparison'],
            legend_width,
            break_long_words=False,
        ),
    )
    ax.scatter(
        ANGLES,
        COMPARISON,
        s=60,
        color=GREY12,
        zorder=11,
        label=comparison_text,
    )
    # Add interquartile comparison reference lines
    ax.vlines(
        ANGLES,
        city_stats['percentiles']['p25'],
        city_stats['percentiles']['p75'],
        color=GREY12,
        zorder=11,
        label='Interquartile range',
    )
    # Add labels for the indicators
    try:
        LABELS = [
            '\n'.join(wrap(r, 12, break_long_words=False)) for r in INDICATORS
        ]
    except Exception:
        LABELS = INDICATORS
    # Set the labels
    ax.set_xticks(ANGLES)
    ax.set_xticklabels(LABELS, size=textsize)
    # Remove lines for polar axis (x)
    ax.xaxis.grid(False)
    # Put grid lines for radial axis (y) at 0, 1000, 2000, and 3000
    ax.set_yticklabels([])
    ax.set_yticks([0, 25, 50, 75, 100])
    # Remove spines
    ax.spines['start'].set_color('none')
    ax.spines['polar'].set_color('none')
    # Adjust padding of the x axis labels ----------------------------
    # This is going to add extra space around the labels for the
    # ticks of the x axis.
    XTICKS = ax.xaxis.get_major_ticks()
    for tick in XTICKS:
        tick.set_pad(10)
    # Add custom annotations -----------------------------------------
    # The following represent the heights in the values of the y axis
    PAD = 0
    for num in [0, 50, 100]:
        ax.text(
            -0.2 * np.pi / 2,
            num + PAD,
            f'{num}%',
            ha='center',
            va='center',
            bbox=dict(facecolor='white', edgecolor='red'),
            backgroundcolor='white',
            size=textsize,
        )
    # Add text to explain the meaning of the height of the bar and the
    # height of the dot
    ax.text(
        ANGLES[0],
        -50,
        '\n'.join(
            wrap(
                title.format(city_name=phrases['city_name']),
                13,
                break_long_words=False,
            ),
        ),
        rotation=0,
        ha='center',
        va='center',
        size=textsize,
        zorder=12,
    )
    # locate position of legend
    ax.legend(
        loc=legend_anchor,
        bbox_to_anchor=(legend_xy[0], legend_xy[1]),
    )
    fig.savefig(path, dpi=dpi, transparent=True)
    plt.close(fig)
    return path
