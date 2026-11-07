#!/usr/bin/env bash
# Download Synthea (open-source synthetic patient generator, MITRE) and
# generate synthetic adult patients as FHIR bundles.
# Output: data/synthea/fhir/*.json  (gitignored)
set -euo pipefail
cd "$(dirname "$0")/.."

JAVA="${JAVA:-/opt/homebrew/opt/openjdk@17/bin/java}"
JAR=vendor/synthea-with-dependencies.jar
URL=https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar
POPULATION="${POPULATION:-450}"
SEED="${SEED:-42}"

mkdir -p vendor data/synthea
[ -f "$JAR" ] || curl -sSL -o "$JAR" "$URL"

"$JAVA" -jar "$JAR" -p "$POPULATION" -s "$SEED" -cs "$SEED" -a 45-90 Missouri \
  --exporter.baseDirectory=data/synthea \
  --exporter.fhir.export=true \
  --exporter.hospital.fhir.export=false \
  --exporter.practitioner.fhir.export=false \
  --exporter.csv.export=false \
  --generate.only_alive_patients=true

echo "Synthea patients: $(ls data/synthea/fhir/*.json | wc -l)"
