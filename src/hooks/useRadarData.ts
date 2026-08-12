import { useState, useEffect, useCallback, useRef } from 'react';
import { UnknownTargetData } from '../components/UnknownTarget';
import radarStore from '../stores/RadarStore';
import agentStore, { ServerAIParameterRecommendation } from '../stores/AgentStore'; // Import AgentStore and type
import audioManager from '../managers/AudioManager'; // 引入新的全局音频管理器
import { normalizeTimestampMs } from '../utils/trustCalibration';
import type { TrustControlState } from '../types/trustControl';
import { clearTaskCompletionForStart } from '../utils/taskGroupCompletion';

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
  enhancedThreats?: any[];
  serverRadarConfig?: any;
  useEnhancedProtocol?: boolean;
  trustControl?: TrustControlState | null;
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
  private messageSequence: number = 0;
  
  // 确保单例模式
  public static getInstance(): GlobalWebSocketManager {
    if (!GlobalWebSocketManager.instance) {
      GlobalWebSocketManager.instance = new GlobalWebSocketManager();
    }
    return GlobalWebSocketManager.instance;
  }
  
  // 初始化连接
  public connect(url: string) {
    if (
      this.ws &&
      this.url === url &&
      (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)
    ) {
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
      const messageSequence = ++this.messageSequence;
      rawData.__message_seq = messageSequence;
      rawData.__received_at = Date.now();
      
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

      if (rawData.type === 'attention_feedback') {
        console.log('【全局WS】收到眼动注意力反馈:', rawData);
        this.lastMessage = rawData;
        this.updateState({
          ...this.state,
        });
        return;
      }

      if (
        rawData.type === 'radar_data'
        && rawData.task_id !== undefined
        && rawData.task_id !== null
        && radarStore.taskId !== null
        && String(rawData.task_id) !== String(radarStore.taskId)
      ) {
        console.log('[GlobalWS] Ignored radar data for another task:', {
          messageTaskId: rawData.task_id,
          currentTaskId: radarStore.taskId,
        });
        return;
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
      } else if (rawData.type === 'sa_task_updated') {
        const saCandidates = Array.isArray(rawData.threats)
          ? rawData.threats
          : Array.isArray(rawData.saThreats) ? rawData.saThreats : [];
        messageId += '_' + [
          rawData.task_id ?? 'pending',
          rawData.repetition_info?.current ?? 'unknown',
          rawData.repetition_info?.total ?? 'unknown',
          saCandidates.map((candidate: any) => candidate?.id).filter(Boolean).sort().join(','),
        ].join(':');
      } else if (rawData.type === 'init_settings') {
        const rep = rawData.repetition_info;
        messageId += '_' + [
          rawData.task_id ?? 'pending',
          rawData.task_type ?? 'unknown',
          rep?.current ?? 'unknown',
          rep?.total ?? 'unknown',
          rawData.timestamp ?? Date.now(),
        ].join(':');
      } else if (rawData.type === 'settings_validation') {
        messageId += '_' + [rawData.task_id ?? 'unknown', rawData.timestamp ?? messageSequence].join(':');
      } else if (rawData.type === 'all_tasks_completed') {
        messageId += '_' + [
          rawData.task_type ?? 'unknown',
          rawData.task_group_id ?? rawData.repetition_info?.task_group_id ?? rawData.task_id ?? 'unknown',
          rawData.timestamp ?? messageSequence,
        ].join(':');
      } else if (rawData.type === 'externalTargets' && rawData.externalTargets) {
        console.log('externalTargets agentStore.isAIActive', agentStore.isAIActive);
        if (agentStore.isAIActive) {
          audioManager.play('radarAISelect');
        }
        messageId += '_' + JSON.stringify(rawData.externalTargets.map((t:any) => t.id).sort());
      } else if (rawData.type === 'adjust_antenna' && rawData.targetElevation !== undefined) {
        messageId += '_' + rawData.targetElevation + '_' + messageSequence;
      } else if (rawData.targetElevation !== undefined) {
        messageId += '_' + rawData.targetElevation;
      } else if (rawData.type === 'radar_data' && rawData.timestamp) {
        messageId += '_' + rawData.timestamp;
      } else if (rawData.type === 'platform_task_config') {
        const pid = rawData.normalized?.platform_task_id ?? rawData.raw?.ID;
        const level = rawData.normalized?.current_level ?? rawData.normalized?.ai_autonomy_level ?? rawData.raw?.AIAutonomyLevel ?? rawData.raw?.AIAutonomyLeve;
        const difficulty = rawData.normalized?.difficulty_key ?? rawData.raw?.Difficulty;
        const taskNumber = rawData.normalized?.repetition_total_override ?? rawData.normalized?.task_number ?? rawData.raw?.TaskNumber;
        const taskKind = rawData.normalized?.web_task_kind ?? rawData.normalized?.task_type ?? rawData.raw?.TaskName;
        messageId += '_' + [pid ?? 'unknown', taskKind ?? 'unknown', level ?? 'unknown', difficulty ?? 'unknown', taskNumber ?? 'unknown'].join(':');
      } else if (rawData.type === 'attention_feedback' && rawData.server_time_ms) {
        messageId += '_' + rawData.server_time_ms;
      } else if (rawData.type === 'tobii_aoi_snapshot_result') {
        messageId += '_' + (rawData.client_snapshot_id ?? rawData.__message_seq);
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
      const shouldClearExternalTargets =
        rawData.type === 'init_settings' ||
        rawData.type === 'all_tasks_completed' ||
        rawData.type === 'reset_view';

      const shouldClearTargets = shouldClearExternalTargets;
      const isEnhancedSaUpdate =
        rawData.type === 'sa_task_updated' && Array.isArray(rawData.threats) && !!rawData.radar_config;
      const isLegacySaUpdate =
        rawData.type === 'sa_task_updated' && Array.isArray(rawData.saThreats);
      const enhancedThreatUpdate = Array.isArray(rawData.updated_threats)
        ? rawData.updated_threats
        : isEnhancedSaUpdate ? rawData.threats : undefined;

      const newData: RadarData = {
        // 对于列表数据，如果新消息中没有，则保留旧值
        targets: rawData.targets !== undefined
          ? rawData.targets
          : shouldClearTargets
            ? []
            : (this.state.radarData?.targets || []),
        
        // Preserve target returns across unrelated control/feedback messages.
        externalTargets: rawData.externalTargets !== undefined
          ? rawData.externalTargets
          : shouldClearExternalTargets
            ? []
            : (this.state.radarData?.externalTargets || []),

        externalTargetsTimestamp: rawData.externalTargets !== undefined
          ? Date.now()
          : shouldClearExternalTargets
            ? null
            : (this.state.radarData?.externalTargetsTimestamp ?? null),
        saThreats: isLegacySaUpdate
          ? rawData.saThreats
          : isEnhancedSaUpdate
            ? []
            : (this.state.radarData?.saThreats || []),
        enhancedThreats: enhancedThreatUpdate !== undefined
          ? enhancedThreatUpdate
          : isLegacySaUpdate
            ? []
            : (this.state.radarData?.enhancedThreats || []),
        serverRadarConfig: rawData.radar_config !== undefined
          ? rawData.radar_config
          : this.state.radarData?.serverRadarConfig,
        useEnhancedProtocol: isEnhancedSaUpdate || enhancedThreatUpdate !== undefined
          ? true
          : isLegacySaUpdate
            ? false
            : (this.state.radarData?.useEnhancedProtocol ?? false),
        // Keep the trial-start history with the persisted task snapshot.  SA can
        // mount after sa_task_updated has already arrived (for example after a
        // platform autostart); relying only on the transient raw message leaves
        // the history chart empty even though the server sent valid history.
        trustControl: rawData.trust_control !== undefined
          ? rawData.trust_control
          : rawData.type === 'all_tasks_completed' || rawData.type === 'reset_view'
            ? null
            : (this.state.radarData?.trustControl ?? null),
        
        // 对于数值数据，如果新消息中没有，则保留旧值或使用默认值
        radar_azimuth: rawData.radar_azimuth !== undefined ? rawData.radar_azimuth : (this.state.radarData?.radar_azimuth || 0),
        own_heading: rawData.own_heading !== undefined ? rawData.own_heading : (this.state.radarData?.own_heading || 0),
        
        // 时间戳通常随消息更新或取当前时间；兼容后端秒级和毫秒级时间戳
        timestamp: rawData.timestamp !== undefined
          ? normalizeTimestampMs(rawData.timestamp)
          : Date.now(),
        
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

  /**
   * A new SA trial has been requested but its authoritative task payload has
   * not arrived yet.  Drop the previous trial snapshot so candidates and AI
   * history are not reused during this gap.  The next sa_task_updated message
   * repopulates all of these fields together.
   */
  public clearSaTaskSnapshot() {
    if (!this.state.radarData) return;
    this.updateState({
      ...this.state,
      radarData: {
        ...this.state.radarData,
        saThreats: [],
        enhancedThreats: [],
        serverRadarConfig: undefined,
        useEnhancedProtocol: false,
        trustControl: null,
        emergency: undefined,
        timestamp: Date.now(),
      },
    });
  }
  
  // 修改sendMessage以优先使用消息中自带的event_owner
  public sendMessage(message: object): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const payload = {
        event_owner: agentStore.currentOperationOwner,
        ...message,
        user_id: radarStore.userId,
      };
      console.log('useRadarData sendMessage - Sending:', payload);
      this.ws.send(JSON.stringify(payload));
      return true;
    } else {
      console.error('WebSocket is not connected.');
      return false;
    }
  }

  public isOpen(): boolean {
    return !!this.ws && this.ws.readyState === WebSocket.OPEN;
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

export const getDefaultRadarWsUrl = (): string => {
  if (typeof window === 'undefined') return 'ws://localhost:8080/ws';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const hostname = window.location.hostname || 'localhost';
  return `${protocol}//${hostname}:8080/ws`;
};

// 定义任务进度的接口
export interface RepetitionInfo {
  current: number;
  total: number;
  task_id?: number;
  task_group_id?: number;
  scenario_index?: number;
  scenario_total?: number;
  is_practice?: boolean;
  audio_enabled?: boolean;
  difficulty?: string;
  is_ai_active?: boolean;
  previous_task_completed?: boolean;
  will_difficulty_change?: boolean;
}

export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

// 定义不同任务类型的进度状态接口
interface AllRepetitionInfos {
  RADAR_TARGETING: RepetitionInfo | 'ALL_COMPLETED' | null;
  SA_THREAT_RESPONSE: RepetitionInfo | 'ALL_COMPLETED' | null;
  PLATFORM_CONTROL: RepetitionInfo | 'ALL_COMPLETED' | null;
  WEAPON_FIRING: RepetitionInfo | 'ALL_COMPLETED' | null;
}

interface UseRadarDataOptions {
  // gazerelation: 仅在 Radar 组件实例中启用天线回合 WS；其他调用方保持关闭，避免多实例重复发送
  enableAntennaRound?: boolean;
}

// 修改后的useRadarData hook使用全局WebSocket管理器
const useRadarData = (
  wsUrl: string = getDefaultRadarWsUrl(),
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
    const [button3, setButton3] = useState<boolean>(false); // 按钮3状态：人工复核
    const [button7, setButton7] = useState<boolean>(false); // 按钮7状态
    const [joystickConnected, setJoystickConnected] = useState<boolean>(false);
    const [trustControl, setTrustControl] = useState<TrustControlState | null>(null);
  // 修改：任务重复信息状态，以支持多个任务类型
  const [repetitionInfos, setRepetitionInfos] = useState<AllRepetitionInfos>({
    RADAR_TARGETING: null,
    SA_THREAT_RESPONSE: null,
    PLATFORM_CONTROL: null,
    WEAPON_FIRING: null,
  });
  // Preserve group completion independently from repetitionInfos. The next
  // init_settings can otherwise overwrite ALL_COMPLETED in the same render.
  const [lastTaskGroupCompletion, setLastTaskGroupCompletion] = useState<any>(null);
  
  // 初始设置参数状态
  const [initSettings, setInitSettings] = useState<any>(null);
  const [initSettingsTimestamp, setInitSettingsTimestamp] = useState<number | null>(null);
  const [settingsValidationTimestamp, setSettingsValidationTimestamp] = useState<number | null>(null);
  const submittedSettingsKeysRef = useRef<Set<string>>(new Set());
  
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
    useJoystick: boolean;
    taskNumber?: number;
    autonomyLevel?: string;
    requestId: string;
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
    // bbox 预留为集合，当前先上报一个提示框
    const bbox = [[left, top, right, bottom]];
    const coordinateSpace = promptPosition?.gazeCoordinateSpace === 'physical'
      ? 'physical_pixel'
      : (promptPosition?.gazeCoordinateSpace || 'display_area_normalized');
    const regions = [{ shape: 'rect', left, top, right, bottom }];
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;

    return {
      bbox,
      regions,
      coordinate_space: coordinateSpace,
      ...(coordinateSpace === 'physical_pixel' ? {
        screen_data: [
          typeof window !== 'undefined' ? Math.round((window.screen?.width ?? 0) * dpr) : 0,
          typeof window !== 'undefined' ? Math.round((window.screen?.height ?? 0) * dpr) : 0,
        ],
      } : {}),
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
    if (
      promptPosition?.gazeCoordinateSpace === 'physical' ||
      promptPosition?.gazeCoordinateSpace === 'physical_pixel' ||
      promptPosition?.gazeCoordinateSpace === 'display_area_normalized'
    ) return promptPosition;

    const viewportWidth = typeof window !== 'undefined' ? Math.max(1, window.innerWidth || 1) : 1;
    const viewportHeight = typeof window !== 'undefined' ? Math.max(1, window.innerHeight || 1) : 1;
    const left = Number(promptPosition.left ?? 0);
    const top = Number(promptPosition.top ?? 0);
    const right = Number(promptPosition.right ?? left);
    const bottom = Number(promptPosition.bottom ?? top);
    const width = Number(promptPosition.width ?? Math.max(0, right - left));
    const height = Number(promptPosition.height ?? Math.max(0, bottom - top));

    return {
      ...promptPosition,
      x: left / viewportWidth,
      y: top / viewportHeight,
      left: left / viewportWidth,
      top: top / viewportHeight,
      right: right / viewportWidth,
      bottom: bottom / viewportHeight,
      width: width / viewportWidth,
      height: height / viewportHeight,
      gazeCoordinateSpace: 'display_area_normalized',
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

  const sendTobiiHandMessage = useCallback((payload: any, label: string) => {
    const message = { type: 'tobii_hand', ...payload };
    console.log('[gazerelation] tobii_hand payload fields', {
      label,
      task_id: message.task_id,
      coordinate_space: message.coordinate_space,
      bbox: message.bbox,
      regions: message.regions,
      screen_data: message.screen_data,
    });
    globalWS.connect(wsUrl);
    let attempts = 0;
    const trySend = () => {
      if (globalWS.isOpen() && globalWS.sendMessage(message)) return;
      attempts += 1;
      if (attempts >= 20) {
        console.warn(`[gazerelation] ${label} send skipped because global WS is not open`, message);
        return;
      }
      window.setTimeout(trySend, 100);
    };
    trySend();
  }, [wsUrl]);

  // gazerelation: 关闭当前回合 WS；可选先发送 hand(box_visible=false) 结束消息
  const closeAntennaRoundWs = useCallback((sendEndPayload: boolean) => {
    if (sendEndPayload && antennaTaskIdRef.current) {
      const endPayload = buildAntennaStatusPayload(false, lastAntennaPromptPositionRef.current);
      sendTobiiHandMessage({ ...endPayload, task_id: antennaTaskIdRef.current }, 'antenna end');
      console.log('[gazerelation] antenna round sent end message through global WS:', endPayload);
    } else if (sendEndPayload && !antennaTaskIdRef.current) {
      console.warn('[gazerelation] antenna round has no task_id, skip end message');
    }
    antennaRoundWsRef.current = null;
  }, [buildAntennaStatusPayload, sendTobiiHandMessage]);

  // gazerelation: 打开当前回合 Radar WS；连接成功后发送 tobii_hand(box_visible=true) 消息
  const openAntennaRoundWs = useCallback((roundId: number, promptPosition?: any) => {
    const hasValidPromptPosition = (pos: any): boolean =>
      !!pos &&
      typeof pos.left === 'number' &&
      typeof pos.top === 'number' &&
      typeof pos.right === 'number' &&
      typeof pos.bottom === 'number' &&
      !(pos.left === 0 && pos.top === 0 && pos.right === 0 && pos.bottom === 0);

    closeAntennaRoundWs(false);
    if (promptPosition) {
      lastAntennaPromptPositionRef.current = promptPosition;
    }

    if (!hasValidPromptPosition(lastAntennaPromptPositionRef.current)) return;
    if (hasReportedAntennaPromptRef.current) return;
    if (!antennaRoundActiveRef.current || antennaRoundIdRef.current !== roundId) return;

    hasReportedAntennaPromptRef.current = true;
    const startPayload = buildAntennaStatusPayload(true, lastAntennaPromptPositionRef.current);
    sendTobiiHandMessage(startPayload, 'antenna start');
    console.log('[gazerelation] antenna round sent start message through global WS:', startPayload);
  }, [buildAntennaStatusPayload, closeAntennaRoundWs, sendTobiiHandMessage]);

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
    saTobiiRoundStartedRef.current = true;
    saTobiiRoundEndedRef.current = false;
    saTobiiTaskIdRef.current = null;
    saTobiiWsRef.current = null;

    const startPayload = buildTobiiStatusPayload(
      true,
      lastSaTobiiPromptPositionRef.current,
      'sa_highest_priority_threat_noAI'
    );
    sendTobiiHandMessage(startPayload, 'sa tobii start');
    console.log('[gazerelation] SA Tobii round sent start message through global WS:', startPayload);
  }, [buildTobiiStatusPayload, sendTobiiHandMessage]);

  // gazerelation: 结束SA最高优先级目标的Tobii回合
  const endSaTobiiRound = useCallback((promptPosition?: any) => {
    if (!saTobiiRoundStartedRef.current || saTobiiRoundEndedRef.current) return;
    saTobiiRoundEndedRef.current = true;
    saTobiiRoundActiveRef.current = false;

    if (promptPosition) {
      lastSaTobiiPromptPositionRef.current = promptPosition;
    }

    const endPayload = buildTobiiStatusPayload(
      false,
      lastSaTobiiPromptPositionRef.current,
      'sa_highest_priority_threat_noAI'
    );
    sendTobiiHandMessage(
      saTobiiTaskIdRef.current ? { ...endPayload, task_id: saTobiiTaskIdRef.current } : endPayload,
      'sa tobii end'
    );
    console.log('[gazerelation] SA Tobii round sent end message through global WS:', endPayload);
    saTobiiWsRef.current = null;
  }, [buildTobiiStatusPayload, sendTobiiHandMessage]);

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
      if (!antennaRoundActiveRef.current) {
        antennaRoundIdRef.current += 1;
        antennaRoundActiveRef.current = true;
        hasReportedAntennaPromptRef.current = false;
        antennaTaskIdRef.current = null;
        hasEndedRoundRef.current = false;
        openAntennaRoundWs(antennaRoundIdRef.current, lastAntennaPromptPositionRef.current);
        return;
      }

      if (!hasReportedAntennaPromptRef.current) {
        hasReportedAntennaPromptRef.current = true;
        const startPayload = buildAntennaStatusPayload(true, lastAntennaPromptPositionRef.current);
        sendTobiiHandMessage(startPayload, 'antenna start');
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
  }, [enableAntennaRound, buildAntennaStatusPayload, closeAntennaRoundWs, openAntennaRoundWs, sendTobiiHandMessage]);

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
  const initializeSystem = useCallback((userId: string, includeAI: boolean, isPractice: boolean, taskNumber?: number) => {
    radarStore.setUserId(userId); // 修正：设置到 radarStore
    agentStore.setAIActive(includeAI);

    const initMessage = {
      type: 'task_start',
      user_id: userId,
      include_ai: includeAI,
      is_practice: isPractice, // 添加练习模式参数
      task_number: taskNumber,
      repetition_total_override: taskNumber,
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

    const settingsKey = `${radarStore.taskId || 'pending'}:${settings.range}:${settings.scanAngle}`;
    if (submittedSettingsKeysRef.current.has(settingsKey)) {
      console.log('[useRadarData] 跳过重复 settings_update:', settingsKey);
      return;
    }
    submittedSettingsKeysRef.current.add(settingsKey);

    const timestamp = Date.now();
    const settingsMessage = {
      type: 'settings_update',
      task_id: radarStore.taskId,
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
    setRepetitionInfos({ RADAR_TARGETING: null, SA_THREAT_RESPONSE: null, PLATFORM_CONTROL: null, WEAPON_FIRING: null });
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

    if (message.type === 'attention_feedback') {
      console.log('[useRadarData] Processing gaze attention feedback:', message);
      if (enableAntennaRound && antennaRoundActiveRef.current) {
        handleAntennaStatusResponse(message);
      }
      if (saTobiiRoundActiveRef.current) {
        handleSaTobiiResponse(message);
      }
      return;
    }

    if (message.type === 'tobii_hand_result') {
      if (message?.task_id) {
        if (antennaRoundActiveRef.current && !antennaTaskIdRef.current) {
          antennaTaskIdRef.current = String(message.task_id);
        }
        if (saTobiiRoundActiveRef.current && !saTobiiTaskIdRef.current) {
          saTobiiTaskIdRef.current = String(message.task_id);
        }
      }
      if (enableAntennaRound && antennaRoundActiveRef.current) {
        handleAntennaStatusResponse(message);
      }
      if (saTobiiRoundActiveRef.current) {
        handleSaTobiiResponse(message);
      }
      return;
    }

    // 处理操纵杆数据消息
    if (message.type === 'joystick_data' && joystickEnabled) {
      console.log('[useRadarData] Processing joystick_data:', message.data);
      
      if (message.data) {
        setJoystickConnected(message.device_status !== 'disconnected');
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
          // pygame/DirectInput uses zero-based indexes: physical key 3 is button2.
          setButton3(message.data.buttons.button2 || false);
          setButton7(message.data.buttons.button7 || false);
        }
      }
    }

    const isJoystickLifecycleStatus =
      message.type === 'joystick_connect_response' ||
      message.type === 'joystick_disconnect_response' ||
      message.type === 'joystick_status_response' ||
      (
        message.type === 'joystick_status' &&
        ['device_connected', 'device_disconnected', 'device_connection_failed'].includes(message.event)
      );
    if (isJoystickLifecycleStatus) {
      const statusValue = message.status?.device_status ?? message.status?.status ?? message.device_status;
      const deviceConnected = message.type === 'joystick_disconnect_response'
        ? false
        : message.event === 'device_connected' ||
          message.connected === true ||
          statusValue === 'connected' ||
          (message.type === 'joystick_connect_response' && message.success === true);
      setJoystickConnected(deviceConnected);
      if (!deviceConnected) {
        setButton1(false);
        setButton2(false);
        setButton3(false);
        setButton7(false);
      }
    }

    if ((message.type === 'init_settings' || message.type === 'sa_task_updated') && message.trust_control) {
      setTrustControl(message.trust_control as TrustControlState);
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
        const internalTaskType = taskType === 'sa' ? 'SA_THREAT_RESPONSE' : 'RADAR_TARGETING';
        // This message arrives before init_settings. Clear the old group's
        // completion now so a user/group switch cannot replay ALL_COMPLETED.
        setRepetitionInfos(previous => clearTaskCompletionForStart(previous, internalTaskType));
        setLastTaskGroupCompletion(null);
        const userId = String(message.userId || message.normalized.platform_task_id || '');
        console.log('[useRadarData] platform autostart triggered:', { userId, taskType, includeAI: message.normalized.include_ai });
        const rawTaskNumber = message.normalized.repetition_total_override ?? message.normalized.task_number;
        const parsedTaskNumber = Number(rawTaskNumber);
        const taskNumber = Number.isFinite(parsedTaskNumber) && parsedTaskNumber > 0
          ? Math.max(1, Math.floor(parsedTaskNumber))
          : undefined;
        const autonomyLevel = String(
          message.normalized.current_level ?? message.normalized.ai_autonomy_level ?? ''
        ) || undefined;
        const requestId = `platform:${[
          message.normalized.platform_task_id ?? message.raw.ID ?? userId,
          message.normalized.web_task_kind ?? message.normalized.task_type ?? taskType,
          autonomyLevel ?? 'unknown',
          message.normalized.difficulty_key ?? message.raw.Difficulty ?? 'unknown',
          taskNumber ?? 'unknown',
        ].join(':')}`;
        setPlatformAutoStart({
          userId,
          taskType,
          includeAI: Boolean(message.normalized.include_ai),
          isPractice: Boolean(message.normalized.is_practice),
          useJoystick: message.useJoystick !== false,
          taskNumber,
          autonomyLevel,
          requestId,
        });
      }
      return;
    }

    if (message.type === 'init_settings') {
      console.log('[useRadarData] Processing full init_settings from server:', message);
      // 每一轮新任务开始都重置雷达参数提交去重集合。
      // 该去重原本只为防止同一轮内重复提交，但 key 为 `${taskId}:${range}:${scanAngle}`，
      // 当服务端在同一场景的多轮重复中复用相同 task_id 时会跨轮误命中，
      // 导致第 2 轮及以后的 settings_update 被静默跳过、雷达参数无法自动设置。
      submittedSettingsKeysRef.current.clear();
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

      // 每次传感器任务开始时，天线高度从 0 开始，避免沿用上一轮调整结果。
      if (message.task_type === 'RADAR_TARGETING') {
        radarStore.setCurrentAntennaElevation(0, 'server');
        setAntennaAdjustmentRequired(false);
        radarStore.setAntennaAdjustmentRequired(false);
        setTargetAntennaElevation(null);
        radarStore.setTargetAntennaElevation(null);
      }

      // 3. 设置雷达参数供UI自动配置；保留轮次元信息，确保相同参数的新一轮也会被处理。
      const enrichedInitSettings = {
        ...(message.settings || {}),
        __task_id: message.task_id,
        __task_type: message.task_type,
        __repetition_current: message.repetition_info?.current,
        __repetition_total: message.repetition_info?.total,
        __message_seq: message.__message_seq,
        __received_at: message.__received_at ?? Date.now(),
      };
      setInitSettings(enrichedInitSettings);
      if (typeof window !== 'undefined' && message.task_type === 'RADAR_TARGETING') {
        window.dispatchEvent(new CustomEvent('radar:init_settings', { detail: enrichedInitSettings }));
      }

      // 4. 设置任务重复信息（附带 task_id 供问卷触发使用）
      if (message.task_type && message.repetition_info) {
        console.log('[useRadarData] Received repetition_info:', message.repetition_info);
        setRepetitionInfos(prev => ({
          ...prev,
          [message.task_type]: {
            ...message.repetition_info,
            task_id: message.task_id,
            autonomy_level: message.repetition_info.autonomy_level ?? message.ai_level,
          },
        }));
      }

      // 5. 记录操作和时间戳
      const ts = Date.now();
      recordOperation({ operationType: 'init_settings_received', timestamp: ts, isActive: false, parameters: message.settings });
      setInitSettingsTimestamp(ts);


    } else if (message.type === 'settings_validation') {
      if ((window as any).__settingsTimeoutRef) clearTimeout((window as any).__settingsTimeoutRef.current);
      if (message.status === 'ignored') {
        console.log('[useRadarData] Ignored stale settings validation:', message.message);
        return;
      }
      if (
        message.task_id !== undefined
        && message.task_id !== null
        && radarStore.taskId !== null
        && String(message.task_id) !== String(radarStore.taskId)
      ) {
        console.log('[useRadarData] Ignored settings validation for another task:', {
          messageTaskId: message.task_id,
          currentTaskId: radarStore.taskId,
        });
        return;
      }
      const ts = Date.now();
      recordOperation({ operationType: 'settings_validation_received', timestamp: ts, isActive: false, parameters: { status: message.status, message: message.message, settings: message.settings }});
    } else if (message.type === 'adjust_antenna') {
      const antennaCommandKey = message.__message_seq !== undefined
        ? `seq_${message.__message_seq}`
        : `${radarStore.taskId || 'pending'}:${message.targetElevation}`;
      if (lastAntennaCommandKeyRef.current === antennaCommandKey && targetAntennaElevation === message.targetElevation && antennaAdjustmentRequired) return;
      lastAntennaCommandKeyRef.current = antennaCommandKey;
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
      if (message.task_id !== undefined && message.task_id !== null) {
        radarStore.setTaskId(message.task_id);
      }

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
          [message.task_type]: {
            ...message.repetition_info,
            task_id: message.task_id,
            autonomy_level: message.repetition_info.autonomy_level ?? message.ai_level,
          },
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
        const completedGroupId = message.task_group_id ?? message.repetition_info?.task_group_id;
        if (completedGroupId === undefined || completedGroupId === null) {
          // Only the backend-marked task-entry case should show the completed
          // notice.  Other group-less messages remain stale/invalid events.
          if (message.entry_completed === true) {
            setLastTaskGroupCompletion({
              ...message,
              entry_completed: true,
              received_at: Date.now(),
            });
            return;
          }
          console.warn('[useRadarData] Ignored group-less all_tasks_completed:', message);
          return;
        }
        setLastTaskGroupCompletion({
          ...message,
          task_group_id: completedGroupId,
          received_at: Date.now(),
        });
        setRepetitionInfos(prev => ({
          ...prev,
          [completedTaskType]: 'ALL_COMPLETED',
        }));
      }
    }
    // SAThreats and SAEmergency are typically part of the general radarData update, no specific handling here needed for AgentStore

  }, [recordOperation, targetAntennaElevation, antennaAdjustmentRequired, joystickEnabled, enableAntennaRound, handleAntennaStatusResponse, handleSaTobiiResponse]);
  
  const confirmAntennaAdjustmentHandled = useCallback(() => {
    console.log('Confirming to backend that antenna adjustment has been handled.');
    setAntennaAdjustmentRequired(false);
    setTargetAntennaElevation(null); // Reset the elevation state as the signal is handled
    radarStore.setAntennaAdjustmentRequired(false);
    radarStore.setTargetAntennaElevation(null);
    console.log('[useRadarData] Antenna adjustment requirement handled and states reset.');
  }, []); // Dependencies: setAntennaAdjustmentRequired, setTargetAntennaElevation are stable from useState

  const changeAntennaAdjustmentRequired = useCallback((value: boolean) => {
    setAntennaAdjustmentRequired(value);
    radarStore.setAntennaAdjustmentRequired(value);
  }, [setAntennaAdjustmentRequired]);


  const lastProcessedMessageIdForHook = useRef<string>('');
  const lastProcessedEmergencyId = useRef<string>('');
  const lastAntennaCommandKeyRef = useRef<string>('');
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

      const latestMsgFromGlobal = globalWS.getLastMessage();
      if (latestMsgFromGlobal) {
        let currentMsgId = latestMsgFromGlobal.__message_seq !== undefined
          ? `seq_${latestMsgFromGlobal.__message_seq}`
          : latestMsgFromGlobal.type;
        if (latestMsgFromGlobal.__message_seq === undefined) {
          if (latestMsgFromGlobal.timestamp) currentMsgId += '_' + latestMsgFromGlobal.timestamp;
          if (latestMsgFromGlobal.task_id) currentMsgId += '_' + latestMsgFromGlobal.task_id;
          if (latestMsgFromGlobal.repetition_info) {
            currentMsgId += `_${latestMsgFromGlobal.repetition_info.current}_${latestMsgFromGlobal.repetition_info.total}`;
          }
          if (latestMsgFromGlobal.type === 'adjust_antenna' && latestMsgFromGlobal.targetElevation !== undefined) {
            currentMsgId += `_${latestMsgFromGlobal.targetElevation}`;
          }
        }

        if (currentMsgId !== lastProcessedMessageIdForHook.current) {
          handleHookMessage(latestMsgFromGlobal);
          lastProcessedMessageIdForHook.current = currentMsgId;
        }
      }

      // 处理雷达数据更新
      if (state.radarData) {
        setRadarData(state.radarData);
        setSaThreats(state.radarData.saThreats || []);
        setEnhancedThreats(state.radarData.enhancedThreats || []);
        setServerRadarConfig(state.radarData.serverRadarConfig ?? null);
        setUseEnhancedProtocol(state.radarData.useEnhancedProtocol ?? false);
        setTrustControl(state.radarData.trustControl ?? null);
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
    // Accuracy/history is authoritative only after the server returns the new
    // sa_task_updated payload.  Clear the previous trial first so the waiting
    // interval cannot display or calculate against stale SA state.
    globalWS.clearSaTaskSnapshot();
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
    setButton3(false);
    setButton7(false);
    setJoystickConnected(false);
    
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
    lastTaskGroupCompletion,
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
    button3,
    button7,
    joystickConnected,
    trustControl,
    resetJoystickData,
    changeAntennaAdjustmentRequired,
    startSaTobiiRound,
    endSaTobiiRound,
    platformTaskConfig,
    platformAutoStart,
  };
};

export default useRadarData;
