import { useState, useEffect, useCallback, useRef } from 'react';
import { UnknownTargetData } from '../components/UnknownTarget';
import radarStore from '../stores/RadarStore';

export interface TargetHistory {
  x: number;
  y: number;
}

export interface RadarTarget {
  id: number;
  x: number;  // 相对位置 (NM)
  y: number;
  distance: number;  // 距离 (NM)
  bearing: number;   // 方位角 (度)
  heading: number;   // 航向 (度)
  speed: number;     // 速度 (节)
  quality: number;   // 跟踪质量 (0-1)
  threat_level: number; // 威胁等级 (0-3)
  history: [number, number][]; // 历史轨迹点 [x, y]
}

export interface RadarData {
  targets: RadarTarget[];
  externalTargets?: UnknownTargetData[]; // 从服务端接收的未知目标数据
  saThreats?: Array<{
    id: string;
    type: string;
    label: string;
  }>;
  radar_azimuth: number;  // 雷达当前扫描方位角
  own_heading: number;    // 自机航向
  timestamp: number;      // 时间戳
  emergency?: {
    event: 'upgrade' | 'missile';
    missileType?: 'MissileUp' | 'MissileDown';
    saThreats?: Array<{
      id: string;
      type: string;
      label: string;
    }>;
  };
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
      
      // 生成消息的唯一标识
      let messageId = rawData.type;
      if (rawData.type === 'SAThreats' && rawData.saThreats) {
        messageId += '_' + JSON.stringify(rawData.saThreats);
      } else if (rawData.targetElevation !== undefined) {
        messageId += '_' + rawData.targetElevation;
      }
      
      // 如果这个消息已经处理过，则跳过
      if (messageId === this.lastMessageId) {
        console.log('【全局WS】跳过已处理的消息:', messageId);
        return;
      }
      
      // 更新最后处理的消息ID
      this.lastMessageId = messageId;
      this.lastMessage = rawData;
      
      // 创建一个新的数据对象
      const newData: RadarData = {
        targets: [],
        radar_azimuth: rawData.radar_azimuth || 0,
        own_heading: rawData.own_heading || 0,
        timestamp: Date.now(),
      };
      
      // 处理externalTargets数据
      if ('externalTargets' in rawData && Array.isArray(rawData.externalTargets)) {
        newData.externalTargets = [...rawData.externalTargets];
        console.log('【全局WS】接收到externalTargets数据，数量:', newData.externalTargets.length);
      }
      
      // 处理saThreats数据
      if ('saThreats' in rawData && Array.isArray(rawData.saThreats)) {
        newData.saThreats = [...rawData.saThreats];
        console.log('【全局WS】接收到saThreats数据，数量:', newData.saThreats.length);
      }
      
      // 处理emergency数据
      if ('emergency' in rawData) {
        newData.emergency = { ...rawData.emergency };
        console.log('【全局WS】接收到emergency数据:', newData.emergency);
      }
      
