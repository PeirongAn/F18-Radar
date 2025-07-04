import { useState, useEffect, useCallback, useRef } from 'react';
import { UnknownTargetData } from '../components/UnknownTarget';
import radarStore from '../stores/RadarStore';
import agentStore, { ServerAIParameterRecommendation } from '../stores/AgentStore'; // Import AgentStore and type
import audioManager from '../managers/AudioManager'; // 引入新的全局音频管理器

export interface TargetHistory {
  x: number;
  y: number;
}

// 定义雷达目标数据接口 - 统一为与UnknownTargetData类似的结构
export interface RadarTarget {
  id: string;
  position: { x: number, y: number };
  speed: number;
  direction: number; // 这是弧度
  direction_degrees?: number; // 预处理的导航坐标系角度（度数）
  type: 'friend' | 'army';
  quality?: number; // Make quality optional
  threat_level?: number; // Make threat_level optional
  threat_score?: number; // 后端计算的威胁评分
  history: { x: number, y: number }[];
  selected?: boolean;
  relative_heading?: number; // 新增：相对航向（度）
  trail_length?: number; // 新增：拖尾长度
}

export interface RadarData {
  targets: RadarTarget[];
  externalTargets?: UnknownTargetData[]; // 从服务端接收的未知目标数据
  externalTargetsTimestamp?: number | null; // 添加这个字段，记录接收时间
  saThreats?: Array<{
    id: string;
    type: string;
    label: string;
  }>;
  radar_azimuth: number;  // 雷达当前扫描方位角
  own_heading: number;    // 自机航向
  timestamp: number;      // 时间戳
  audioEnabled?: boolean;
  emergency?: {
    event: 'upgrade' | 'missile';
    missileType?: 'MissileUp' | 'MissileDown';
    saThreats?: Array<{
      id: string;
      type: string;
      label: string;
    }>;
    receivedAt?: number; // 接收时间戳，用于生成唯一ID
  };
  // 新增: 允许服务端直接发送AI参数建议
  ai_param_recommendation?: ServerAIParameterRecommendation;
}

export interface IFFResult {
  targetId: string;
  // ... existing code ...
}

// WebSocket连接状态类型
type WebSocketState = {
  connected: boolean;
  error: string | null;
  radarData: RadarData | null;
};

// 创建全局WebSocket管理器
class GlobalWebSocketManager {
  private static instance: GlobalWebSocketManager;
  private ws: WebSocket | null = null;
  private url: string = '';
  private state: WebSocketState = {
    connected: false,
    error: null,
    radarData: null
  };
  private listeners: Set<(state: WebSocketState) => void> = new Set();
  private reconnectTimeout: number | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private lastMessage: any = null; // 存储最后一条消息
  private lastMessageId: string = ''; // 存储最后一条消息的ID
  
  // 确保单例模式
  public static getInstance(): GlobalWebSocketManager {
    if (!GlobalWebSocketManager.instance) {
      GlobalWebSocketManager.instance = new GlobalWebSocketManager();
    }
    return GlobalWebSocketManager.instance;
  }
  
  // 初始化连接
  public connect(url: string) {
    if (this.ws && this.url === url && this.ws.readyState === WebSocket.OPEN) {
      console.log('【全局WS】WebSocket连接已存在');
      return;
    }
    
    this.url = url;
    this.createConnection();
  }
  
  // 创建WebSocket连接
  private createConnection() {
    try {
      console.log(`【全局WS】创建新WebSocket连接到: ${this.url}`);
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = this.handleOpen;
      this.ws.onmessage = this.handleMessage;
      this.ws.onerror = this.handleError;
      this.ws.onclose = this.handleClose;
    } catch (error) {
      console.error('【全局WS】创建WebSocket连接时出错:', error);
      this.updateState({
        ...this.state,
        connected: false,
        error: error instanceof Error ? error.message : '未知错误'
      });
      this.scheduleReconnect();
    }
  }
  
