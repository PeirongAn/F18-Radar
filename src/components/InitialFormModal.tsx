import React, { useRef, useEffect, useState } from 'react';
import { observer } from 'mobx-react-lite';


interface InitialFormModalProps {
  onStart: (userId: string, includeAI: boolean, taskType: 'radar' | 'sa', isPractice: boolean) => void;
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
      onStart(userId, includeAI, taskType, isPractice);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
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
                <span className="ml-2 text-green-400 font-mono">雷达任务</span>
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