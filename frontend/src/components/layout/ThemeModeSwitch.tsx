import clsx from 'clsx';

import { useTheme, type ThemePreference } from '../../features/theme/state';

const options: Array<{ value: ThemePreference; label: string }> = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' }
];

export function ThemeModeSwitch() {
  const { preference, setPreference } = useTheme();

  return (
    <div className="theme-mode-switch" role="group" aria-label="Theme mode">
      {options.map((option) => (
        <button
          key={option.value}
          className={clsx(
            'theme-mode-switch__item',
            preference === option.value && 'theme-mode-switch__item--active'
          )}
          onClick={() => setPreference(option.value)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
