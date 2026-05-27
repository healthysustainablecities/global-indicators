"""
Define functions for spatial indicator analyses.

This module contains functions to set up sample points stats within study regions.
"""

import geopandas as gpd
import numpy
import numpy as np
import pandas as pd
from tqdm import tqdm


def spatial_join_index_to_gdf(
    gdf,
    join_gdf,
    join_type='within',
    dropna=True,
):
    """Append to a geodataframe the named index of another using spatial join.

    Parameters
    ----------
    gdf: GeoDataFrame
    join_gdf: GeoDataFrame
    join_type: str (default 'within')
    dropna: True

    Returns
    -------
    GeoDataFrame
    """
    gdf_columns = list(gdf.columns)
    gdf = gpd.sjoin(gdf, join_gdf, how='left', predicate=join_type)
    if 'index_right' in gdf.columns:
        gdf = gdf.rename(columns={'index_right': join_gdf.index.name})
    gdf = gdf[gdf_columns + [join_gdf.index.name]]
    if dropna:
        gdf = gdf[~gdf[join_gdf.index.name].isna()]
        gdf[join_gdf.index.name] = gdf[join_gdf.index.name].astype(
            join_gdf.index.dtype,
        )
    return gdf


def filter_ids(df, query, message):
    """Pandas query designed to filter and report feedback on counts before and after query.

    Parameters
    ----------
    df: DataFrame
    query: str Pandas query string
    message: str An informative message to print describing query in plain language

    Returns
    -------
    DataFrame
    """
    print(message)
    pre_discard = len(df)
    df = df.query(query)
    post_discard = len(df)
    print(
        f'  {pre_discard - post_discard} sample points discarded, '
        f'leaving {post_discard} remaining.',
    )
    return df


def _snap_pois_to_nodes(r, layer, geom_col, where_clause=''):
    """Find unique node osmids nearest to POIs.

    Uses pre-computed n1/n2 columns when available (added by
    Region.add_nearest_node_associations), otherwise falls back to a
    PostGIS KNN query against the nodes table.
    Returns a list of unique osmid ints, or an empty list if no POIs match.
    """
    cond = f'WHERE {where_clause}' if where_clause else ''
    col_check = r.get_df(
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema = current_schema() "
        f"  AND table_name = '{layer}' "
        f"  AND column_name IN ('n1', 'n2')",
    )
    if col_check is not None and len(col_check) == 2:
        sql = (
            f'SELECT n1 AS osmid FROM {layer} {cond} '
            f'UNION '
            f'SELECT n2 AS osmid FROM {layer} {cond}'
        )
    else:
        sql = (
            f'SELECT DISTINCT '
            f'(SELECT osmid FROM nodes ORDER BY nodes.geometry <-> poi.{geom_col} LIMIT 1) AS osmid '
            f'FROM {layer} poi {cond}'
        )
    result = r.get_df(sql)
    if result is None or len(result) == 0:
        return []
    return result['osmid'].dropna().astype('int64').tolist()


def _pgr_nearest_poi_dist(r, poi_node_ids, distance, col_name, node_index):
    """Return a Series of network distances (metres) from each node to the nearest POI node.

    Uses pgr_drivingDistance on edges_simplified (undirected walkable network).
    Nodes outside the distance threshold are assigned -999.
    """
    default = pd.Series(-999.0, index=node_index, name=col_name)
    if not poi_node_ids:
        return default
    ids_sql = ', '.join(str(int(nid)) for nid in poi_node_ids)
    sql = (
        f"SELECT node, MIN(agg_cost) AS dist "
        f"FROM pgr_drivingDistance("
        f"'SELECT row_number() OVER () AS id, u AS source, v AS target, "
        f"length::float AS cost, length::float AS reverse_cost FROM edges_simplified',"
        f" ARRAY[{ids_sql}]::bigint[], {distance}, false)"
        f" GROUP BY node"
    )
    result = r.get_df(sql)
    if result is None or len(result) == 0:
        return default
    reachable = pd.Series(
        result['dist'].to_numpy(dtype=float),
        index=pd.Index(result['node'].to_numpy(dtype='int64'), name='osmid'),
        name=col_name,
    )
    default.update(reachable)
    return default


