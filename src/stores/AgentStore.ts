import { makeAutoObservable, runInAction, computed } from "mobx";
import { TrustCalibrationConfig } from "../types/trustCalibration";

export type ControlMode = '0' | '1' | '2';

export const normalizeControlMode = (value: unknown, includeAI?: boolean): ControlMode => {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === '0' || normalized === 'false' || normalized === 'manual') return '0';
  if (normalized === '2' || normalized === 'pure_ai' || normalized === 'pure-ai' || normalized === 'ai_only' || normalized === 'ai-only') return '2';
  if (normalized !== '') return '1';
  return includeAI ? '1' : '0';
};

// 定义 agent_level.json 中每个配置对象的接口
export interface AgentLevelConfig {
  level: string;
  desc: string;
  threat_select_delay_ms: number;
  tdc_select_delay_ms: number;
  tdc_move_delay_ms?: number; // Added: Optional, for AI TDC movement simulation delay
  // Can be made non-optional if all levels must have it.
  // radar_auto_range?: number;
  // 可以根据需要添加更多雷达相关的AI配置，例如：
  // radar_auto_scan_angle?: number;
  decision_probabilities?: number[];
  scan_interval_ms: number;
}

// 新增：定义服务端AI参数推荐的接口
export interface ServerAIParameterRecommendation {
  range: number;
  scanAngle: number;
}

export type RadarAISelectionStatus = 'waiting' | 'recording' | 'ready' | 'failed';

export interface RadarAISelectionState {
  status: RadarAISelectionStatus;
  taskId: string | null;
  targetId: string | null;
  error: string | null;
}

class AgentStore {
  // --- AI 激活状态 ---
  isAIActive: boolean = false; // 由服务器初始化
  // 0=人工，1=AI（允许人工参与），2=纯AI（禁止人工操作）
  controlMode: ControlMode = '0';

  // --- AI 等级与配置 ---
  aiConfigs: AgentLevelConfig[] = []; // 由服务器初始化
  currentAILevel: string = ""; // 由服务器初始化

  // --- 事件归属 ---
  currentOperationOwner: 'AI' | 'manual' = 'manual';

  // 新增：存储服务端对AI的参数推荐
  serverAIRecommendation: ServerAIParameterRecommendation | null = null;

  // 新增：音频状态
  audioEnabled = true; // 默认值

  // 信任状态调控配置，由服务端随任务配置下发
  trustCalibrationConfig: Partial<TrustCalibrationConfig> | null = null;

  radarAISelection: RadarAISelectionState = {
    status: 'waiting',
    taskId: null,
    targetId: null,
    error: null,
  };

  constructor() {
    makeAutoObservable(this, {
      currentAILevelConfig: computed,
    });
    // 不再主动加载配置
    // this.loadConfig(); 
  }

  // --- Computed Property ---
  // 根据 currentAILevel 从 aiConfigs 中获取当前等级的详细配置
  get currentAILevelConfig(): AgentLevelConfig | null {
    if (this.aiConfigs.length === 0) {
      return null;
    }
    const config = this.aiConfigs.find(c => c.level === this.currentAILevel);
    // 如果找不到指定等级，或configs为空，则返回第一个作为回退或null
    return config || (this.aiConfigs.length > 0 ? this.aiConfigs[0] : null); 
  }

  get isManualControlDisabled(): boolean {
    return this.controlMode === '2';
  }

  get requiresHumanConfirmation(): boolean {
    return this.controlMode === '2';
  }

  isRadarAISelectionReadyFor(taskId: unknown): boolean {
    if (!this.isManualControlDisabled) return true;
    if (taskId === undefined || taskId === null) return false;
    return this.radarAISelection.status === 'ready'
      && this.radarAISelection.taskId === String(taskId);
  }

  // --- Actions ---

  // 新增：由服务器消息来初始化或重置状态
  initializeFromServer = (data: { 
    is_ai_active: boolean; 
    ai_level: string; 
    ai_configs: AgentLevelConfig[];
    audio_enabled: boolean; 
    trust_calibration?: Partial<TrustCalibrationConfig>;
    control_mode?: unknown;
    manual_control_disabled?: boolean;
    platform_task?: { normalized?: { control_mode?: unknown; default_control_mode?: unknown } };
  }) => {
    runInAction(() => {
      const serverMode = data.control_mode
        ?? data.platform_task?.normalized?.control_mode
        ?? data.platform_task?.normalized?.default_control_mode
        ?? (data.manual_control_disabled ? '2' : undefined);
      this.controlMode = normalizeControlMode(serverMode, data.is_ai_active);
      this.isAIActive = this.controlMode !== '0';
      this.currentAILevel = data.ai_level;
      this.aiConfigs = data.ai_configs;
      this.audioEnabled = data.audio_enabled;
      this.trustCalibrationConfig = data.trust_calibration ?? null;
      this.currentOperationOwner = this.isAIActive ? 'AI' : 'manual';
      console.log(`[AgentStore] Initialized from server. AI Active: ${this.isAIActive}, Level: ${this.currentAILevel}, Audio: ${this.audioEnabled}`);
    });
  }

