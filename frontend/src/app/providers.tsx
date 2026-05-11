import type { PropsWithChildren } from 'react';

import { QueryClientProvider } from '@tanstack/react-query';

import { ThemeProvider } from '../features/theme/state';
import { queryClient } from './queryClient';

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}
