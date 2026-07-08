# -*- coding: utf-8 -*-
"""Generate the 7 annotated Wuerzburg case-study maps for the R-vs-GHSCI summary.

Each map illustrates one comparison dimension. Off the live ghsci `würzburg` DB
(25832) and the R baseline gpkg (4326 -> 25832). Robust per-map (try/except).
"""
import os, sys, traceback
os.chdir('/home/ghsci/process')
sys.path.insert(0, '/home/ghsci/process/subprocesses')
import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.patheffects as pe
import contextily as cx
from shapely.geometry import box
import ghsci
from batlow import batlow_map

YML = "data/Cycling/Würzburg/Würzburg.yml"
R_GPKG = "/home/ghsci/r_output/Würzburg/Würzburg_cyclingIndicators.gpkg"
OUTDIR = "/home/ghsci/process/cycling_R_vs_GHSCI_maps"
os.makedirs(OUTDIR, exist_ok=True)
SRID = 25832
LTS_COLORS = {1: '#1a9850', 2: '#a6d96a', 3: '#fdae61', 4: '#d7191c'}

r = ghsci.Region(YML)

def add_basemap(ax):
    try:
        cx.add_basemap(ax, crs=f'EPSG:{SRID}', source=cx.providers.CartoDB.Positron,
                       attribution_size=5)
    except Exception as e:
        print('  (basemap unavailable:', e, ')')

def add_scalebar(ax):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    span = x1 - x0
    if not np.isfinite(span) or span <= 0:
        return
    target = span * 0.25
    mag = 10 ** int(np.floor(np.log10(target)))
    length = next((m * mag for m in (5, 2, 1) if target >= m * mag), mag)
    xr = x0 + span * 0.05; yb = y0 + (y1 - y0) * 0.06; h = (y1 - y0) * 0.013
    half = length / 2.0
    ax.add_patch(mpatches.Rectangle((xr, yb), half, h, facecolor='white',
                 edgecolor='black', lw=0.8, zorder=20))
    ax.add_patch(mpatches.Rectangle((xr + half, yb), half, h, facecolor='black',
                 edgecolor='black', lw=0.8, zorder=20))
    label = f'{length/1000:g} km' if length >= 1000 else f'{length:g} m'
    ax.text(xr + length/2.0, yb + h*1.7, label, ha='center', va='bottom',
            color='white', fontsize=8, fontweight='bold', zorder=21,
            path_effects=[pe.withStroke(linewidth=2.5, foreground='black')])

def set_window(ax, cx_, cy_, half):
    ax.set_xlim(cx_ - half, cx_ + half); ax.set_ylim(cy_ - half, cy_ + half)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_aspect('equal')

def clipbox(cx_, cy_, half):
    return box(cx_ - half, cy_ - half, cx_ + half, cy_ + half)

