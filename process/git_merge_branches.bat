title Merge branches with origin/master
echo Merge branches with origin/master

FOR %%A  IN (li_adelaide_2016,li_albury_wodonga_2016,li_ballarat_2016,li_bendigo_2016,li_bris_2016,li_cairns_2016,li_canberra_2016,li_darwin_2016,li_geelong_2016,li_goldcoast_tweedheads_2016,li_hobart_2016,li_launceston_2016,li_mackay_2016,li_melb_2016,li_mitchell_2016,li_newcastle_maitland_2016,li_perth_2016,li_sunshine_coast_2016,li_syd_2016,li_toowoomba_2016,li_townsville_2016,li_western_sydney_2016,li_wollongong_2016) DO (
  git fetch && git checkout %%A
  git pull
  git merge origin/master
  git commit -a -m "merged branch %%A with master"
  git push
)
git fetch && git checkout master
@pause