def cal_dist_node_to_nearest_pois(
    r,
    layer,
    geometry,
    distance,
    category_field=None,
    categories=None,
    filter_field=None,
    filter_iterations=None,
    output_names=None,
    output_prefix='',
):
    """Calculate the distance from each network node to the nearest POI within the distance threshold.

    Uses pgr_drivingDistance on the PostGIS edges_simplified table (undirected).
    POIs are snapped to the nearest node via a PostGIS KNN query on the nodes table.
    Nodes where no POI is reachable within the threshold are coded as -999.

    Parameters
    ----------
    r : Region
        Study region object providing database connection
    layer : str
        Name of the PostGIS table containing the destination points-of-interest
    geometry : str
        Name of the geometry column in the POI table
    distance : int
        Maximum search distance in metres
    category_field : str, optional
        Field to filter POI rows by values in the categories list
    categories : list, optional
        List of category values found in category_field
    filter_field : str, optional
        Field to filter POI rows using SQL-compatible expressions from filter_iterations
    filter_iterations : list, optional
        List of SQL-compatible filter expressions applied to filter_field (e.g. ['>=0', '<=30'])
    output_names : list, optional
        Names for output columns (must match order of categories or filter_iterations)
    output_prefix : str
        Prefix to prepend to output_names (default '')

    Returns
    -------
    DataFrame
        Indexed by osmid, one column per category/iteration, distances in metres or -999
    """
    node_index = pd.Index(
        r.get_df('SELECT osmid FROM nodes ORDER BY osmid')['osmid'].to_numpy(dtype='int64'),
        name='osmid',
    )
    if category_field is not None and categories is not None:
        if output_names is None:
            output_names = categories
        output_names = [f'{output_prefix}{x}' for x in output_names]
        appended_data = []
        for x in categories:
            col_name = output_names[categories.index(x)]
            x_sql = str(x).replace("'", "''")
            poi_node_ids = _snap_pois_to_nodes(r, layer, geometry, f"{category_field} = '{x_sql}'")
            appended_data.append(_pgr_nearest_poi_dist(r, poi_node_ids, distance, col_name, node_index))
        gdf_poi_dist = pd.concat(appended_data, axis=1)
    elif filter_field is not None and filter_iterations is not None:
        if output_names is None:
            output_names = filter_iterations
        output_names = [f'{output_prefix}{x}' for x in output_names]
        appended_data = []
        for x in filter_iterations:
            col_name = output_names[filter_iterations.index(x)]
            poi_node_ids = _snap_pois_to_nodes(r, layer, geometry, f"{filter_field} {str(x).replace('==', '=')}")
            appended_data.append(_pgr_nearest_poi_dist(r, poi_node_ids, distance, col_name, node_index))
        gdf_poi_dist = pd.concat(appended_data, axis=1)
    else:
        if output_names is None:
            output_names = ['POI']
        output_names = [f'{output_prefix}{x}' for x in output_names]
        poi_node_ids = _snap_pois_to_nodes(r, layer, geometry)
        gdf_poi_dist = _pgr_nearest_poi_dist(r, poi_node_ids, distance, output_names[0], node_index).to_frame()
    return gdf_poi_dist


