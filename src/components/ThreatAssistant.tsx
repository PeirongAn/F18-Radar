import React, { useState, useEffect } from 'react';

interface ThreatAssistantProps {
  selectedTarget: string | null;
}

interface ThreatEntry {
  id: string;
  type: 'missile_lock' | 'friendly_lock' | 'radar_lock' | 'proximity';
  source: string;
  distance: number;
  heading: number;
  priority: 'high' | 'medium' | 'low';
  timestamp: Date;
}

const ThreatAssistant: React.FC<ThreatAssistantProps> = ({ selectedTarget }) => {
  const [isActive, setIsActive] = useState(false);
  const [threats, setThreats] = useState<ThreatEntry[]>([
    {
      id: 'threat-1',
      type: 'missile_lock',
      source: 'MiG-29',
      distance: 28.5,
      heading: 315,
      priority: 'high',
      timestamp: new Date()
    },
    {
      id: 'threat-2',
      type: 'radar_lock',
      source: 'SA-10',
      distance: 42.3,
      heading: 45,
      priority: 'medium',
      timestamp: new Date(Date.now() - 15000)
    },
    {
      id: 'threat-3',
      type: 'proximity',
      source: 'Su-27',
      distance: 15.7,
      heading: 270,
      priority: 'low',
      timestamp: new Date(Date.now() - 30000)
    }
  ]);

  // 当选择目标变化时，添加到威胁列表
  useEffect(() => {
    if (selectedTarget && isActive) {
      const newThreat: ThreatEntry = {
        id: `threat-${Date.now()}`,
        type: 'radar_lock',
        source: selectedTarget,
        distance: Math.floor(Math.random() * 30) + 10,
        heading: Math.floor(Math.random() * 360),
        priority: 'medium',
        timestamp: new Date()
      };
      
      setThreats(prev => [newThreat, ...prev].slice(0, 5)); // 保持最多5个威胁
    }
  }, [selectedTarget, isActive]);

  // 激活系统时模拟威胁变化
  useEffect(() => {
    if (!isActive) return;
    
    const interval = setInterval(() => {
      // 随机更新威胁优先级或距离
      setThreats(prev => 
        prev.map(threat => {
          if (Math.random() > 0.7) {
            const priorities: ('high' | 'medium' | 'low')[] = ['high', 'medium', 'low'];
            const currentIndex = priorities.indexOf(threat.priority);
            const newIndex = Math.max(0, Math.min(2, currentIndex + (Math.random() > 0.5 ? 1 : -1)));
            
            return {
              ...threat,
              priority: priorities[newIndex],
              distance: Math.max(0, threat.distance + (Math.random() > 0.5 ? 1 : -1) * Math.random() * 5)
            };
          }
          return threat;
        })
      );
    }, 5000);
    
    return () => clearInterval(interval);
  }, [isActive]);

  const handleActivate = () => {
    setIsActive(!isActive);
  };

  // 获取威胁类型的中文描述
  const getThreatTypeText = (type: string): string => {
    switch (type) {
      case 'missile_lock': return '导弹来袭';
      case 'friendly_lock': return '友方导弹锁定';
      case 'radar_lock': return '敌方雷达锁定';
      case 'proximity': return '敌方靠近';
      default: return '未知威胁';
    }
  };

  // 获取优先级对应的颜色类
  const getPriorityColorClass = (priority: string): string => {
    switch (priority) {
      case 'high': return 'bg-red-700';
      case 'medium': return 'bg-yellow-600';
      case 'low': return 'bg-blue-700';
      default: return 'bg-gray-700';
    }
  };

  // 获取威胁源的中文描述
  const getThreatSourceText = (source: string): string => {
    if (source.includes('导弹')) {
      return source;
    }
    return source;
  };

  return (
    <div className="flex flex-col h-[600px] bg-gray-900 rounded-lg overflow-hidden">
      {/* 状态区域 */}
      <div className="bg-gray-800 p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-white font-mono text-lg">
              威胁评估系统: {isActive ? 'ACTIVE' : 'STANDBY'}
            </span>
          </div>
          <div className="text-gray-400 font-mono">
            {new Date().toLocaleTimeString()}
          </div>
        </div>
      </div>
      
      {/* 威胁列表区域 */}
      <div className="flex-1 overflow-y-auto bg-black bg-opacity-50">
        <div className="p-2 bg-gray-800 border-b border-gray-700 font-mono text-sm text-gray-300 flex">
          <div className="w-8">#</div>
          <div className="w-32">类型</div>
          <div className="w-24">来源</div>
          <div className="w-24">距离/方位</div>
          <div className="w-24">时间</div>
        </div>
        
        {threats.length === 0 && (
          <div className="p-8 text-center text-gray-500 font-mono">
            未检测到威胁
          </div>
        )}
        
        {threats.map((threat, index) => (
          <div 
            key={threat.id} 
            className={`p-2 border-b border-gray-800 font-mono text-sm flex items-center ${
              index % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'
            }`}
          >
            <div className="w-8 flex items-center justify-center">
              <div className={`w-3 h-3 rounded-full ${getPriorityColorClass(threat.priority)}`}></div>
            </div>
            <div className="w-32 text-white">{getThreatTypeText(threat.type)}</div>
            <div className="w-24 text-yellow-400">{getThreatSourceText(threat.source)}</div>
            <div className="w-24 text-blue-300">{threat.distance.toFixed(1)}nm/{threat.heading}°</div>
            <div className="w-24 text-gray-500">{threat.timestamp.toLocaleTimeString()}</div>
          </div>
        ))}
      </div>
      
      {/* 控制区域 */}
      <div className="p-4 bg-gray-800 border-t border-gray-700">
        <div className="flex justify-between items-center">
          <div className="text-gray-400">
            {isActive 
              ? '威胁评估系统已激活，实时监控中' 
              : '威胁评估系统待机中，点击激活'}
          </div>
          <button
            onClick={handleActivate}
            className={`px-6 py-3 rounded-lg font-bold transition-colors ${
              isActive 
                ? 'bg-red-600 hover:bg-red-700 text-white' 
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isActive ? '停用系统' : '激活系统'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ThreatAssistant; 