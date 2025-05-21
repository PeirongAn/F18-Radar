import React, { useEffect, useState, useRef } from 'react';
import { observer } from 'mobx-react-lite'; // Import observer
import agentStore from '../stores/AgentStore'; // Import agentStore

interface AIAssistantProps {
  selectedTarget: string | null;
}

interface LogEntry {
  id: number;
  message: string;
  timestamp: Date;
  type: 'info' | 'warning' | 'success' | 'error';
}

const AIAssistant: React.FC<AIAssistantProps> = observer(({ selectedTarget }) => {
  // const [isActive, setIsActive] = useState(false); // Removed: Use agentStore.isAIActive
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      id: Date.now(), // Ensure unique initial ID
      message: '智能辅助系统已初始化',
      timestamp: new Date(),
      type: 'info'
    }
  ]);

  const logIdCounter = useRef(Date.now());

  useEffect(() => {
    if (selectedTarget) {
      addLog(`已检测到目标 ${selectedTarget}，开始分析`, 'info');
      setTimeout(() => {
        addLog(`目标 ${selectedTarget} 分析完成：敌方战斗机，距离35海里，高度23,000英尺`, 'success');
      }, 1500);
    }
  }, [selectedTarget]);

  // Effect reacts to global AI active state change
  useEffect(() => {
    if (agentStore.isAIActive) {
      addLog('智能辅助系统已激活，开始自动分析雷达数据', 'success');
    } else {
      addLog('智能辅助系统已停用，切换到手动控制模式', 'warning');
      // setTimeout(() => { // This specific suggestion might be better handled elsewhere or removed
      //   addLog('建议将扫描宽度设置为30度，扫描高度设置为80海里，以获得最佳探测效果', 'warning');
      // }, 10);
    }
  }, [agentStore.isAIActive]); // Depend on global state

  const addLog = (message: string, type: 'info' | 'warning' | 'success' | 'error') => {
    const newLog: LogEntry = {
      id: ++logIdCounter.current,
      message,
      timestamp: new Date(),
      type
    };
    setLogs(prev => [...prev, newLog]);
  };

  const handleToggleAI = () => {
    const currentAIState = agentStore.isAIActive;
    agentStore.setAIActive(!currentAIState);

    // Logs are now handled by the useEffect listening to agentStore.isAIActive
    // Additional immediate logs if needed:
    if (!currentAIState) { // If AI was off and is now being turned ON
      // setTimeout(() => {
      //   addLog('开始扫描空域...', 'info');
      // }, 1000);
      // setTimeout(() => {
      //   addLog('检测到3个潜在目标', 'info');
      // }, 3000);
      // setTimeout(() => {
      //   addLog('建议切换到TWS模式以同时跟踪多个目标', 'warning');
      // }, 5000);
    }
  };

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
      <div className="bg-gray-800 p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${agentStore.isAIActive ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-white font-mono text-lg">
              智能辅助系统: {agentStore.isAIActive ? 'ACTIVE' : 'STANDBY (人工接管)'}
            </span>
          </div>
          <div className="text-gray-400 font-mono">
            {new Date().toLocaleTimeString()}
          </div>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 font-mono bg-black bg-opacity-50">
        {logs.map(log => (
          <div key={log.id} className="mb-2">
            <span className="text-gray-500">[{log.timestamp.toLocaleTimeString()}]</span>{' '}
            <span className={getLogTypeClass(log.type)}>{log.message}</span>
          </div>
        ))}
      </div>
      
      <div className="p-4 bg-gray-800 border-t border-gray-700">
        <div className="flex justify-between items-center">
          <div className="text-gray-400">
            {agentStore.isAIActive 
              ? '系统当前由AI辅助操作，点击按钮切换到人工接管' 
              : '系统当前为人工操作模式，点击按钮激活AI辅助'}
          </div>
          <button
            onClick={handleToggleAI} // Use the new handler
            className={`px-6 py-3 rounded-lg font-bold transition-colors ${
              agentStore.isAIActive 
                ? 'bg-red-600 hover:bg-red-700 text-white' // Button to deactivate AI (Manual Override)
                : 'bg-green-600 hover:bg-green-700 text-white' // Button to activate AI
            }`}
          >
            {agentStore.isAIActive ? '人工接管 (停用AI)' : '激活AI辅助'}
          </button>
        </div>
      </div>
    </div>
  );
});

export default AIAssistant; 