def create_full_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    This is achieved by first allocating sample points coincident with nodes their direct estimates, and then through a sub-function process_distant_nodes() deriving estimates for sample points based on terminal nodes of the edge segments on which they are located, accounting for respective distances.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        'Derive sample point estimates for accessibility and densities based on node distance relations',
    )
    simple_nodes = gdf_nodes_poi_dist.join(gdf_nodes_simple)
    print(
        '\t - match sample points whose locations coincide with intersections directly with intersection record data',
    )
    coincident_nodes = (
        pd.concat(
            [
                samplePointsData.query('n1_distance==0')[['n1']].rename(
                    {'n1': 'node'},
                    axis='columns',
                ),
                samplePointsData.query('n1_distance!=0 and n2_distance==0')[
                    ['n2']
                ].rename({'n2': 'node'}, axis='columns'),
            ],
        )
        .join(simple_nodes, on='node', how='left')[
            [
                x
                for x in simple_nodes.columns
                if x not in ['grid_id', 'geometry']
            ]
        ]
        .copy()
    )
    distant_nodes = process_distant_nodes(
        samplePointsData,
        gdf_nodes_simple,
        gdf_nodes_poi_dist,
        density_statistics,
    )
    full_nodes = pd.concat([coincident_nodes, distant_nodes]).sort_index()
    return full_nodes


def process_distant_nodes(
    samplePointsData,
    gdf_nodes_simple,
    gdf_nodes_poi_dist,
    density_statistics,
):
    """Create long form working dataset of sample points to evaluate respective node distances and densities.

    Parameters
    ----------
    samplePointsData: GeoDataFrame
        GeoDataFrame of sample points
    gdf_nodes_simple:  GeoDataFrame
        GeoDataFrame with density records
    gdf_nodes_poi_dist:  GeoDataFrame
        GeoDataFrame of distances to points of interest
    density_statistics: list
        list of density statistic sample point indicator names

    Returns
    -------
    GeoDataFrame
    """
    print(
        '\t - for sample points not co-located with intersections, derive estimates by:',
    )
    print('\t\t - accounting for distances')
    distant_nodes = samplePointsData.query(
        'n1_distance!=0 and n2_distance!=0',
    )[['n1', 'n2', 'n1_distance', 'n2_distance']].copy()
    distant_nodes['nodes'] = distant_nodes.apply(
        lambda x: [[int(x.n1), x.n1_distance], [int(x.n2), x.n2_distance]],
        axis=1,
    )
    distant_nodes = distant_nodes[['nodes']].explode('nodes')
    distant_nodes[['node', 'node_distance_m']] = pd.DataFrame(
        distant_nodes.nodes.values.tolist(),
        index=distant_nodes.index,
    )
    distant_nodes = distant_nodes[['node', 'node_distance_m']].join(
        gdf_nodes_poi_dist,
        on='node',
        how='left',
    )
    distance_fields = []
    for d in list(gdf_nodes_poi_dist.columns):
        distant_nodes[d] = distant_nodes[d] + distant_nodes['node_distance_m']
        distance_fields.append(d)

    print(
        '\t\t - calculating proximity-weighted average of density statistics for each sample point',
    )
    # define aggregation functions for per sample point estimates
    # ie. we take
    #       - minimum of full distances
    #       - and weighted mean of densities
    # The latter is so that if distance from two nodes for a point are 10m and 30m
    #  the weight of 10m is 0.75 and the weight of 30m is 0.25.
    #  ie. 1 - (10/(10+30)) = 0.75    , and 1 - (30/(10+30)) = 0.25
    # ie. the more proximal node is the dominant source of the density estimate, but the distal one still has
    # some contribution to ensure smooth interpolation across sample points (ie. a 'best guess' at true value).
    # This is not perfect; ideally the densities would be calculated for the sample points directly.
    # But it is better than just assigning the value of the nearest node (which may be hundreds of metres away).
    #
    # An important exceptional case which needs to be accounted for is a sample point co-located with a node
    # intersection which is the beginning and end of a cul-de-sac loop.  In such a case, n1 and n2 are identical,
    # and the distance to each is zero, which therefore results in a division by zero error. To resolve this issue,
    # and a general rule of efficiency, if distance to any node is zero that nodes esimates shall be employed directly.
    # This is why the weighting and full distance calculation is only considered for sample points with "distant nodes",
    # and not those with "coincident nodes".

    node_weight_denominator = (
        distant_nodes['node_distance_m'].groupby(distant_nodes.index).sum()
    )
    distant_nodes = distant_nodes[
        ['node', 'node_distance_m'] + distance_fields
    ].join(node_weight_denominator, how='left', rsuffix='_denominator')
    distant_nodes['density_weight'] = 1 - (
        distant_nodes['node_distance_m']
        / distant_nodes['node_distance_m_denominator']
    )
    # join up full nodes with density fields
    distant_nodes = distant_nodes.join(
        gdf_nodes_simple[density_statistics],
        on='node',
        how='left',
    )
    for statistic in density_statistics:
        distant_nodes[statistic] = (
            distant_nodes[statistic] * distant_nodes.density_weight
        )
    agg_functions = dict(
        zip(
            distance_fields + density_statistics,
            ['min'] * len(distance_fields) + ['sum'] * len(density_statistics),
        ),
    )
    distant_nodes = distant_nodes.groupby(distant_nodes.index).agg(
        agg_functions,
    )
    return distant_nodes


