import React, { useState, useEffect, useRef, useCallback } from 'react';

export type MessageType = 'info' | 'warning' | 'error' | 'success' | 'client' | 'server' | 'system' 
  | 'sa_init' | 'sa_emergency' | 'sa_threat' | 'sa_missile';

export interface LogMessage {
  id: number;
  type: MessageType;
  content: string;
  timestamp: Date;
}

interface CommunicationLogProps {
  userId?: string;
  isStarted?: boolean; // 系统是否已启动的标志
  taskId?: number | null;
  messages: LogMessage[];
  // 添加新的消息接收props
  onAddMessage?: (type: MessageType, content: string) => void;
  // 添加雷达参数显示相关的props
  radarRange?: number;
  scanAngle?: number;
  antennaAdjustmentRequired?: boolean;
  targetAntennaElevation?: number; // 目标天线高度属性
  initSettings?: any; // 添加初始设置参数
  connected?: boolean; // 添加WebSocket连接状态
  error?: string | null; // 添加WebSocket错误信息
  operations?: any[]; // 添加操作数组
}

const CommunicationLog: React.FC<CommunicationLogProps> = ({ 
  userId, 
  isStarted = false,
  taskId = null,
  messages: otherMessages,
  onAddMessage,
  radarRange,
  scanAngle,
  antennaAdjustmentRequired = false,
  targetAntennaElevation,  // 接收目标天线高度
  initSettings,  // 接收初始设置参数
  connected = false, // 默认为未连接
  error = null, // 默认无错误
  operations = [] // 默认空操作数组
}) => {
  const [messages, setMessages] = useState<LogMessage[]>([]);
  const logContainerRef = useRef<HTMLDivElement>(null);
  // 使用ref保存计数器，确保ID唯一性
  const messageIdCounter = useRef<number>(0);
  // 使用ref记录上一次的状态
  const prevRangeRef = useRef<number | undefined>(undefined);
  const prevAngleRef = useRef<number | undefined>(undefined);
  const prevAntennaAdjustmentRef = useRef<boolean>(false);
  const initSettingsProcessedRef = useRef<boolean>(false);
  const prevConnectedRef = useRef<boolean>(false);
  
  // 滚动到最新消息
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [messages]);
  useEffect(() => {
    if (otherMessages.length > 0) {
      console.log('get otherMessages', otherMessages);
      setMessages((prevMessages) => [...prevMessages, ...otherMessages]);
    }
  }, [otherMessages]);
  
  // 监听雷达参数变化
  useEffect(() => {
    if (isStarted) {
      // 检查雷达范围是否变化
      if (radarRange !== undefined && radarRange !== prevRangeRef.current) {
        addMessage('system', `雷达范围已设置为: ${radarRange} 海里`);
        prevRangeRef.current = radarRange;
      }
      
      // 检查扫描角度是否变化
      if (scanAngle !== undefined && scanAngle !== prevAngleRef.current) {
        addMessage('system', `扫描角度已设置为: ${scanAngle}°`);
        prevAngleRef.current = scanAngle;
      }
    }
  }, [radarRange, scanAngle, isStarted]);
  
  // 监听初始设置参数
  useEffect(() => {
    if (isStarted && initSettings && !initSettingsProcessedRef.current) {
      addMessage('server', '收到服务器参数设置');
      console.log('initSettings', initSettings);
    
      if (initSettings.range) {
        addMessage('info', `服务器建议雷达范围: ${initSettings.range} 海里, 扫描角度: ${initSettings.scanAngle}°`);
      }
      initSettingsProcessedRef.current = true;
    }
  }, [initSettings, isStarted]);
  
  // 监听天线调整需求变化
  useEffect(() => {
    if (isStarted && antennaAdjustmentRequired && !prevAntennaAdjustmentRef.current) {
      if (targetAntennaElevation !== undefined) {
        addMessage('info', `需要调整天线${targetAntennaElevation > 0 ? '上移' : '下移'} ${Math.abs(targetAntennaElevation)}格，请使用b/t键进行调整`);
      } else {
        addMessage('warning', '重置系统');
      }
      prevAntennaAdjustmentRef.current = true;
    } else if (isStarted && !antennaAdjustmentRequired && prevAntennaAdjustmentRef.current) {
      addMessage('success', '天线高度已调整到合适位置');
      prevAntennaAdjustmentRef.current = false;
    }
  }, [antennaAdjustmentRequired, isStarted, targetAntennaElevation]);
  
  // 添加系统启动消息
  useEffect(() => {
    // 如果系统尚未启动，不进行任何操作
    if (!isStarted) return;
    
    // 系统启动后显示初始连接消息
    addMessage('client', '正在连接到雷达服务器...');
      
    if (userId) {
      addMessage('info', `飞行员 ${userId} 已登入系统`);
    }
    
  }, [userId, isStarted]);
  
  // 监听WebSocket连接状态变化
  useEffect(() => {
    if (isStarted) {
      // 连接状态发生变化
      if (connected && !prevConnectedRef.current) {
        addMessage('server', '服务器已连接');
        addMessage('info', '请使用左侧第1号按钮开始任务初始化');
        prevConnectedRef.current = true;
      } else if (!connected && prevConnectedRef.current) {
        addMessage('error', '与服务器的连接已断开');
        prevConnectedRef.current = false;
      }
      
      // 显示错误信息
      if (error && !connected) {
        addMessage('error', `连接错误: ${error}`);
      }
    }
  }, [connected, error, isStarted]);
  
  // 监听操作变化，显示超时消息
  useEffect(() => {
    if (isStarted && operations) {
      // 查找最近的超时操作
      const timeoutOp = operations.find(op => 
        op.operationType === 'settings_validation_timeout' && 
        !op._displayed // 标记为未显示过
      );
      
      if (timeoutOp) {
        // 添加超时警告消息
        addMessage('warning', timeoutOp.parameters.message || '服务器响应超时，参数可能不正确');
        
        // 标记为已显示
        timeoutOp._displayed = true;
      }

      // 查找最近的参数验证操作
      const validationOp = operations.find(op => 
        op.operationType === 'settings_validation_received' && 
        !op._displayed
      );

      if (validationOp) {
        const { status, message, settings } = validationOp.parameters;
        if (status === 'success') {
          addMessage('success', `参数验证成功: ${message}`);
          if (settings) {
            addMessage('info', `当前参数设置: 范围 ${settings.range} 海里, 扫描角度 ${settings.scanAngle}°`);
          }
        } else {
          addMessage('error', `参数验证失败: ${message}`);
        }
        
        // 标记为已显示
        validationOp._displayed = true;
      }
    }
  }, [operations, isStarted]);
  
  // 添加新消息到日志，使用递增计数器生成唯一ID
  const addMessage = (type: MessageType, content: string) => {
    // 递增ID计数器
    const uniqueId = ++messageIdCounter.current;
    
    setMessages(prev => [...prev, {
      id: uniqueId, // 使用递增的唯一ID
      type,
      content,
      timestamp: new Date()
    }]);
    
    // 如果提供了外部消息处理函数，也调用它
    // if (onAddMessage) {
    //   onAddMessage(type, content);
    // }
  };
  
  // 添加一个公开方法，允许外部组件添加消息
  const addExternalMessage = useCallback((type: MessageType, content: string) => {
    addMessage(type, content);
  }, []);
  
  // 暴露方法给父组件
  React.useImperativeHandle(
    React.useRef({
      addMessage: addExternalMessage
    }),
    () => ({
      addMessage: addExternalMessage
    }),
    [addExternalMessage]
  );
  
  // 根据消息类型返回相应的样式
  const getMessageStyles = (type: MessageType): string => {
    switch (type) {
      case 'info':
        return 'text-blue-300';
      case 'warning':
        return 'text-yellow-300 font-bold';
      case 'error':
        return 'text-red-500 font-bold text-lg';
      case 'success':
        return 'text-green-400 font-bold';
      case 'client':
        return 'text-purple-300';
      case 'server':
        return 'text-orange-300';
      case 'system':
        return 'text-cyan-300 font-bold';
      case 'sa_init':
        return 'text-pink-400 font-bold';
      case 'sa_emergency':
        return 'text-red-400 font-bold';
      case 'sa_threat':
        return 'text-yellow-400 font-bold';
      case 'sa_missile':
        return 'text-red-600 font-extrabold text-lg animate-pulse';
      default:
        return 'text-gray-300';
    }
  };
  
  // 返回消息类型的标签
  const getMessagePrefix = (type: MessageType): string => {
    switch (type) {
      case 'info':
        return '信息';
      case 'warning':
        return '警告';
      case 'error':
        return '错误';
      case 'success':
        return '成功';
      case 'client':
        return '客户端';
      case 'server':
        return '服务器';
      case 'system':
        return '系统';
      case 'sa_init':
        return 'SA系统';
      case 'sa_emergency':
        return '临机事件';
      case 'sa_threat':
        return '威胁处理';
      case 'sa_missile':
        return '导弹来袭';
      default:
        return '';
    }
  };
  
  // 渲染当前雷达参数信息板
  const renderRadarParams = () => {
    if (!isStarted) return null;
    
    return (
      <div className="p-2 mb-2 bg-gray-800 rounded border border-gray-700">
        <h4 className="text-green-400 font-mono text-sm mb-1">雷达参数</h4>
        <div className="flex justify-between text-xs">
          <div>
            <span className="text-gray-400">范围: </span>
            <span className="text-green-300">{radarRange || '未设置'} 海里</span>
          </div>
          <div>
            <span className="text-gray-400">扫描角度: </span>
            <span className="text-green-300">{scanAngle || '未设置'}°</span>
          </div>
        </div>
        {antennaAdjustmentRequired && (
          <div className="mt-1 text-xs text-yellow-300 font-bold">
            请调整天线高度{targetAntennaElevation !== undefined ? ` 至 ${targetAntennaElevation}°` : ''}!
          </div>
        )}
        
        {/* 添加显示推荐参数的部分 */}
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
  
  return (
    <div className="flex flex-col h-full">
      <div className="bg-gray-800 p-2 rounded-t-lg border-b border-gray-700">
        <h3 className="text-green-400 font-mono text-lg">系统通信日志</h3>
        {taskId !== null && (
          <div className="text-xs text-green-200">任务ID: {taskId}</div>
        )}
      </div>
      
      {/* 添加雷达参数信息面板 */}
      {renderRadarParams()}
      
      <div 
        ref={logContainerRef}
        className="flex-1 overflow-y-auto bg-gray-900 p-4 font-mono text-sm"
        style={{ maxHeight: 'calc(100vh - 320px)' }}
      >
        {/* 显示等待消息或实际日志 */}
        {!isStarted ? (
          <div className="text-center py-10 text-gray-500 italic">
            等待系统启动...
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center py-10 text-gray-500 italic">
            正在建立连接...
          </div>
        ) : (
          messages.map(msg => (
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
      
      <div className="bg-gray-800 p-2 rounded-b-lg border-t border-gray-700 text-center">
        <span className="text-gray-400 text-xs">通信状态: </span>
        <span className={isStarted ? "text-green-400 text-xs" : "text-yellow-400 text-xs"}>
          {isStarted ? '已连接' : '等待启动'}
        </span>
      </div>
    </div>
  );
};

export default CommunicationLog; 