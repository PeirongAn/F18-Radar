import React, { useState, useEffect, useCallback } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';
import SAPage from './components/SAPage';
import InitialFormModal from './components/InitialFormModal';
import CommunicationLog, { LogMessage, MessageType } from './components/CommunicationLog';
import useRadarData from './hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from './stores/StoreProvider';
import radarStore from './stores/RadarStore';
import agentStore from './stores/AgentStore';

// 日志类型声明，需与CommunicationLog保持一致

interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean;
  externalTargetsTimestamp?: number | null;
}

const App: React.FC = observer(() => {
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [activeDisplay, setActiveDisplay] = useState<'radar' | 'navigation'>('radar');
  const [showInitialForm, setShowInitialForm] = useState<boolean>(true);
  const [userId, setUserId] = useState<string>('');
  const [includeAI, setIncludeAI] = useState<boolean>(false);
  const [isStarted, setIsStarted] = useState<boolean>(false);
  
  // 添加雷达参数状态
  const [radarRange, setRadarRange] = useState<number>(20); // 默认20海里
  const [scanAngle, setScanAngle] = useState<number>(60);   // 默认60度
  
  // 使用MobX Store
  const { radarStore } = useStore();
  
  // 使用useRadarData hook获取任务状态
  const { 
    connected,
    error,
    taskId, 
    antennaAdjustmentRequired, 
    targetAntennaElevation,
    initSettings,
    operations,
    sendMessage  // 添加 sendMessage
  } = useRadarData();
  
  // 统一管理通信日志
  const [messages, setMessages] = useState<LogMessage[]>([]);
  const messageIdRef = React.useRef(0);
  
  // 使用useCallback包装addMessage函数
  const addMessage = useCallback((type: MessageType, content: string) => {
    setMessages(prev => [
      ...prev,
      {
        id: `msg_${Date.now()}_${++messageIdRef.current}`,
        type,
        content,
        timestamp: new Date()
      }
    ]);
  }, []);
  
  // 同步 userId 到 radarStore
  useEffect(() => {
    radarStore.setUserId(userId);
  }, [userId, radarStore]);
  
  // 检查是否有保存的用户名（页面重置后恢复）
  useEffect(() => {
    const preservedUserId = sessionStorage.getItem('preservedUserId');
    const preservedIncludeAI = sessionStorage.getItem('preservedIncludeAI');
    
    if (preservedUserId) {
      console.log('检测到保存的用户信息，正在恢复:', { 
        userId: preservedUserId, 
        includeAI: preservedIncludeAI === 'true' 
      });
      
      // 预填充用户信息到表单，但仍然显示表单让用户确认
      setUserId(preservedUserId);
      setIncludeAI(preservedIncludeAI === 'true');
      // 保持showInitialForm为true，让用户可以重新选择AI选项
      
      // 清除保存的信息，避免下次启动时误用
      sessionStorage.removeItem('preservedUserId');
      sessionStorage.removeItem('preservedIncludeAI');
      
      console.log('✅ 用户信息已预填充到表单');
    }
  }, []); // 只在组件挂载时运行一次
  
  // 监听WebSocket连接状态，在连接成功时初始化系统
  useEffect(() => {
    if (isStarted && connected && !error) {
      // 当系统已启动且WebSocket已连接，且没有错误时，记录日志
      console.log('[雷达系统] 连接成功');
    } else if (isStarted && !connected && error) {
      // 连接失败，显示错误信息
      console.error('WebSocket连接失败，无法初始化系统:', error);
    }
  }, [isStarted, connected, error]);
  
  // 处理目标选择
  const handleTargetSelect = useCallback((params: TargetSelectParams) => {
    const { targetId, lockX, iffMode, externalTargetsTimestamp } = params;

    // currentOperationOwner 应该由调用方 (Radar.tsx 或 RadarDisplay.tsx) 提前设置
    // agentStore.setOperationOwner(lockX === undefined && targetId ? 'manual' : agentStore.currentOperationOwner);

    radarStore.setLockedTargetId(targetId);
    if (targetId && lockX !== undefined) { // 确保 lockX 有效值才设置
      radarStore.setLockScreenX(lockX);
    } else if (!targetId) {
      radarStore.setLockScreenX(undefined); // 清除锁定
    }

    // 如果成功锁定目标，自动激活IFF
    if (lockX !== undefined) {
      console.log('✅ 目标锁定完成，触发IFF激活');
      // 通过事件通知RadarDisplay激活IFF
      // window.dispatchEvent(new CustomEvent('autoActivateIFF'));
      
      // 发送IFF激活消息到服务器
      if (sendMessage) {
        sendMessage({
          type: 'iff_activated',
          targetId: targetId,
          timestamp: Date.now(),
          auto_triggered: true // 标记为自动触发
        });
      }
    }

    if (targetId) {
      const messagePayload: any = {
        type: 'target_selected',
        timestamp: Date.now(),
        target_id: targetId,
        action: 'select',
      };
      // 只有当这些值有效时才添加到消息中
      if (iffMode !== undefined) {
        messagePayload.iff_mode = iffMode;
      }
      if (externalTargetsTimestamp !== undefined && externalTargetsTimestamp !== null) {
        messagePayload.receive_timestamp = externalTargetsTimestamp;
      }
      
      console.log('[App.tsx] Sending target_selected:', messagePayload, 'with owner:', agentStore.currentOperationOwner);
      if (sendMessage) {
        sendMessage(messagePayload);
      } else {
        console.error('[App.tsx] sendMessage function is not available from useRadarData');
      }
    } else {
      // 如果是取消选择，可能也需要发送一个消息，或者由后端逻辑处理
      console.log('[App.tsx] Target deselected / no target selected.');
    }
    // AI 的操作所有者恢复应该由 AI 的控制逻辑自行处理
  }, [sendMessage]);
  
  // 处理初始表单提交
  const handleStartApp = (id: string, withAI: boolean) => {
    setUserId(id);
    setIncludeAI(withAI);
    setShowInitialForm(false);
    setIsStarted(true); // 设置系统为已启动状态
    console.log(`应用已启动 - 用户ID: ${id}, 启用AI: ${withAI}`);
  };
  
  // 处理雷达参数更新
  const handleRadarParamsUpdate = (range: number, angle: number) => {
    setRadarRange(range);
    setScanAngle(angle);
    console.log(`雷达参数已更新 - 范围: ${range}海里, 角度: ${angle}°`);
  };

  // 处理显示切换
  const handleDisplayChange = (display: 'radar' | 'navigation') => {
    setActiveDisplay(display);
    if (display === 'navigation') {
      // 发送 SwitchSA 事件
      sendMessage({
        type: 'SwitchSA',
        timestamp: Date.now(),
        user_id: userId,
        event_owner: 'manual'
      });
    }
  };

  return (
    <div className="min-h-screen bg-black text-gray-300">
      {/* 显示初始表单模态框 */}
      {showInitialForm && (
        <InitialFormModal 
          onStart={handleStartApp} 
          defaultUserId={userId}
          defaultIncludeAI={includeAI}
        />
      )}
      
      <h1 className="text-center text-2xl text-green-500 font-mono pt-6 pb-4">
        JF-17 航电系统 {userId ? `- 飞行员: ${userId}` : ''}
      </h1>
      
      {/* 显示切换按钮 */}
      <div className="flex justify-center mb-4">
        <button 
          className={`px-4 py-2 mx-2 font-mono rounded ${activeDisplay === 'radar' ? 'bg-green-700 text-white' : 'bg-gray-800 text-green-500'}`}
          onClick={() => handleDisplayChange('radar')}
        >
          雷达显示器
        </button>
        <button 
          className={`px-4 py-2 mx-2 font-mono rounded ${activeDisplay === 'navigation' ? 'bg-green-700 text-white' : 'bg-gray-800 text-green-500'}`}
          onClick={() => handleDisplayChange('navigation')}
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
              <Radar 
                width={700} 
                height={700} 
                onTargetSelect={handleTargetSelect}
                isStarted={isStarted} // 传递系统启动状态
                onRadarParamsUpdate={handleRadarParamsUpdate} // 添加参数更新回调
              />
            ) : (
              <div className='flex justify-center'>
                <SAPage onAddMessage={addMessage} userId={userId}/>
              </div>
            )}
          </div>
        </div>
        
        {/* 右侧内容 - 始终显示日志，AI激活时额外显示AI助手 */}
        <div className="w-full lg:w-2/5 flex flex-col gap-4">
          {includeAI && (
            <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
              <h2 className="text-green-500 font-mono text-lg mb-4">AI助手</h2>
              <AIAssistant selectedTarget={selectedTarget} />
            </div>
          )}
          <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800 flex-grow">
            <h2 className="text-green-500 font-mono text-lg mb-4">通信日志</h2>
              <CommunicationLog 
                userId={userId} 
                isStarted={isStarted} 
                taskId={taskId}
                radarRange={radarRange}
                scanAngle={scanAngle}
                antennaAdjustmentRequired={antennaAdjustmentRequired}
              targetAntennaElevation={targetAntennaElevation || undefined}
              initSettings={initSettings}
              connected={connected}
              error={error}
              operations={operations}
                onAddMessage={addMessage}
                messages={messages}
              />
          </div>
        </div>
      </div>
    </div>
  );
});

export default App; 