import React from 'react';
import Modal from 'react-modal';
import { observer } from 'mobx-react-lite';
import radarStore from '../stores/RadarStore';

// Modal的样式，可以根据需要调整
const customStyles = {
  content: {
    top: '50%',
    left: '50%',
    right: 'auto',
    bottom: 'auto',
    marginRight: '-50%',
    transform: 'translate(-50%, -50%)',
    backgroundColor: '#2d3748', // dark gray background
    color: '#e2e8f0', // light gray text
    border: '1px solid #4a5568', // gray border
    borderRadius: '8px',
    padding: '2rem',
    minWidth: '300px',
    maxWidth: '500px',
  },
  overlay: {
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
  },
};

// 确保Modal在根元素上正确挂载，以支持无障碍访问
Modal.setAppElement('#root');

const CompletionModal: React.FC = observer(() => {
  const { isOpen, message } = radarStore.completionModalInfo;

  const handleConfirm = () => {
    // 隐藏弹窗后立即刷新
    radarStore.hideCompletionModal();
    // window.location.reload();
  };

  const handleCancel = () => {
    radarStore.hideCompletionModal();
  };

  return (
    <Modal
      isOpen={isOpen}
      onRequestClose={handleCancel}
      style={customStyles}
      contentLabel="Task Completion Modal"
    >
      <div className="flex flex-col items-center">
        <h2 className="text-2xl font-bold mb-4">任务完成</h2>
        <p className="text-lg mb-6 text-center">{message}</p>
        <div className="flex justify-around w-full">
         
          <button
            onClick={handleCancel}
            className="bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            className="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-6 rounded transition-colors duration-200"
          >
            确认
          </button>
        </div>
      </div>
    </Modal>
  );
});

export default CompletionModal; 