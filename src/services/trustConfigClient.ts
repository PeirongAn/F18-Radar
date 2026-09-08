import { globalWS } from '../hooks/useRadarData';
import type { TrustFileConfig } from '../types/trustConfig';

export function requestTrustConfig(config?: TrustFileConfig): Promise<TrustFileConfig> {
  if (!globalWS.isOpen()) return Promise.reject(new Error('后端未连接，请连接后重新打开设置'));
  return new Promise((resolve, reject) => {
    const requestId = crypto.randomUUID();
    let unsubscribe = () => {};
    const finish = (error?: string, result?: TrustFileConfig) => {
      clearTimeout(timer);
      unsubscribe();
      if (error) reject(new Error(error));
      else if (result) resolve(result);
    };
    const timer = window.setTimeout(() => finish('请求超时，请重新打开设置核对是否保存成功'), 10000);
    unsubscribe = globalWS.subscribe(state => {
      if (!state.connected) { finish('连接已断开，请重新打开设置核对配置'); return; }
      const message = globalWS.getLastMessage();
      if (message?.type !== 'trust_config_result' || message.request_id !== requestId) return;
      if (!message.ok || !message.config) finish(message.error || '配置请求失败');
      else finish(undefined, message.config as TrustFileConfig);
    });
    if (!globalWS.sendMessage({ type: config ? 'trust_config_save' : 'trust_config_get',
      request_id: requestId, ...(config ? { config } : {}) })) finish('配置未发送，后端未连接');
  });
}
