import json

def pp_json(json_thing, sort=True, indents=4):
    if type(json_thing) is str:
        print(json.dumps(json.loads(json_thing), sort_keys=sort, indent=indents))
    else:
        print(json.dumps(json_thing, sort_keys=sort, indent=indents))
    return None




indicators = dict()
indicators["city"] = "Bangkok"
indicators["indicators"] = {}
indicators["indicators"]["Crime"] = {}
indicators["indicators"]["Crime"]["priority"] = "1 - immediate"
indicators["indicators"]["Crime"]["measures"] = {}
indicators["indicators"]["Crime"]["measures"]["Criminal cases per 100,000 persons"] = {}
indicators["indicators"]["Crime"]["measures"]["Criminal cases per 100,000 persons"]["data"] = {}
indicators["indicators"]["Crime"]["measures"]["Criminal cases per 100,000 persons"]["data"]["boundaries"] = "D:/ind_bangkok/data/boundaries/humdata/tha_adm2_gista_plyg_v5.zip"

pp_json(your_json_string_or_dict)
