import React from 'react';

interface DifficultyChangeModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const DifficultyChangeModal: React.FC<DifficultyChangeModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex justify-center items-center z-[100]">
      <div className="bg-gray-800 border border-green-700 rounded-lg p-6 shadow-xl text-center">
        <h2 className="text-xl text-green-400 font-bold mb-4">任务阶段更新</h2>
        <p className="text-white mb-6">
          当前难度任务场景已完成，需要切换任务或联系主试。
        </p>
        <button
          onClick={onClose}
          className="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
        >
          确认
        </button>
      </div>
    </div>
  );
};

export default DifficultyChangeModal; 