export type TrustTendency = 'under_trust' | 'normal' | 'over_trust';
export interface TrustDisplayPolicy {
  show_evidence: boolean;
  show_reliability: boolean;
  highlight: 'none' | 'observation' | 'reliability';
}
export interface TrustFileConfig {
  tendency: TrustTendency;
  policies: Record<TrustTendency, TrustDisplayPolicy>;
}
export interface TrustDisplayConfig {
  tendency: TrustTendency;
  source: 'config' | 'fallback';
  valid: boolean;
  reason?: string;
  policy: TrustDisplayPolicy;
}
export const tendencyLabels: Record<TrustTendency, string> = {
  under_trust: '欠信任', normal: '正常', over_trust: '过信任',
};
export function strategyLabel(policy: TrustDisplayPolicy): string {
  const content = policy.show_evidence || policy.show_reliability;
  const form = policy.highlight !== 'none';
  return content ? (form ? '联合调控' : '内容调控') : (form ? '形式调控' : '基础显示');
}
