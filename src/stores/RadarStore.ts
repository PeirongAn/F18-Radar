import { makeObservable, observable, action } from 'mobx';
import agentStore from './AgentStore'; // Restore the import for agentStore


interface RadarDataHook {
  sendMessage: (message: any) => void;
  settingsValidationTimestamp: number | null;
  initializeSystem: (userId: string, includeAI: boolean) => void;
  validateSettings: (settings: { range: number, scanAngle: number }) => boolean;
  submitSettings: (settings: { range: number, scanAngle: number }) => void;
  resetTargets: () => void;
}

export interface AntennaAdjustment {
  targetElevation: number;
  timestamp: number;
}

export interface TargetDisplayPosition {
  x: number;
  y: number;
}

/**
 * 雷达系统的MobX Store，管理雷达相关状态
 */
export class RadarStore {
  // 系统状态
  isStarted: boolean = false;
  isSystemInitializing: boolean = false;
  isAwaitingSettings: boolean = false;
  userId: string = `user_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  taskId: number | null = null;
  antennaAdjustmentRequired: boolean = false;
  radarRange: number = 20; // 默认20海里
  scanAngle: number = 60;  // 默认60度
  settingsValidationTimestamp: number | null = null; // 声明
  
  // 内部变量
  private radarDataHook: RadarDataHook | null = null;
  
  // 天线高度相关状态
  currentAntennaElevation: number = 0;
  targetAntennaElevation: number | null = null;
  saEmergency: { type: string, saThreats?: any[] } | null = null;
  saEmergencyHistory: Array<{ type: string, saThreats?: any[], timestamp: number }> = [];
  lastSAEmergencyTimestamp: number = 0;

  // AI相关状态
  lockedTargetId: string | undefined = undefined; // 当前系统锁定的目标ID (AI或手动)
  lockScreenX: number | undefined = undefined; // 锁定目标时，TDC在屏幕上的X坐标
  
  // 存储目标在屏幕上的动态显示位置
  targetDisplayPositions: Map<string, TargetDisplayPosition> = new Map();
  
  constructor() {
    makeObservable(this, {
      isStarted: observable,
      isSystemInitializing: observable,
      isAwaitingSettings: observable,
      userId: observable,
      taskId: observable,
      antennaAdjustmentRequired: observable,
      radarRange: observable,
      scanAngle: observable,
      settingsValidationTimestamp: observable,
      currentAntennaElevation: observable,
      targetAntennaElevation: observable,
      saEmergency: observable,
      saEmergencyHistory: observable,
      lastSAEmergencyTimestamp: observable,
      targetDisplayPositions: observable,
      setRadarDataHook: action,
      startSystem: action,
      initializeSystem: action,
      setTaskId: action,
      setAntennaAdjustmentRequired: action,
      updateRadarParams: action,
      submitSettings: action,
      resetSystem: action,
      setCurrentAntennaElevation: action,
      setTargetAntennaElevation: action,
      setUserId: action,
      triggerSAEmergency: action,
      resetSAEmergency: action,
      setTargetDisplayPosition: action,
      removeTargetDisplayPosition: action,
      clearAllTargetDisplayPositions: action,
      setLockedTargetId: action,
      setLockScreenX: action,
    });
    console.log('RadarStore initialized with User ID:', this.userId);
  }
  
  // 初始化radar data hook引用
  setRadarDataHook(hook: RadarDataHook) {
    this.radarDataHook = hook;
    // 确保 settingsValidationTimestamp 被正确设置
    if (hook.settingsValidationTimestamp !== undefined) {
      this.settingsValidationTimestamp = hook.settingsValidationTimestamp;
    }
  }
  
  // 系统启动
  startSystem(userId: string, withAI: boolean = false) {
    this.userId = userId;
    this.isStarted = true;
    agentStore.setAIActive(withAI); // 确保AI状态也被设置
    this.initializeSystem(userId, withAI); // 直接调用初始化
    console.log(`系统已启动 - 用户ID: ${userId}, 启用AI: ${withAI}`);
  }
  
  // 初始化雷达系统
  initializeSystem(userId: string, includeAI: boolean) {
    console.log('[雷达系统] 正在初始化雷达系统...', this.isStarted);
    if (!this.isStarted) {
      console.warn('系统未启动，无法执行初始化操作');
      return;
    }
    // 调用雷达数据hook中的初始化方法
    if (this.radarDataHook && this.radarDataHook.initializeSystem) {
      console.log('[雷达系统] 正在调用初始化方法...');
      this.radarDataHook.initializeSystem(userId, includeAI);
    } else {
      console.error('雷达数据hook未初始化或不包含initializeSystem方法');
    }
  }
  
  // 设置任务ID
  setTaskId(id: number | null) {
    this.taskId = id;
  }
  
  // 更新天线调整需求
  setAntennaAdjustmentRequired(value: boolean) {
    this.antennaAdjustmentRequired = value;
  }
  
  // 更新雷达参数
  updateRadarParams(range: number, angle: number) {
    this.radarRange = range;
    this.scanAngle = angle;
    console.log(`雷达参数已更新 - 范围: ${range}海里, 角度: ${angle}°`);
  }
  
  // 提交雷达设置
  submitSettings(settings: { range: number, scanAngle: number }) {
    if (!this.isStarted) {
      console.warn('系统未启动，无法提交设置');
      return;
    }
    
    // 验证参数是否在推荐范围内
    if (!this.radarDataHook || !this.radarDataHook.validateSettings) {
      console.error('雷达数据hook未初始化或不包含validateSettings方法');
      return;
    }
    
    if (!this.radarDataHook.validateSettings(settings)) {
      console.warn('参数设置无效，未发送到服务端');
      return;
    }
    
    console.log('提交雷达参数设置...');
    this.updateRadarParams(settings.range, settings.scanAngle);
    
    // 调用雷达数据hook中的提交设置方法
    if (this.radarDataHook && this.radarDataHook.submitSettings) {
      this.radarDataHook.submitSettings(settings);
    } else {
      console.error('雷达数据hook未初始化或不包含submitSettings方法');
    }
  }
  
  // 重置系统
  resetSystem() {
    this.isStarted = false;
    this.taskId = null;
    this.antennaAdjustmentRequired = false;
    this.radarRange = 20;
    this.scanAngle = 60;
    
    // 调用雷达数据hook中的重置方法
    if (this.radarDataHook && this.radarDataHook.resetTargets) {
      this.radarDataHook.resetTargets();
    }
    
    console.log('系统已重置');
  }
  
  // 天线高度相关方法
  setCurrentAntennaElevation(elevation: number, source: 'user' | 'ai' | 'server' = 'user', sendMessageCallback?: (message: any) => void) {
    const newElevation = Math.max(-30, Math.min(30, elevation)); // 限制在-30到30度
    if (this.currentAntennaElevation !== newElevation) {
      const previousElevation = this.currentAntennaElevation;
      this.currentAntennaElevation = newElevation;
      console.log(`[RadarStore] Antenna elevation changed from ${previousElevation}° to ${newElevation}° by ${source}.`);

      // 如果提供了回调且源不是服务器（避免循环），则发送消息
      if (sendMessageCallback && source !== 'server') {
        const message = {
          type: 'antenna_adjusted', // 使用新的消息类型
          elevation: newElevation,
          timestamp: Date.now(),
          receive_timestamp: Date.now(), // 或者从特定事件获取
          // user_id is now added by globalWS.sendMessage
        };
        sendMessageCallback(message);
        console.log('[RadarStore] Sent antenna_adjusted message to server:', message);
      }
    }
  }
  
  setTargetAntennaElevation(elevation: number | null) {
    this.targetAntennaElevation = elevation;
    if (elevation !== null) {
      console.log(`[RadarStore] Target antenna elevation set to: ${elevation}° by server.`);
    } else {
      console.log('[RadarStore] Target antenna elevation cleared.');
    }
  }

  setUserId(userId: string) {
    this.userId = userId;
  }

  triggerSAEmergency(type: string, saThreats?: any[]) {
    const now = Date.now();
    // Prevent re-triggering too quickly, e.g., within 5 seconds for the same type
    if (this.saEmergency?.type === type && (now - this.lastSAEmergencyTimestamp < 5000)) {
        console.log(`[RadarStore] SA Emergency of type "${type}" re-trigger suppressed.`);
        return;
    }
    this.saEmergency = { type, saThreats };
    this.saEmergencyHistory.push({ type, saThreats, timestamp: now });
    this.lastSAEmergencyTimestamp = now;
    console.log(`[RadarStore] SA Emergency triggered: Type - ${type}, Threats - ${saThreats ? saThreats.length : 0}`);
  }

  resetSAEmergency() {
    if (this.saEmergency) {
      console.log(`[RadarStore] SA Emergency reset: Type - ${this.saEmergency.type}`);
      this.saEmergency = null;
    }
  }

  // 新增：设置特定目标ID的显示位置
  setTargetDisplayPosition(targetId: string, position: TargetDisplayPosition) {
    this.targetDisplayPositions.set(targetId, position);
  }

  // 新增：移除特定目标ID的显示位置
  removeTargetDisplayPosition(targetId: string) {
    if (this.targetDisplayPositions.delete(targetId)) {
      // console.log(`[RadarStore] Display position for target ${targetId} removed.`);
    }
  }

  // 可选：清空所有目标显示位置
  clearAllTargetDisplayPositions() {
    this.targetDisplayPositions.clear();
    console.log('[RadarStore] All target display positions cleared.');
  }

  setLockedTargetId(id: string | undefined) {
    this.lockedTargetId = id;
    console.log(`[RadarStore] Locked target ID set to: ${id}`);
    if (!id) {
      this.setLockScreenX(undefined); // 如果目标被清除，也清除锁定线
    }
  }

  setLockScreenX(x: number | undefined) {
    this.lockScreenX = x;
    console.log(`[RadarStore] Lock screen X set to: ${x}`);
  }
}

// 创建单例实例
const radarStore = new RadarStore();

export default radarStore; 