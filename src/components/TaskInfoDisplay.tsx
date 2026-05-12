import React from 'react';

// 从 useRadarData 导入任务类型定义
type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

interface TaskInfoDisplayProps {
  current: number;
  total: number;
  scenario_index?: number;
  scenario_total?: number;
  is_practice?: boolean;
  task_type?: TaskType; // 新增：任务类型
  difficulty?: string;
  audio_enabled?: boolean;
}

const TaskInfoDisplay: React.FC<TaskInfoDisplayProps> = ({ current, total, scenario_index, scenario_total, is_practice, task_type, difficulty, audio_enabled }) => {
  const remaining = total - current;
  
  // 根据任务类型确定说明文件的链接
  const rulesHref = task_type === 'RADAR_TARGETING' 
    ? '/radar_target_identification.html' 
    : task_type === 'SA_THREAT_RESPONSE'
    ? '/threat_calculation_rules.html'
    : null;

  function translateDifficulty(difficulty: string): React.ReactNode {
      switch (difficulty) {
        case 'low':
        case '3':
          return '低';
        case 'medium':
        case '2':
          return '中';
        case 'high':
        case '1':
          return '高';
        default:
          return difficulty;
      }
    }
  

  return (
    <div 
      className="absolute top-4 left-4 bg-black bg-opacity-75 border border-green-700 rounded-md p-3 shadow-lg z-50 flex flex-col space-y-2"
      style={{ fontFamily: "'Share Tech Mono', 'SimHei', 'Microsoft YaHei', monospace" }}
    >
      <div className="text-green-400 text-sm">
        {task_type && (
          <p>任务: <span className="font-bold text-white">
            {{ RADAR_TARGETING: '传感器任务', SA_THREAT_RESPONSE: '威胁排序任务', PLATFORM_CONTROL: '平台控制', WEAPON_FIRING: '武器发射' }[task_type] ?? task_type}
          </span></p>
        )}
        <p>模式: <span className="font-bold text-white">{is_practice ? '练习模式' : '正式模式'}</span></p>
        {/* {scenario_index !== undefined && scenario_total !== undefined && (
          <p>场景类型: <span className="font-bold text-white">{scenario_index} / {scenario_total}</span></p>
        )} */}
        {difficulty && <p>难度: <span className="font-bold text-white">{translateDifficulty(difficulty)}</span></p>}
        <p>任务进度: <span className="font-bold text-white">{current} / {total}</span></p>
      </div>
      
      {/* 新增：策略说明按钮 */}
      {rulesHref && (
        <a 
          href={rulesHref}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 text-center bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold py-1 px-2 rounded transition-colors duration-200"
        >
          策略说明
        </a>
      )}
    </div>
  );
};

export default TaskInfoDisplay; 