  // 处理连接打开
  private handleOpen = () => {
    console.log('【全局WS】WebSocket连接已成功打开');
    this.reconnectAttempts = 0;
    this.updateState({
      ...this.state,
      connected: true,
      error: null
    });
  };
  
  // 处理接收到的消息
  private handleMessage = (event: MessageEvent) => {
    try {
      console.log('【全局WS】收到消息:', event.data);
      const rawData = JSON.parse(event.data);
      
      // 添加调试日志 - 检查消息类型
      console.log('【调试】消息类型:', rawData.type);
      if (rawData.type === 'externalTargets') {
        console.log('【调试】收到 externalTargets 消息:', rawData);
      }
      
      // 生成消息的唯一标识
      let messageId = rawData.type;
      if (rawData.type === 'SAThreats' && rawData.saThreats) {
        messageId += '_' + JSON.stringify(rawData.saThreats.map((t:any) => t.id).sort());
      } else if (rawData.type === 'externalTargets' && rawData.externalTargets) {
        console.log('externalTargets agentStore.isAIActive', agentStore.isAIActive);
        if (agentStore.isAIActive) {
          audioManager.play('radarAISelect');
        }
        messageId += '_' + JSON.stringify(rawData.externalTargets.map((t:any) => t.id).sort());
      } else if (rawData.targetElevation !== undefined) {
        messageId += '_' + rawData.targetElevation;
      } else if (rawData.type === 'radar_data' && rawData.timestamp) {
        messageId += '_' + rawData.timestamp;
      }
      
      // 如果这个消息已经处理过，则跳过
      if (messageId === this.lastMessageId && rawData.type !== 'radar_data') {
        console.log('【全局WS】跳过已处理或重复的消息:', messageId);
        return;
      }
      
      // 更新最后处理的消息ID
      this.lastMessageId = messageId;
      this.lastMessage = rawData;
      
      // 处理 emergency 数据
      let emergencyData: RadarData['emergency'] | undefined = undefined;
      if (rawData.type === "SAEmergency") {
        // 如果消息类型本身是 SAEmergency，则从顶层字段构造 emergency 对象
        emergencyData = {
            event: rawData.event,
            missileType: rawData.missileType,
            saThreats: rawData.saThreats,
            // 添加接收时间戳作为唯一标识符
            receivedAt: Date.now()
        };
      } else if (rawData.emergency) {
        // 否则，如果 rawData 中有一个名为 emergency 的字段，则使用它
        emergencyData = {
          ...rawData.emergency,
          // 添加接收时间戳作为唯一标识符
          receivedAt: Date.now()
        };
      }
      
      // 创建一个新的数据对象
      const newData: RadarData = {
        // 对于列表数据，如果新消息中没有，则保留旧值
        targets: rawData.targets !== undefined ? rawData.targets : (this.state.radarData?.targets || []),
        
        // If the new message doesn't have externalTargets, it should be considered empty.
        externalTargets: rawData.externalTargets !== undefined ? rawData.externalTargets : [],

        externalTargetsTimestamp: rawData.externalTargets !== undefined ? Date.now() : null,
        saThreats: rawData.saThreats !== undefined ? rawData.saThreats : (this.state.radarData?.saThreats || []),
        
        // 对于数值数据，如果新消息中没有，则保留旧值或使用默认值
        radar_azimuth: rawData.radar_azimuth !== undefined ? rawData.radar_azimuth : (this.state.radarData?.radar_azimuth || 0),
        own_heading: rawData.own_heading !== undefined ? rawData.own_heading : (this.state.radarData?.own_heading || 0),
        
        // 时间戳通常随消息更新或取当前时间
        timestamp: rawData.timestamp || Date.now(),
        
        // 使用处理过的 emergencyData
        emergency: emergencyData,
        ai_param_recommendation: rawData.ai_param_recommendation // 如果rawData中没有，则为undefined
      };
      
      // 更新状态
      this.updateState({
        ...this.state,
        radarData: newData
      });
    } catch (error) {
      console.error('【全局WS】解析消息时出错:', error, event.data);
    }
  };
  
