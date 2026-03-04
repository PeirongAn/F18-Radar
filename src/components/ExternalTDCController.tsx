import React, { useCallback, useEffect } from 'react';
import useExternalTDCControl, { TDCCoordinateMessage } from '../hooks/useExternalTDCControl';

interface ExternalTDCControllerProps {
  onTDCUpdate?: (coordinate: TDCCoordinateMessage) => void;
  wsUrl?: string;
  enabled?: boolean;
}

/**
 * 外部TDC控制器组件
 * 处理来自8765端口的外部设备TDC控制
 */
const ExternalTDCController: React.FC<ExternalTDCControllerProps> = ({
  onTDCUpdate,
  wsUrl, // 可选，如果不提供则从配置文件读取
  enabled = true
}) => {
  
  // TDC坐标更新处理函数
  const handleTDCUpdate = useCallback((coordinate: TDCCoordinateMessage) => {
    console.log('[ExternalTDCController] 收到TDC坐标更新:', coordinate);
    
    // 调用父组件的回调
    if (onTDCUpdate) {
      onTDCUpdate(coordinate);
    }
  }, [onTDCUpdate]);

  // 使用外部TDC控制hook
  const {
    connected,
    error,
    lastTDCCoordinate,
    messageCount,
    connectionAttempts,
    connect,
    disconnect,
    setChangeThreshold,
    sendTestMessage,
    changeThreshold,
    configLoaded,
    wsUrl: actualWsUrl
  } = useExternalTDCControl(wsUrl, undefined, handleTDCUpdate);

  // 根据enabled状态控制连接
  useEffect(() => {
    if (enabled && !connected && !error) {
      connect();
    } else if (!enabled && connected) {
      disconnect();
    }
  }, [enabled, connected, error, connect, disconnect]);

  // 测试函数
  const handleTestClick = useCallback(() => {
    const testCoordinates: [number, number][] = [
      [0, 0],      // 中心
      [0.5, 0.3],  // 右上
      [-0.5, -0.3], // 左下
      [1, 1],      // 右上角
      [-1, -1],    // 左下角
      [0, 0]       // 回到中心
    ];

    testCoordinates.forEach((coord, index) => {
      setTimeout(() => {
        sendTestMessage(coord);
      }, index * 1000);
    });
  }, [sendTestMessage]);

  if (!enabled) {
    return (
      <div className="external-tdc-controller disabled">
        <h3>🎮 外部TDC控制器</h3>
        <p>已禁用</p>
      </div>
    );
  }

  return (
    <div className="external-tdc-controller">
      <h3>🎮 外部TDC控制器</h3>
      
      {/* 配置加载状态 */}
      {!configLoaded && (
        <div className="loading-status">
          ⏳ 正在加载配置...
        </div>
      )}
      
      {/* 连接状态 */}
      <div className="connection-status">
        <div className={`status-indicator ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '🟢 已连接' : '🔴 未连接'}
        </div>
        <div className="connection-info">
          <span>服务地址: {actualWsUrl}</span>
          <span>连接尝试: {connectionAttempts}</span>
          {configLoaded && <span>✅ 配置已加载</span>}
        </div>
      </div>

      {/* 错误信息 */}
      {error && (
        <div className="error-message">
          ❌ 错误: {error}
        </div>
      )}

      {/* 统计信息 */}
      <div className="statistics">
        <div>📊 消息计数: {messageCount}</div>
        <div>🎯 变化阈值: {changeThreshold.toFixed(6)}</div>
      </div>

      {/* 最后的TDC坐标 */}
      {lastTDCCoordinate && (
        <div className="last-coordinate">
          <h4>📍 最后坐标:</h4>
          <div>X: {lastTDCCoordinate.x.toFixed(6)}</div>
          <div>Y: {lastTDCCoordinate.y.toFixed(6)}</div>
          <div>时间: {new Date(lastTDCCoordinate.timestamp).toLocaleTimeString()}</div>
          <div>来源: {lastTDCCoordinate.source}</div>
        </div>
      )}

      {/* 控制按钮 */}
      <div className="controls">
        <button onClick={connect} disabled={connected}>
          🔌 连接
        </button>
        <button onClick={disconnect} disabled={!connected}>
          🔌 断开
        </button>
        <button onClick={handleTestClick} disabled={!connected}>
          🧪 测试序列
        </button>
      </div>

      {/* 阈值调整 */}
      <div className="threshold-control">
        <label>变化检测阈值:</label>
        <input
          type="range"
          min="0.0001"
          max="0.01"
          step="0.0001"
          value={changeThreshold}
          onChange={(e) => setChangeThreshold(parseFloat(e.target.value))}
        />
        <span>{changeThreshold.toFixed(6)}</span>
      </div>

      <style>{`
        .external-tdc-controller {
          border: 1px solid #ccc;
          border-radius: 8px;
          padding: 16px;
          margin: 16px 0;
          background: #f9f9f9;
          font-family: monospace;
        }

        .external-tdc-controller.disabled {
          opacity: 0.6;
          background: #e0e0e0;
        }

        .connection-status {
          display: flex;
          align-items: center;
          gap: 16px;
          margin-bottom: 12px;
        }

        .status-indicator.connected {
          color: green;
          font-weight: bold;
        }

        .status-indicator.disconnected {
          color: red;
          font-weight: bold;
        }

        .connection-info {
          display: flex;
          flex-direction: column;
          font-size: 12px;
          color: #666;
        }

        .error-message {
          background: #ffebee;
          color: #c62828;
          padding: 8px;
          border-radius: 4px;
          margin-bottom: 12px;
        }

        .statistics {
          display: flex;
          gap: 16px;
          margin-bottom: 12px;
          font-size: 14px;
        }

        .last-coordinate {
          background: #e8f5e8;
          padding: 12px;
          border-radius: 4px;
          margin-bottom: 12px;
        }

        .last-coordinate h4 {
          margin: 0 0 8px 0;
        }

        .last-coordinate div {
          margin: 4px 0;
          font-size: 14px;
        }

        .controls {
          display: flex;
          gap: 8px;
          margin-bottom: 12px;
        }

        .controls button {
          padding: 8px 16px;
          border: 1px solid #ccc;
          border-radius: 4px;
          background: white;
          cursor: pointer;
        }

        .controls button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .controls button:hover:not(:disabled) {
          background: #f0f0f0;
        }

        .threshold-control {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
        }

        .threshold-control input {
          flex: 1;
        }
      `}</style>
    </div>
  );
};

export default ExternalTDCController;
