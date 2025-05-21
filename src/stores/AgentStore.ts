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
}

// 新增：定义服务端AI参数推荐的接口
export interface ServerAIParameterRecommendation {
  range: number;
  scanAngle: number;
}

class AgentStore {
  // --- AI 激活状态 ---
  isAIActive: boolean = false; // 默认AI不激活

  // --- AI 等级与配置 ---
  aiConfigs: AgentLevelConfig[] = []; // 存储从JSON加载的所有等级配置
  currentAILevel: string = "L1"; // 默认AI等级，可以根据实际情况调整初始值

  // --- 事件归属 ---
  currentOperationOwner: 'AI' | 'manual' = 'manual';

  // 新增：存储服务端对AI的参数推荐
  serverAIRecommendation: ServerAIParameterRecommendation | null = null;

  constructor() {
    makeAutoObservable(this, {
      currentAILevelConfig: computed,
      // serverAIRecommendation is observable by default
    });
    this.loadAgentConfig(); // 在构造时自动加载配置
  }

  // --- Computed Property ---
  // 根据 currentAILevel 从 aiConfigs 中获取当前等级的详细配置
  get currentAILevelConfig(): AgentLevelConfig | null {
    if (this.aiConfigs.length === 0) {
      return null;
    }
    const config = this.aiConfigs.find(c => c.level === this.currentAILevel);
    // 如果找不到指定等级，或configs为空，则返回第一个作为回退或null
    // 如果希望在找不到精确匹配的等级时严格返回null，可以修改下面的逻辑
    return config || (this.aiConfigs.length > 0 ? this.aiConfigs[0] : null); 
  }

  // --- Actions ---
  toggleAIActive = () => {
    this.isAIActive = !this.isAIActive;
    console.log(`AI Active state: ${this.isAIActive}`);
  }

  setAIActive = (isActive: boolean) => {
    this.isAIActive = isActive;
    // 自动同步 currentOperationOwner
    this.currentOperationOwner = isActive ? 'AI' : 'manual';
    console.log(`AI Active state set to: ${this.isAIActive}, operation owner: ${this.currentOperationOwner}`);
  }

  setCurrentAILevel = (level: string) => {
    const isValidLevel = this.aiConfigs.some(config => config.level === level);
    if (isValidLevel) {
      this.currentAILevel = level;
      console.log(`AI Level set to: ${this.currentAILevel}`);
    } else if (this.aiConfigs.length > 0 && !isValidLevel) {
      // 如果尝试设置的level无效，但配置已加载，可以警告并保持不变，或设置为默认
      console.warn(`Attempted to set invalid AI level: ${level}. Valid levels are: ${this.aiConfigs.map(c=>c.level).join(', ')}. Keeping current: ${this.currentAILevel}`);
    } else {
      // 配置尚未加载时，可能允许设置，加载后再验证
      this.currentAILevel = level;
       console.log(`AI Level tentatively set to: ${this.currentAILevel} (pending config load)`);
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

  async loadAgentConfig() {
    try {
      const resp = await fetch("/agent_level.json");
      if (!resp.ok) {
        throw new Error(`Failed to fetch agent_level.json: ${resp.statusText} (status: ${resp.status})`);
      }
      const data = await resp.json();
      
      runInAction(() => {
        if (data && data.levels && Array.isArray(data.levels) && data.levels.length > 0) {
          this.aiConfigs = data.levels;
          // 使用配置文件中的current_level
          if (data.current_level && this.aiConfigs.some(c => c.level === data.current_level)) {
            this.currentAILevel = data.current_level;
          } else {
            console.warn(`Config file's current_level "${data.current_level}" is invalid. Defaulting to "${this.aiConfigs[0].level}".`);
            this.currentAILevel = this.aiConfigs[0].level;
          }
          console.log("Agent configurations loaded:", JSON.stringify(this.aiConfigs, null, 2));
          console.log("Current AI Level:", this.currentAILevel);
          console.log("Current AI Config:", JSON.stringify(this.currentAILevelConfig, null, 2));
        } else {
          console.warn("agent_level.json is empty, not an array, or invalid. Agent will use fallback configurations or defaults.");
          this.aiConfigs = []; 
        }
      });
    } catch (e) {
      console.error("加载智能体配置失败:", e);
      runInAction(() => {
        // Fallback to a default configuration if loading fails
        this.aiConfigs = [
          { level: "L0", desc: "Fallback L0", threat_select_delay_ms: 2500, tdc_select_delay_ms: 2000 },
          { level: "L1", desc: "Fallback L1 (Default)", threat_select_delay_ms: 1500, tdc_select_delay_ms: 1000 },
          { level: "L2", desc: "Fallback L2", threat_select_delay_ms: 700, tdc_select_delay_ms: 500 }
        ];
        // 在fallback情况下使用L1作为默认值
        this.currentAILevel = "L1";
        console.warn("Using hardcoded fallback agent configurations due to loading error.");
        console.log("Current AI Level (fallback):", this.currentAILevel);
        console.log("Current AI Config (fallback):", JSON.stringify(this.currentAILevelConfig, null, 2));
      });
    }
    // Log final state after attempting to load/fallback
    console.log("Final AI Configs in Store:", JSON.stringify(this.aiConfigs, null, 2));
    console.log("Final Current AI Level in Store:", this.currentAILevel);
    console.log("Final Current AI Config in Store:", JSON.stringify(this.currentAILevelConfig, null, 2));
  }
}

const agentStore = new AgentStore();
export default agentStore; 