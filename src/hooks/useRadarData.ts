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
  distance_nm?: number; // 新增：原始距离（海里）
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
    type: 'SAEmergency' | 'SAUpgrade';
    event: 'upgrade' | 'missile';
    missileType?: 'MissileUp' | 'MissileDown';
    saThreats?: Array<{
      id: string;
      type: string;
      label: string;
    }>;
    receivedAt?: number; // 接收时间戳，用于生成唯一ID
    // 增强协议字段
    enhanced_data?: any;
    missile_threat?: any;
    updated_threats?: any;
    radar_config?: any;
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
      const rawData = JSON.parse(event.data);
      
      // 详细记录所有消息，特别关注重复调用的原因
      console.log('【全局WS】handleMessage被调用:', {
        messageType: rawData.type,
        timestamp: rawData.timestamp || 'no_timestamp',
        hasData: !!rawData.data,
        callTime: new Date().toISOString()
      });
      
      // 如果是操纵杆消息，额外记录详情
      if (rawData.type?.startsWith('joystick_') || rawData.type === 'joystick_status') {
        console.log('【操纵杆消息详情】:', {
          type: rawData.type,
          event: rawData.event,
          hasData: !!rawData.data,
          dataKeys: rawData.data ? Object.keys(rawData.data) : [],
          fullMessage: rawData
        });
        
        // 对于操纵杆消息，直接更新lastMessage并通知监听器
        this.lastMessage = rawData;
        this.updateState({
          ...this.state,
          // 不修改 radarData，只触发状态更新让监听器能收到消息
        });
        return; // 提前返回，不执行后续的雷达数据处理逻辑
      }
      
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
      } else if (rawData.type === 'platform_task_config') {
        const pid = rawData.normalized?.platform_task_id ?? rawData.raw?.ID;
        messageId += '_' + String(pid ?? Date.now());
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
            type: rawData.type,
            missileType: rawData?.missile_threat?.missile_type,
            saThreats: rawData.saThreats,
            // 添加接收时间戳作为唯一标识符
            receivedAt: Date.now()
        };
        
        // 如果是增强协议，添加增强数据字段
        if (rawData.enhanced_data || rawData.missile_threat || rawData.updated_threats) {
          console.log('【全局WS】处理增强SAEmergency消息');
          emergencyData = {
            ...emergencyData,
            // 保持原有字段的同时，添加增强数据
            enhanced_data: rawData.enhanced_data,
            missile_threat: rawData.missile_threat,
            updated_threats: rawData.updated_threats,
            radar_config: rawData.radar_config
          };
        }
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
  
  // 设置操纵杆数据更新频率

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
  difficulty?: string;
  is_ai_active?: boolean;
  previous_task_completed?: boolean;
  will_difficulty_change?: boolean;
}

export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE';

// 定义不同任务类型的进度状态接口
interface AllRepetitionInfos {
  RADAR_TARGETING: RepetitionInfo | 'ALL_COMPLETED' | null;
  SA_THREAT_RESPONSE: RepetitionInfo | 'ALL_COMPLETED' | null;
}

interface UseRadarDataOptions {
  // gazerelation: 仅在 Radar 组件实例中启用天线回合 WS；其他调用方保持关闭，避免多实例重复发送
  enableAntennaRound?: boolean;
}

