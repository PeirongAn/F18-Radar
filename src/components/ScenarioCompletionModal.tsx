import React from 'react';

interface ScenarioCompletionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ScenarioCompletionModal: React.FC<ScenarioCompletionModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-75 flex justify-center items-center z-[101]">
      <div className="bg-gray-800 border border-yellow-500 rounded-lg p-6 shadow-xl text-center">
        <h2 className="text-xl text-yellow-400 font-bold mb-4">场景完成</h2>
        <p className="text-white mb-6">
          当前任务场景已完成，需要填写主观评价表。
        </p>
        <button
          onClick={onClose}
          className="bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
        >
          确认
        </button>
      </div>
    </div>
  );
};

export default ScenarioCompletionModal; 