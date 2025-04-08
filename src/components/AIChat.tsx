import React, { useState, useEffect } from 'react';

interface AIChatProps {
  selectedTarget: string | null;
}

interface Message {
  id: number;
  text: string;
  sender: 'ai' | 'user';
  timestamp: Date;
}

const AIChat: React.FC<AIChatProps> = ({ selectedTarget }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: '我是您的智能雷达辅助系统。请问有什么可以帮助您的？',
      sender: 'ai',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');

  // 当选择目标变化时，AI给出相关信息
  useEffect(() => {
    if (selectedTarget) {
      const targetInfo = `已锁定目标 ${selectedTarget}。这是一架敌方战斗机，距离35海里，高度23,000英尺，航向280°，速度540节。建议使用AIM-120C导弹进行中距离攻击。`;
      
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          text: targetInfo,
          sender: 'ai',
          timestamp: new Date()
        }
      ]);
    }
  }, [selectedTarget]);

  const handleSend = () => {
    if (!input.trim()) return;
    
    // 添加用户消息
    const userMessage: Message = {
      id: Date.now(),
      text: input,
      sender: 'user',
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    
    // 模拟AI回复
    setTimeout(() => {
      const aiResponse: Message = {
        id: Date.now() + 1,
        text: getAIResponse(input),
        sender: 'ai',
        timestamp: new Date()
      };
      
      setMessages(prev => [...prev, aiResponse]);
    }, 1000);
  };
  
  // 简单的AI响应逻辑
  const getAIResponse = (userInput: string): string => {
    const input = userInput.toLowerCase();
    
    if (input.includes('目标') || input.includes('敌人')) {
      return '雷达扫描范围内有3个潜在目标。您可以使用TDC游标选择目标进行锁定。';
    } else if (input.includes('武器') || input.includes('导弹')) {
      return '当前挂载: 2x AIM-9X, 4x AIM-120C, 2x AGM-65。建议对空中目标使用AIM-120C。';
    } else if (input.includes('模式') || input.includes('扫描')) {
      return '当前雷达模式为RWS (Range While Search)。您可以切换到TWS (Track While Scan)以同时跟踪多个目标。';
    } else {
      return '我理解您的问题。请提供更多细节，我可以提供关于雷达操作、目标信息或武器系统的建议。';
    }
  };

  return (
    <div className="flex flex-col h-[600px] bg-gray-900 rounded-lg overflow-hidden">
      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map(message => (
          <div 
            key={message.id}
            className={`flex ${message.sender === 'ai' ? 'justify-start' : 'justify-end'}`}
          >
            <div 
              className={`max-w-[80%] rounded-lg px-4 py-2 ${
                message.sender === 'ai' 
                  ? 'bg-blue-900 text-blue-100' 
                  : 'bg-green-800 text-green-100'
              }`}
            >
              <p>{message.text}</p>
              <p className="text-xs opacity-70 mt-1">
                {message.timestamp.toLocaleTimeString()}
              </p>
            </div>
          </div>
        ))}
      </div>
      
      {/* 输入区域 */}
      <div className="p-4 bg-gray-800 border-t border-gray-700">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            className="flex-1 bg-gray-700 text-white px-4 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="输入消息..."
          />
          <button
            onClick={handleSend}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
};

export default AIChat; 