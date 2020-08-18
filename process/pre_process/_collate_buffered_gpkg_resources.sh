for i in valencia_es_2019 vic_es_2019 abuja_ng_2019 adelaide_au_2019 auckland_nz_2019 baltimore_us_2019 bangkok_th_2019 barcelona_es_2019 belfast_gb_2019 bern_ch_2019 brisbane_au_2019 cambridge_gb_2019 canberra_au_2019 chennai_in_2019 cologne_de_2019 darwin_au_2019 edinburgh_gb_2019 ghent_be_2019 graz_at_2019 hanoi_vn_2019 hobart_au_2019 hong_kong_hk_2019 hong_kong_hk_2019_old lisbon_pt_2019 london_gb_2019 maiduguri_ng_2019 maiduguri_ng_2019_old melbourne_au_2019 mexico_city_mx_2019 odense_dk_2019 olomouc_cz_2019 perth_au_2019 phoenix_us_2019 sao_paolo_br_2019 sao_paulo_br_2019 seattle_us_2019 sydney_au_2019
    do
        echo $i
        graphml="${i}_10000m_pedestrian_osm_20190902.graphml"
        gpkg="${i}_1600m_buffer.gpkg"
        cp ./../data/study_region/${i}/${graphml} \
           ./../data/study_region/_study_regions_for_analysis/${graphml}
        cp ./../data/study_region/${i}/${gpkg} \
           ./../data/study_region/_study_regions_for_analysis/${gpkg}
    done