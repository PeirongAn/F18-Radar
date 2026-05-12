import React, { useRef, useEffect, useState } from 'react';
import { observer } from 'mobx-react-lite';
import { globalWS } from '../hooks/useRadarData';


interface InitialFormModalProps {
  onStart: (userId: string, includeAI: boolean, taskType: 'radar' | 'sa', isPractice: boolean, useJoystick: boolean) => void;
  defaultUserId?: string;
  defaultIncludeAI?: boolean;
}

const InitialFormModal: React.FC<InitialFormModalProps> = observer(({ 
  onStart, 
  defaultUserId = '', 
  defaultIncludeAI = false 
}) => {
  const userIdRef = useRef<HTMLInputElement>(null);
  const [includeAI, setIncludeAI] = useState(defaultIncludeAI);
  const [taskType, setTaskType] = useState<'radar' | 'sa'>('radar');
  const [isPractice, setIsPractice] = useState(true);
  const [useJoystick, setUseJoystick] = useState(true);

  useEffect(() => {
    if (userIdRef.current) {
      userIdRef.current.focus();
      if (defaultUserId) {
        userIdRef.current.value = defaultUserId;
      }
    }
  }, [defaultUserId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const userId = userIdRef.current?.value.trim();
    if (userId) {
      // 如果选择使用摇杆，则连接摇杆
      if (useJoystick) {
        const wsState = globalWS.getState();
        if (wsState.connected) {
          // 连接摇杆
          globalWS.sendMessage({
            type: 'joystick_connect',
            timestamp: Date.now(),
            user_id: userId
          });
          globalWS.sendMessage({
            type: 'joystick_subscribe',
            timestamp: Date.now(),
            user_id: userId
          });
        } else {
          // 如果WebSocket未连接，先连接WebSocket
          globalWS.connect('ws://localhost:8765');
          // 稍后连接摇杆
          setTimeout(() => {
            globalWS.sendMessage({
              type: 'joystick_connect',
              timestamp: Date.now(),
              user_id: userId
            });
            globalWS.sendMessage({
              type: 'joystick_subscribe',
              timestamp: Date.now(),
              user_id: userId
            });
          }, 1000);
        }
      }
      
      onStart(userId, includeAI, taskType, isPractice, useJoystick);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[9999]">
      <div className="bg-gray-900 border border-green-500 rounded-lg p-8 w-full max-w-md">
        <h2 className="text-green-500 font-mono text-2xl mb-6 text-center">飞行任务初始化</h2>
        
        <form onSubmit={handleSubmit}>
          <div className="mb-6">
            <label htmlFor="userId" className="block text-green-400 font-mono mb-2">
              飞行员 ID
            </label>
            <input
              ref={userIdRef}
              type="text"
              id="userId"
              className="w-full bg-gray-800 border border-gray-600 text-white py-2 px-3 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 font-mono"
              placeholder="请输入飞行员ID"
              autoComplete="off"
              autoFocus
              required
            />
          </div>
          
          <div className="mb-6">
            <label className="block text-green-400 font-mono mb-2">
              任务类型
            </label>
            <div className="flex space-x-6">
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="taskType"
                  value="radar"
                  checked={taskType === 'radar'}
                  onChange={() => setTaskType('radar')}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">传感器任务</span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="taskType"
                  value="sa"
                  checked={taskType === 'sa'}
                  onChange={() => setTaskType('sa')}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">威胁排序任务</span>
              </label>
            </div>
          </div>
          
          <div className="mb-6">
            <label className="block text-green-400 font-mono mb-2">
              任务模式
            </label>
            <div className="flex space-x-6">
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="taskMode"
                  value="practice"
                  checked={isPractice === true}
                  onChange={() => setIsPractice(true)}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">练习</span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="taskMode"
                  value="formal"
                  checked={isPractice === false}
                  onChange={() => setIsPractice(false)}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">正式</span>
              </label>
            </div>
          </div>

          <div className="mb-6">
            <label className="block text-green-400 font-mono mb-2">
              是否使用摇杆
            </label>
            <div className="flex space-x-6">
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="useJoystick"
                  value="yes"
                  checked={useJoystick === true}
                  onChange={() => setUseJoystick(true)}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">是</span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="useJoystick"
                  value="no"
                  checked={useJoystick === false}
                  onChange={() => setUseJoystick(false)}
                  className="form-radio h-5 w-5 text-green-500 focus:ring-green-500 border-gray-600 bg-gray-800"
                />
                <span className="ml-2 text-green-400 font-mono">否</span>
              </label>
            </div>
          </div>

          <div className="mb-8">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="form-checkbox h-5 w-5 text-green-500 rounded focus:ring-green-500 border-gray-600 bg-gray-800"
                checked={includeAI}
                onChange={(e) => setIncludeAI(e.target.checked)}
              />
              <span className="ml-2 text-green-400 font-mono">启用智能辅助系统</span>
            </label>
          </div>

          <div className="my-6 flex justify-center space-x-4">
            <a
              href="/用户手册.html"
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500/10 to-blue-500/10 border border-green-400/30 rounded-lg text-green-400 hover:text-green-300 hover:border-green-300/50 hover:bg-gradient-to-r hover:from-green-500/20 hover:to-blue-500/20 font-mono text-sm transition-all duration-300 ease-in-out transform hover:scale-105 hover:shadow-lg hover:shadow-green-500/20"
            >
              <span className="text-lg">📖</span>
              <span>用户手册</span>
              <svg 
                className="w-4 h-4 opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
            <a
              href="/joystick-test"
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-400/30 rounded-lg text-blue-400 hover:text-blue-300 hover:border-blue-300/50 hover:bg-gradient-to-r hover:from-blue-500/20 hover:to-purple-500/20 font-mono text-sm transition-all duration-300 ease-in-out transform hover:scale-105 hover:shadow-lg hover:shadow-blue-500/20"
            >
              <span className="text-lg">🎮</span>
              <span>摇杆测试</span>
              <svg 
                className="w-4 h-4 opacity-70 group-hover:opacity-100 group-hover:translate-x-1 transition-all duration-300" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
          
          <button
            type="submit"
            className="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-4 rounded-md transition duration-200 font-mono text-lg"
          >
            开始任务
          </button>
          
         
        </form>
      </div>
    </div>
  );
});

export default InitialFormModal; 
