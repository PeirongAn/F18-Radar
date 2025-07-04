import React from 'react';

interface ThreatData {
  id: string;
  type: string;
  label: string;
  index: number;
  distance: number;
  score: number;
  displayType: string;
  priorityLevel: string;
  priorityColor: string;
}

interface ThreatListProps {
  threats: ThreatData[];
  showDetailedInfo?: boolean;
}

const ThreatList: React.FC<ThreatListProps> = ({ threats, showDetailedInfo = false }) => {
  if (!threats || threats.length === 0) {
    return (
      <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
        <h2 className="text-green-500 font-mono text-lg mb-4">威胁列表</h2>
        <div className="text-gray-400 font-mono text-sm text-center">
          暂无威胁数据
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
      <h2 className="text-green-500 font-mono text-lg mb-4">威胁列表</h2>
      
      <div className="bg-black border border-gray-700 rounded-md overflow-hidden">
        {/* 表头 */}
        <div className="p-2 bg-gray-800 font-mono text-sm text-gray-300 flex border-b border-gray-800">
          <div className="w-8 text-center">#</div>
          <div className="w-20">类型</div>
          <div className="w-20">来源</div>
          {showDetailedInfo && <div className="w-16 text-center">距离</div>}
          {showDetailedInfo && <div className="w-16 text-center">得分</div>}
          <div className="w-12 text-center">优先级</div>
        </div>
        
        {/* 威胁列表 */}
        <div className="max-h-64 overflow-y-auto">
          {threats.map((threat, index) => (
            <div 
              key={threat.id} 
              className={`p-2 border-b border-gray-800 font-mono text-xs flex items-center ${
                index % 2 === 0 ? 'bg-gray-900' : 'bg-gray-950'
              }`}
            >
              <div className="w-8 text-center text-gray-400">{threat.index}</div>
              <div className="w-20 text-green-400 truncate" title={threat.displayType}>
                {threat.displayType}
              </div>
              <div className="w-20 text-yellow-400 truncate" title={threat.label}>
                {threat.label}
              </div>
              {showDetailedInfo && (
                <div className="w-16 text-center text-blue-300">
                  {threat.distance > 0 ? threat.distance.toFixed(0) : '--'}
                </div>
              )}
              {showDetailedInfo && (
                <div className="w-16 text-center text-orange-300">
                  {threat.score > 0 ? threat.score.toFixed(2) : '--'}
                </div>
              )}
              <div className="w-12 flex items-center justify-center">
                <span 
                  className="w-2 h-2 rounded-full mr-1" 
                  style={{ backgroundColor: threat.priorityColor }}
                ></span>
                <span className="text-white text-xs">{threat.priorityLevel}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ThreatList; 