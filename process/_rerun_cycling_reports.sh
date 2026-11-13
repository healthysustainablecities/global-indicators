#!/bin/bash
# Regenerate the cycling validation report for every city with a live study region
# database.  DarEsSalaamCustom is deliberately absent: its database no longer exists,
# so it cannot be re-run, and it has been withdrawn from the validation site.
export PATH=/env/bin:$PATH
cd /home/ghsci/process || exit 1

LOGDIR=/home/ghsci/process/_rerun_logs
mkdir -p "$LOGDIR"

# Updated 2026-09-13: every region is restricted to the urban portion of its administrative
# boundary using the shared GHSL UCDB R2024A urban centres (urban_intersection: true), so
# Minneapolis runs from Minneapolis.yml (MSA boundary) and Minneapolis-Urban is superseded;
# the metropolitan MexicoCity configuration is absent (MexicoCityProper carries Mexico City).
# HelsinkiOsmDefault is a sensitivity configuration that is not published on the site.
# DarEsSalaamCustom is absent pending confirmation that it is still wanted.
CITIES=(
  "data/Cycling/Würzburg/Würzburg"
  "data/Cycling/Turin/Turin"
  "data/Cycling/Suzhou/Suzhou"
  "data/Cycling/Curitiba/Curitiba"
  "data/Cycling/Chennai/Chennai"
  "data/Cycling/Barcelona/Barcelona"
  "data/Cycling/Tarragona/Tarragona"
  "data/Cycling/Valencia/Valencia"
  "data/Cycling/Helsinki/Helsinki"
  "data/Cycling/MexicoCity/MexicoCityProper"
  "data/Cycling/Melbourne/Melbourne"
  "data/Cycling/Minneapolis/Minneapolis"
  "data/Cycling/Dar es Salaam/DarEsSalaam"
)

overall=0
for codename in "${CITIES[@]}"; do
  name=$(basename "$codename")
  log="$LOGDIR/${name}_report.log"
  echo "=== $name report : $(date -u +%H:%M:%S) ==="
  if /env/bin/python subprocesses/_cycling_validation_report.py "$codename" > "$log" 2>&1; then
    echo "    report OK"
  else
    echo "    report FAILED (see $log)"
    tail -5 "$log"
    overall=1
  fi
done

echo "REPORTS DONE (overall_status=$overall)"
exit $overall
