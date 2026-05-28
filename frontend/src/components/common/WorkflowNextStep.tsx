import { useWorkflowSelection } from '../../features/workflow/state';

/**
 * WorkflowNextStep renders contextual next-action hints based on the
 * current workflow selection state. Placed at the bottom of workflow pages.
 */
export function WorkflowNextStep() {
  const workflow = useWorkflowSelection();

  // Only render when there is meaningful context to show
  if (!workflow.projectId && !workflow.benchmarkDefinitionId) {
    return null;
  }

  return (
    <div className="workflow-next-step" aria-live="polite">
      {/* Placeholder: future contextual guidance */}
    </div>
  );
}
