import { makeAutoObservable, runInAction, computed } from "mobx";

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

class AgentStore {
  // --- AI 激活状态 ---
  isAIActive: boolean = false; // 由服务器初始化

  // --- AI 等级与配置 ---
  aiConfigs: AgentLevelConfig[] = []; // 由服务器初始化
  currentAILevel: string = ""; // 由服务器初始化

  // --- 事件归属 ---
  currentOperationOwner: 'AI' | 'manual' = 'manual';

  // 新增：存储服务端对AI的参数推荐
  serverAIRecommendation: ServerAIParameterRecommendation | null = null;

  // 新增：音频状态
  audioEnabled = true; // 默认值

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

  // --- Actions ---

  // 新增：由服务器消息来初始化或重置状态
  initializeFromServer = (data: { 
    is_ai_active: boolean; 
    ai_level: string; 
    ai_configs: AgentLevelConfig[];
    audio_enabled: boolean; 
  }) => {
    runInAction(() => {
      this.isAIActive = data.is_ai_active;
      this.currentAILevel = data.ai_level;
      this.aiConfigs = data.ai_configs;
      this.audioEnabled = data.audio_enabled;
      this.currentOperationOwner = this.isAIActive ? 'AI' : 'manual';
      console.log(`[AgentStore] Initialized from server. AI Active: ${this.isAIActive}, Level: ${this.currentAILevel}, Audio: ${this.audioEnabled}`);
    });
  }

  toggleAIActive = () => {
    this.isAIActive = !this.isAIActive;
    console.log(`AI Active state: ${this.isAIActive}`);
  }

  setAIActive = (isActive: boolean) => {
    this.isAIActive = isActive;
    // 自动同步 currentOperationOwner
    this.currentOperationOwner = isActive ? 'AI' : 'manual';
    console.log(`AI Active state set to: ${this.isAIActive}, operation owner: ${this.currentOperationOwner}`);
    if (!isActive) {
      // 当AI被禁用时，可以考虑是否要重置AI等级和推荐
      this.serverAIRecommendation = null;
    }
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