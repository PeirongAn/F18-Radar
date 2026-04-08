import { makeAutoObservable, observable, action } from 'mobx';
import agentStore from './AgentStore'; // Restore the import for agentStore


interface RadarDataHook {
  sendMessage: (message: any) => void;
  settingsValidationTimestamp: number | null;
  initializeSystem: (userId: string, includeAI: boolean, isPractice: boolean) => void;
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

// 定义任务类型，确保与useRadarData和服务器中使用的类型一致
export type TaskType = 'RADAR_TARGETING' | 'SA_THREAT_RESPONSE' | 'PLATFORM_CONTROL' | 'WEAPON_FIRING';

/**
 * 雷达系统的MobX Store，管理雷达相关状态
 */
export class RadarStore {
  // 系统状态
  isStarted: boolean = false;
  isSystemInitializing: boolean = false;
  isAwaitingSettings: boolean = false;
  userId: string = '';
  taskId: number | null = null;
  antennaAdjustmentRequired: boolean = false;
  radarRange: number = 20; // 默认20海里
  scanAngle: number = 60;  // 默认60度
  settingsValidationTimestamp: number | null = null; // 声明
  isPractice: boolean = false; // 添加 isPractice 状态
  
  // 内部变量
  private radarDataHook: RadarDataHook | null = null;
  
  // 天线高度相关状态
  currentAntennaElevation: number = 0;
  targetAntennaElevation: number | null = null;
  saEmergency: { type: string, saThreats?: any[] } | null = null;
  saEmergencyHistory: Array<{ type: string, saThreats?: any[], timestamp: number }> = [];
  lastSAEmergencyTimestamp: number = 0;
  adjustAntennaReceiveTimestamp: number | null = null; // 保存adjust_antenna消息的接收时间戳

  // AI相关状态
  lockedTargetId: string | undefined = undefined; // 当前系统锁定的目标ID (AI或手动)
  lockScreenX: number | undefined = undefined; // 锁定目标时，TDC在屏幕上的X坐标
  
  // 存储目标在屏幕上的动态显示位置
  targetDisplayPositions: Map<string, TargetDisplayPosition> = new Map();
  

  constructor() {
    makeAutoObservable(this, {
      userId: observable,
      isStarted: observable,
      isPractice: observable,
      lockedTargetId: observable,
      lockScreenX: observable,
      targetDisplayPositions: observable,
      setUserId: action,
      startSystem: action,
      setLockedTargetId: action,
      setLockScreenX: action,
      setTargetDisplayPositions: action,
      setRadarDataHook: action,
    });
    console.log('RadarStore initialized with User ID:', this.userId);
  }
  
  setRadarDataHook(hook: RadarDataHook) {
    this.radarDataHook = hook;
  }
  
  // 系统启动

  startSystem = (userId: string, includeAI: boolean, isPractice: boolean) => {
    // This action should ONLY update the state.
    this.userId = userId;
    this.isStarted = true;
    this.isPractice = isPractice; // 保存 isPractice 状态
    agentStore.setAIActive(includeAI); // It's okay to call another store's action here
    console.log(`[RadarStore] System state started. UserID: ${this.userId}, AI: ${includeAI}, Practice: ${isPractice}`);
  }
  
  // 设置任务ID

  setTaskId = (id: number | null) => {
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
          receive_timestamp: this.adjustAntennaReceiveTimestamp || Date.now(), // 使用保存的接收时间戳
          // user_id is now added by globalWS.sendMessage
        };
        sendMessageCallback(message);
        console.log('[RadarStore] Sent antenna_adjusted message to server:', message);
      }
    }
  }
  
  setTargetAntennaElevation(elevation: number | null, receiveTimestamp?: number) {
    this.targetAntennaElevation = elevation;
    if (receiveTimestamp !== undefined) {
      this.adjustAntennaReceiveTimestamp = receiveTimestamp;
    }
    if (elevation !== null) {
      console.log(`[RadarStore] Target antenna elevation set to: ${elevation}° by server.`);
    } else {
      console.log('[RadarStore] Target antenna elevation cleared.');
    }
  }

  setUserId = (userId: string) => {
    // console.log(`[RadarStore] User ID set to: ${userId}`);
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
    this.targetDisplayPositions.delete(targetId);
  }

  // 新增：清空所有目标显示位置
  clearAllTargetDisplayPositions() {
    this.targetDisplayPositions.clear();
  }

  setLockedTargetId(id: string | undefined) {
    if (this.lockedTargetId !== id) {
      console.log(`[RadarStore] Locked target ID changed from ${this.lockedTargetId} to ${id}`);
      this.lockedTargetId = id;
    }
  }

  setLockScreenX(x: number | undefined) {
    if (this.lockScreenX !== x) {
      this.lockScreenX = x;
      console.log(`[RadarStore] Lock screen X set to: ${x}`);
    }
  }

  setTargetDisplayPositions(positions: Map<string, TargetDisplayPosition>) {
    this.targetDisplayPositions.clear();
    positions.forEach((value, key) => {
      this.targetDisplayPositions.set(key, value);
    });
  }
}

// 创建单例实例
const radarStore = new RadarStore();

export default radarStore; 