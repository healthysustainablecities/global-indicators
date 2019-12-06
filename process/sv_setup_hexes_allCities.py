def getMeanStd(gdf, columnName):
    """
    calculate mean and std from the big dataframe of all cities
    
    Arguments:
        gdf {[geodataframe]} -- [all cities]
        columnName {[str]} -- [field name]
    """
    mean = gdf[columnName].mean()
    std = gdf[columnName].std()
    return mean, std