def finish(fig, name):
    p = os.path.join(OUTDIR, name)
    fig.savefig(p, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print('  wrote', p)

# ---------------------------------------------------------------- load data
print('Loading GHSCI layers...')
ge = r.get_gdf("SELECT ogc_fid, highway, foot, bicycle, lvl_traf_stress, lts_imped, "
               "cost_dist, cost_lts, bike_permitted, foot_dismount, length, geom FROM edges",
               geom_col='geom').set_crs(epsg=SRID, allow_override=True)
gn = r.get_gdf("SELECT osmid, highway, geom FROM nodes", geom_col='geom').set_crs(epsg=SRID, allow_override=True)
gsp = r.get_gdf("SELECT * FROM sample_points_cycling", geom_col='geom').set_crs(epsg=SRID, allow_override=True)
usp = r.get_gdf("SELECT point_id, n1, n2, geom FROM urban_sample_points", geom_col='geom').set_crs(epsg=SRID, allow_override=True)
ffm = r.get_gdf("SELECT geom FROM destinations WHERE dest_name='fresh_food_market'", geom_col='geom').set_crs(epsg=SRID, allow_override=True)
aos = r.get_gdf("SELECT geom FROM aos_public_large_nodes_30m_line", geom_col='geom').set_crs(epsg=SRID, allow_override=True)
# standardise active geometry column name to 'geometry' (R layers already use it)
ge = ge.rename_geometry('geometry'); gn = gn.rename_geometry('geometry')
gsp = gsp.rename_geometry('geometry'); usp = usp.rename_geometry('geometry')
ffm = ffm.rename_geometry('geometry'); aos = aos.rename_geometry('geometry')
# NaN-safe normalised tag columns (postgres NULLs otherwise break boolean masks)
ge['foot_l'] = ge['foot'].astype('string').str.lower().fillna('')
ge['bike_l'] = ge['bicycle'].astype('string').str.lower().fillna('')
gn['hw_l'] = gn['highway'].astype('string').str.lower().fillna('')
print(f'  edges={len(ge)} nodes={len(gn)} sp_cycling={len(gsp)} usp={len(usp)} ffm={len(ffm)} aos={len(aos)}')

print('Loading R gpkg layers...')
re_ = gpd.read_file(R_GPKG, layer='edges').to_crs(SRID)
rn = gpd.read_file(R_GPKG, layer='nodes').to_crs(SRID)
rsp = gpd.read_file(R_GPKG, layer='sample_points_accessibility').to_crs(SRID)
rgrid = gpd.read_file(R_GPKG, layer='grid_accessibility').to_crs(SRID)
print(f'  R edges={len(re_)} nodes={len(rn)} sp={len(rsp)} grid={len(rgrid)}')

# city centre from sample points
CX, CY = float(usp.geometry.x.median()), float(usp.geometry.y.median())
print(f'  centre approx: {CX:.0f}, {CY:.0f}')

# study-region boundary (for the buffer/extent comparison)
try:
    bnd = r.get_gdf("SELECT ST_Union(geom) AS geom FROM urban_study_region",
                    geom_col='geom').set_crs(epsg=SRID, allow_override=True)
    bnd = bnd.rename_geometry('geometry')
except Exception as e:
    print('  (no urban_study_region:', e, ')')
    bnd = None

def _extent(gdf, label):
    b = gdf.total_bounds
    w, h = (b[2]-b[0])/1000.0, (b[3]-b[1])/1000.0
    beyond = None
    if bnd is not None:
        bound_geom = bnd.geometry.iloc[0]
        beyond = float(gdf.geometry.union_all().convex_hull.distance(bound_geom))  # 0 if inside
        # max reach of edges beyond the boundary (buffer size proxy)
        far = gdf.geometry.representative_point()
        beyond = float((far.distance(bound_geom)).max())
    print(f'  extent[{label}]: bbox {w:.1f} x {h:.1f} km; max reach beyond boundary '
          f'{beyond:.0f} m' if beyond is not None else f'  extent[{label}]: {w:.1f}x{h:.1f} km')
    return b

_extent(re_, 'R edges (gpkg, boundary-clipped)')
_extent(ge, 'GHSCI edges (5000 m buffer)')

def lts_plot(ax, edges, col, window, lw=0.9):
    b = clipbox(*window)
    sub = edges[edges.intersects(b)]
    for lts in (1, 2, 3, 4):
        s = sub[sub[col] == lts]
        if len(s):
            s.plot(ax=ax, color=LTS_COLORS[lts], linewidth=lw if lts <= 2 else lw*1.4,
                   zorder=5 if lts <= 2 else 6)
    return sub

# ============================================================ MAP 1: network inclusion
def map1():
    # focus on a cluster of foot=no bicycle-only segments (included by GHSCI, dropped by R filter)
    fn = ge[(ge['foot_l'] == 'no') & (ge['bike_l'] != 'no')].copy()
    fn = fn[fn['bike_permitted']]
    # pick densest cluster near centre
    fn['d'] = ((fn.geometry.centroid.x - CX)**2 + (fn.geometry.centroid.y - CY)**2)**0.5
    if len(fn):
        pick = fn.sort_values('d').geometry.centroid.iloc[min(3, len(fn)-1)]
        wx, wy = pick.x, pick.y
    else:
        wx, wy = CX, CY
    half = 700
    win = (wx, wy, half); b = clipbox(*win)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6))
    # Panel A: R cyclable network
    ax = axes[0]
    rsub = re_[re_.intersects(b)]
    rsub.plot(ax=ax, color='#4a4a4a', linewidth=0.9, zorder=5)
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.set_title('(a) R cyclable network\n(footways / paths / steps excluded entirely)', fontsize=11)
    # Panel B: GHSCI network by routability class
    ax = axes[1]
    gsub = ge[ge.intersects(b)]
    ride = gsub[gsub['bike_permitted'] & (gsub['foot_l'] != 'no')]
    dism = gsub[gsub['foot_dismount']]
    excl = gsub[~gsub['bike_permitted'] & ~gsub['foot_dismount']]
    fnw = gsub[(gsub['foot_l']=='no') & (gsub['bike_l']!='no') & gsub['bike_permitted']]
    ride.plot(ax=ax, color='#4a4a4a', linewidth=0.9, zorder=5, label='rideable')
    dism.plot(ax=ax, color='#2c7fb8', linewidth=0.9, zorder=6)
    excl.plot(ax=ax, color='#d7191c', linewidth=1.0, linestyle=':', zorder=6)
    if len(fnw):
        fnw.plot(ax=ax, color='#e6194b', linewidth=2.4, zorder=8)
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.set_title('(b) GHSCI network\n(footway/path routable as dismount; bicycle-only kept)', fontsize=11)
    handles = [
        mlines.Line2D([], [], color='#4a4a4a', lw=2, label='rideable (bike permitted)'),
        mlines.Line2D([], [], color='#2c7fb8', lw=2, label='footway/path dismount (walk bike, LTS 1)'),
        mlines.Line2D([], [], color='#e6194b', lw=3, label='bicycle-only, foot=no (dropped by R OSM filter)'),
        mlines.Line2D([], [], color='#d7191c', lw=2, ls=':', label='excluded (steps / corridor)'),
    ]
    ax.legend(handles=handles, loc='lower right', fontsize=7.5, framealpha=0.9)
    fig.suptitle('Dimension 1 — Road network inclusion (Würzburg)', fontsize=13, y=1.02)
    finish(fig, 'map1_network_inclusion.png')

