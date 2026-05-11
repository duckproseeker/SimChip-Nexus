import type { components, paths } from './openapi';

type Schema<Name extends keyof components['schemas']> = components['schemas'][Name];
type HttpMethod<Path extends keyof paths> = Exclude<keyof paths[Path], 'parameters'>;
type JsonRequestBody<
  Path extends keyof paths,
  Method extends HttpMethod<Path>
> = paths[Path][Method] extends {
  requestBody: {
    content: {
      'application/json': infer Body;
    };
  };
}
  ? Body
  : never;
type JsonResponseBody<
  Path extends keyof paths,
  Method extends HttpMethod<Path>
> = paths[Path][Method] extends {
  responses: {
    200: {
      content: {
        'application/json': infer Body;
      };
    };
  };
}
  ? Body
  : never;
type JsonResponseData<
  Path extends keyof paths,
  Method extends HttpMethod<Path>
> = JsonResponseBody<Path, Method> extends { data?: infer Data }
  ? NonNullable<Data>
  : never;

export type HilConfigPayloadSchema = Schema<'HilConfigPayload'>;
export type EvaluationProfilePayloadSchema = Schema<'EvaluationProfilePayload'>;
export type CreateRunPayloadSchema = JsonRequestBody<'/runs', 'post'>;
export type ScenarioLaunchPayloadSchema = JsonRequestBody<'/scenarios/launch', 'post'>;
export type CreateBenchmarkTaskPayloadSchema = JsonRequestBody<'/benchmark-tasks', 'post'>;
export type CreateCapturePayloadSchema = JsonRequestBody<'/captures', 'post'>;
export type RunEnvironmentUpdatePayloadSchema = JsonRequestBody<'/runs/{run_id}/environment', 'post'>;
export type ReportExportPayloadSchema = JsonRequestBody<'/reports/export', 'post'>;
export type RerunBenchmarkTaskPayloadSchema = JsonRequestBody<'/benchmark-tasks/{benchmark_task_id}/rerun', 'post'>;

export type RunCreateResponseSchema = JsonResponseData<'/runs', 'post'>;
export type RunRecordSchema = JsonResponseData<'/runs/{run_id}', 'get'>;
export type RunListSchema = JsonResponseData<'/runs', 'get'>;
export type RunEventSchema = JsonResponseData<'/runs/{run_id}/events', 'get'> extends Array<infer Item>
  ? Item
  : never;
export type RunEnvironmentStateSchema = JsonResponseData<'/runs/{run_id}/environment', 'get'>;
export type RunViewerInfoSchema = JsonResponseData<'/runs/{run_id}/viewer', 'get'>;

export type BenchmarkDefinitionSchema = JsonResponseData<
  '/benchmark-definitions/{benchmark_definition_id}',
  'get'
>;
export type BenchmarkDefinitionListSchema = JsonResponseData<'/benchmark-definitions', 'get'>;
export type BenchmarkTaskSchema = JsonResponseData<'/benchmark-tasks/{benchmark_task_id}', 'get'>;
export type BenchmarkTaskListSchema = JsonResponseData<'/benchmark-tasks', 'get'>;

export type ReportSchema = JsonResponseData<'/reports/{report_id}', 'get'>;
export type ReportListSchema = JsonResponseData<'/reports', 'get'>;
export type ReportsWorkspaceSchema = JsonResponseData<'/reports/workspace', 'get'>;
