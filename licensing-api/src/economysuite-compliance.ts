export const ECONOMYSUITE_POLICY_VERSIONS = {
  privacy: '2026-10-06',
  purchase: '2026-10-06',
  refund: '2026-10-06',
  delivery: '2026-10-06',
} as const;

export const ECONOMYSUITE_POLICY_URLS = {
  purchase: 'https://tomaspisar.cz/legal/economysuite-purchases/',
  refund: 'https://tomaspisar.cz/legal/refunds/',
  privacy: 'https://tomaspisar.cz/legal/privacy/',
} as const;

export function policyVersionsMatch(value: unknown): boolean {
  const candidate = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  return candidate.privacy === ECONOMYSUITE_POLICY_VERSIONS.privacy
    && candidate.purchase === ECONOMYSUITE_POLICY_VERSIONS.purchase
    && candidate.refund === ECONOMYSUITE_POLICY_VERSIONS.refund
    && candidate.delivery === ECONOMYSUITE_POLICY_VERSIONS.delivery;
}