# ============================================================ MAP 2: sampling & snapping
def map2():
    # window over a footway cluster near centre
    dism_edges = ge[ge['foot_dismount']].copy()
    dism_edges['d'] = ((dism_edges.geometry.centroid.x-CX)**2+(dism_edges.geometry.centroid.y-CY)**2)**0.5
    seed = dism_edges.sort_values('d').geometry.centroid.iloc[min(5, len(dism_edges)-1)]
    wx, wy = seed.x, seed.y
    half = 200
    win = (wx, wy, half); b = clipbox(*win)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.9))
    gsub = ge[ge.intersects(b)]
    ride = gsub[gsub['bike_permitted'] & ~gsub['foot_dismount']]
    foot = gsub[gsub['foot_dismount']]
    rnw = rn[rn.within(clipbox(wx, wy, half*2.2))]
    rspw = rsp[rsp.within(b)]
    # subsample R points for legibility
    rspw = rspw.iloc[::max(1, len(rspw)//45)]
    gspw = usp[usp.within(b)]
    gspw = gspw.iloc[::max(1, len(gspw)//45)]

    # Panel (a) R: points snapped to nearest cyclable node; footways are absent
    ax = axes[0]
    ride.plot(ax=ax, color='#9a9a9a', linewidth=1.1, zorder=4)
    foot.plot(ax=ax, color='#d9d9d9', linewidth=0.8, linestyle=(0, (1, 2)), zorder=3)
    longest = (0, None, None)
    for _, pt in rspw.iterrows():
        pg = pt['geometry']
        if len(rnw) == 0:
            break
        d = rnw.geometry.distance(pg)
        nn = rnw.geometry.iloc[int(d.values.argmin())]
        ax.plot([pg.x, nn.x], [pg.y, nn.y], color='#e6194b', lw=0.9, ls='--', zorder=6)
        if float(d.min()) > longest[0]:
            longest = (float(d.min()), pg, nn)
    rspw.plot(ax=ax, color='#e6194b', marker='^', markersize=20, zorder=8, edgecolor='white', linewidth=0.4)
    if longest[1] is not None and longest[0] > 25:
        pg, nn = longest[1], longest[2]
        ax.annotate(f'snap {longest[0]:.0f} m\n(not counted)', (pg.x, pg.y), fontsize=8,
                    color='#b00020', xytext=(5, 5), textcoords='offset points',
                    path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.set_title('(a) R — snap each point to nearest cyclable node\n(footways excluded, shown faint)', fontsize=10.5)
    ax.legend(handles=[
        mlines.Line2D([], [], color='#9a9a9a', lw=2, label='cyclable street'),
        mlines.Line2D([], [], color='#e6194b', marker='^', ls='', label='R sample point'),
        mlines.Line2D([], [], color='#e6194b', lw=1, ls='--', label='snap to nearest node'),
    ], loc='lower right', fontsize=7.5, framealpha=0.92)

    # Panel (b) GHSCI: points stay on their own edge (incl. footways, routable dismount)
    ax = axes[1]
    ride.plot(ax=ax, color='#9a9a9a', linewidth=1.1, zorder=4)
    foot.plot(ax=ax, color='#2c7fb8', linewidth=1.8, zorder=5)
    gspw.plot(ax=ax, color='#111111', markersize=16, zorder=8, edgecolor='white', linewidth=0.4)
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.set_title('(b) GHSCI — points kept on their edge\n(footway routable as dismount, distance counted)', fontsize=10.5)
    ax.legend(handles=[
        mlines.Line2D([], [], color='#2c7fb8', lw=2.5, label='footway/path (routable dismount, LTS 1)'),
        mlines.Line2D([], [], color='#9a9a9a', lw=2, label='rideable street'),
        mlines.Line2D([], [], color='#111111', marker='o', ls='', label='GHSCI sample point (n1/n2 + offset)'),
    ], loc='lower right', fontsize=7.5, framealpha=0.92)
    fig.suptitle('Dimension 2 — Sampling & node association  '
                 f'(city totals: R {len(rsp):,} vs GHSCI {len(usp):,} points)', fontsize=12.5, y=1.02)
    finish(fig, 'map2_sampling_snapping.png')

# ============================================================ MAP 3: LTS side-by-side
def map3():
    half = 1250
    win = (CX, CY, half)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.8))
    lts_plot(axes[0], re_, 'lvl_traf_stress', win, lw=0.8)
    set_window(axes[0], *win); add_basemap(axes[0]); add_scalebar(axes[0])
    axes[0].set_title('(a) R LTS', fontsize=11)
    lts_plot(axes[1], ge[ge['bike_permitted']], 'lvl_traf_stress', win, lw=0.8)
    set_window(axes[1], *win); add_basemap(axes[1]); add_scalebar(axes[1])
    axes[1].set_title('(b) GHSCI LTS (rideable edges)', fontsize=11)
    handles = [mlines.Line2D([], [], color=LTS_COLORS[l], lw=3, label=f'LTS {l}') for l in (1,2,3,4)]
    axes[1].legend(handles=handles, loc='lower right', fontsize=8, framealpha=0.9, ncol=2)
    fig.suptitle('Dimension 3 — Level of Traffic Stress classification (central Würzburg)', fontsize=13, y=1.01)
    finish(fig, 'map3_lts.png')

# ============================================================ MAP 4: dismount / full distance
def map4():
    from shapely.geometry import Point
    dism = ge[ge['foot_dismount']]
    ride = ge[ge['bike_permitted']]
    ffm2 = ffm.copy()
    ffm2['dd'] = ffm2.geometry.apply(lambda g: dism.distance(g).min())
    ffm2['dr'] = ffm2.geometry.apply(lambda g: ride.distance(g).min())
    ffm2['dn'] = ffm2.geometry.apply(lambda g: rn.geometry.distance(g).min())
    ffm2['dcx'] = ((ffm2.geometry.x-CX)**2+(ffm2.geometry.y-CY)**2)**0.5
    # boundary distance: keep the case DEEP inside so R's boundary-clip is not the cause
    bline = bnd.geometry.iloc[0].boundary if bnd is not None else None
    ffm2['bd'] = ffm2.geometry.apply(lambda g: bline.distance(g)) if bline is not None else 9e9
    # genuine footway case, well inside the boundary: the market's NEAREST edge is a
    # footway (dd < dr), and R's nearest cyclable node (dn) is an in-window, visible snap
    def _pick():
        for dd, lo, hi, bd in [(20, 80, 240, 1500), (25, 70, 260, 1200), (30, 60, 300, 900)]:
            p = ffm2[(ffm2['dd'] < ffm2['dr']) & (ffm2['dd'] < dd)
                     & (ffm2['dn'] > lo) & (ffm2['dn'] < hi) & (ffm2['bd'] > bd)]
            if len(p):
                return p.sort_values('dcx').iloc[0]
        p = ffm2[(ffm2['dd'] < ffm2['dr']) & (ffm2['dn'] < 300) & (ffm2['bd'] > 800)]
        return p.sort_values('dcx').iloc[0] if len(p) else ffm2.sort_values('dcx').iloc[0]
    target = _pick()
    tg = target['geometry']; wx, wy = tg.x, tg.y
    bdist = float(bnd.geometry.iloc[0].boundary.distance(tg)) if bnd is not None else -1
    print(f"  map4 market: dd(footway)={target['dd']:.0f} dr(GHSCI ride)={target['dr']:.0f} "
          f"dn(R node)={target['dn']:.0f} dist_to_boundary={bdist:.0f} m")
    half = 140; win = (wx, wy, half); b = clipbox(*win)

    # nearest GHSCI edge -> match point on the edge + along-edge offsets to its two nodes
    near = ge[ge.intersects(clipbox(wx, wy, half*1.8))]
    ne = near.geometry.iloc[int(near.geometry.distance(tg).values.argmin())]
    proj = ne.project(tg)
    match_pt = ne.interpolate(proj)
    mp_dist = tg.distance(match_pt)
    p0, p1 = Point(ne.coords[0]), Point(ne.coords[-1])
    off0, off1 = proj, ne.length - proj

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.9))
    gp = ge[ge.intersects(b)]

    # Panel (b) GHSCI 'full distance' — match to nearest edge + both terminal-node offsets
    ax = axes[1]
    gp[gp['bike_permitted'] & ~gp['foot_dismount']].plot(ax=ax, color='#9a9a9a', lw=1.1, zorder=4)
    gp[gp['foot_dismount']].plot(ax=ax, color='#2c7fb8', lw=1.9, zorder=5)
    gpd.GeoSeries([ne], crs=ge.crs).plot(ax=ax, color='#6a3d9a', lw=3.2, zorder=6)
    ax.plot([tg.x, match_pt.x], [tg.y, match_pt.y], color='#111', lw=1.6, ls=':', zorder=8)
    ax.scatter([match_pt.x], [match_pt.y], s=55, color='#6a3d9a', edgecolor='white', lw=0.5, zorder=9)
    ax.scatter([p0.x, p1.x], [p0.y, p1.y], s=48, color='#111', zorder=9)
    ax.scatter([wx], [wy], s=210, marker='*', color='#e6194b', edgecolor='white', lw=0.8, zorder=10)
    ax.annotate(f'match {mp_dist:.0f} m', (tg.x, tg.y), fontsize=8.5, color='#111', ha='left',
                xytext=(12, -10), textcoords='offset points',
                path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])
    ax.annotate(f'n1_distance {off0:.0f} m', (p0.x, p0.y), fontsize=8, color='#6a3d9a', ha='center',
                xytext=(0, 11), textcoords='offset points',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    ax.annotate(f'n2_distance {off1:.0f} m', (p1.x, p1.y), fontsize=8, color='#6a3d9a', ha='center',
                xytext=(0, -16), textcoords='offset points',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.legend(handles=[
        mlines.Line2D([], [], color='#e6194b', marker='*', ls='', markersize=12, label='fresh food market'),
        mlines.Line2D([], [], color='#6a3d9a', lw=3, label='matched (nearest) edge'),
        mlines.Line2D([], [], color='#111', lw=1.5, ls=':', label='match distance (to edge)'),
        mlines.Line2D([], [], color='#111', marker='o', ls='', label='edge terminal nodes n1, n2'),
        mlines.Line2D([], [], color='#2c7fb8', lw=2.2, label='footway/path (dismount)'),
    ], loc='lower right', fontsize=7.3, framealpha=0.92)
    ax.set_title('(b) GHSCI "full distance": snap to nearest edge, then route via BOTH\n'
                 'terminal nodes with along-edge offsets (min of the two)', fontsize=9.8)

    # Panel (a) R snap to nearest cyclable node — with the sparser R cyclable network shown
    ax = axes[0]
    gp[gp['bike_permitted']].plot(ax=ax, color='#d6d6d6', lw=1.0, zorder=3)
    rloc = re_[re_.intersects(b)]
    rloc.plot(ax=ax, color='#ff7f00', lw=1.5, zorder=5)
    ax.scatter([wx], [wy], s=210, marker='*', color='#e6194b', edgecolor='white', lw=0.8, zorder=10)
    rnw = rn[rn.within(clipbox(wx, wy, half*2))]
    if len(rnw):
        d = rnw.geometry.distance(tg)
        nn = rnw.geometry.iloc[int(d.values.argmin())]
        ax.plot([wx, nn.x], [wy, nn.y], color='#e6194b', lw=1.7, ls='--', zorder=8)
        ax.scatter([nn.x], [nn.y], s=55, color='#e6194b', edgecolor='white', lw=0.5, zorder=9)
        ax.annotate(f'R snap {d.min():.0f} m\n(uncounted)', ((wx+nn.x)/2, (wy+nn.y)/2), fontsize=8.5,
                    color='#b00020', ha='center', path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    ax.legend(handles=[
        mlines.Line2D([], [], color='#e6194b', marker='*', ls='', markersize=12, label='fresh food market'),
        mlines.Line2D([], [], color='#ff7f00', lw=2.2, label='R cyclable network (sparser)'),
        mlines.Line2D([], [], color='#d6d6d6', lw=2.2, label='GHSCI rideable (for reference)'),
        mlines.Line2D([], [], color='#e6194b', lw=1.6, ls='--', label='R snap to nearest cyclable node'),
    ], loc='lower right', fontsize=7.3, framealpha=0.92)
    ax.set_title('(a) R: destination snapped to nearest cyclable NODE (discarded).\n'
                 'The footway the market sits on is excluded from R’s network → it snaps to a road node',
                 fontsize=9.8)
    fig.suptitle('Dimension 4 — Destination access: R node-snap vs GHSCI full-distance', fontsize=12.5, y=1.02)
    finish(fig, 'map4_dismount.png')

# ============================================================ MAP 5: intersections
def map5():
    signals = gn[gn['hw_l'] == 'traffic_signals']
    # window around a central signal with nearby high-LTS crossings
    signals = signals.copy()
    if len(signals):
        signals['d'] = ((signals.geometry.x-CX)**2+(signals.geometry.y-CY)**2)**0.5
        s0 = signals.sort_values('d').geometry.iloc[0]
        wx, wy = s0.x, s0.y
    else:
        wx, wy = CX, CY
    half = 500
    win = (wx, wy, half); b = clipbox(*win)
    fig, ax = plt.subplots(figsize=(9.6, 9))
    gsub = ge[ge.intersects(b)].copy()
    # colour by impedance presence
    noimp = gsub[gsub['lts_imped'].fillna(0) <= 0.01]
    imp = gsub[gsub['lts_imped'].fillna(0) > 0.01]
    noimp.plot(ax=ax, color='#bdbdbd', linewidth=1.0, zorder=4)
    if len(imp):
        imp.plot(ax=ax, column='lts_imped', cmap='YlOrRd', linewidth=2.0, zorder=6,
                 vmin=0, vmax=float(np.nanpercentile(ge['lts_imped'], 99)))
    sw = signals[signals.within(b)] if len(signals) else signals
    if len(sw):
        sw.plot(ax=ax, color='#1a9850', marker='s', markersize=45, zorder=9, edgecolor='white', linewidth=0.6)
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    handles = [
        mlines.Line2D([], [], color='#bdbdbd', lw=2, label='no added impedance (LTS 1 / signalised approach)'),
        mlines.Line2D([], [], color='#f03b20', lw=3, label='LTS impedance added (link + unsignalised crossing)'),
        mlines.Line2D([], [], color='#1a9850', marker='s', ls='', label='traffic signal node (no crossing penalty)'),
    ]
    ax.legend(handles=handles, loc='lower right', fontsize=7.8, framealpha=0.92)
    ax.set_title('Dimension 5 — Intersection impedance\n'
                 'Both pipelines add (buffer_b−buffer_a)·(imped_b−1) at unsignalised crossings of a\n'
                 'higher-stress link; signalised nodes are exempt. (GHSCI lts_imped shown.)', fontsize=10)
    finish(fig, 'map5_intersections.png')

# ============================================================ MAP 6: low-stress access grid
def map6():
    # R comparable composite = ffm & pos_large & pt_any (safe), matching R all_safe (ffm+pos+pt_any)
    def col(df, name):
        return df[name] if name in df.columns else pd.Series(0, index=df.index)
    gsp2 = gsp.copy()
    gsp2['rcomp'] = ((col(gsp2, 'sp_cycle_safe_access_fresh_food_market_2000m').fillna(0).astype(float) > 0) &
                     (col(gsp2, 'sp_cycle_safe_access_public_open_space_large_2000m').fillna(0).astype(float) > 0) &
                     (col(gsp2, 'sp_cycle_safe_access_pt_any_2000m').fillna(0).astype(float) > 0)).astype(int)
    grid = rgrid[['cell', 'all_safe_access_2km', 'population', 'geometry']].copy()
    # R value scale
    rv = pd.to_numeric(grid['all_safe_access_2km'], errors='coerce')
    grid['R'] = rv * (100 if np.nanmax(rv.values) <= 1.5 else 1)
    j = gpd.sjoin(gsp2[['rcomp', 'geometry']], grid[['cell', 'geometry']], predicate='within', how='inner')
    agg = j.groupby('cell')['rcomp'].mean() * 100
    grid['G'] = grid['cell'].map(agg)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6))
    for ax, colr, ttl in ((axes[0], 'R', '(a) R  — all_safe_access 2 km'),
                          (axes[1], 'G', '(b) GHSCI — safe all (ffm∧POS∧PT) 2 km')):
        grid.plot(ax=ax, column=colr, cmap=batlow_map, vmin=0, vmax=100,
                  linewidth=0, zorder=4, legend=False, missing_kwds={'color': '#eeeeee'})
        add_basemap(ax); add_scalebar(ax)
        ax.set_xticks([]); ax.set_yticks([])
        m = np.nanmean(grid[colr].values)
        ax.set_title(f'{ttl}\ncell mean {m:.0f}%', fontsize=10.5)
    sm = plt.cm.ScalarMappable(cmap=batlow_map, norm=plt.Normalize(0, 100))
    cb = fig.colorbar(sm, ax=axes, fraction=0.03, pad=0.02)
    cb.set_label('% sample points with fully low-stress access', fontsize=9)
    fig.suptitle('Dimension 6 — Low-stress (fully LTS≤2) access, 2 km (population grid)', fontsize=13, y=1.02)
    finish(fig, 'map6_lowstress_access.png')

# ============================================================ MAP 7: danger-weighting benefit
def map7():
    safe = pd.to_numeric(gsp.get('sp_cycle_safe_access_fresh_food_market_2000m'), errors='coerce').fillna(0)
    dw = pd.to_numeric(gsp.get('sp_cycle_access_fresh_food_market_2000m'), errors='coerce').fillna(0)
    g = gsp.copy()
    g['cls'] = np.where((safe > 0), 2, np.where(dw > 0, 1, 0))
    fig, ax = plt.subplots(figsize=(10.5, 9.5))
    order = [(0, '#c8c8c8', 6, 'no access (neither measure)'),
             (1, '#f16913', 12, 'access only via danger-weighting (benefit of the doubt)'),
             (2, '#3182bd', 4, 'fully low-stress access')]
    for v, c, s, lab in order:
        sub = g[g['cls'] == v]
        if len(sub):
            sub.plot(ax=ax, color=c, markersize=s, zorder=5 if v == 0 else (7 if v == 1 else 4), label=lab)
    add_basemap(ax); add_scalebar(ax)
    ax.set_xticks([]); ax.set_yticks([])
    n1 = int((g['cls'] == 1).sum()); ntot = len(g)
    handles = [mlines.Line2D([], [], color=c, marker='o', ls='', markersize=7, label=lab)
               for _, c, _, lab in order]
    ax.legend(handles=handles, loc='lower right', fontsize=8, framealpha=0.92)
    ax.set_title('Dimension 7 — Danger-weighted routing (fresh food, 2 km)\n'
                 f'Orange = points the danger-weighted measure rescues over the strict low-stress\n'
                 f'measure ({n1:,} of {ntot:,}; safe {100*(safe>0).mean():.0f}% → DW {100*(dw>0).mean():.0f}%).',
                 fontsize=10.5)
    finish(fig, 'map7_danger_weighting.png')

# ============================================================ MAP 8: study-region buffer / extent
def map8():
    if bnd is None:
        print('  no boundary; skipping map8'); return
    bg = bnd.geometry.iloc[0]
    r1600 = gpd.GeoSeries([bg.buffer(1600).boundary], crs=ge.crs)
    r5000 = gpd.GeoSeries([bg.buffer(5000).boundary], crs=ge.crs)
    fig, ax = plt.subplots(figsize=(9.6, 9.6))
    ge.plot(ax=ax, color='#9ecae1', lw=0.25, zorder=3)
    re_.plot(ax=ax, color='#e6550d', lw=0.35, zorder=4)
    gpd.GeoSeries([bg.boundary], crs=ge.crs).plot(ax=ax, color='#111', lw=1.8, zorder=6)
    r1600.plot(ax=ax, color='#e6550d', lw=1.6, ls='--', zorder=6)
    r5000.plot(ax=ax, color='#08519c', lw=1.6, ls='--', zorder=6)
    bb = bg.buffer(5400).bounds
    ax.set_xlim(bb[0], bb[2]); ax.set_ylim(bb[1], bb[3])
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
    add_basemap(ax); add_scalebar(ax)
    ax.legend(handles=[
        mlines.Line2D([], [], color='#111', lw=2, label='urban study region boundary'),
        mlines.Line2D([], [], color='#e6550d', lw=2, ls='--', label='1600 m buffer (R input network)'),
        mlines.Line2D([], [], color='#08519c', lw=2, ls='--', label='5000 m buffer (current GHSCI)'),
        mlines.Line2D([], [], color='#9ecae1', lw=2, label='GHSCI edges (fill the 5000 m ring)'),
        mlines.Line2D([], [], color='#e6550d', lw=2, label='R edges (gpkg, boundary-clipped)'),
    ], loc='lower right', fontsize=7.8, framealpha=0.94)
    ax.set_title('Study-region buffer: R 1600 m → GHSCI 5000 m\n'
                 'GHSCI edges reach the 5000 m ring; R routed a 1600 m-buffered network '
                 '(its stored edges are clipped to the boundary).', fontsize=10.5)
    finish(fig, 'map8_buffer_extent.png')

ALLMAPS = {'1': map1, '2': map2, '3': map3, '4': map4, '5': map5, '6': map6, '7': map7, '8': map8}
sel = sys.argv[1:] if len(sys.argv) > 1 else list(ALLMAPS)
for k in sel:
    fn = ALLMAPS[k]
    try:
        print('Running', fn.__name__)
        fn()
    except Exception:
        print('  FAILED', fn.__name__)
        traceback.print_exc()
print('ALL DONE')
