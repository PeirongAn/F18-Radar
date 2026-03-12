import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import Radar from './components/Radar';
import AIAssistant from './components/AIAssistant';
import SAPage from './components/SAPage';
import CommunicationLog, { LogMessage, MessageType } from './components/CommunicationLog';
import TaskInfoDisplay from './components/TaskInfoDisplay';
import useRadarData, { globalWS } from './hooks/useRadarData';
import { observer } from 'mobx-react-lite';
import { useStore } from './stores/StoreProvider';
import agentStore from './stores/AgentStore';
import radarStore from './stores/RadarStore';
import { Toaster, toast } from 'react-hot-toast';
import CompletionModal from './components/CompletionModal';
// import ScenarioCompletionModal from './components/ScenarioCompletionModal';
import ThreatList from './components/ThreatList';
// import ConnectionStatus from './components/ConnectionStatus';
// import audioManager from './managers/AudioManager';
import JoystickInitializationPage from './pages/JoystickInitializationPage';

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
  const [activeDisplay, setActiveDisplay] = useState<'radar' | 'navigation' | 'joystick'>('radar');
  const [userId, setUserId] = useState<string>('');
  const [includeAI, setIncludeAI] = useState<boolean>(false);
  const [isPractice, setIsPractice] = useState<boolean>(true);
  const [isStarted, setIsStarted] = useState<boolean>(false);
  // const [showScenarioCompletionModal, setShowScenarioCompletionModal] = useState(false);
  
  // 添加雷达参数状态
  const [radarRange, setRadarRange] = useState<number>(20); // 默认20海里
  const [scanAngle, setScanAngle] = useState<number>(60);   // 默认60度
  
  // 使用MobX Store
  const { radarStore } = useStore();
  
  const previousScenarioIndexRef = React.useRef<number | undefined>();
  
  // 使用useRadarData hook获取任务状态
  const { 
    connected,
    error,
    taskId, 
    initSettings,
    operations,
    sendMessage,
    initializeSystem,
    sendResetSA,
    repetitionInfos,
    resetTargets,
    radarData,
    lastMessage,
  } = useRadarData();

  // 从 MobX 全局 store 读取天线状态，避免多 hook 实例间的状态隔离问题
  const antennaAdjustmentRequired = radarStore.antennaAdjustmentRequired;
  const targetAntennaElevation = radarStore.targetAntennaElevation;


  
  // 统一管理通信日志
  const [messages, setMessages] = useState<LogMessage[]>([]);
  const messageIdRef = React.useRef(0);
  
  // SA任务临机事件状态
  const [emergencyReceived, setEmergencyReceived] = useState<boolean>(false);
  const [lastEmergencyType, setLastEmergencyType] = useState<string>('');
  const [lastEmergencyTime, setLastEmergencyTime] = useState<Date | undefined>(undefined);
  const lastEmergencyIdRef = React.useRef<string>('');
  
  // 新增：威胁列表状态
  const [threatListData, setThreatListData] = useState<any[]>([]);
  const [showDetailedInfo, setShowDetailedInfo] = useState(false);

  useEffect(()=> {
      console.log('get values222', targetAntennaElevation, antennaAdjustmentRequired)
    }, [targetAntennaElevation, antennaAdjustmentRequired])
  
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
  
  // 添加清空消息的功能
  const clearMessages = useCallback(() => {
    setMessages([]);
    messageIdRef.current = 0;
  }, []);
  
  // 同步 userId 到 radarStore
  useEffect(() => {
    radarStore.setUserId(userId);
  }, [userId, radarStore]);
  
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


  
  // 监听SA任务相关消息
  useEffect(() => {
    if (!lastMessage) return;
    
    // 生成消息ID来防止重复处理
    const messageId = JSON.stringify({
      type: lastMessage.type,
      timestamp: lastMessage.timestamp || Date.now(),
      event: lastMessage.event,
      saThreats: lastMessage.saThreats?.length || 0
    });

    if (messageId !== lastEmergencyIdRef.current) {
      console.log('[App.tsx] 检测到新的SA消息:', lastMessage);
      
      // 只有特定消息类型才认为是临机事件
      if (lastMessage.type === 'SAEmergency') {
        // SAEmergency 是具体的临机事件（导弹来袭等）
        setEmergencyReceived(true);
        setLastEmergencyType(lastMessage.event || 'unknown');
        setLastEmergencyTime(new Date());
        lastEmergencyIdRef.current = messageId;
        
        const eventText = lastMessage.event === 'missile' ? '导弹来袭' : 
                         lastMessage.event === 'upgrade' ? '威胁升级' : '未知事件';
        addMessage('sa_emergency', `收到临机事件：${eventText}`);
      }
    }
  }, [lastMessage, addMessage]);
  
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
  
  // 处理启动（从JSON配置自动调用，或手动调用）
  const handleStartApp = useCallback((id: string, withAI: boolean, taskType: 'radar' | 'sa', practice: boolean, useJoystick: boolean) => {
    setUserId(id);
    setIncludeAI(withAI);
    setIsPractice(practice);
    
    // 摇杆连接
    if (useJoystick) {
      const connectJoystick = () => {
        globalWS.sendMessage({ type: 'joystick_connect', timestamp: Date.now(), user_id: id });
        globalWS.sendMessage({ type: 'joystick_subscribe', timestamp: Date.now(), user_id: id });
      };
      if (globalWS.getState().connected) {
        connectJoystick();
      } else {
        setTimeout(connectJoystick, 1000);
      }
    }
    
    radarStore.startSystem(id, withAI, practice);
    agentStore.setAIActive(withAI);
    setIsStarted(true);
    
    if (taskType === 'sa') {
      setActiveDisplay('navigation');
      sendMessage({
        type: 'SwitchSA',
        timestamp: Date.now(),
        user_id: id,
        is_practice: practice,
        is_ai_active: withAI,
      });
    } else {
      setActiveDisplay('radar');
    }
    
    console.log(`应用已启动 - 用户ID: ${id}, 启用AI: ${withAI}, 任务: ${taskType}, 练习: ${practice}, 摇杆: ${useJoystick}`);
    if (taskType === 'radar') {
      initializeSystem(id, withAI, practice);
    }
  }, [sendMessage, initializeSystem, radarStore]);

  // 点击"开始传感器任务"后加载配置并启动
  const handleStartTask = useCallback(() => {
    fetch('/init_config.json')
      .then(res => res.json())
      .then((cfg: { userId: string; includeAI: boolean; taskType: 'radar' | 'sa'; isPractice: boolean; useJoystick: boolean }) => {
        console.log('加载启动配置:', cfg);
        handleStartApp(cfg.userId, cfg.includeAI, cfg.taskType, cfg.isPractice, cfg.useJoystick);
      })
      .catch(err => {
        console.error('加载 init_config.json 失败:', err);
      });
  }, [handleStartApp]);
  
  // 处理雷达参数更新
  const handleRadarParamsUpdate = (range: number, angle: number) => {
    setRadarRange(range);
    setScanAngle(angle);
    console.log(`雷达参数已更新 123- 范围: ${range}海里, 角度: ${angle}°`);
    radarStore.updateRadarParams(range, angle);
  };

  // 处理SA任务重置（包含临机事件状态重置）
  const handleSATaskReset = useCallback(() => {
    console.log('App.tsx - 执行SA任务完整重置');
    
    // 1. 重置临机事件状态
    setEmergencyReceived(false);
    setLastEmergencyType('');
    setLastEmergencyTime(undefined);
    lastEmergencyIdRef.current = '';
    
    // 2. 清空消息历史
    clearMessages();
    
    // 3. 调用服务器重置
    sendResetSA();
    
    console.log('✅ App.tsx - SA任务重置完成，包括临机事件状态');
  }, [sendResetSA, clearMessages]);

  // 处理显示切换
  const handleDisplayChange = (display: 'radar' | 'navigation' | 'joystick') => {
    setActiveDisplay(display);
    // 切换视图时清空消息历史
    clearMessages();
    
    // 如果切换到SA页面，重置临机事件状态
    if (display === 'navigation') {
      setEmergencyReceived(false);
      setLastEmergencyType('');
      setLastEmergencyTime(undefined);
      lastEmergencyIdRef.current = '';
      
      // 发送SwitchSA消息以加载SA任务数据
      if (sendMessage) {
        sendMessage({
          type: 'SwitchSA',
          timestamp: Date.now(),
          user_id: userId,
          is_practice: isPractice,
          is_ai_active: includeAI,
        });
      }
    } else if (display === 'radar') {
      // 当切换回雷达时，重新初始化雷达任务
      console.log(`切换到雷达视图。为用户重新初始化雷达任务: ${userId}, AI: ${includeAI}`);
      if (initializeSystem) {
        initializeSystem(userId, includeAI, isPractice);
      }
    } else if (display === 'joystick') {
      // 切换到操纵杆初始化页面
      console.log('切换到操纵杆初始化页面');
    }
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Check if F12 is pressed
      if (event.key === 'F12') {
        // event.preventDefault(); // Prevent default browser action
        console.log("F12 pressed, resetting SA threats.");
        // handleSATaskReset(); // Call the complete reset function
      }
    };

    // Add event listener
    window.addEventListener('keydown', handleKeyDown);

    // Cleanup event listener
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleSATaskReset]); // Add handleSATaskReset to dependency array

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
    } else if (activeDisplay === 'joystick') {
      // 操纵杆初始化页面不显示任务信息
      return null;
    }

    if (!info || typeof info === 'string' || !task_type) return null;

    return { 
      ...info,
      task_type,
      difficulty: (info as any).difficulty,
      is_ai_active: (info as any).is_ai_active
    };
  }, [activeDisplay, repetitionInfos]);

  // 使用难度变化检测hook
  // const { showDifficultyChangeModal, closeDifficultyChangeModal } = useDifficultyChangeDetection(
  //   infoToShow?.difficulty,
  //   !!infoToShow?.is_ai_active
  // );

  // 监听场景索引变化（仅AI模式）
  // useEffect(() => {
  //   const currentScenarioIndex = infoToShow?.scenario_index;

  //   if (
  //     agentStore.isAIActive &&
  //     previousScenarioIndexRef.current &&
  //     currentScenarioIndex &&
  //     currentScenarioIndex !== previousScenarioIndexRef.current
  //   ) {
  //     setShowScenarioCompletionModal(true);
  //   }
    
  //   previousScenarioIndexRef.current = currentScenarioIndex;
  // }, [infoToShow?.scenario_index, agentStore.isAIActive]);

  const allTasksCompleted = useMemo(() => {
    const radarCompleted = repetitionInfos['RADAR_TARGETING'] === 'ALL_COMPLETED';
    const saCompleted = repetitionInfos['SA_THREAT_RESPONSE'] === 'ALL_COMPLETED';
    return radarCompleted && saCompleted;
  }, [repetitionInfos]);

  // 处理威胁列表数据更新
  const handleThreatListUpdate = useCallback((threatData: any[]) => {
    console.log('App 威胁列表', threatData);
    setThreatListData(threatData);
  }, []);
  
  // 处理详细信息显示状态变化
  const handleShowDetailedInfoChange = useCallback((showDetailed: boolean) => {
    setShowDetailedInfo(showDetailed);
  }, []);

  return (
    <div className="min-h-screen bg-black text-gray-300">
      {/* 启动 Modal */}
      {!isStarted && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-90">
          <div className="bg-gray-900 border border-green-700 rounded-lg p-10 text-center shadow-2xl">
            <h2 className="text-green-400 font-mono text-2xl mb-3">JF-17 航电系统</h2>
            <p className="text-gray-400 font-mono text-sm mb-8">传感器任务训练平台</p>
            <button
              className={`px-8 py-3 font-mono text-lg rounded transition-colors ${
                connected
                  ? 'bg-green-700 hover:bg-green-600 text-white cursor-pointer'
                  : 'bg-gray-700 text-gray-500 cursor-not-allowed'
              }`}
              disabled={!connected}
              onClick={handleStartTask}
            >
              {connected ? '开始传感器任务' : '正在连接服务器...'}
            </button>
          </div>
        </div>
      )}

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
      {/* <DifficultyChangeModal 
        isOpen={showDifficultyChangeModal} 
        onClose={closeDifficultyChangeModal} 
      /> */}
      {/* <ScenarioCompletionModal 
        isOpen={showScenarioCompletionModal}
        onClose={() => setShowScenarioCompletionModal(false)}
      /> */}
      
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
        {/* <button 
          className={`px-4 py-2 mx-2 font-mono rounded ${activeDisplay === 'joystick' ? 'bg-green-700 text-white' : 'bg-gray-800 text-green-500'}`}
          onClick={() => handleDisplayChange('joystick')}
        >
          操纵杆初始化
        </button> */}
      </div>
      
      <div className="flex flex-col lg:flex-row gap-8 px-4 max-w-8xl mx-auto">
        {/* 左侧显示区域 */}
        <div className={`w-full ${activeDisplay === 'joystick' ? 'lg:w-full' : 'lg:w-3/5'}`}>
          <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
            <h2 className="text-green-500 font-mono text-lg mb-4">
              {activeDisplay === 'radar' ? '雷达显示器' : 
               activeDisplay === 'navigation' ? 'SA页面' : '操纵杆初始化'}
            </h2>
            
            {activeDisplay === 'radar' ? (
              <Radar 
                width={700} 
                height={700} 
                onTargetSelect={handleTargetSelect}
                isStarted={isStarted}
                onRadarParamsUpdate={handleRadarParamsUpdate}
                onAddMessage={addMessage}
                onClearMessages={clearMessages}
                onNavigateToSA={() => handleDisplayChange('navigation')}
              />
            ) : activeDisplay === 'navigation' ? (
              <div className='flex justify-center'>
                <SAPage 
                  width={800} 
                  height={600} 
                  onAddMessage={addMessage}
                  onClearMessages={clearMessages}
                  userId={userId}
                  onResetSA={handleSATaskReset}
                  onThreatListUpdate={handleThreatListUpdate}
                  onShowDetailedInfoChange={handleShowDetailedInfoChange}
                />
              </div>
            ) : (
              <div className='flex justify-center'>
                <JoystickInitializationPage />
              </div>
            )}
          </div>
        </div>
        
        {/* 右侧内容 - 调整顺序：通信日志在最上面 */}
        {activeDisplay !== 'joystick' && (
          <div className="w-full lg:w-2/5 flex flex-col gap-4">
            {/* AI助手 - 放在最上面*/}
            {includeAI && (
                <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800">
                  <AIAssistant selectedTarget={selectedTarget} />
                </div>
              )}
            {/* 通信日志 - 固定高度 */}
            <div className="bg-gray-900 p-4 rounded-lg shadow-lg border border-gray-800" style={{ height: '500px' }}>
              <h2 className="text-green-500 font-mono text-lg mb-4">通信日志</h2>
                <CommunicationLog 
                  userId={userId} 
                  isStarted={isStarted} 
                  taskId={taskId}
                  currentTask={activeDisplay === 'navigation' ? 'sa' : 'radar'}
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
                  emergencyReceived={emergencyReceived}
                  lastEmergencyType={lastEmergencyType}
                  lastEmergencyTime={lastEmergencyTime}
                />
            </div>
            
         
            {/* 威胁列表 - 最下面，只在SA页面时显示 */}
            {activeDisplay === 'navigation' && (
              <ThreatList threats={threatListData} showDetailedInfo={showDetailedInfo} />
            )}
          </div>
        )}
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
          audio_enabled={infoToShow.audio_enabled}
        />
      )}
    </div>
  );
});

export default App; 