  // 处理错误
  private handleError = (event: Event) => {
    console.error('【全局WS】WebSocket错误:', event);
    this.updateState({
      ...this.state,
      error: '连接错误'
    });
  };
  
  // 处理连接关闭
  private handleClose = (event: CloseEvent) => {
    console.log(`【全局WS】WebSocket连接已关闭: code=${event.code}, reason=${event.reason}`);
    this.updateState({
      ...this.state,
      connected: false
    });
    
    // 尝试重新连接
    this.scheduleReconnect();
  };
  
  // 安排重新连接
  private scheduleReconnect() {
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
    }
    
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay = Math.min(3000 * Math.pow(1.5, this.reconnectAttempts), 30000);
      console.log(`【全局WS】将在 ${delay}ms 后尝试重新连接 (尝试 ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);
      
      this.reconnectTimeout = setTimeout(() => {
        this.reconnectAttempts++;
        this.createConnection();
      }, delay);
    } else {
      console.log('【全局WS】达到最大重连次数，停止尝试');
      this.updateState({
        ...this.state,
        error: '无法连接到服务器，请检查网络或刷新页面'
      });
    }
  }
  
  // 更新状态并通知所有监听器
  private updateState(newState: WebSocketState) {
    this.state = newState;
    this.listeners.forEach(listener => listener(this.state));
  }
  
  // 添加状态监听器
  public subscribe(listener: (state: WebSocketState) => void) {
    this.listeners.add(listener);
    // 立即通知新的监听器当前状态
    listener(this.state);
    
    // 返回取消订阅的函数
    return () => {
      this.listeners.delete(listener);
    };
  }
  
  // 修改sendMessage以优先使用消息中自带的event_owner
  public sendMessage(message: object) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const payload = {
        event_owner: agentStore.currentOperationOwner,
        ...message,
        user_id: radarStore.userId,
      };
      console.log('useRadarData sendMessage - Sending:', payload);
      this.ws.send(JSON.stringify(payload));
    } else {
      console.error('WebSocket is not connected.');
    }
  }
  
  // 关闭连接
  public disconnect() {
    if (this.ws) {
      console.log('【全局WS】关闭WebSocket连接');
      this.ws.close();
      this.ws = null;
    }
    
    if (this.reconnectTimeout !== null) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }
  
  // 获取当前状态
  public getState(): WebSocketState {
    return { ...this.state };
  }
  
  // 获取最后一条消息
  public getLastMessage(): any {
    return this.lastMessage;
  }
}

// 获取全局WebSocket实例
export const globalWS = GlobalWebSocketManager.getInstance();

// 定义任务进度的接口
export interface RepetitionInfo {
  current: number;
  total: number;
  scenario_index?: number;
  scenario_total?: number;
  is_practice?: boolean;
  audio_enabled?: boolean;
}

export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE';

// 定义不同任务类型的进度状态接口
interface AllRepetitionInfos {
  RADAR_TARGETING: RepetitionInfo | 'ALL_COMPLETED' | null;
  SA_THREAT_RESPONSE: RepetitionInfo | 'ALL_COMPLETED' | null;
}

// 修改后的useRadarData hook使用全局WebSocket管理器
const useRadarData = (wsUrl: string = 'ws://localhost:8765') => {
  const [connected, setConnected] = useState<boolean>(false);
  const [radarData, setRadarData] = useState<any>({});
  const [error, setError] = useState<string | null>(null);
  const [antennaAdjustmentRequired, setAntennaAdjustmentRequired] = useState(false);
  const [targetAntennaElevation, setTargetAntennaElevation] = useState<number | null>(null);
  const [saThreats, setSaThreats] = useState<any[]>([]); // 重新添加 saThreats 状态
  
  // 修改：任务重复信息状态，以支持多个任务类型
  const [repetitionInfos, setRepetitionInfos] = useState<AllRepetitionInfos>({
    RADAR_TARGETING: null,
    SA_THREAT_RESPONSE: null,
  });
  
  // 初始设置参数状态
  const [initSettings, setInitSettings] = useState<any>(null);
  const [initSettingsTimestamp, setInitSettingsTimestamp] = useState<number | null>(null);
  const [settingsValidationTimestamp, setSettingsValidationTimestamp] = useState<number | null>(null);
  
  // 当前有效的参数设置
  const [currentSettings, setCurrentSettings] = useState<{ range: number, scanAngle: number } | null>(null);
  
  // 记录操作到本地
  const [operations, setOperations] = useState<Array<{
    operationType: string;
    timestamp: number;
    isActive: boolean;
    parameters?: any;
  }>>([]);
  
  const clearInitSettings = useCallback(() => {
    setInitSettings(null);
  }, []);
  
  const resetAntennaAdjustment = useCallback(() => {
    setAntennaAdjustmentRequired(false);
    setTargetAntennaElevation(null);
  }, []);
  
  // 验证参数是否在推荐范围内
  const validateSettings = useCallback((settings: { range: number, scanAngle: number }) => {
    console.log('验证参数:', initSettings, settings);
    if (!initSettings) return false;
    
    const {range: recommended_range, scanAngle: recommended_scan_angle } = initSettings;
    const rangeTolerance = recommended_range * 0.2; // 允许20%的误差
    const angleTolerance = 10; // 允许10度的误差
    
    return Math.abs(settings.range - recommended_range) <= rangeTolerance &&
           Math.abs(settings.scanAngle - recommended_scan_angle) <= angleTolerance;
  }, [initSettings]);
  
  // 使用全局WebSocket管理器发送消息
  const sendMessage = useCallback((message: object) => {
    // 确保在发送时，如果消息本身带有event_owner，则使用它
    const payload = {
      event_owner: agentStore.currentOperationOwner, // 默认值
      ...message, // 传入的消息可以覆盖默认值
      user_id: radarStore.userId, // 修正：从 radarStore 获取 userId
    };
    globalWS.sendMessage(payload);
  }, []);
  
  // 记录操作
  const recordOperation = useCallback((operation: {
    operationType: string;
    timestamp: number;
    isActive: boolean;
    parameters?: any;
  }) => {
    console.log('记录操作:', operation);
    setOperations(prev => [...prev, operation]);
    
  }, []);
  
  // 初始化系统，请求任务ID和初始设置
  const initializeSystem = useCallback((userId: string, includeAI: boolean, isPractice: boolean) => {
    radarStore.setUserId(userId); // 修正：设置到 radarStore
    agentStore.setAIActive(includeAI);

    const initMessage = {
      type: 'task_start',
      user_id: userId,
      include_ai: includeAI,
      is_practice: isPractice, // 添加练习模式参数
    };
    sendMessage(initMessage);
    console.log('System initialization message sent:', initMessage);
    // Set a temporary task ID, the real one comes from the server in init_settings
    radarStore.setTaskId(new Date().getTime());
  }, [sendMessage]);
  
  // 发送参数设置给服务器
  const submitSettings = useCallback((settings: { range: number, scanAngle: number }) => {
    if (!connected) {
      console.error('WebSocket未连接');
      return;
    }

    // 验证参数是否在推荐范围内
    if (!validateSettings(settings)) {
      console.warn('参数设置无效，未发送到服务端');
      return;
    }

    const timestamp = Date.now();
    const settingsMessage = {
      type: 'settings_update',
      timestamp: timestamp,
      receive_timestamp: initSettingsTimestamp,  // 使用之前保存的时间戳
      user_id: radarStore.userId, // 添加用户ID
      ...settings,
    };

    console.log('发送设置更新:', settingsMessage);
    sendMessage(settingsMessage);
  }, [connected, sendMessage, initSettingsTimestamp, validateSettings]);
  
  // 添加重置目标函数
  const resetTargets = useCallback(() => {
    console.log("############radarData reset 222 #####");

    console.log('重置所有目标数据');
    // 发送重置目标的消息到服务器
    const resetMessage = {
      type: 'reset_targets'
    };
    globalWS.sendMessage(resetMessage);
    
    // 如果有本地缓存的目标数据，也一并清除
    if (radarData && radarData.externalTargets) {

      setRadarData({
        ...radarData,
        externalTargets: []
      });
    }
  }, [radarData]);
  
  const clearAndResetView = useCallback(() => {
    setRadarData(null); 
    // 重置所有任务次数信息
    setRepetitionInfos({ RADAR_TARGETING: null, SA_THREAT_RESPONSE: null });
    sendMessage({ type: 'reset_view' });
    console.log("View reset command sent, data stream paused, and local state cleared.");
  }, [sendMessage]);

  
  // 处理接收到的消息
  const handleHookMessage = useCallback((message: any) => {
    if (!message || !message.type) return;

    console.log('[useRadarData] Processing message:', message);

    // Handle AI parameter recommendations specifically
    if (message.type === 'ai_param_recommendation' && message.recommendation) {
      agentStore.setServerAIRecommendation(message.recommendation);
    } else if (message.ai_param_recommendation) { // Check if it's a field in another message type
        agentStore.setServerAIRecommendation(message.ai_param_recommendation);
    }

    // Handle other message types
    if (message.type === 'init_settings') {
      // Play sound only if it's a new task and the correct type
      if (message.task_id !== radarStore.taskId && message.task_type === 'RADAR_TARGETING' && message.audio_enabled && !message.is_ai_active) {
        audioManager.play('radarRange');
      }

      console.log('[useRadarData] Processing full init_settings from server:', message);
      
      // 1. 初始化AI和任务状态
      agentStore.initializeFromServer(message);
      
      // 2. 设置任务ID
      radarStore.setTaskId(message.task_id);

      // 3. 设置雷达参数供UI自动配置
      setInitSettings(message.settings);

      // 4. 设置任务重复信息
      if (message.task_type && message.repetition_info) {
        console.log('[useRadarData] Received repetition_info:', message.repetition_info);
        setRepetitionInfos(prev => ({
          ...prev,
          [message.task_type]: message.repetition_info,
        }));
      }

      // 5. 记录操作和时间戳
      const ts = Date.now();
      recordOperation({ operationType: 'init_settings_received', timestamp: ts, isActive: false, parameters: message.settings });
      setInitSettingsTimestamp(ts);


    } else if (message.type === 'settings_validation') {
      if ((window as any).__settingsTimeoutRef) clearTimeout((window as any).__settingsTimeoutRef.current);
      const ts = Date.now();
      recordOperation({ operationType: 'settings_validation_received', timestamp: ts, isActive: false, parameters: { status: message.status, message: message.message, settings: message.settings }});
    } else if (message.type === 'adjust_antenna') {
      // Only play sound if an adjustment is not already pending
      if (!antennaAdjustmentRequired && !agentStore.isAIActive) {
        audioManager.play('radarHeight'); // 播放提示音
      }
      if (targetAntennaElevation === message.targetElevation && antennaAdjustmentRequired) return;
      console.log('[useRadarData] Received adjust_antenna message:', message);
      const ts = Date.now();
      setAntennaAdjustmentRequired(true);
      setTargetAntennaElevation(message.targetElevation);
      radarStore.setTargetAntennaElevation(message.targetElevation, ts); // 传递接收时间戳
      recordOperation({ operationType: 'antenna_adjustment_required', timestamp: ts, isActive: false, parameters: { targetElevation: message.targetElevation }});
      setSettingsValidationTimestamp(ts);
    } else if (message.type === 'agent_level_data') {
      console.log('Received agent_level_data:', message.level, message.config);
      // agentStore.setCurrentAILevel(message.level); // Temporarily commented out to avoid type errors
    } else if (message.type === 'server_ai_recommendation') {
      console.log('Received server_ai_recommendation:', message.recommendation);
      agentStore.setServerAIRecommendation(message.recommendation);
    } else if (message.type === 'sa_task_updated') {
      console.log('[useRadarData] Received sa_task_updated:', message);
      // 更新 saThreats 状态
      if (message.saThreats) {
        setSaThreats(message.saThreats);
      }
      if (message.task_type && message.repetition_info) {
        setRepetitionInfos(prev => ({
          ...prev,
          [message.task_type]: message.repetition_info,
        }));
      }
      //  初始化AI和任务状态
      agentStore.initializeFromServer(message);
    } else if (message.type === 'all_tasks_completed') {
      console.log('[useRadarData] Received all_tasks_completed:', message);
      // 只有在正式模式下才显示任务完成弹窗
      if (!radarStore.isPractice) {
        // 检查此任务类型是否已弹窗过
        if (message.task_type && !radarStore.completedTaskTypes.has(message.task_type)) {
          radarStore.showCompletionModal(message.message);
          // 标记为已完成，防止重复弹窗
          radarStore.addCompletedTaskType(message.task_type);
        } else {
          console.log(`[useRadarData] Completion modal for ${message.task_type} has already been shown. Suppressing.`);
        }
      } else {
        console.log('[useRadarData] Practice mode: Suppressing completion modal.');
      }
    }
    // SAThreats and SAEmergency are typically part of the general radarData update, no specific handling here needed for AgentStore

  }, [recordOperation, targetAntennaElevation, antennaAdjustmentRequired]);
  
  const confirmAntennaAdjustmentHandled = useCallback(() => {
    console.log('Confirming to backend that antenna adjustment has been handled.');
    setAntennaAdjustmentRequired(false);
    setTargetAntennaElevation(null); // Reset the elevation state as the signal is handled
    console.log('[useRadarData] Antenna adjustment requirement handled and states reset.');
  }, []); // Dependencies: setAntennaAdjustmentRequired, setTargetAntennaElevation are stable from useState

  const lastProcessedMessageIdForHook = useRef<string>('');

  useEffect(() => {
    // 确保连接到指定URL
    globalWS.connect(wsUrl);
    
    // 自定义消息处理函数
    const processSubscribedState = (state: WebSocketState) => {
      setConnected(state.connected);
      setError(state.error);
      console.log("############radarData 111#####", state.radarData);
      
      // 处理雷达数据更新
      if (state.radarData) {
        setRadarData(state.radarData);
        
        // Process the most recent message that formed this radarData state IF it's new for the hook
        const latestMsgFromGlobal = globalWS.getLastMessage();
        if (latestMsgFromGlobal) {
            let currentMsgId = latestMsgFromGlobal.type; // Simple ID for now, could be enhanced
            if (latestMsgFromGlobal.timestamp) currentMsgId += '_' + latestMsgFromGlobal.timestamp;

            if (currentMsgId !== lastProcessedMessageIdForHook.current) {
                handleHookMessage(latestMsgFromGlobal);
                lastProcessedMessageIdForHook.current = currentMsgId;
            }
        }
      }
    };
    
    // 订阅状态变化
    const unsubscribe = globalWS.subscribe(processSubscribedState);
    
    // 清理函数 - 取消订阅，但不关闭连接
    return () => {
      unsubscribe();
    };
  }, [wsUrl, handleHookMessage]);
  
  const sendResetSA = useCallback(() => {
    sendMessage({ type: 'ResetSA', timestamp: Date.now(), is_practice: radarStore.isPractice, is_ai_active: agentStore.isAIActive });
  }, [sendMessage]);

  
  return { 
    connected, 
    radarData, 
    error, 
    sendMessage, 
    resetTargets,
    clearAndResetView,
    clearInitSettings,
    resetAntennaAdjustment,
    taskId: radarStore.taskId,
    initializeSystem,
    submitSettings,
    recordOperation,
    operations,
    antennaAdjustmentRequired,
    targetAntennaElevation,
    initSettings,
    currentSettings,
    settingsValidationTimestamp,
    validateSettings,
    userId: radarStore.userId,
    sendResetSA,
    confirmAntennaAdjustmentHandled,
    repetitionInfos, // 导出新的字典状态
    saThreats, // 确保导出 saThreats
    lastMessage: globalWS.getLastMessage(), // 导出最后一条消息
  };
};

export default useRadarData; 