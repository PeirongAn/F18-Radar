import { describe, expect, it } from 'vitest';
import { hasAuthoritativeRadarTaskIdentity } from './radarTaskIdentity';

describe('hasAuthoritativeRadarTaskIdentity', () => {
  it('rejects the temporary client task id before init_settings arrives', () => {
    expect(hasAuthoritativeRadarTaskIdentity(1723456789000, null)).toBe(false);
  });

  it('rejects a temporary id that differs from the server task id', () => {
    expect(hasAuthoritativeRadarTaskIdentity(1723456789000, { __task_id: 42 })).toBe(false);
  });

  it('accepts the server task id after init_settings is applied', () => {
    expect(hasAuthoritativeRadarTaskIdentity(42, { __task_id: '42' })).toBe(true);
  });
});
