import { useEffect, useRef } from 'react';
import type { TrustTrialSnapshot } from '../types/trustControl';

export type TrustTrialUpdateHandler = (snapshot: TrustTrialSnapshot | null) => void;

/**
 * A snapshot contains arrays and nested objects that can be recreated while
 * MobX/React is rendering even when their observable content is unchanged.
 * Publishing by object identity would feed that render back into the parent
 * forever.  Use a content signature so only a real trial-state change is sent.
 */
export const getTrustTrialSnapshotSignature = (
  snapshot: TrustTrialSnapshot | null,
): string => JSON.stringify(snapshot);

export function useTrustTrialPublisher(
  snapshot: TrustTrialSnapshot | null,
  onUpdate?: TrustTrialUpdateHandler,
) {
  const onUpdateRef = useRef(onUpdate);
  const publishedSignatureRef = useRef<string | null>(null);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  useEffect(() => {
    const signature = getTrustTrialSnapshotSignature(snapshot);
    if (publishedSignatureRef.current === signature) return;

    publishedSignatureRef.current = signature;
    onUpdateRef.current?.(snapshot);
  }, [snapshot]);

  // Clear the parent only when this publisher is actually unmounted.  Doing
  // this in the snapshot effect cleanup inserts an extra parent update before
  // every publication and is the core of the maximum-update-depth loop.
  useEffect(() => () => {
    onUpdateRef.current?.(null);
  }, []);
}
