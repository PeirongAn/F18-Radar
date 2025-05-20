import { makeAutoObservable, observable, action } from 'mobx';

interface RadarDataHook {
  sendMessage: (message: any) => void;
  settingsValidationTimestamp: number | null;
  initializeSystem: () => void;
  validateSettings: (settings: { range: number, scanAngle: number }) => boolean;
  submitSettings: (settings: { range: number, scanAngle: number }) => void;
  resetTargets: () => void;
}

/**
 * 雷达系统的MobX Store，管理雷达相关状态
 */
export class RadarStore {
  // 系统状态
  isStarted: boolean = false;
  taskId: number | null = null;
  antennaAdjustmentRequired: boolean = false;
  userId: string | null = null;
  
  // 雷达参数
  radarRange: number = 20; // 默认20海里
  scanAngle: number = 60;  // 默认60度
  
  // 内部变量
  private radarDataHook: RadarDataHook | null = null;
  
  // 天线高度相关状态
  currentAntennaElevation: number = 0;
  targetAntennaElevation: number | null = null;
  private settingsValidationTimestamp: number | null = null;
  private isAdjusting: boolean = false;  // 添加调整状态标志
  
  constructor() {
    makeAutoObservable(this, {
      userId: observable,
      setUserId: action,
      setTaskId: action,
      setAntennaAdjustmentRequired: action,
      updateRadarParams: action,
      submitSettings: action,
      resetSystem: action,
      setCurrentAntennaElevation: action,
      setTargetAntennaElevation: action,
      startSystem: action,
      initializeSystem: action,
      setRadarDataHook: action
    });
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
    console.log(`系统已启动 - 用户ID: ${userId}, 启用AI: ${withAI}`);
  }
  
  // 初始化雷达系统
  initializeSystem() {
    console.log('[雷达系统] 正在初始化雷达系统...', this.isStarted);
    if (!this.isStarted) {
      console.warn('系统未启动，无法执行初始化操作');
      return;
    }
    // 调用雷达数据hook中的初始化方法
    if (this.radarDataHook && this.radarDataHook.initializeSystem) {
      console.log('[雷达系统] 正在调用初始化方法...');
      this.radarDataHook.initializeSystem();
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
  setCurrentAntennaElevation(value: number) {
    console.log('[天线]setCurrentAntennaElevation', value, this.targetAntennaElevation, this.antennaAdjustmentRequired);
    this.currentAntennaElevation = value;
    
    // 检查是否达到目标高度（允许±1格的误差）
    if (this.targetAntennaElevation !== null && 
        Math.abs(value - this.targetAntennaElevation) <= 0.1 && 
        this.antennaAdjustmentRequired &&
        !this.isAdjusting) {  // 添加调整状态检查
      
      console.log('[天线] 发送前参数', value - this.targetAntennaElevation, this.targetAntennaElevation);
      if (this.radarDataHook && this.radarDataHook.sendMessage) {
        console.log('[天线] 准备发送调整指令', value, this.targetAntennaElevation);
        this.isAdjusting = true;  // 设置调整状态
        
        this.radarDataHook.sendMessage({
          type: 'antenna_adjusted',
          elevation: value,
          timestamp: Date.now(),
          receive_timestamp: this.radarDataHook.settingsValidationTimestamp,
          user_id: this.userId,
        });
        
        // 重置天线调整状态
        this.antennaAdjustmentRequired = false;
        this.targetAntennaElevation = null;
        this.isAdjusting = false;  // 重置调整状态
      }
    }
  }
  
  setTargetAntennaElevation(value: number | null) {
    this.targetAntennaElevation = value;
    this.antennaAdjustmentRequired = true;
  }

  setUserId(userId: string | null) {
    this.userId = userId;
  }
}

// 创建单例实例
const radarStore = new RadarStore();

export default radarStore; 