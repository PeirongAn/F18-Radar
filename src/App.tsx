import React from 'react';
import Radar from './components/Radar';

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-100">
      <h1 className="text-center text-2xl text-gray-800 font-mono pt-8">F18-C 雷达界面</h1>
      <Radar width={600} height={600} />
    </div>
  );
};

export default App; 