import zipfile
from os import listdir, path

global_indicators_path = path.dirname(path.abspath(__file__))
edge_validation_data_path = path.join(global_indicators_path, "data", "edge_validation")
for city in listdir(edge_validation_data_path):
    with zipfile.ZipFile(path.join(edge_validation_data_path, city), "r") as zip_data:
        zip_data.extractall(path.join(edge_validation_data_path))
