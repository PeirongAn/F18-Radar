import React, { useState, useEffect } from 'react';

interface AIAssistantProps {
  selectedTarget: string | null;
}

interface LogEntry {
  id: number;
  message: string;
  timestamp: Date;
  type: 'info' | 'warning' | 'success' | 'error';
}

const AIAssistant: React.FC<AIAssistantProps> = ({ selectedTarget }) => {
  const [isActive, setIsActive] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      id: 1,
      message: '智能辅助系统已初始化',
      timestamp: new Date(),
      type: 'info'
    }
  ]);

  // 当选择目标变化时，添加日志
  useEffect(() => {
    if (selectedTarget) {
      addLog(`已检测到目标 ${selectedTarget}，开始分析`, 'info');
      
      // 模拟分析过程
      setTimeout(() => {
        addLog(`目标 ${selectedTarget} 分析完成：敌方战斗机，距离35海里，高度23,000英尺`, 'success');
      }, 1500);
    }
  }, [selectedTarget]);

  // 当激活状态变化时，添加日志
  useEffect(() => {
    if (isActive) {
      addLog('智能辅助系统已激活，开始自动分析雷达数据', 'success');
    } else {
      addLog('智能辅助系统已停用，切换到手动控制模式', 'warning');
      setTimeout(() => {
        addLog('建议将扫描宽度设置为30度，扫描高度设置为80海里，以获得最佳探测效果', 'warning');
      }, 10);
    }
  }, [isActive]);

  const addLog = (message: string, type: 'info' | 'warning' | 'success' | 'error') => {
    const newLog: LogEntry = {
      id: Date.now(),
      message,
      timestamp: new Date(),
      type
    };
    
    setLogs(prev => [...prev, newLog]);
  };

  const handleTakeControl = () => {
    if (isActive) {
      // 停用智能辅助
      setIsActive(false);
    } else {
      // 激活智能辅助
      setIsActive(true);
      
      // 模拟自动操作
      setTimeout(() => {
        addLog('开始扫描空域...', 'info');
      }, 1000);
      
      setTimeout(() => {
        addLog('检测到3个潜在目标', 'info');
      }, 3000);
      
      setTimeout(() => {
        addLog('建议切换到TWS模式以同时跟踪多个目标', 'warning');
      }, 5000);
      
      
    }
  };

  // 根据日志类型返回对应的颜色类
  const getLogTypeClass = (type: string) => {
    switch (type) {
      case 'info': return 'text-blue-300';
      case 'warning': return 'text-yellow-300';
      case 'success': return 'text-green-300';
      case 'error': return 'text-red-300';
      default: return 'text-white';
    }
  };

  return (
    <div className="flex flex-col h-[600px] bg-gray-900 rounded-lg overflow-hidden">
      {/* 状态区域 */}
      <div className="bg-gray-800 p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-white font-mono text-lg">
              智能辅助系统: {isActive ? 'ACTIVE' : 'STANDBY'}
            </span>
          </div>
          <div className="text-gray-400 font-mono">
            {new Date().toLocaleTimeString()}
          </div>
        </div>
      </div>
      
      {/* 日志区域 */}
      <div className="flex-1 overflow-y-auto p-4 font-mono bg-black bg-opacity-50">
        {logs.map(log => (
          <div key={log.id} className="mb-2">
            <span className="text-gray-500">[{log.timestamp.toLocaleTimeString()}]</span>{' '}
            <span className={getLogTypeClass(log.type)}>{log.message}</span>
          </div>
        ))}
      </div>
      
      {/* 控制区域 */}
      <div className="p-4 bg-gray-800 border-t border-gray-700">
        <div className="flex justify-between items-center">
          <div className="text-gray-400">
            {isActive 
              ? '系统当前处于自动模式，点击按钮切换到手动控制' 
              : '系统当前处于手动模式，点击按钮激活智能辅助'}
          </div>
          <button
            onClick={handleTakeControl}
            className={`px-6 py-3 rounded-lg font-bold transition-colors ${
              isActive 
                ? 'bg-red-600 hover:bg-red-700 text-white' 
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isActive ? '停用智能辅助' : '激活智能辅助'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AIAssistant; 