# Cumulative opportunities (binary)
# 1 if d <= access_dist
# 0 if d > access_dist
def binary_access_score(df, distance_names, threshold=500):
    """Calculate accessibiity score using binary measure.

    1 if access <= access_dist, 0 otherwise.

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters

    Returns
    -------
    DataFrame
    """
    df1 = (df[distance_names] <= threshold).fillna(False).astype(int)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Soft threshold access score
# Higgs, C., Badland, H., Simons, K. et al. (2019) The Urban Liveability Index
def soft_access_score(df, distance_names, threshold=500, k=5):
    """Calculate accessibiity score using soft threshold approach.

    1 / (1+ e^(k *((dist-access_dist)/access_dist)))

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of original distance field names
    threshold: int
        access distance threshold, default is 500 meters
    k: int
        the slope of decay, default is 5

    Returns
    -------
    DataFrame
    """
    df1 = 1 / (
        1 + numpy.exp(k * ((df[distance_names] - threshold) / threshold))
    )
    df1 = df1.fillna(0).astype(float)
    # If any of distance_names were all null in DF, should be returned as all null
    nulls = df[distance_names].isnull().all()
    df1[nulls.index[nulls]] = np.nan
    return df1


# Cumulative-Gaussian
# Reference: Vale, D. S., & Pereira, M. (2017).
# The influence of the impedance function on gravity-based pedestrian accessibility measures
def cumulative_gaussian_access_score(
    df,
    distance_names,
    threshold=500,
    k=129842,
):
    """Calculate accessibiity score using Cumulative-Gaussian approach.

    1 if d <= access_dist ; otherwise, e ^(-1 *((d^2)/k)) if d > access_dist

    Parameters
    ----------
    df: DataFrame
        DataFrame with origin-destination distances
    distance_names: list
        list of field names for distance records
    threshold: int
        access distance threshold
    k: int
        the slope of decay

    Returns
    -------
    DataFrame
    """
    df1 = df[distance_names].copy()
    df1 = df1.astype(float)
    df1[df1 <= threshold] = 1
    df1[df1 > threshold] = numpy.exp(
        -1 * (((df1[df1 > threshold] - threshold) ** 2) / k),
    )
    df1 = df1.fillna(0).astype(float)
    return df1


def split_list(alist, wanted_parts=1):
    """Split list.

    Parameters
    ----------
    alist: list
        the split list
    wanted_parts: int
        the number of parts (default: {1})

    Returns
    -------
    list
    """
    length = len(alist)
    # return all parts in a list, like [[],[],[]]
    return [
        alist[i * length // wanted_parts : (i + 1) * length // wanted_parts]
        for i in range(wanted_parts)
    ]
