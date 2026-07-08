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

# ============================================================ MAP 4: dismount to destination
def map4():
    # find a fresh food market that sits on/beside a footway (dismount) but off the
    # rideable network, with its nearest R cyclable node close enough to keep in-window
    dism = ge[ge['foot_dismount']]
    ride = ge[ge['bike_permitted']]
    ffm2 = ffm.copy()
    ffm2['dd'] = ffm2.geometry.apply(lambda g: dism.distance(g).min())
    ffm2['dr'] = ffm2.geometry.apply(lambda g: ride.distance(g).min())
    ffm2['dn'] = ffm2.geometry.apply(lambda g: rn.geometry.distance(g).min())
    ffm2['dcx'] = ((ffm2.geometry.x-CX)**2+(ffm2.geometry.y-CY)**2)**0.5
    # market in a genuine footway pocket: on a footway (dd small), well off the rideable
    # network (dr large) AND a meaningful, in-window distance from the nearest R node (dn)
    def _pick():
        for dd, dr_, lo, hi in [(20, 80, 100, 210), (25, 60, 90, 220), (30, 45, 80, 230)]:
            p = ffm2[(ffm2['dd'] < dd) & (ffm2['dr'] > dr_) &
                     (ffm2['dn'] > lo) & (ffm2['dn'] < hi)]
            if len(p):
                return p.sort_values('dcx').iloc[0]
        return ffm2[(ffm2['dn'] > 90) & (ffm2['dn'] < 230)].sort_values('dcx').iloc[0]
    target = _pick()
    tg = target['geometry']
    wx, wy = tg.x, tg.y
    half = 260
    win = (wx, wy, half); b = clipbox(*win)
    fig, ax = plt.subplots(figsize=(9.5, 9))
    gsub = ge[ge.intersects(b)]
    gsub[gsub['bike_permitted'] & ~gsub['foot_dismount']].plot(ax=ax, color='#9a9a9a', linewidth=1.1, zorder=4)
    gsub[gsub['foot_dismount']].plot(ax=ax, color='#2c7fb8', linewidth=2.1, zorder=6)
    # market marker
    ax.scatter([wx], [wy], s=190, marker='*', color='#e6194b', edgecolor='white', linewidth=0.8, zorder=10)
    ax.annotate('fresh food market\n(on footway)', (wx, wy), fontsize=8, color='#111',
                xytext=(7, -18), textcoords='offset points',
                path_effects=[pe.withStroke(linewidth=2, foreground='white')])
    # nearest R cyclable node (snap target)
    rnw = rn[rn.within(clipbox(wx, wy, half*2))]
    if len(rnw):
        d = rnw.geometry.distance(tg)
        nn = rnw.geometry.iloc[int(d.values.argmin())]
        ax.plot([wx, nn.x], [wy, nn.y], color='#e6194b', lw=1.6, ls='--', zorder=8)
        ax.scatter([nn.x], [nn.y], s=55, color='#e6194b', edgecolor='white', linewidth=0.5, zorder=9)
        mx, my = (wx+nn.x)/2, (wy+nn.y)/2
        ax.annotate(f'R: snap {d.min():.0f} m\n(free, uncounted)',
                    (mx, my), fontsize=8.5, color='#b00020', ha='center',
                    path_effects=[pe.withStroke(linewidth=2.5, foreground='white')])
    set_window(ax, *win); add_basemap(ax); add_scalebar(ax)
    handles = [
        mlines.Line2D([], [], color='#e6194b', marker='*', ls='', markersize=13, label='fresh food market'),
        mlines.Line2D([], [], color='#2c7fb8', lw=2.5, label='footway/path (GHSCI dismount, counted ×3)'),
        mlines.Line2D([], [], color='#9a9a9a', lw=2, label='rideable street'),
        mlines.Line2D([], [], color='#e6194b', lw=1.5, ls='--', label='R snap to nearest cyclable node'),
    ]
    ax.legend(handles=handles, loc='lower right', fontsize=7.8, framealpha=0.92)
    ax.set_title('Dimension 4 — Dismount / destination access\n'
                 'GHSCI walks the bike along the footway (distance counted); R teleports the\n'
                 'destination to the nearest cyclable node (snap distance not counted).', fontsize=10)
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

ALLMAPS = {'1': map1, '2': map2, '3': map3, '4': map4, '5': map5, '6': map6, '7': map7}
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
