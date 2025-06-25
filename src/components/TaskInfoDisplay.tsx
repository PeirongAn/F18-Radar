import React from 'react';

interface TaskInfoDisplayProps {
  current: number;
  total: number;
  scenario_index?: number;
  scenario_total?: number;
  is_practice?: boolean;
}

const TaskInfoDisplay: React.FC<TaskInfoDisplayProps> = ({ current, total, scenario_index, scenario_total, is_practice }) => {
  const remaining = total - current;
  
  return (
    <div 
      className="absolute top-4 left-4 bg-black bg-opacity-50 border border-green-700 rounded-md p-2 shadow-lg z-50"
      style={{ fontFamily: '"Courier New", Courier, monospace' }}
    >
      <div className="text-green-400 text-sm">
        <p>模式: <span className="font-bold text-white">{is_practice ? '练习模式' : '正式模式'}</span></p>
        {scenario_index !== undefined && scenario_total !== undefined && (
          <p>场景类型: <span className="font-bold text-white">{scenario_index} / {scenario_total}</span></p>
        )}
        <p>重复进度: <span className="font-bold text-white">{current} / {total}</span></p>
        <p>本轮剩余: <span className="font-bold text-white">{remaining}</span></p>
      </div>
    </div>
  );
};

export default TaskInfoDisplay; 