      // 更新状态
      this.updateState({
        ...this.state,
        radarData: newData
      });
    } catch (error) {
      console.error('【全局WS】解析消息时出错:', error);
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
  
  // 发送消息
  public sendMessage(message: any, retryCount: number = 3, retryDelay: number = 300) {
    if (!this.ws) {
      console.warn('【全局WS】无法发送消息：WebSocket未初始化');
      return false;
    }
    
    // 检查连接状态
    if (this.ws.readyState !== WebSocket.OPEN) {
      // 如果连接未就绪但尝试次数仍然有剩余
      if (retryCount > 0 && this.ws.readyState === WebSocket.CONNECTING) {
        console.log(`【全局WS】连接尚未就绪，将在${retryDelay}ms后重试发送消息(剩余${retryCount}次)`);
        // 设置定时器延迟重试
        setTimeout(() => {
          this.sendMessage(message, retryCount - 1, retryDelay);
        }, retryDelay);
        return true; // 返回true表示消息将会被重试
      }
      
      console.warn(`【全局WS】无法发送消息：WebSocket未连接(状态:${this.ws.readyState})`);
      return false;
    }
    
    try {
      const messageStr = JSON.stringify(message);
      this.ws.send(messageStr);
      console.log('【全局WS】已发送消息:', message);
      return true;
    } catch (error) {
      console.error('【全局WS】发送消息时出错:', error);
      return false;
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

// 修改后的useRadarData hook使用全局WebSocket管理器
const useRadarData = (wsUrl: string = 'ws://localhost:8765') => {
  const [connected, setConnected] = useState<boolean>(false);
  const [radarData, setRadarData] = useState<RadarData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<number | null>(null);
  const [antennaAdjustmentRequired, setAntennaAdjustmentRequired] = useState(false);
  const [targetAntennaElevation, setTargetAntennaElevationState] = useState<number | null>(null);
  
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
  
  // 添加 userId 状态
  const [userId, setUserId] = useState<string | null>(radarStore.userId);
  
  // 监听 radarStore.userId 的变化
  useEffect(() => {
    console.log('radarStore.userId 变化:', radarStore.userId);
    setUserId(radarStore.userId);
  }, [radarStore.userId]);
  
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
  const sendMessage = useCallback((message: any) => {
    const success = globalWS.sendMessage(message);
    if (!success) {
      console.warn('消息发送失败，WebSocket未连接');
    }
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
  const initializeSystem = useCallback(() => {
    console.log('[雷达系统] 正在初始化雷达系统...');
    const timestamp = Date.now();
    
    // 先检查WebSocket连接状态
    const wsState = globalWS.getState();
    if (!wsState.connected) {
      console.error('[雷达系统] WebSocket未连接，无法初始化系统');
      return;
    }
    
    // 发送系统初始化请求
    const initMessage = {
      type: 'task_start',
      timestamp: timestamp,
      receive_timestamp: timestamp,
      user_id: radarStore.userId // 添加用户ID
    };
    
    console.log('[雷达系统] 发送初始化请求...');
    // 使用重试机制发送消息
    const success = globalWS.sendMessage(initMessage, 5, 200); // 最多重试5次，每次间隔200ms
    
    if (!success) {
      console.warn('[雷达系统] 初始化请求发送失败，WebSocket未连接');
    } else {
      console.log('[雷达系统] 初始化请求已发送');
    }
  }, [recordOperation]);
  
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
    console.log('重置所有目标数据');
    // 发送重置目标的消息到服务器
    const resetMessage = {
      type: 'reset_targets'
    };
    const success = globalWS.sendMessage(resetMessage);
    if (!success) {
      console.warn('重置目标消息发送失败，WebSocket未连接');
    }
    
    // 如果有本地缓存的目标数据，也一并清除
    if (radarData && radarData.externalTargets) {
      setRadarData({
        ...radarData,
        externalTargets: []
      });
    }
  }, [radarData]);
  
  // 处理接收到的消息
  const handleMessage = useCallback((message: any) => {
    console.log('处理接收到的消息:', message);
    
    if (message.type === 'task_id_assigned') {
      setTaskId(message.task_id);
      
    }
    else if (message.type === 'init_settings') {
      // 接收到初始设置参数
      console.log('收到初始设置参数:', message.settings);
      
      // 更新初始设置参数状态
      setInitSettings(message.settings);
      
      // 记录被动操作并保存时间戳
      const timestamp = Date.now();
      recordOperation({
        operationType: 'init_settings_received',
        timestamp: timestamp,
        isActive: false,
        parameters: message.settings
      });
      setInitSettingsTimestamp(timestamp);
  
    }
    else if (message.type === 'settings_validation') {
      if ((window as any).__settingsTimeoutRef) {
        clearTimeout((window as any).__settingsTimeoutRef.current);
        (window as any).__settingsTimeoutRef = null;
      }
      
      console.log('收到参数验证结果:', message);
      
      // 记录被动操作并保存时间戳
      const timestamp = Date.now();
      recordOperation({
        operationType: 'settings_validation_received',
        timestamp: timestamp,
        isActive: false,
        parameters: { 
          status: message.status, 
          message: message.message,
          settings: message.settings
        }
      });
     
    }
    else if (message.type === 'adjust_antenna') {
      // 检查是否已经处理过相同的目标高度
      if (targetAntennaElevation === message.targetElevation && antennaAdjustmentRequired) {
        console.log('已处理过相同的天线调整指令，忽略重复消息');
        return;
      }

      console.log('收到调整天线高度指令:', message);
      const timestamp = Date.now();
      console.log('setSettingsValidationTimestamp 收到调整天线高度指令:', timestamp);

      setAntennaAdjustmentRequired(true);
      setTargetAntennaElevationState(message.targetElevation);
      
      // 更新 RadarStore 中的目标天线高度
      radarStore.setTargetAntennaElevation(message.targetElevation);
      
      // 记录被动操作
      recordOperation({
        operationType: 'antenna_adjustment_required',
        timestamp,
        isActive: false,
        parameters: { targetElevation: message.targetElevation }
      });
      setSettingsValidationTimestamp(timestamp);
    }
    else if (message.type === 'SAThreats') {
      // 处理SA页面威胁数组
      setRadarData(prev => ({
        ...(prev || {
          targets: [],
          radar_azimuth: 0,
          own_heading: 0,
          timestamp: Date.now(),
        }),
        saThreats: Array.isArray(message.saThreats) ? message.saThreats : [],
      }));
    }
    else if (message.type === 'SAEmergency') {
      setRadarData(prev => {
        if (!prev) return null;
        return {
          ...prev,
          emergency: {
            event: message.event,
            missileType: message.missileType,
            saThreats: message.saThreats
          }
        };
      });
    }
  }, [recordOperation, setTaskId, setAntennaAdjustmentRequired, setTargetAntennaElevationState, targetAntennaElevation, antennaAdjustmentRequired]);
  
  // 使用全局WebSocket管理器并订阅状态变化
  const lastProcessedMessage = useRef<string>('');  // 添加 ref 来记录最后处理的消息

  useEffect(() => {
    // 确保连接到指定URL
    globalWS.connect(wsUrl);
    
    // 自定义消息处理函数
    const processMessage = (state: WebSocketState) => {
      setConnected(state.connected);
      setError(state.error);
      
      // 处理雷达数据更新
      if (state.radarData) {
        setRadarData(state.radarData);
      }
      
      // 处理其他类型的消息
      const lastMessage = globalWS.getLastMessage();
      if (lastMessage && typeof lastMessage === 'object') {
        console.log('跳过当前信息', lastMessage)
        // 生成消息的唯一标识，type+saThreats内容（如有）
        let messageId = lastMessage.type;
        if (lastMessage.type === 'SAThreats' && lastMessage.saThreats) {
          messageId += '_' + JSON.stringify(lastMessage.saThreats);
        } else if (lastMessage.targetElevation !== undefined) {
          messageId += '_' + lastMessage.targetElevation;
        }
        // 如果这个消息已经处理过，则跳过
        if (messageId === lastProcessedMessage.current) {
          console.log('跳过已处理的消息:', messageId);
          return;
        }
        // 更新最后处理的消息ID
        lastProcessedMessage.current = messageId;
        // 处理消息
        handleMessage(lastMessage);
      }
    };
    
    // 订阅状态变化
    const unsubscribe = globalWS.subscribe(processMessage);
    
    // 清理函数 - 取消订阅，但不关闭连接
    return () => {
      unsubscribe();
    };
  }, [wsUrl, handleMessage]);
  
  const sendResetSA = useCallback(() => {
    sendMessage({ type: 'ResetSA', timestamp: Date.now() });
  }, [sendMessage]);
  
  return { 
    connected, 
    radarData, 
    error, 
    sendMessage, 
    resetTargets,
    taskId,
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
    userId,
    sendResetSA
  };
};

export default useRadarData; 