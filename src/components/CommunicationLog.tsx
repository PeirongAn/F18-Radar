import React, { useState, useEffect, useRef, useCallback } from 'react';

export type MessageType = 'info' | 'warning' | 'error' | 'success' | 'client' | 'server' | 'system' 
  | 'sa_init' | 'sa_emergency' | 'sa_threat' | 'sa_missile';

export interface LogMessage {
  id: string;
  type: MessageType;
  content: string;
  timestamp: Date;
}

interface CommunicationLogProps {
  userId?: string;
  isStarted?: boolean; // 系统是否已启动的标志
  taskId?: number | null;
  currentTask?: 'radar' | 'sa'; // 当前任务类型
  messages: LogMessage[];
  onAddMessage?: (type: MessageType, content: string) => void;
  radarRange?: number;
  scanAngle?: number;
  antennaAdjustmentRequired?: boolean;
  targetAntennaElevation?: number;
  initSettings?: any;
  connected?: boolean;
  error?: string | null;
  operations?: any[];
  // SA任务相关状态
  emergencyReceived?: boolean; // 是否收到临机事件
  lastEmergencyType?: string; // 最后一次临机事件类型
  lastEmergencyTime?: Date; // 最后一次临机事件时间
}

const CommunicationLog: React.FC<CommunicationLogProps> = ({ 
  userId, 
  isStarted = false,
  taskId = null,
  currentTask = 'radar',
  messages: incomingMessages,
  onAddMessage: onAddMessageProp,
  radarRange,
  scanAngle,
  antennaAdjustmentRequired = false,
  targetAntennaElevation,
  initSettings,
  connected = false,
  error = null,
  operations = [],
  emergencyReceived,
  lastEmergencyType,
  lastEmergencyTime
}) => {
  const logContainerRef = useRef<HTMLDivElement>(null);
  const prevRangeRef = useRef<number | undefined>(undefined);
  const prevAngleRef = useRef<number | undefined>(undefined);
  const prevAntennaAdjustmentRef = useRef<boolean>(false);
  const initSettingsProcessedRef = useRef<boolean>(false);
  const prevConnectedRef = useRef<boolean>(false);
  
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [incomingMessages]);
  
  useEffect(() => {
    if (isStarted && onAddMessageProp) {
      if (radarRange !== undefined && radarRange !== prevRangeRef.current) {
        // onAddMessageProp('system', `雷达范围已设置为: ${radarRange} 海里`);
        prevRangeRef.current = radarRange;
      }
      
      if (scanAngle !== undefined && scanAngle !== prevAngleRef.current) {
        // onAddMessageProp('system', `扫描角度已设置为: ${scanAngle}°`);
        prevAngleRef.current = scanAngle;
      }
    }
  }, [radarRange, scanAngle, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && initSettings && !initSettingsProcessedRef.current && onAddMessageProp) {
      onAddMessageProp('server', '收到服务器参数设置');
      console.log('initSettings', initSettings);
    
      if (initSettings.range) {
        onAddMessageProp('system', `服务器建议雷达范围: ${initSettings.range} 海里, 扫描角度: ${initSettings.scanAngle}°`);
      }
      initSettingsProcessedRef.current = true;
    }
  }, [initSettings, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && onAddMessageProp) {
      if (antennaAdjustmentRequired && !prevAntennaAdjustmentRef.current) {
        if (targetAntennaElevation !== undefined) {
          onAddMessageProp('system', `需要调整天线${targetAntennaElevation > 0 ? '上移' : '下移'} ${Math.abs(targetAntennaElevation)}格，请使用b/t键进行调整`);
        } else {
          onAddMessageProp('warning', '重置系统');
        }
        prevAntennaAdjustmentRef.current = true;
      } else if (!antennaAdjustmentRequired && prevAntennaAdjustmentRef.current) {
        onAddMessageProp('success', '天线高度已调整到合适位置');
        prevAntennaAdjustmentRef.current = false;
      }
    }
  }, [antennaAdjustmentRequired, isStarted, targetAntennaElevation, onAddMessageProp]);
  
  useEffect(() => {
    if (!isStarted || !onAddMessageProp) return;
    
    onAddMessageProp('client', '正在连接到雷达服务器...');
      
    if (userId) {
      onAddMessageProp('system', `飞行员 ${userId} 已登入系统`);
    }
    
  }, [userId, isStarted, onAddMessageProp]);
  
  useEffect(() => {
    if (isStarted && operations && onAddMessageProp) {
      const timeoutOp = operations.find(op => 
        op.operationType === 'settings_validation_timeout' && 
        !op._displayed 
      );
      
      if (timeoutOp) {
        onAddMessageProp('warning', timeoutOp.parameters.message || '服务器响应超时，参数可能不正确');
        timeoutOp._displayed = true;
      }

      const validationOp = operations.find(op => 
        op.operationType === 'settings_validation_received' && 
        !op._displayed
      );

      if (validationOp) {
        const { status, message, settings } = validationOp.parameters;
        if (status === 'success') {
          onAddMessageProp('success', `参数验证成功: ${message}`);
          if (settings) {
            onAddMessageProp('info', `当前参数设置: 范围 ${settings.range} 海里, 扫描角度 ${settings.scanAngle}°`);
          }
        } else {
          // onAddMessageProp('error', `参数验证失败: ${message}`);
        }
        validationOp._displayed = true;
      }
    }
  }, [operations, isStarted, onAddMessageProp]);
  
  const addExternalMessage = useCallback((type: MessageType, content: string) => {
    if (onAddMessageProp) {
      onAddMessageProp(type, content);
    }
  }, [onAddMessageProp]);
  
  const getMessageStyles = (type: MessageType): string => {
    switch (type) {
      case 'info': return 'text-blue-300';
      case 'warning': return 'text-yellow-300 font-bold';
      case 'error': return 'text-red-500 font-bold text-lg';
      case 'success': return 'text-green-400 font-bold';
      case 'client': return 'text-purple-300';
      case 'server': return 'text-orange-300';
      case 'system': return 'text-cyan-300 font-bold';
      case 'sa_init': return 'text-pink-400 font-bold';
      case 'sa_emergency': return 'text-red-400 font-bold';
      case 'sa_threat': return 'text-yellow-400 font-bold';
      case 'sa_missile': return 'text-red-600 font-extrabold text-lg animate-pulse';
      default: return 'text-gray-300';
    }
  };
  
  const getMessagePrefix = (type: MessageType): string => {
    switch (type) {
      case 'info': return '信息';
      case 'warning': return '警告';
      case 'error': return '错误';
      case 'success': return '成功';
      case 'client': return '客户端';
      case 'server': return '服务器';
      case 'system': return '系统';
      case 'sa_init': return 'SA系统';
      case 'sa_emergency': return '临机事件';
      case 'sa_threat': return '威胁处理';
      case 'sa_missile': return '导弹来袭';
      default: return '';
    }
  };
  
  const renderRadarParams = () => {
    if (!isStarted || currentTask !== 'radar') return null;
    
    return (
      <div className="p-2 mb-2 bg-gray-800 rounded border border-gray-700">
        <h4 className="text-green-400 font-mono text-sm mb-1">雷达参数</h4>
        {/* <div className="flex justify-between text-xs">
          <div>
            <span className="text-gray-400">范围: </span>
            <span className="text-green-300">{radarRange || '未设置'} 海里</span>
          </div>
          <div>
            <span className="text-gray-400">扫描角度: </span>
            <span className="text-green-300">{scanAngle || '未设置'}°</span>
          </div>
        </div> */}
        {initSettings && (
          <div className="mt-1 text-xs text-white font-bold">
            请调整雷达范围{initSettings !== undefined ? ` 至 范围 ${initSettings.range}海里，扫描角度 ${initSettings.scanAngle}°` : ''}!
          </div>
        )}
        {antennaAdjustmentRequired && (
          <div className="mt-1 text-xs text-yellow-300 font-bold">
            请调整天线高度{targetAntennaElevation !== undefined ? ` 至 ${targetAntennaElevation}°` : ''}!
          </div>
        )}
        
        {initSettings && initSettings.settings && (
          <div className="mt-2 pt-1 border-t border-gray-700">
            <h5 className="text-blue-400 font-mono text-xs mb-1">服务器建议参数</h5>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {initSettings.settings.range && (
                <div>
                  <span className="text-gray-400">建议范围: </span>
                  <span className="text-blue-300">{initSettings.settings.range} 海里</span>
                </div>
              )}
              {initSettings.settings.scanAngle && (
                <div>
                  <span className="text-gray-400">建议角度: </span>
                  <span className="text-blue-300">{initSettings.settings.scanAngle}°</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderSAStatus = () => {
    if (!isStarted || currentTask !== 'sa') return null;
    
    return (
      <div className="p-2 mb-2 bg-gray-800 rounded border border-gray-700">
        <h4 className="text-green-400 font-mono text-sm mb-1">SA任务状态</h4>
        
        <div className="grid grid-cols-1 gap-1 text-xs">
          <div className="flex justify-between">
            <span className="text-gray-400">任务状态: </span>
            <span className="text-green-300">威胁评估中</span>
          </div>
          
          <div className="flex justify-between">
            <span className="text-gray-400">临机事件: </span>
            <span className={emergencyReceived ? "text-red-400 font-bold animate-pulse" : "text-gray-500"}>
              {emergencyReceived ? "已收到" : "等待中"}
            </span>
          </div>
          
          {emergencyReceived && lastEmergencyType && (
            <div className="flex justify-between">
              <span className="text-gray-400">事件类型: </span>
              <span className="text-yellow-300 font-bold">
                {lastEmergencyType === 'missile' ? '导弹来袭' : 
                 lastEmergencyType === 'upgrade' ? '威胁升级' : 
                 lastEmergencyType === 'task_updated' ? '威胁任务更新' : lastEmergencyType}
              </span>
            </div>
          )}
          
          {emergencyReceived && lastEmergencyTime && (
            <div className="flex justify-between">
              <span className="text-gray-400">事件时间: </span>
              <span className="text-cyan-300 text-xs">
                {lastEmergencyTime.toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>
        
        {emergencyReceived && (
          <div className="mt-2 pt-1 border-t border-gray-700">
            <div className="text-red-400 font-bold text-xs animate-pulse">
              ⚠️ 请立即处理临机事件！
            </div>
          </div>
        )}
      </div>
    );
  };
  
  return (
    <div className="flex flex-col h-full">
      <div className="bg-gray-800 p-2 rounded-t-lg border-b border-gray-700 mb-2 flex justify-between">
       <span className="text-gray-400 text-xs">通信状态: </span>
        <span className={isStarted ? "text-green-400 text-xs" : "text-yellow-400 text-xs"}>
          {isStarted ? '已连接' : '等待启动'}
        </span>
        </div>
      <div className="bg-gray-800 p-2 rounded-t-lg border-b border-gray-700">
        <h3 className="text-green-400 font-mono text-lg">系统通信日志</h3>
       
        <div className="flex justify-between text-xs">
          {
            userId && (
              <div className="text-xs text-green-200">飞行员: {userId}</div>
            )
          }
          {taskId !== null && (
            <div className="text-xs text-green-200">任务ID: {taskId}</div>
          )}
        </div>
      </div>
      
      {renderRadarParams()}
      
      {renderSAStatus()}
      
      <div 
        ref={logContainerRef}
        className="flex-1 overflow-y-auto bg-gray-900 p-4 font-mono text-sm mb-10"
      >
        {!isStarted ? (
          <div className="text-center py-10 text-gray-500 italic">
            等待系统启动...
          </div>
        ) : (
          incomingMessages.map(msg => (
            <div key={msg.id} className="mb-2">
              <span className="text-gray-500 mr-2">
                {msg.timestamp.toLocaleTimeString()}
              </span>
              <span className={`font-bold mr-2 ${getMessageStyles(msg.type)}`}>
                [{getMessagePrefix(msg.type)}]
              </span>
              <span className={getMessageStyles(msg.type)}>
                {msg.content}
              </span>
            </div>
          ))
        )}
      </div>
      
    
    </div>
  );
};

export default CommunicationLog; 