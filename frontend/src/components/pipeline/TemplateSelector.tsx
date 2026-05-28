import { TEMPLATES, type PipelineTemplate } from '../../features/pipeline/templates';

interface Props {
  onSelect: (template: PipelineTemplate) => void;
  onClose: () => void;
}

export function TemplateSelector({ onSelect, onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-zinc-800 rounded-xl p-6 w-[500px] max-h-[80vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-100 mb-4">选择模板</h2>
        <div className="grid gap-3">
          {TEMPLATES.map((t) => (
            <button
              key={t.id}
              onClick={() => { onSelect(t); onClose(); }}
              className="text-left p-4 rounded-lg border border-zinc-200 dark:border-zinc-600 hover:border-blue-400 transition-colors"
            >
              <div className="font-medium text-zinc-800 dark:text-zinc-100">{t.name}</div>
              <div className="text-xs text-zinc-400 mt-1">{t.description}</div>
            </button>
          ))}
        </div>
        <button onClick={onClose} className="mt-4 text-sm text-zinc-400 hover:text-zinc-600">取消</button>
      </div>
    </div>
  );
}
