import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';
import SAPage from './components/SAPage';
import InitialFormModal from './components/InitialFormModal';
import CommunicationLog, { LogMessage, MessageType } from './components/CommunicationLog';
import TaskInfoDisplay from './components/TaskInfoDisplay';
import useRadarData from './hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from './stores/StoreProvider';
import agentStore from './stores/AgentStore';
import radarStore from './stores/RadarStore';
import { Toaster, toast } from 'react-hot-toast';
import CompletionModal from './components/CompletionModal';
import DifficultyChangeModal from './components/DifficultyChangeModal';
import ScenarioCompletionModal from './components/ScenarioCompletionModal';

// 日志类型声明，需与CommunicationLog保持一致

interface TargetSelectParams {
  targetId: string | undefined;
  lockX?: number;
  iffMode?: boolean;
  externalTargetsTimestamp?: number | null;
  event_owner?: 'AI' | 'manual';
}

const App: React.FC = observer(() => {
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [activeDisplay, setActiveDisplay] = useState<'radar' | 'navigation'>('radar');
  const [showInitialForm, setShowInitialForm] = useState<boolean>(true);
  const [userId, setUserId] = useState<string>('');
  const [includeAI, setIncludeAI] = useState<boolean>(false);
  const [isPractice, setIsPractice] = useState<boolean>(true);
  const [isStarted, setIsStarted] = useState<boolean>(false);
  const [showDifficultyChangeModal, setShowDifficultyChangeModal] = useState(false);
  const [showScenarioCompletionModal, setShowScenarioCompletionModal] = useState(false);
  
  // 添加雷达参数状态
  const [radarRange, setRadarRange] = useState<number>(20); // 默认20海里
  const [scanAngle, setScanAngle] = useState<number>(60);   // 默认60度
  
  // 使用MobX Store
  const { radarStore } = useStore();
  
  const previousDifficultyRef = React.useRef<string | undefined>();
  const previousScenarioIndexRef = React.useRef<number | undefined>();
  
  // 使用useRadarData hook获取任务状态
  const { 
    connected,
    error,
    taskId, 
    antennaAdjustmentRequired, 
    targetAntennaElevation,
    initSettings,
    operations,
    sendMessage,
    initializeSystem,
    sendResetSA,
    repetitionInfos,
    resetTargets,
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
    // 检查是否已经锁定了同一个目标
    if (params.targetId && params.targetId === radarStore.lockedTargetId) {
      console.log(`目标 ${params.targetId} 已被锁定，无需重复操作`);
      return; // 如果是同一个目标，则不执行任何操作
    }
    
    // 更新锁定的目标ID
    radarStore.setLockedTargetId(params.targetId);
    
    // 更新锁定时的屏幕X坐标
    if (params.targetId && params.lockX !== undefined) {
      radarStore.setLockScreenX(params.lockX);
    } else {
      // 如果没有目标ID，则清除锁定线
      radarStore.setLockScreenX(undefined);
    }

    console.log(`App.tsx - 目标选择已处理: id=${params.targetId}, lockX=${params.lockX}`);
    
    // 如果有目标被锁定，则自动触发IFF
    if (params.targetId && params.iffMode) {
      // 触发一个全局的自动激活IFF事件
      // window.dispatchEvent(new CustomEvent('autoActivateIFF'));
    }

    if (params.targetId) {
      const messagePayload: any = {
        type: 'target_selected',
        timestamp: Date.now(),
        target_id: params.targetId,
        action: 'select',
        event_owner: params.event_owner,
      };
      // 只有当这些值有效时才添加到消息中
      if (params.iffMode !== undefined) {
        messagePayload.iff_mode = params.iffMode;
      }
      if (params.externalTargetsTimestamp !== undefined && params.externalTargetsTimestamp !== null) {
        messagePayload.receive_timestamp = params.externalTargetsTimestamp;
      }
      
      console.log('[App.tsx] Sending target_selected:', messagePayload, 'with owner:', messagePayload.event_owner);
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
  const handleStartApp = (id: string, withAI: boolean, taskType: 'radar' | 'sa', isPractice: boolean) => {
    setUserId(id);
    setIncludeAI(withAI);
    setIsPractice(isPractice);
    
    // 1. 更新所有相关的 store 状态
    radarStore.startSystem(id, withAI, isPractice); // This now only sets state in radarStore
    agentStore.setAIActive(withAI); // Explicitly set AI state here
    
    // 2. 更新 App.tsx 的本地 UI 状态
    setShowInitialForm(false);
    setIsStarted(true); // 设置系统为已启动状态
    
    // 根据选择的任务类型设置初始视图
    if (taskType === 'sa') {
      setActiveDisplay('navigation');
      // 启动时如果选择SA，则立即发送SwitchSA消息以加载数据
      sendMessage({
        type: 'SwitchSA',
        timestamp: Date.now(),
        user_id: id,
        is_practice: isPractice,
      });
    } else {
      setActiveDisplay('radar');
    }
    
    // 3. 日志记录和系统初始化调用（雷达任务）
    console.log(`应用已启动 - 用户ID: ${id}, 启用AI: ${withAI}, 任务: ${taskType}, 练习: ${isPractice}`);
    // 只有雷达任务需要这个初始化
    if (taskType === 'radar') {
      initializeSystem(id, withAI, isPractice);
    }
  };
  
  // 处理雷达参数更新
  const handleRadarParamsUpdate = (range: number, angle: number) => {
    setRadarRange(range);
    setScanAngle(angle);
    console.log(`雷达参数已更新 123- 范围: ${range}海里, 角度: ${angle}°`);
    radarStore.updateRadarParams(range, angle);
  };

  // 处理显示切换
  const handleDisplayChange = (display: 'radar' | 'navigation') => {
    setActiveDisplay(display);
    if (display === 'navigation') {
      sendMessage({
        type: 'SwitchSA',
        timestamp: Date.now(),
        user_id: userId,
        is_practice: isPractice,
      });
    } else if (display === 'radar') {
      // 当切换回雷达时，重新初始化雷达任务
      console.log(`切换到雷达视图。为用户重新初始化雷达任务: ${userId}, AI: ${includeAI}`);
      initializeSystem(userId, includeAI, isPractice);
    }
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Check if F12 is pressed
      if (event.key === 'F12') {
        event.preventDefault(); // Prevent default browser action
        console.log("F12 pressed, resetting SA threats.");
        sendResetSA(); // Call the reset function
      }
    };

    // Add event listener
    window.addEventListener('keydown', handleKeyDown);

    // Cleanup event listener
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [sendResetSA]); // Add sendResetSA to dependency array

  // 根据当前视图决定要显示哪个任务的进度
  const infoToShow = useMemo(() => {
    let info = null;
    let task_type: 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | null = null;

    if (activeDisplay === 'radar') {
      info = repetitionInfos['RADAR_TARGETING'];
      task_type = 'RADAR_TARGETING';
    } else if (activeDisplay === 'navigation') {
      info = repetitionInfos['SA_THREAT_RESPONSE'];
      task_type = 'SA_THREAT_RESPONSE';
    }

    if (!info || typeof info === 'string' || !task_type) return null;

    return { 
      ...info,
      task_type,
      difficulty: (info as any).difficulty,
      is_ai_active: (info as any).is_ai_active
    };
  }, [activeDisplay, repetitionInfos]);

  // 监听难度变化并发送通知
  useEffect(() => {
    const currentDifficulty = infoToShow?.difficulty;

    // 仅当难度从一个已定义的值变为另一个已定义的值时，才显示通知
    if (
      previousDifficultyRef.current &&
      currentDifficulty &&
      currentDifficulty !== previousDifficultyRef.current
    ) {
      setShowDifficultyChangeModal(true);
    }

    // 更新上一个难度的引用
    previousDifficultyRef.current = currentDifficulty;
  }, [infoToShow?.difficulty]);

  // 监听场景索引变化（仅AI模式）
  useEffect(() => {
    const currentScenarioIndex = infoToShow?.scenario_index;

    if (
      agentStore.isAIActive &&
      previousScenarioIndexRef.current &&
      currentScenarioIndex &&
      currentScenarioIndex !== previousScenarioIndexRef.current
    ) {
      setShowScenarioCompletionModal(true);
    }
    
    previousScenarioIndexRef.current = currentScenarioIndex;
  }, [infoToShow?.scenario_index, agentStore.isAIActive]);

  const allTasksCompleted = useMemo(() => {
    const radarCompleted = repetitionInfos['RADAR_TARGETING'] === 'ALL_COMPLETED';
    const saCompleted = repetitionInfos['SA_THREAT_RESPONSE'] === 'ALL_COMPLETED';
    return radarCompleted && saCompleted;
  }, [repetitionInfos]);

  return (
    <div className="min-h-screen bg-black text-gray-300">
      <Toaster 
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#333',
            color: '#fff',
          },
        }}
      />
      <CompletionModal />
      <DifficultyChangeModal 
        isOpen={showDifficultyChangeModal} 
        onClose={() => setShowDifficultyChangeModal(false)} 
      />
      <ScenarioCompletionModal 
        isOpen={showScenarioCompletionModal}
        onClose={() => setShowScenarioCompletionModal(false)}
      />
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
                <SAPage 
                  width={700} 
                  height={700} 
                  onAddMessage={addMessage} 
                  userId={userId}
                  onResetSA={sendResetSA}
                  onResetTargets={resetTargets}
                />
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

      {infoToShow && isStarted && (
        <TaskInfoDisplay
          current={infoToShow.current}
          total={infoToShow.total}
          scenario_index={infoToShow.scenario_index}
          scenario_total={infoToShow.scenario_total}
          is_practice={infoToShow.is_practice}
          task_type={infoToShow.task_type}
          difficulty={infoToShow.difficulty}
        />
      )}
    </div>
  );
});

export default App; 