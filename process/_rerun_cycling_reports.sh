#!/bin/bash
# Regenerate the cycling validation report for every city with a live study region
# database.  DarEsSalaamCustom is deliberately absent: its database no longer exists,
# so it cannot be re-run, and it has been withdrawn from the validation site.
export PATH=/env/bin:$PATH
cd /home/ghsci/process || exit 1

LOGDIR=/home/ghsci/process/_rerun_logs
mkdir -p "$LOGDIR"

CITIES=(
  "data/Cycling/Würzburg/Würzburg"
  "data/Cycling/Dar es Salaam/DarEsSalaam"
  "data/Cycling/Helsinki/Helsinki"
  "data/Cycling/Helsinki/HelsinkiOsmDefault"
  "data/Cycling/Melbourne/Melbourne"
  "data/Cycling/MexicoCity/MexicoCity"
  "data/Cycling/MexicoCity/MexicoCityProper"
  "data/Cycling/Minneapolis/Minneapolis"
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
