import networkx as nx

ox.config(use_cache=True, log_console=True)

def graph_from_file_filtered(filename, 
                             network_type='all_private', 
                             simplify=True,
                             retain_all=False, 
                             name='unnamed',
                             custom_filter=None):
    """
    Create a networkx graph from OSM data in an XML file.

    Parameters
    ----------
    filename : string
        the name of a file containing OSM XML data
    network_type : string
        what type of street network to get
    custom_filter : string
        a custom network filter to be used instead of the network_type presets, following OSMnx (Overpass) format
    simplify : bool
        if true, simplify the graph topology
    retain_all : bool
        if True, return the entire graph even if it is not connected
    name : string
        the name of the graph

    Returns
    -------
    networkx multidigraph
    """
    import osmnx as ox
    # transmogrify file of OSM XML data into JSON
    response_jsons = [ox.overpass_json_from_file(filename)]
    
    if custom_filter is not None:
        filter_list = format_filter_list(custom_filter)
        response_jsons[0]['elements'] = [x for x in response_jsons[0]['elements'] if x['type'] in ['way','node'] and (check_filter_list(x,filter_list) or x['tags']=={})]
    
    # create graph using this response JSON
    G = ox.create_graph(response_jsons, 
                     network_type=network_type,
                     retain_all=retain_all, name=name)
    
    # simplify the graph topology as the last step.
    if simplify:
        G = ox.simplify_graph(G)
    
    log('graph_from_file() returning graph with {:,} nodes and {:,} edges'.format(len(list(G.nodes())), len(list(G.edges()))))
    return G 