import React, { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { requestTrustConfig } from '../services/trustConfigClient';
import { strategyLabel, tendencyLabels } from '../types/trustConfig';
import type { TrustDisplayPolicy, TrustFileConfig, TrustTendency } from '../types/trustConfig';
import './TrustConfigSettings.css';

export default function TrustConfigSettings({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<TrustFileConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('正在读取配置…');
  const [error, setError] = useState('');
  useEffect(() => {
    dialog.current?.showModal();
    let alive = true;
    requestTrustConfig().then(value => {
      if (alive) { setDraft(value); setStatus('修改保存后立即生效。'); }
    }).catch(reason => { if (alive) { setError(String(reason.message)); setStatus(''); } });
    return () => { alive = false; };
  }, []);
  const policy = draft?.policies[draft.tendency];
  const change = (patch: Partial<TrustDisplayPolicy>) => {
    if (!draft || !policy) return;
    setDraft({ ...draft, policies: { ...draft.policies, [draft.tendency]: { ...policy, ...patch } } });
    setStatus('有未保存修改');
    setError('');
  };
  const save = async () => {
    if (!draft) return;
    setBusy(true); setError(''); setStatus('正在保存…');
    try {
      await requestTrustConfig(draft);
      toast.success('已保存，已立即生效');
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败'); setStatus('修改尚未确认保存');
    } finally { setBusy(false); }
  };
  return (
    <dialog ref={dialog} className="trust-config-dialog" aria-labelledby="trust-config-title"
      onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
      <h2 id="trust-config-title">信任调控设置</h2>
      <p className="trust-config-intro">按信任倾向配置显示内容与呈现方式</p>
      {draft && policy && <>
        <label className="trust-config-select">信任倾向
          <select value={draft.tendency} disabled={busy} onChange={event => {
            setDraft({ ...draft, tendency: event.target.value as TrustTendency });
            setStatus('有未保存修改'); setError('');
          }}>
            {Object.entries(tendencyLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <fieldset disabled={busy}>
          <legend>信息内容调控 <small>显示什么</small></legend>
          <label><input type="checkbox" checked={policy.show_evidence}
            onChange={event => change({ show_evidence: event.target.checked })} />显示补充观测依据</label>
          <label><input type="checkbox" checked={policy.show_reliability}
            onChange={event => change({ show_reliability: event.target.checked })} />显示可靠性说明</label>
        </fieldset>
        <fieldset disabled={busy}>
          <legend>呈现形式调控 <small>怎么显示</small></legend>
          <label className="trust-config-select">高亮区域
            <select value={policy.highlight} onChange={event => change({ highlight: event.target.value as TrustDisplayPolicy['highlight'] })}>
              <option value="none">无</option><option value="observation">观测信息区</option>
              <option value="reliability">可靠性信息区</option>
            </select>
          </label>
          <p className="trust-config-help">只强调已有区域，不自动增加内容。</p>
        </fieldset>
        <p className="trust-config-classification">策略类型 <strong>{strategyLabel(policy)}</strong></p>
      </>}
      <p role="status" className="trust-config-status">{status}</p>
      {error && <p role="alert" className="trust-config-error">{error}</p>}
      <footer><button type="button" disabled={busy} onClick={onClose}>取消</button>
        <button type="button" className="trust-config-save" disabled={!draft || busy} onClick={save}>保存</button></footer>
    </dialog>
  );
}