// 修改后的useRadarData hook使用全局WebSocket管理器
const useRadarData = (
  wsUrl: string = 'ws://localhost:8080/ws',
  options: UseRadarDataOptions = {}
) => {
  const { enableAntennaRound = false } = options;
  const [connected, setConnected] = useState<boolean>(false);
  const [radarData, setRadarData] = useState<any>({});
  const [error, setError] = useState<string | null>(null);
  // gazerelation: 当前是否处于天线调整任务阶段（false->true 开启回合，true->false 结束回合）
  const [antennaAdjustmentRequired, setAntennaAdjustmentRequired] = useState(false);
  // gazerelation: 服务端要求的目标天线高度
  const [targetAntennaElevation, setTargetAntennaElevation] = useState<number | null>(null);
  // gazerelation: 当前回合是否已经上报过开始消息，避免重复上报
  const hasReportedAntennaPromptRef = useRef<boolean>(false);
  // gazerelation: 最近一次提示框 bbox 坐标（来自 CommunicationLog 广播）
  const lastAntennaPromptPositionRef = useRef<any>(null);
  // gazerelation: 回合序号，每次 Radar 激活后收到首个有效 bbox 时自增
  const antennaRoundIdRef = useRef<number>(0);
  // gazerelation: 当前回合是否激活；Radar 销毁时结束回合
  const antennaRoundActiveRef = useRef<boolean>(false);
  // gazerelation: 当前回合独立 WebSocket 连接实例
  const antennaRoundWsRef = useRef<WebSocket | null>(null);
  // gazerelation: 服务端返回的任务ID，结束消息时需要携带
  const antennaTaskIdRef = useRef<string | null>(null);
  // gazerelation: 当前回合是否已发送结束消息，避免“提前结束+卸载结束”重复发送
  const hasEndedRoundRef = useRef<boolean>(false);
  // gazerelation: SA最高威胁提示回合WS连接实例
  const saTobiiWsRef = useRef<WebSocket | null>(null);
  // gazerelation: SA回合任务ID（由Tobii服务返回）
  const saTobiiTaskIdRef = useRef<string | null>(null);
  // gazerelation: SA回合状态标记
  const saTobiiRoundActiveRef = useRef<boolean>(false);
  const saTobiiRoundStartedRef = useRef<boolean>(false);
  const saTobiiRoundEndedRef = useRef<boolean>(false);
  // gazerelation: SA回合最近一次bbox（用于结束请求复用）
  const lastSaTobiiPromptPositionRef = useRef<any>(null);
  const [saThreats, setSaThreats] = useState<any[]>([]); // 重新添加 saThreats 状态
  // 增强协议状态
  const [enhancedThreats, setEnhancedThreats] = useState<any[]>([]);
  const [serverRadarConfig, setServerRadarConfig] = useState<any>(null);
  const [useEnhancedProtocol, setUseEnhancedProtocol] = useState<boolean>(false);
    // 操纵杆相关状态
    const [joystickEnabled, setJoystickEnabled] = useState<boolean>(true); // 是否启用操纵杆，默认为是
    const [mainPos, setMainPos] = useState<{ x: number; y: number }>({ x: 0.0, y: 0.0 }); // 主轴位置
    const [subY, setSubY] = useState<number>(0.0); // 副轴Y坐标
    const [button1, setButton1] = useState<boolean>(false); // 按钮1状态
    const [button2, setButton2] = useState<boolean>(false); // 按钮2状态
    const [button7, setButton7] = useState<boolean>(false); // 按钮7状态
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

  /** 平台下发、服务端透传的 platform_task_config（含 raw / normalized） */
  const [platformTaskConfig, setPlatformTaskConfig] = useState<{
    raw: Record<string, unknown>;
    normalized: Record<string, unknown>;
  } | null>(null);

  /** 平台包触发的自动启动请求 */
  const [platformAutoStart, setPlatformAutoStart] = useState<{
    userId: string;
    taskType: 'radar' | 'sa';
    includeAI: boolean;
    isPractice: boolean;
  } | null>(null);

  // gazerelation: 统一构造 Tobii 回合消息体（与 Tobii main.py 的 hand 协议一致）
  const buildTobiiStatusPayload = useCallback((
    boxVisible: boolean,
    promptPosition: any,
    taskName: string
  ) => {
    const left = promptPosition?.left ?? 0.0;
    const top = promptPosition?.top ?? 0.0;
    const right = promptPosition?.right ?? left;
    const bottom = promptPosition?.bottom ?? top;
    const screenWidth = typeof window !== 'undefined' ? window.screen?.width ?? 0 : 0;
    const screenHeight = typeof window !== 'undefined' ? window.screen?.height ?? 0 : 0;

    // bbox 预留为集合，当前先上报一个提示框
    const bbox = [[left, top, right, bottom]];

    return {
      bbox,
      scream_data: [screenWidth, screenHeight],
      system_time: Date.now() * 1000, // 微秒
      box_visible: boxVisible,
      user_id: radarStore.userId || 1,
      task_source: 'web',
      task_name: taskName,
    };
  }, []);

  // gazerelation: 将提示框坐标统一转换为物理像素坐标（CSS像素 * DPR）
  const toPhysicalPromptPosition = useCallback((promptPosition: any) => {
    if (!promptPosition) return promptPosition;
    if (promptPosition?.gazeCoordinateSpace === 'physical') return promptPosition;

    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    const left = Number(promptPosition.left ?? 0);
    const top = Number(promptPosition.top ?? 0);
    const right = Number(promptPosition.right ?? left);
    const bottom = Number(promptPosition.bottom ?? top);
    const width = Number(promptPosition.width ?? Math.max(0, right - left));
    const height = Number(promptPosition.height ?? Math.max(0, bottom - top));

    return {
      ...promptPosition,
      x: Math.round(left * dpr),
      y: Math.round(top * dpr),
      left: Math.round(left * dpr),
      top: Math.round(top * dpr),
      right: Math.round(right * dpr),
      bottom: Math.round(bottom * dpr),
      width: Math.round(width * dpr),
      height: Math.round(height * dpr),
      gazeCoordinateSpace: 'physical',
      gazeDpr: dpr,
    };
  }, []);

  // gazerelation: 天线任务消息体
  const buildAntennaStatusPayload = useCallback((boxVisible: boolean, promptPosition?: any) => {
    const physicalPromptPosition = toPhysicalPromptPosition(promptPosition);
    return buildTobiiStatusPayload(boxVisible, physicalPromptPosition, 'demo_task');
  }, [buildTobiiStatusPayload, toPhysicalPromptPosition]);

  // gazerelation: 触发提示框高亮/闪烁事件
  const triggerAntennaPromptAttention = useCallback((durationMs: number = 3000) => {
    window.dispatchEvent(
      new CustomEvent('antenna-prompt-attention', {
        detail: {
          mode: 'flash_mode',
          durationMs,
          timestamp: Date.now(),
        },
      })
    );
  }, []);

  // gazerelation: 处理服务端消息，命中 flash_mode 或 should_flash 时触发闪烁
  const handleAntennaStatusResponse = useCallback((responseBody: any) => {
    const shouldFlash = responseBody?.should_flash === true || responseBody?.action === 'flash_mode';
    if (shouldFlash) {
      const durationMs = Number(responseBody?.duration_ms) || 3000;
      triggerAntennaPromptAttention(durationMs);
    }
  }, [triggerAntennaPromptAttention]);

  // gazerelation: 触发SA最高优先级目标闪烁事件
  const triggerSaHighestThreatAttention = useCallback((durationMs: number = 3000) => {
    window.dispatchEvent(
      new CustomEvent('sa-highest-threat-attention', {
        detail: {
          mode: 'flash_mode',
          durationMs,
          timestamp: Date.now(),
        },
      })
    );
  }, []);

  // gazerelation: 处理SA Tobii服务消息，命中 flash_mode 或 should_flash 时触发闪烁
  const handleSaTobiiResponse = useCallback((responseBody: any) => {
    const shouldFlash = responseBody?.should_flash === true || responseBody?.action === 'flash_mode';
    if (shouldFlash) {
      const durationMs = Number(responseBody?.duration_ms) || 3000;
      triggerSaHighestThreatAttention(durationMs);
    }
  }, [triggerSaHighestThreatAttention]);

  // gazerelation: 关闭当前回合 WS；可选先发送 hand(box_visible=false) 结束消息
  const closeAntennaRoundWs = useCallback((sendEndPayload: boolean) => {
    const ws = antennaRoundWsRef.current;
    if (!ws) return;

    if (sendEndPayload && ws.readyState === WebSocket.OPEN && antennaTaskIdRef.current) {
      const endPayload = buildAntennaStatusPayload(false, lastAntennaPromptPositionRef.current);
      ws.send(JSON.stringify({ type: 'tobii_hand', ...endPayload, task_id: antennaTaskIdRef.current }));
      console.log('[gazerelation] 天线回合WS发送结束消息:', endPayload);
      
      // 等待后端响应后再关闭连接
      const originalOnMessage = ws.onmessage as ((event: MessageEvent) => void) | null;
      
      // 监听后端响应
      ws.onmessage = (event: MessageEvent) => {
        try {
          const responseBody = JSON.parse(event.data);
          if (responseBody?.ok === true && responseBody?.msg?.includes('窗口消失')) {
            console.log('[gazerelation] 收到后端结束响应，关闭连接');
            try {
              ws.close();
            } catch (err) {
              console.error('[gazerelation] 关闭天线回合WS失败:', err);
            }
            antennaRoundWsRef.current = null;
          }
        } catch (err) {
          console.error('[gazerelation] 解析后端响应失败:', err);
        }
        if (originalOnMessage) {
          originalOnMessage(event);
        }
      };
      
      // 设置超时，确保连接最终会关闭
      setTimeout(() => {
        if (antennaRoundWsRef.current === ws) {
          console.log('[gazerelation] 超时，强制关闭连接');
          try {
            ws.close();
          } catch (err) {
            console.error('[gazerelation] 关闭天线回合WS失败:', err);
          }
          antennaRoundWsRef.current = null;
        }
      }, 3000);
    } else if (sendEndPayload && !antennaTaskIdRef.current) {
      console.warn('[gazerelation] 当前回合没有 task_id，跳过结束消息发送');
      try {
        ws.close();
      } catch (err) {
        console.error('[gazerelation] 关闭天线回合WS失败:', err);
      }
      antennaRoundWsRef.current = null;
    } else {
      try {
        ws.close();
      } catch (err) {
        console.error('[gazerelation] 关闭天线回合WS失败:', err);
      }
      antennaRoundWsRef.current = null;
    }
  }, [buildAntennaStatusPayload]);

  // gazerelation: 打开当前回合 Radar WS；连接成功后发送 hand(box_visible=true) 开始消息
  const openAntennaRoundWs = useCallback((roundId: number, promptPosition?: any) => {
    const hasValidPromptPosition = (pos: any): boolean =>
      !!pos &&
      typeof pos.left === 'number' &&
      typeof pos.top === 'number' &&
      typeof pos.right === 'number' &&
      typeof pos.bottom === 'number' &&
      !(pos.left === 0 && pos.top === 0 && pos.right === 0 && pos.bottom === 0);

    const sendStartRoundIfReady = () => {
      if (!hasValidPromptPosition(lastAntennaPromptPositionRef.current)) return;
      if (hasReportedAntennaPromptRef.current) return;
      if (!antennaRoundActiveRef.current || antennaRoundIdRef.current !== roundId) return;
      if (!antennaRoundWsRef.current || antennaRoundWsRef.current.readyState !== WebSocket.OPEN) return;
      hasReportedAntennaPromptRef.current = true;
      const startPayload = buildAntennaStatusPayload(true, lastAntennaPromptPositionRef.current);
      antennaRoundWsRef.current.send(JSON.stringify({ type: 'tobii_hand', ...startPayload }));
      console.log('[gazerelation] 天线回合WS发送开始消息:', startPayload);
    };

    closeAntennaRoundWs(false);
    if (promptPosition) {
      lastAntennaPromptPositionRef.current = promptPosition;
    }

    const ws = new WebSocket('ws://localhost:8082');
    antennaRoundWsRef.current = ws;
    // 处理 WS 连接成功事件
    ws.onopen = () => {
      if (!antennaRoundActiveRef.current || antennaRoundIdRef.current !== roundId) {
        closeAntennaRoundWs(false);
        return;
      }
      sendStartRoundIfReady();
      console.log('[gazerelation] 天线回合WS连接成功');
    };
    // 处理服务端消息，更新 task_id 并触发闪烁
    ws.onmessage = (event) => {
      if (!antennaRoundActiveRef.current || antennaRoundIdRef.current !== roundId) return;
      try {
        const responseBody = JSON.parse(event.data);
        if (responseBody?.task_id) {
          antennaTaskIdRef.current = String(responseBody.task_id);
        }
        handleAntennaStatusResponse(responseBody);
      } catch (err) {
        console.error('[gazerelation] 天线回合WS消息解析失败:', err);
      }
    };
    // 处理 WS 错误
    ws.onerror = (event) => {
      console.error('[gazerelation] 天线回合WS错误:', event);
    };

    ws.onclose = () => {
      if (antennaRoundWsRef.current === ws) {
        antennaRoundWsRef.current = null;
      }
    };
  }, [buildAntennaStatusPayload, closeAntennaRoundWs, handleAntennaStatusResponse]);

  // gazerelation: 开始SA最高优先级目标的Tobii回合
  const startSaTobiiRound = useCallback((promptPosition: any) => {
    const hasValidPromptPosition =
      !!promptPosition &&
      typeof promptPosition.left === 'number' &&
      typeof promptPosition.top === 'number' &&
      typeof promptPosition.right === 'number' &&
      typeof promptPosition.bottom === 'number' &&
      !(promptPosition.left === 0 && promptPosition.top === 0 && promptPosition.right === 0 && promptPosition.bottom === 0);

    if (!hasValidPromptPosition) return;
    if (saTobiiRoundStartedRef.current && !saTobiiRoundEndedRef.current) return;

    lastSaTobiiPromptPositionRef.current = promptPosition;
    saTobiiRoundActiveRef.current = true;
    saTobiiRoundStartedRef.current = false;
    saTobiiRoundEndedRef.current = false;
    saTobiiTaskIdRef.current = null;

    if (saTobiiWsRef.current) {
      try {
        saTobiiWsRef.current.close();
      } catch {
        // no-op
      }
      saTobiiWsRef.current = null;
    }

    const ws = new WebSocket('ws://localhost:8082');
    saTobiiWsRef.current = ws;
    ws.onopen = () => {
      if (!saTobiiRoundActiveRef.current || saTobiiRoundEndedRef.current) return;
      console.log(`[gazerelation] isAIActive111111: ${agentStore.isAIActive}`);
      if (agentStore.isAIActive) {
         const startPayload = buildTobiiStatusPayload(true, lastSaTobiiPromptPositionRef.current, 'sa_highest_priority_threat_withAI');
         ws.send(JSON.stringify({ type: 'tobii_hand', ...startPayload }));
         console.log('[gazerelation] SA Tobii回合发送开始消息:', startPayload);
      }
      else {
        const startPayload = buildTobiiStatusPayload(true, lastSaTobiiPromptPositionRef.current, 'sa_highest_priority_threat_noAI');
        ws.send(JSON.stringify({ type: 'tobii_hand', ...startPayload }));
        console.log('[gazerelation] SA Tobii回合发送开始消息:', startPayload);
      }
      saTobiiRoundStartedRef.current = true;
    };
    ws.onmessage = (event: MessageEvent) => {
      if (!saTobiiRoundActiveRef.current) return;
      try {
        const responseBody = JSON.parse(event.data);
        if (responseBody?.task_id) {
          saTobiiTaskIdRef.current = String(responseBody.task_id);
        }
        handleSaTobiiResponse(responseBody);
      } catch (err) {
        console.error('[gazerelation] SA Tobii回合消息解析失败:', err);
      }
    };
    ws.onerror = (event) => {
      console.error('[gazerelation] SA Tobii回合WS错误:', event);
    };
    ws.onclose = () => {
      if (saTobiiWsRef.current === ws) {
        saTobiiWsRef.current = null;
      }
    };
  }, [buildTobiiStatusPayload, handleSaTobiiResponse]);

  // gazerelation: 结束SA最高优先级目标的Tobii回合
  const endSaTobiiRound = useCallback((promptPosition?: any) => {
    if (saTobiiRoundEndedRef.current) return;
    saTobiiRoundEndedRef.current = true;
    saTobiiRoundActiveRef.current = false;

    if (promptPosition) {
      lastSaTobiiPromptPositionRef.current = promptPosition;
    }

    const ws = saTobiiWsRef.current;
    if (!ws) return;

    if (agentStore.isAIActive){
      
    }
    const endPayload = buildTobiiStatusPayload(
      false,
      lastSaTobiiPromptPositionRef.current,
      agentStore.isAIActive
    ? 'sa_highest_priority_threat_withAI'
    : 'sa_highest_priority_threat_noAI'
    );
    

    if (ws.readyState === WebSocket.OPEN) {
      const payload = saTobiiTaskIdRef.current
        ? { type: 'tobii_hand', ...endPayload, task_id: saTobiiTaskIdRef.current }
        : { type: 'tobii_hand', ...endPayload };
      ws.send(JSON.stringify(payload));
      console.log('[gazerelation] SA Tobii回合发送结束消息:', payload);

      const originalOnMessage = ws.onmessage as ((event: MessageEvent) => void) | null;
      ws.onmessage = (event: MessageEvent) => {
        try {
          const responseBody = JSON.parse(event.data);
          if (responseBody?.ok === true && responseBody?.msg?.includes('窗口消失')) {
            ws.close();
            saTobiiWsRef.current = null;
          }
        } catch {
          // no-op
        }
        if (originalOnMessage) {
          originalOnMessage(event);
        }
      };

      setTimeout(() => {
        if (saTobiiWsRef.current === ws) {
          try {
            ws.close();
          } catch {
            // no-op
          }
          saTobiiWsRef.current = null;
        }
      }, 3000);
      return;
    }

    try {
      ws.close();
    } catch {
      // no-op
    }
    saTobiiWsRef.current = null;
  }, [buildTobiiStatusPayload]);

  // gazerelation: 监听页面卸载事件刷新，尝试结束 天线 Tobii 回合
  useEffect(() => {
      const handleBeforeUnload = () => {
        // 尝试结束 天线 Tobii 回合
        if (antennaRoundActiveRef.current) {
          hasEndedRoundRef.current = true;
          antennaRoundActiveRef.current = false;
          closeAntennaRoundWs(true);
          hasReportedAntennaPromptRef.current = false;
        }
      };

      // 监听页面卸载事件
      window.addEventListener('beforeunload', handleBeforeUnload);
      
      return () => {
        window.removeEventListener('beforeunload', handleBeforeUnload);
      };
  }, [closeAntennaRoundWs, endSaTobiiRound]);

  // gazerelation: 新状态机
  // gazerelation: 1) Radar组件激活（hook实例启用）后，收到首个有效 bbox 才开启回合并发送开始消息
  // gazerelation: 2) Radar组件销毁（hook清理）时发送结束消息并断开连接
  useEffect(() => {
    if (!enableAntennaRound) return;// 仅在启用天线回合时处理
    const handlePromptPosition = async (event: Event) => {
      const customEvent = event as CustomEvent<{
        x: number;
        y: number;
        left: number;
        top: number;
        right: number;
        bottom: number;
        width: number;
        height: number;
        timestamp: number;
      }>;

      if (!customEvent.detail) return;
      const detail = customEvent.detail;
      const hasValidPromptPosition =
        typeof detail.left === 'number' &&
        typeof detail.top === 'number' &&
        typeof detail.right === 'number' &&
        typeof detail.bottom === 'number' &&
        !(detail.left === 0 && detail.top === 0 && detail.right === 0 && detail.bottom === 0);
      if (!hasValidPromptPosition) return;

      const physicalDetail = toPhysicalPromptPosition(detail);
      lastAntennaPromptPositionRef.current = physicalDetail;
      const ws = antennaRoundWsRef.current;
      if (!antennaRoundActiveRef.current) {
        antennaRoundIdRef.current += 1;
        antennaRoundActiveRef.current = true;
        hasReportedAntennaPromptRef.current = false;
        antennaTaskIdRef.current = null;
        hasEndedRoundRef.current = false;
        openAntennaRoundWs(antennaRoundIdRef.current, lastAntennaPromptPositionRef.current);
        return;
      }

      if (ws && ws.readyState === WebSocket.OPEN && !hasReportedAntennaPromptRef.current) {
        hasReportedAntennaPromptRef.current = true;
        const startPayload = buildAntennaStatusPayload(true, lastAntennaPromptPositionRef.current);
        ws.send(JSON.stringify({ type: 'tobii_hand', ...startPayload }));
        console.log('[gazerelation] 收到首个bbox后发送开始消息:', startPayload);
      }
    };

    window.addEventListener('antenna-prompt-position', handlePromptPosition as EventListener);
    return () => {
      window.removeEventListener('antenna-prompt-position', handlePromptPosition as EventListener);
      // gazerelation: Radar 组件销毁时，结束当前回合并断开WS
      if (antennaRoundActiveRef.current && !hasEndedRoundRef.current) {
        hasEndedRoundRef.current = true;
        antennaRoundActiveRef.current = false;
        closeAntennaRoundWs(true);
        hasReportedAntennaPromptRef.current = false;
      }
    };
  }, [enableAntennaRound, buildAntennaStatusPayload, closeAntennaRoundWs, openAntennaRoundWs]);

  // gazerelation: 若回合进行中且 antennaAdjustmentRequired 变为 true，则提前结束并发送结束消息
  useEffect(() => {
    if (!enableAntennaRound) return;
    if (!antennaAdjustmentRequired) return;
    if (!antennaRoundActiveRef.current) return;
    if (hasEndedRoundRef.current) return;

    hasEndedRoundRef.current = true;
    antennaRoundActiveRef.current = false;
    closeAntennaRoundWs(true);
    hasReportedAntennaPromptRef.current = false;
  }, [enableAntennaRound, antennaAdjustmentRequired, closeAntennaRoundWs]);
  
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
    console.log('自动设置 submitSettings', settings)
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
    setPlatformTaskConfig(null);
    sendMessage({ type: 'reset_view' });
    console.log("View reset command sent, data stream paused, and local state cleared.");
  }, [sendMessage]);

  
  // 处理接收到的消息
  const handleHookMessage = useCallback((message: any) => {
    if (!message || !message.type) {
      console.log('[useRadarData] ⚠️ 收到无效消息:', message);
      return;
    }

    console.log('[useRadarData] Processing message:', message);

    // 处理操纵杆数据消息
    if (message.type === 'joystick_data' && joystickEnabled) {
      console.log('[useRadarData] Processing joystick_data:', message.data);
      
      if (message.data) {
        // 更新主轴位置
        setMainPos({ 
          x: message.data.main_x || 0.0, 
          y: message.data.main_y || 0.0 
        });
        
        // 更新副轴Y坐标
        setSubY(message.data.sub_y || 0.0);
        
        // 更新按钮状态
        if (message.data.buttons) {
          setButton1(message.data.buttons.button0 || false);
          setButton2(message.data.buttons.button1 || false);
          setButton7(message.data.buttons.button7 || false);
        }
      }
    }

    // Handle AI parameter recommendations specifically
    if (message.type === 'ai_param_recommendation' && message.recommendation) {
      agentStore.setServerAIRecommendation(message.recommendation);
    } else if (message.ai_param_recommendation) { // Check if it's a field in another message type
        agentStore.setServerAIRecommendation(message.ai_param_recommendation);
    }

    // Handle other message types
    if (message.type === 'platform_task_config' && message.raw && message.normalized) {
      console.log('[useRadarData] platform_task_config from server:', message);
      setPlatformTaskConfig({ raw: message.raw, normalized: message.normalized });
      if (message.autostart) {
        const kind = message.normalized.web_task_kind;
        const taskType: 'radar' | 'sa' = kind === 'sa' ? 'sa' : 'radar';
        const userId = String(message.userId || message.normalized.platform_task_id || '');
        console.log('[useRadarData] platform autostart triggered:', { userId, taskType, includeAI: message.normalized.include_ai });
        setPlatformAutoStart({
          userId,
          taskType,
          includeAI: Boolean(message.normalized.include_ai),
          isPractice: Boolean(message.normalized.is_practice),
        });
      }
      return;
    }

    if (message.type === 'init_settings') {
      // Play sound only if it's a new task and the correct type
      // if (message.task_id !== radarStore.taskId && message.task_type === 'RADAR_TARGETING' && message.audio_enabled && !message.is_ai_active) {
      //   audioManager.play('radarRange');
      // }

      console.log('[useRadarData] Processing full init_settings from server:', message);
      if (message.platform_task?.raw && message.platform_task?.normalized) {
        setPlatformTaskConfig({
          raw: message.platform_task.raw,
          normalized: message.platform_task.normalized,
        });
      }
      
      // 1. 初始化AI和任务状态
      agentStore.initializeFromServer(message);
      
      // 2. 设置任务ID
      radarStore.setTaskId(message.task_id);

      // 3. 设置雷达参数供UI自动配置
      setInitSettings(message.settings);

      // 4. 设置任务重复信息（附带 task_id 供问卷触发使用）
      if (message.task_type && message.repetition_info) {
        console.log('[useRadarData] Received repetition_info:', message.repetition_info);
        setRepetitionInfos(prev => ({
          ...prev,
          [message.task_type]: { ...message.repetition_info, task_id: message.task_id },
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
      if (targetAntennaElevation === message.targetElevation && antennaAdjustmentRequired) return;
      console.log('[useRadarData] Received adjust_antenna message:', message);
      const ts = Date.now();
      setAntennaAdjustmentRequired(true);
      radarStore.setAntennaAdjustmentRequired(true);
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
      console.log('[useRadarData] 🎯 收到 sa_task_updated 消息!');
      console.log('[useRadarData] 完整消息内容:', message);
      console.log('[useRadarData] 消息字段:', Object.keys(message));
      
      // 检查是否是增强协议消息（包含threats数组和radar_config）
      if (message.threats && message.radar_config) {
        console.log('[useRadarData] 处理增强sa_task_updated消息:', message.threats.length, '个威胁');
        console.log('[useRadarData] 增强威胁详情:', message.threats);
        console.log('[useRadarData] 雷达配置:', message.radar_config);
        
        // 更新增强协议状态（确保原子性更新）
        console.log('[useRadarData] 开始更新增强协议状态...');
        setEnhancedThreats(message.threats);
        console.log('[useRadarData] ✓ enhancedThreats 已设置');
        setServerRadarConfig(message.radar_config);
        console.log('[useRadarData] ✓ serverRadarConfig 已设置');
        setUseEnhancedProtocol(true);
        console.log('[useRadarData] ✓ useEnhancedProtocol 已设置为 true');
        console.log('[useRadarData] 增强威胁数据已更新，协议切换为增强模式');
      } else if (message.saThreats) {
        // 传统协议消息，更新 saThreats 状态
        console.log('[useRadarData] 处理传统sa_task_updated消息:', message.saThreats.length, '个威胁');
        console.log('[useRadarData] 传统威胁详情:', message.saThreats);
        setSaThreats(message.saThreats);
        setUseEnhancedProtocol(false);
        console.log('[useRadarData] 传统威胁数据已更新，协议切换为传统模式');
      } else {
        console.warn('[useRadarData] sa_task_updated消息缺少威胁数据:', message);
      }
      
      if (message.task_type && message.repetition_info) {
        setRepetitionInfos(prev => ({
          ...prev,
          [message.task_type]: { ...message.repetition_info, task_id: message.task_id },
        }));
      }
      //  初始化AI和任务状态
      agentStore.initializeFromServer(message);
    } else if (message.type === 'SAEmergency') {
      console.log('[useRadarData] Received SAEmergency:', message);
      // 检查是否是增强协议的紧急事件
      if (message.updated_threats) {
        console.log('[useRadarData] 处理增强SAEmergency升级事件:', message.updated_threats.length, '个威胁');
        // 更新增强威胁数据
        setEnhancedThreats(message.updated_threats);
        setUseEnhancedProtocol(true);
      }
    } else if (message.type === 'all_tasks_completed') {
      console.log('[useRadarData] Received all_tasks_completed:', message);
      const completedTaskType = message.task_type as TaskType;
      if (completedTaskType) {
        setRepetitionInfos(prev => ({
          ...prev,
          [completedTaskType]: 'ALL_COMPLETED',
        }));
      }
    }
    // SAThreats and SAEmergency are typically part of the general radarData update, no specific handling here needed for AgentStore

  }, [recordOperation, targetAntennaElevation, antennaAdjustmentRequired, joystickEnabled]);
  
  const confirmAntennaAdjustmentHandled = useCallback(() => {
    console.log('Confirming to backend that antenna adjustment has been handled.');
    setAntennaAdjustmentRequired(false);
    setTargetAntennaElevation(null); // Reset the elevation state as the signal is handled
    console.log('[useRadarData] Antenna adjustment requirement handled and states reset.');
  }, []); // Dependencies: setAntennaAdjustmentRequired, setTargetAntennaElevation are stable from useState

  const changeAntennaAdjustmentRequired = useCallback((value: boolean) => {
    setAntennaAdjustmentRequired(value);
    radarStore.setAntennaAdjustmentRequired(value);
  }, [setAntennaAdjustmentRequired]);


  const lastProcessedMessageIdForHook = useRef<string>('');
  const lastProcessedEmergencyId = useRef<string>('');
  // gazerelation: 监听 externalTargets 变化所需的前次签名（跳过首次）
  const prevExternalTargetsSignatureRef = useRef<string>('');
  const externalTargetsFirstRunRef = useRef<boolean>(true);

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

  // 监听radarData.emergency变化，处理增强协议的紧急事件
  useEffect(() => {
    if (radarData?.emergency) {
      const emergencyId = JSON.stringify(radarData.emergency);
      if (emergencyId !== lastProcessedEmergencyId.current) {
        console.log('[useRadarData] 处理emergency变化:', radarData.emergency);
        
                 // 处理增强协议的升级事件
         if (radarData.emergency.event === 'upgrade' && radarData.emergency.updated_threats) {
           console.log('[useRadarData] 处理增强升级事件，更新威胁数据:', radarData.emergency.updated_threats.length);
           console.log('[useRadarData] 升级后的威胁详情:', radarData.emergency.updated_threats);
           setEnhancedThreats(radarData.emergency.updated_threats);
           setUseEnhancedProtocol(true);
           console.log('[useRadarData] 已设置useEnhancedProtocol=true');
           
           // 如果有radar_config，也更新它
           if (radarData.emergency.radar_config) {
             setServerRadarConfig(radarData.emergency.radar_config);
             console.log('[useRadarData] 已更新serverRadarConfig');
           }
         }
        
        lastProcessedEmergencyId.current = emergencyId;
      }
    }
  }, [radarData?.emergency]);

  // gazerelation: 监听 radarData.externalTargets 是否变化（按 id + position 签名对比）
  useEffect(() => {
    const externalTargets = radarData?.externalTargets ?? [];
    const signature = externalTargets
      .map((target: any) => {
        const x = target?.position?.x ?? 0;
        const y = target?.position?.y ?? 0;
        return `${target?.id ?? 'unknown'}:${x},${y}`;
      })
      .sort()
      .join('|');

    if (externalTargetsFirstRunRef.current) {
      externalTargetsFirstRunRef.current = false;
      prevExternalTargetsSignatureRef.current = signature;
      return;
    }

    if (signature !== prevExternalTargetsSignatureRef.current) {
      console.log('[gazerelation] radarData.externalTargets changed:', {
        previousCount: prevExternalTargetsSignatureRef.current
          ? prevExternalTargetsSignatureRef.current.split('|').filter(Boolean).length
          : 0,
        currentCount: externalTargets.length,
        timestamp: Date.now(),
      });
        if (
      enableAntennaRound &&
      antennaRoundActiveRef.current &&
      !hasEndedRoundRef.current
    ) {
      hasEndedRoundRef.current = true;
      antennaRoundActiveRef.current = false;
      hasReportedAntennaPromptRef.current = false;
      closeAntennaRoundWs(true);
    }
      prevExternalTargetsSignatureRef.current = signature;
    }
  }, [radarData?.externalTargets]);
  
  const sendResetSA = useCallback(() => {
    sendMessage({ type: 'ResetSA', timestamp: Date.now(), is_practice: radarStore.isPractice, is_ai_active: agentStore.isAIActive });
  }, [sendMessage]);

  // 操纵杆按钮状态的前一状态引用
  const previousButton1Ref = useRef(false);
  const previousButton2Ref = useRef(false);
  
  
  // button1 的锁定逻辑和 button2(IFF) 逻辑已移至 RadarDisplay.tsx 中直接处理


  // 操纵杆相关控制函数
  const resetJoystickData = useCallback(() => {
    setMainPos({ x: 0.0, y: 0.0 });
    setSubY(0.0);
    setButton1(false);
    setButton2(false);
    setButton7(false);
    
    // 重置状态引用
    previousButton1Ref.current = false;
    previousButton2Ref.current = false;
  }, []);

  
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
    repetitionInfos,
    saThreats,
    lastMessage: globalWS.getLastMessage(),
    // 增强协议相关
    enhancedThreats,
    setEnhancedThreats,
    serverRadarConfig,
    useEnhancedProtocol,
    // 操纵杆相关
    joystickEnabled,
    setJoystickEnabled,
    mainPos,
    subY,
    button1,
    button2,
    button7,
    resetJoystickData,
    changeAntennaAdjustmentRequired,
    startSaTobiiRound,
    endSaTobiiRound,
    platformTaskConfig,
    platformAutoStart,
  };
};

export default useRadarData;