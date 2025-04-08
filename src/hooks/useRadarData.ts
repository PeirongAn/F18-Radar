import { useState, useEffect, useRef, useCallback } from 'react';
import { UnknownTargetData } from '../components/UnknownTarget';

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
  radar_azimuth: number;  // 雷达当前扫描方位角
  own_heading: number;    // 自机航向
  timestamp: number;      // 时间戳
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
  public sendMessage(message: any) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('【全局WS】无法发送消息：WebSocket未连接');
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
}

// 获取全局WebSocket实例
const globalWS = GlobalWebSocketManager.getInstance();

// 修改后的useRadarData hook使用全局WebSocket管理器
const useRadarData = (wsUrl: string = 'ws://localhost:8765') => {
  const [connected, setConnected] = useState<boolean>(false);
  const [radarData, setRadarData] = useState<RadarData | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // 使用全局WebSocket管理器发送消息
  const sendMessage = useCallback((message: any) => {
    const success = globalWS.sendMessage(message);
    if (!success) {
      console.warn('消息发送失败，WebSocket未连接');
    }
  }, []);
  
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
  
  // 使用全局WebSocket管理器并订阅状态变化
  useEffect(() => {
    // 确保连接到指定URL
    globalWS.connect(wsUrl);
    
    // 订阅状态变化
    const unsubscribe = globalWS.subscribe((state) => {
      setConnected(state.connected);
      setRadarData(state.radarData);
      setError(state.error);
    });
    
    // 清理函数 - 取消订阅，但不关闭连接
    return () => {
      unsubscribe();
    };
  }, [wsUrl]);
  
  useEffect(() => {
    console.log('useRadarData hook - radarData changed:', radarData);
  }, [radarData]);
  
  return { connected, radarData, error, sendMessage, resetTargets };
};

export default useRadarData; 