  toggleAIActive = () => {
    if (this.isManualControlDisabled) {
      console.warn('[AgentStore] Pure AI mode blocks manual takeover.');
      return;
    }
    this.isAIActive = !this.isAIActive;
    this.controlMode = this.isAIActive ? '1' : '0';
    console.log(`AI Active state: ${this.isAIActive}`);
  }

  setAIActive = (isActive: boolean) => {
    if (this.isManualControlDisabled && !isActive) {
      console.warn('[AgentStore] Pure AI mode blocks manual takeover.');
      return;
    }
    this.isAIActive = isActive;
    this.controlMode = isActive ? (this.controlMode === '2' ? '2' : '1') : '0';
    // 自动同步 currentOperationOwner
    this.currentOperationOwner = isActive ? 'AI' : 'manual';
    console.log(`AI Active state set to: ${this.isAIActive}, operation owner: ${this.currentOperationOwner}`);
    if (!isActive) {
      // 当AI被禁用时，可以考虑是否要重置AI等级和推荐
      this.serverAIRecommendation = null;
    }
  }

  setControlMode = (mode: unknown, includeAI?: boolean) => {
    this.controlMode = normalizeControlMode(mode, includeAI);
    this.isAIActive = this.controlMode !== '0';
    this.currentOperationOwner = this.isAIActive ? 'AI' : 'manual';
    if (!this.isAIActive) {
      this.serverAIRecommendation = null;
    }
    console.log(`[AgentStore] Control mode set to ${this.controlMode}. AI Active: ${this.isAIActive}, manual disabled: ${this.isManualControlDisabled}`);
  }

  setTrustCalibrationConfig = (config: Partial<TrustCalibrationConfig> | null) => {
    runInAction(() => {
      this.trustCalibrationConfig = config;
      console.log("[AgentStore] Trust calibration config updated:", config);
    });
  }

  resetRadarAISelection = (taskId: unknown) => {
    this.radarAISelection = {
      status: 'waiting',
      taskId: taskId === undefined || taskId === null ? null : String(taskId),
      targetId: null,
      error: null,
    };
  }

  markRadarAISelectionRecording = (taskId: unknown, targetId: unknown) => {
    if (taskId === undefined || taskId === null || !targetId) return;
    this.radarAISelection = {
      status: 'recording',
      taskId: String(taskId),
      targetId: String(targetId),
      error: null,
    };
  }

  markRadarAISelectionReady = (taskId: unknown, targetId: unknown) => {
    if (taskId === undefined || taskId === null) return;
    const normalizedTaskId = String(taskId);
    if (this.radarAISelection.taskId !== normalizedTaskId) return;
    this.radarAISelection = {
      status: 'ready',
      taskId: normalizedTaskId,
      targetId: targetId ? String(targetId) : this.radarAISelection.targetId,
      error: null,
    };
  }

  markRadarAISelectionFailed = (taskId: unknown, error: unknown) => {
    if (taskId === undefined || taskId === null) return;
    const normalizedTaskId = String(taskId);
    if (this.radarAISelection.taskId !== normalizedTaskId) return;
    this.radarAISelection = {
      ...this.radarAISelection,
      status: 'failed',
      error: String(error || 'target_selected_not_recorded'),
    };
  }

  setCurrentAILevel = (level: string) => {
    // 仅在配置列表中存在时才更新
    const isValidLevel = this.aiConfigs.some(config => config.level === level);
    if (isValidLevel) {
      this.currentAILevel = level;
      console.log(`AI Level set to: ${this.currentAILevel}`);
    } else {
      console.warn(`Attempted to set invalid AI level: ${level}.`);
    }
  }

  // 新增：Action来设置服务端的AI参数推荐
  setServerAIRecommendation = (recommendation: ServerAIParameterRecommendation | null) => {
    runInAction(() => {
        this.serverAIRecommendation = recommendation;
        if (recommendation) {
            console.log("[AgentStore] Received server AI parameter recommendation:", recommendation);
        } else {
            console.log("[AgentStore] Server AI parameter recommendation cleared.");
        }
    });
  }

  // 新增：Action来清除服务端的AI参数推荐 (可选，如果希望建议是一次性的)
  clearServerAIRecommendation = () => {
    runInAction(() => {
        this.serverAIRecommendation = null;
        console.log("[AgentStore] Server AI parameter recommendation explicitly cleared.");
    });
  }

  // loadConfig 方法已被移除
  /*
  async loadConfig() {
    ...
  }
  */

  toggleAudioEnabled() {
    this.audioEnabled = !this.audioEnabled;
  }
}

const agentStore = new AgentStore();
export default agentStore;
