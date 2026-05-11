from __future__ import annotations

from pathlib import Path

from app.scenario.native_xosc import build_native_descriptor_plan, load_native_xosc_plan
from app.scenario.validators import validate_descriptor


def test_build_native_descriptor_plan_uses_tm_autopilot_defaults() -> None:
    descriptor = validate_descriptor(
        {
            "version": 1,
            "scenario_name": "town10_autonomous_demo",
            "map_name": "Town10HD_Opt",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": False, "fixed_delta_seconds": 1.0 / 30.0},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.5,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
            "sensors": {"enabled": False},
            "termination": {"timeout_seconds": 12, "success_condition": "timeout"},
            "recorder": {"enabled": False},
            "metadata": {"author": "test", "tags": [], "description": "descriptor"},
        }
    )

    plan = build_native_descriptor_plan(descriptor, target_speed_mps=7.5)

    assert plan.map_name == "Town10HD_Opt"
    assert len(plan.entities) == 1
    hero = plan.entities[0]
    assert hero.entity_ref == "hero"
    assert hero.is_ego is True
    assert hero.init_actions[0].kind == "autopilot"
    assert hero.init_actions[0].target_speed_mps == 7.5
    assert plan.stop_trigger.condition_groups[0][0].kind == "simulation_time"
    assert plan.stop_trigger.condition_groups[0][0].value == 12.0


def test_build_native_descriptor_plan_allows_manual_stop_only_demo_runs() -> None:
    descriptor = validate_descriptor(
        {
            "version": 1,
            "scenario_name": "town10_autonomous_demo",
            "map_name": "Town10HD_Opt",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": False, "fixed_delta_seconds": 1.0 / 30.0},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.5,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
            "sensors": {"enabled": False},
            "termination": {"timeout_seconds": 86400, "success_condition": "manual_stop"},
            "recorder": {"enabled": False},
            "metadata": {"author": "test", "tags": [], "description": "descriptor"},
        }
    )

    plan = build_native_descriptor_plan(descriptor, target_speed_mps=7.5)

    assert plan.stop_trigger.is_empty is True


def test_load_native_xosc_plan_extracts_entities_actions_and_triggers(tmp_path: Path) -> None:
    xosc_path = tmp_path / "follow_leading_vehicle.xosc"
    xosc_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                "<OpenSCENARIO>",
                '  <RoadNetwork><LogicFile filepath="Town01"/></RoadNetwork>',
                "  <Entities>",
                '    <ScenarioObject name="hero"><Vehicle name="vehicle.lincoln.mkz_2017" vehicleCategory="car"/></ScenarioObject>',
                '    <ScenarioObject name="adversary"><Vehicle name="vehicle.tesla.model3" vehicleCategory="car"/></ScenarioObject>',
                "  </Entities>",
                "  <Storyboard>",
                "    <Init>",
                "      <Actions>",
                '        <Private entityRef="hero">',
                "          <PrivateAction>",
                "            <TeleportAction>",
                "              <Position>",
                '                <WorldPosition x="10.0" y="20.0" z="0.5" h="90.0" p="0.0" r="0.0"/>',
                "              </Position>",
                "            </TeleportAction>",
                "          </PrivateAction>",
                "          <PrivateAction>",
                "            <ControllerAction>",
                "              <AssignControllerAction>",
                '                <Controller name="DuckParkAutoPilot_hero">',
                "                  <Properties>",
                '                    <Property name="target_speed_mps" value="8.0"/>',
                "                  </Properties>",
                "                </Controller>",
                "              </AssignControllerAction>",
                "            </ControllerAction>",
                "          </PrivateAction>",
                "        </Private>",
                '        <Private entityRef="adversary">',
                "          <PrivateAction>",
                "            <TeleportAction>",
                "              <Position>",
                '                <WorldPosition x="30.0" y="20.0" z="0.5" h="90.0" p="0.0" r="0.0"/>',
                "              </Position>",
                "            </TeleportAction>",
                "          </PrivateAction>",
                "        </Private>",
                "      </Actions>",
                "    </Init>",
                '    <Story name="Story">',
                '      <Act name="Act">',
                '        <ManeuverGroup maximumExecutionCount="1">',
                '          <Actors selectTriggeringEntities="false">',
                '            <EntityRef entityRef="adversary"/>',
                "          </Actors>",
                '          <Maneuver name="Maneuver">',
                '            <Event name="LeadingVehicleKeepsVelocity" priority="overwrite">',
                '              <Action name="LeadingVehicleKeepsVelocity">',
                "                <PrivateAction>",
                "                  <LongitudinalAction>",
                "                    <SpeedAction>",
                "                      <SpeedActionTarget>",
                '                        <AbsoluteTargetSpeed value="5.5"/>',
                "                      </SpeedActionTarget>",
                "                    </SpeedAction>",
                "                  </LongitudinalAction>",
                "                </PrivateAction>",
                "              </Action>",
                "              <StartTrigger>",
                "                <ConditionGroup>",
                '                  <Condition name="StartCondition" delay="0" conditionEdge="rising">',
                "                    <ByValueCondition>",
                '                      <SimulationTimeCondition value="1.0" rule="greaterThan"/>',
                "                    </ByValueCondition>",
                "                  </Condition>",
                "                </ConditionGroup>",
                "              </StartTrigger>",
                "            </Event>",
                "          </Maneuver>",
                "        </ManeuverGroup>",
                "        <StopTrigger>",
                "          <ConditionGroup>",
                '            <Condition name="EndCondition" delay="0" conditionEdge="rising">',
                "              <ByEntityCondition>",
                '                <TriggeringEntities triggeringEntitiesRule="any">',
                '                  <EntityRef entityRef="hero"/>',
                "                </TriggeringEntities>",
                "                <EntityCondition>",
                '                  <TraveledDistanceCondition value="200.0"/>',
                "                </EntityCondition>",
                "              </ByEntityCondition>",
                "            </Condition>",
                "          </ConditionGroup>",
                "        </StopTrigger>",
                "      </Act>",
                "    </Story>",
                "  </Storyboard>",
                "</OpenSCENARIO>",
            ]
        ),
        encoding="utf-8",
    )

    plan = load_native_xosc_plan(xosc_path, fallback_timeout_seconds=45)

    assert plan.map_name == "Town01"
    assert len(plan.entities) == 2
    hero = next(item for item in plan.entities if item.entity_ref == "hero")
    adversary = next(item for item in plan.entities if item.entity_ref == "adversary")
    assert hero.spawn_point is not None
    assert hero.spawn_point["x"] == 10.0
    assert hero.init_actions[0].kind == "autopilot"
    assert hero.init_actions[0].target_speed_mps == 8.0
    assert adversary.spawn_point is not None
    assert plan.events[0].name == "LeadingVehicleKeepsVelocity"
    assert plan.events[0].actions[0].kind == "keep_velocity"
    assert plan.events[0].actions[0].target_speed_mps == 5.5
    assert plan.events[0].start_trigger.condition_groups[0][0].kind == "simulation_time"
    assert plan.stop_trigger.condition_groups[0][0].kind == "traveled_distance"
