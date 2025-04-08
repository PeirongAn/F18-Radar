import React, { useState } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';

import SAPage from './components/SAPage';

const App: React.FC = () => {
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [activeDisplay, setActiveDisplay] = useState<'radar' | 'navigation'>('radar');
 
  
  // 处理目标选择
  const handleTargetSelect = (targetId: string) => {
    setSelectedTarget(targetId);
  };

  return (
    <div className="min-h-screen bg-black text-gray-300">
      <h1 className="text-center text-2xl text-green-500 font-mono pt-6 pb-4">F18-C 航电系统</h1>
      
      {/* 显示切换按钮 */}
      <div className="flex justify-center mb-4">
        <button 
          className={`px-4 py-2 mx-2 font-mono rounded ${activeDisplay === 'radar' ? 'bg-green-700 text-white' : 'bg-gray-800 text-green-500'}`}
          onClick={() => setActiveDisplay('radar')}
        >
          雷达显示器
        </button>
        <button 
          className={`px-4 py-2 mx-2 font-mono rounded ${activeDisplay === 'navigation' ? 'bg-green-700 text-white' : 'bg-gray-800 text-green-500'}`}
          onClick={() => setActiveDisplay('navigation')}
        >
          SA页面
        </button>
      </div>
      
      <div className="flex flex-col lg:flex-row gap-8 px-4 max-w-8xl mx-auto">
        {/* 左侧显示区域 */}
        <div className="w-full lg:w-3/5">
          <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
            <h2 className="text-green-500 font-mono text-lg mb-4">
              {activeDisplay === 'radar' ? '雷达显示器' : 'SA页面'}
            </h2>
            
            {activeDisplay === 'radar' ? (
              <Radar width={700} height={700} onTargetSelect={handleTargetSelect} />
            ) : (
              <div className='flex justify-center'>
                <SAPage   />
              </div>
            )}
          </div>
        </div>
        
        {/* 右侧智能体状态页面 */}
        <div className="w-full lg:w-2/5">
          <div className="bg-gray-900 p-4 rounded-lg shadow-lg h-full border border-gray-800">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-blue-400 font-mono text-lg">智能辅助系统</h2>
              
            </div>
            
            {activeDisplay === 'radar' ? (
              <AIAssistant selectedTarget={selectedTarget} />
            ) : (
              <AIAssistant selectedTarget={selectedTarget} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default App; 