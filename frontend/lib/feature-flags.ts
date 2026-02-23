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

export function readEvidenceLayerFlag(): boolean {
  return readBool(process.env.NEXT_PUBLIC_ENABLE_STOCK_EVIDENCE_LAYER, false);
}

export function readTransmissionLayerFlag(): boolean {
  return readBool(process.env.NEXT_PUBLIC_ENABLE_STOCK_TRANSMISSION_LAYER, false);
}

export function readAiDebateViewFlag(): boolean {
  return readBool(process.env.NEXT_PUBLIC_ENABLE_STOCK_AI_DEBATE_VIEW, false);
}
