#!/usr/bin/env bash
set -euo pipefail

# Record a scenario using ScenarioRunner with --waitForEgo
# Usage: ./record_scenario.sh <scenario_file> [output_dir]
#
# Example:
#   ./record_scenario.sh PedestrianCrossingFront.xosc
#   ./record_scenario.sh CutIn.xml
#
# Then in another terminal, launch manual_control.py to drive the ego.

SCENARIO="${1:?Usage: $0 <scenario_file> [output_dir]}"
OUTPUT_DIR="${2:-/ros2_ws/recordings}"
HOST="${CARLA_HOST:-localhost}"
PORT="${CARLA_PORT:-2000}"
TM_PORT="${TRAFFIC_MANAGER_PORT:-8010}"
CONTAINER="${CARLA_CONTAINER:-ros2-dev}"

SCENARIO_DIR="/ros2_ws/carla_workspace/scenario_runner/srunner/examples"

# Resolve scenario path
if [[ "$SCENARIO" == /* ]]; then
  SCENARIO_PATH="$SCENARIO"
elif [[ "$SCENARIO" == *.xosc ]] || [[ "$SCENARIO" == *.xml ]]; then
  SCENARIO_PATH="${SCENARIO_DIR}/${SCENARIO}"
else
  # Try .xosc first, then .xml
  if docker exec "$CONTAINER" test -f "${SCENARIO_DIR}/${SCENARIO}.xosc"; then
    SCENARIO_PATH="${SCENARIO_DIR}/${SCENARIO}.xosc"
  else
    SCENARIO_PATH="${SCENARIO_DIR}/${SCENARIO}.xml"
  fi
fi

# Determine flag
if [[ "$SCENARIO_PATH" == *.xosc ]]; then
  SCENARIO_FLAG="--openscenario"
else
  SCENARIO_FLAG="--scenario"
  # Extract scenario type name from XML
  SCENARIO_NAME=$(docker exec "$CONTAINER" python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('${SCENARIO_PATH}')
name = tree.find('.//scenario').get('name', '')
print(name)
" 2>/dev/null || basename "$SCENARIO_PATH" .xml)
  SCENARIO_PATH="$SCENARIO_NAME"
fi

echo "=== CARLA Scenario Recorder ==="
echo "Scenario: $SCENARIO_PATH"
echo "Output:   $OUTPUT_DIR"
echo "Host:     $HOST:$PORT"
echo ""
echo "Waiting for ego vehicle (launch manual_control.py in another terminal):"
echo "  docker exec -e DISPLAY=:1 $CONTAINER python3 \\"
echo "    /ros2_ws/carla_workspace/scenario_runner/manual_control.py \\"
echo "    --host $HOST --port $PORT --rolename hero"
echo ""

docker exec "$CONTAINER" mkdir -p "$OUTPUT_DIR"

docker exec "$CONTAINER" bash -c "
export PYTHONPATH=/ros2_ws/carla_workspace/carla:/ros2_ws/carla_workspace/scenario_runner:\$PYTHONPATH
cd /ros2_ws/carla_workspace/scenario_runner
python3 scenario_runner.py \
  --host $HOST --port $PORT \
  $SCENARIO_FLAG $SCENARIO_PATH \
  --waitForEgo \
  --record $OUTPUT_DIR \
  --trafficManagerPort $TM_PORT \
  --sync \
  --timeout 120
"
