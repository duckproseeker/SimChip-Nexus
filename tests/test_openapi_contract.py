from __future__ import annotations

from app.api.main import app


def test_openapi_exposes_request_models_for_contract_generation() -> None:
    schema = app.openapi()
    components = schema["components"]["schemas"]

    expected_models = {
        "CreateBenchmarkTaskRequest",
        "CreateCaptureRequest",
        "CreateRunRequest",
        "EvaluationProfilePayload",
        "HilConfigPayload",
        "ReportExportRequest",
        "RerunBenchmarkTaskRequest",
        "ScenarioLaunchRequest",
        "RunEnvironmentUpdateRequest",
    }

    assert expected_models.issubset(components.keys())


def test_openapi_request_bodies_reference_named_models() -> None:
    schema = app.openapi()

    assert (
        schema["paths"]["/runs"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/CreateRunRequest"
    )
    assert (
        schema["paths"]["/benchmark-tasks"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/CreateBenchmarkTaskRequest"
    )
    assert (
        schema["paths"]["/captures"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/CreateCaptureRequest"
    )
    assert (
        schema["paths"]["/reports/export"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ReportExportRequest"
    )
    assert (
        schema["paths"]["/scenarios/launch"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ScenarioLaunchRequest"
    )
    scenario_launch_request = schema["components"]["schemas"]["ScenarioLaunchRequest"]
    assert "sensor_profile_name" in scenario_launch_request["properties"]
    assert "template_params" in scenario_launch_request["properties"]
    assert scenario_launch_request["properties"]["template_params"]["type"] == "object"


def test_openapi_high_value_responses_use_typed_envelopes() -> None:
    schema = app.openapi()
    expected_refs = {
        ("/runs", "get"): "#/components/schemas/RunListResponse",
        ("/runs/{run_id}", "get"): "#/components/schemas/RunResponse",
        ("/runs/{run_id}/events", "get"): "#/components/schemas/RunEventListResponse",
        ("/runs/{run_id}/environment", "get"): "#/components/schemas/RunEnvironmentStateResponse",
        ("/runs/{run_id}/environment", "post"): "#/components/schemas/RunEnvironmentStateResponse",
        ("/runs/{run_id}/viewer", "get"): "#/components/schemas/RunViewerInfoResponse",
        ("/benchmark-definitions", "get"): "#/components/schemas/BenchmarkDefinitionListResponse",
        ("/benchmark-definitions/{benchmark_definition_id}", "get"): "#/components/schemas/BenchmarkDefinitionResponse",
        ("/benchmark-tasks", "get"): "#/components/schemas/BenchmarkTaskListResponse",
        ("/benchmark-tasks/{benchmark_task_id}", "get"): "#/components/schemas/BenchmarkTaskResponse",
        ("/benchmark-tasks", "post"): "#/components/schemas/BenchmarkTaskResponse",
        ("/reports", "get"): "#/components/schemas/ReportListResponse",
        ("/reports/{report_id}", "get"): "#/components/schemas/ReportResponse",
        ("/reports/export", "post"): "#/components/schemas/ReportResponse",
        ("/reports/workspace", "get"): "#/components/schemas/ReportsWorkspaceResponse",
        ("/scenarios/launch", "post"): "#/components/schemas/RunResponse",
    }

    for (path, method), expected_ref in expected_refs.items():
        assert (
            schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            == expected_ref
        )
