import { useState } from 'react';

const STEPS = [
  { title: '选择场景', description: '从场景库选择一段录制作为数据源' },
  { title: '添加传感器', description: '拖拽传感器节点并连接到场景' },
  { title: '配置输出', description: '添加输出节点，配置推流地址和格式' },
  { title: '运行', description: '点击运行按钮启动数据生成' },
];

interface Props {
  onDismiss: () => void;
}

export function GuidedTour({ onDismiss }: Props) {
  const [step, setStep] = useState(0);
  const current = STEPS[step];

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-white dark:bg-zinc-800 rounded-xl shadow-xl border border-zinc-200 dark:border-zinc-700 p-4 w-[360px] z-50">
      <div className="flex justify-between items-start mb-2">
        <span className="text-xs text-blue-500 font-medium">步骤 {step + 1}/{STEPS.length}</span>
        <button onClick={onDismiss} className="text-xs text-zinc-400 hover:text-zinc-600">跳过</button>
      </div>
      <h4 className="font-medium text-zinc-800 dark:text-zinc-100">{current.title}</h4>
      <p className="text-sm text-zinc-500 mt-1">{current.description}</p>
      <div className="flex justify-end mt-3 gap-2">
        {step > 0 && (
          <button onClick={() => setStep(step - 1)} className="text-sm text-zinc-500">上一步</button>
        )}
        {step < STEPS.length - 1 ? (
          <button onClick={() => setStep(step + 1)} className="text-sm text-blue-600 font-medium">下一步</button>
        ) : (
          <button onClick={onDismiss} className="text-sm text-blue-600 font-medium">完成</button>
        )}
      </div>
    </div>
  );
}
