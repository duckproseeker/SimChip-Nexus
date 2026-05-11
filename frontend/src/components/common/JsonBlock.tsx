interface JsonBlockProps {
  value: unknown;
  compact?: boolean;
}

export function JsonBlock({ value, compact = false }: JsonBlockProps) {
  return <pre className={compact ? 'json-block json-block--compact' : 'json-block'}>{JSON.stringify(value, null, 2)}</pre>;
}
