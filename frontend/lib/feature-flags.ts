const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);

function readBool(value: string | undefined, defaultValue = false): boolean {
  if (!value) {
    return defaultValue;
  }
  return TRUE_VALUES.has(value.trim().toLowerCase());
}

export function readDashboardV3ExplainFlag(): boolean {
  return readBool(process.env.NEXT_PUBLIC_DASHBOARD_V3_EXPLAIN, false);
}
