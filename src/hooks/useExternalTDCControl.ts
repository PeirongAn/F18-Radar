import { useState, useEffect, useCallback, useRef } from 'react';

// TDC坐标消息接口
export interface TDCCoordinateMessage {
  type: 'tdc_coordinate';
  x: number; // -1 到 1 的归一化坐标
  y: number; // -1 到 1 的归一化坐标
  timestamp: number;
  source?: string; // 消息来源标识
}

// 外部设备原始消息接口
export interface ExternalDeviceMessage {
  RawInput: number;
  YawInput: number;
  PitchInput: number;
  Fire: boolean;
  Throttle: number;
  PawnControl: boolean;
  ForcePress: boolean;
  ForceSwitch: [number, number]; // TDC坐标数据
  timestamp: number;
}

// TDC位置接口
export interface TDCPosition {
  x: number; // 像素坐标
  y: number; // 像素坐标
}

// Hook状态接口
interface ExternalTDCControlState {
  connected: boolean;
  error: string | null;
  lastTDCCoordinate: TDCCoordinateMessage | null;
  messageCount: number;
  connectionAttempts: number;
  tdcPosition: TDCPosition | null; // 当前TDC位置
  lastUpdateTime: number; // 最后更新时间
}

// 坐标转换配置接口
export interface CoordinateConfig {
  frameStartX: number;
  frameStartY: number;
  radarWidth: number;
  radarHeight: number;
  padding: number;
}

/**
 * 外部TDC控制Hook
 * 专门处理来自8765端口的外部设备TDC控制数据
 */
const useExternalTDCControl = (
  wsUrl: string = 'ws://localhost:8765',
  coordinateConfig?: CoordinateConfig,
  onTDCUpdate?: (coordinate: TDCCoordinateMessage, pixelPosition: TDCPosition) => void,
  onForcePress?: () => void // 新增：ForcePress回调，触发Enter效果
) => {
  const [state, setState] = useState<ExternalTDCControlState>({
    connected: false,
    error: null,
    lastTDCCoordinate: null,
    messageCount: 0,
    connectionAttempts: 0,
    tdcPosition: null,
    lastUpdateTime: 0
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const lastForceSwitch = useRef<[number, number] | null>(null);
  const changeThreshold = useRef<number>(0.001); // ForceSwitch变化阈值

  // 将归一化坐标转换为像素坐标
  const convertNormalizedToPixel = useCallback((normalizedX: number, normalizedY: number): TDCPosition => {
    if (!coordinateConfig) {
      // 如果没有配置，返回默认坐标
      console.warn('[useExternalTDCControl] 缺少坐标转换配置，使用默认值');
      return { x: 400, y: 300 };
    }

    const { frameStartX, frameStartY, radarWidth, radarHeight, padding } = coordinateConfig;
    
    // 限制坐标范围
    const clampedX = Math.max(-1, Math.min(1, normalizedX));
    const clampedY = Math.max(-1, Math.min(1, normalizedY));
    
    // 计算可用区域
    const availableWidth = radarWidth - 2 * padding;
    const availableHeight = radarHeight - 2 * padding;
    
    // 转换为像素坐标
    const pixelX = frameStartX + padding + (clampedX + 1) * availableWidth / 2;
    const pixelY = frameStartY + padding + (clampedY + 1) * availableHeight / 2;
    
    return { x: pixelX, y: pixelY };
  }, [coordinateConfig]);

  // 检测ForceSwitch是否发生了显著变化
  const hasForceSwitchChanged = useCallback((newForceSwitch: [number, number]): boolean => {
    if (lastForceSwitch.current === null) {
      return true; // 第一次接收数据
    }

    const [oldX, oldY] = lastForceSwitch.current;
    const [newX, newY] = newForceSwitch;

    const xChange = Math.abs(newX - oldX);
    const yChange = Math.abs(newY - oldY);

    return xChange > changeThreshold.current || yChange > changeThreshold.current;
  }, []);

  // 处理外部设备消息
  const processExternalMessage = useCallback((messageStr: string) => {
    try {
      const data: ExternalDeviceMessage = JSON.parse(messageStr);
      
      // 检查ForcePress状态
      if (data.ForcePress === true && onForcePress) {
        console.log('[useExternalTDCControl] ForcePress激活，触发Enter效果');
        onForcePress();
      }
      
      // 检查ForceSwitch数据
      if (!data.ForceSwitch || data.ForceSwitch.length < 2) {
        console.warn('[useExternalTDCControl] 消息缺少ForceSwitch数据');
        return;
      }

      // 检查是否发生变化
      if (!hasForceSwitchChanged(data.ForceSwitch)) {
        // 数据未变化，静默跳过
        return;
      }

      const [x, y] = data.ForceSwitch;
      
      console.log(`[useExternalTDCControl] ForceSwitch变化: [${x.toFixed(6)}, ${y.toFixed(6)}]`);

      // 更新缓存
      lastForceSwitch.current = [x, y];

      // 验证坐标范围并限制在-1到1之间
      const clampedX = Math.max(-1.0, Math.min(1.0, x));
      const clampedY = Math.max(-1.0, Math.min(1.0, y));

      if (clampedX !== x || clampedY !== y) {
        console.warn(`[useExternalTDCControl] 坐标范围调整: (${x.toFixed(6)}, ${y.toFixed(6)}) -> (${clampedX.toFixed(6)}, ${clampedY.toFixed(6)})`);
      }

      // 构造TDC坐标消息
      const tdcMessage: TDCCoordinateMessage = {
        type: 'tdc_coordinate',
        x: clampedX,
        y: clampedY,
        timestamp: data.timestamp || Date.now(),
        source: 'external_device'
      };

      // 转换为像素坐标
      const pixelPosition = convertNormalizedToPixel(clampedX, clampedY);

      // 更新状态
      setState(prev => ({
        ...prev,
        lastTDCCoordinate: tdcMessage,
        messageCount: prev.messageCount + 1,
        tdcPosition: pixelPosition,
        lastUpdateTime: Date.now()
      }));

      // 调用回调函数
      if (onTDCUpdate) {
        onTDCUpdate(tdcMessage, pixelPosition);
      }

      console.log(`[useExternalTDCControl] TDC坐标已更新: 归一化(${clampedX.toFixed(6)}, ${clampedY.toFixed(6)}) -> 像素(${pixelPosition.x.toFixed(1)}, ${pixelPosition.y.toFixed(1)})`);

    } catch (error) {
      console.error('[useExternalTDCControl] 解析外部设备消息失败:', error);
    }
  }, [hasForceSwitchChanged, onTDCUpdate, convertNormalizedToPixel, onForcePress]);

  // 连接WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[useExternalTDCControl] WebSocket已连接');
      return;
    }

    console.log(`[useExternalTDCControl] 尝试连接到: ${wsUrl}`);
    
    setState(prev => ({
      ...prev,
      connectionAttempts: prev.connectionAttempts + 1
    }));

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[useExternalTDCControl] ✅ 连接成功');
        setState(prev => ({
          ...prev,
          connected: true,
          error: null
        }));
      };

      ws.onmessage = (event) => {
        processExternalMessage(event.data);
      };

      ws.onerror = (error) => {
        console.error('[useExternalTDCControl] WebSocket错误:', error);
        setState(prev => ({
          ...prev,
          error: 'WebSocket连接错误'
        }));
      };

      ws.onclose = (event) => {
        console.log(`[useExternalTDCControl] 连接已关闭: code=${(event as CloseEvent).code}, reason=${(event as CloseEvent).reason}`);
        setState(prev => ({
          ...prev,
          connected: false
        }));
        
        // 自动重连
        scheduleReconnect();
      };

    } catch (error) {
      console.error('[useExternalTDCControl] 创建WebSocket连接失败:', error);
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : '连接失败'
      }));
      scheduleReconnect();
    }
  }, [wsUrl, processExternalMessage]);

  // 安排重连
  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    const delay = Math.min(5000, 1000 * Math.pow(1.5, state.connectionAttempts));
    console.log(`[useExternalTDCControl] ${delay}ms后尝试重连...`);

    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect, state.connectionAttempts]);

  // 断开连接
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setState(prev => ({
      ...prev,
      connected: false,
      error: null
    }));

    console.log('[useExternalTDCControl] 已断开连接');
  }, []);

  // 设置变化检测阈值
  const setChangeThreshold = useCallback((threshold: number) => {
    changeThreshold.current = Math.max(0.0001, Math.min(0.1, threshold));
    console.log(`[useExternalTDCControl] 变化阈值已设置为: ${changeThreshold.current.toFixed(6)}`);
  }, []);

  // 发送测试消息（用于调试）
  const sendTestMessage = useCallback((forceSwitch: [number, number]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const testMessage: ExternalDeviceMessage = {
        RawInput: 0.0,
        YawInput: 0.0,
        PitchInput: 0.0,
        Fire: false,
        Throttle: 0.0,
        PawnControl: false,
        ForcePress: false,
        ForceSwitch: forceSwitch,
        timestamp: Date.now()
      };

      wsRef.current.send(JSON.stringify(testMessage));
      console.log(`[useExternalTDCControl] 已发送测试消息: ForceSwitch=[${forceSwitch[0]}, ${forceSwitch[1]}]`);
    } else {
      console.warn('[useExternalTDCControl] WebSocket未连接，无法发送测试消息');
    }
  }, []);

  // 手动设置TDC位置（用于测试或初始化）
  const setTDCPosition = useCallback((normalizedX: number, normalizedY: number) => {
    const clampedX = Math.max(-1, Math.min(1, normalizedX));
    const clampedY = Math.max(-1, Math.min(1, normalizedY));
    
    const pixelPosition = convertNormalizedToPixel(clampedX, clampedY);
    
    const tdcMessage: TDCCoordinateMessage = {
      type: 'tdc_coordinate',
      x: clampedX,
      y: clampedY,
      timestamp: Date.now(),
      source: 'manual'
    };

    setState(prev => ({
      ...prev,
      lastTDCCoordinate: tdcMessage,
      tdcPosition: pixelPosition,
      lastUpdateTime: Date.now()
    }));

    if (onTDCUpdate) {
      onTDCUpdate(tdcMessage, pixelPosition);
    }

    console.log(`[useExternalTDCControl] 手动设置TDC位置: 归一化(${clampedX.toFixed(6)}, ${clampedY.toFixed(6)}) -> 像素(${pixelPosition.x.toFixed(1)}, ${pixelPosition.y.toFixed(1)})`);
  }, [convertNormalizedToPixel, onTDCUpdate]);

  // 检查TDC控制是否活跃（最近是否有更新）
  const isTDCControlActive = useCallback((timeoutMs: number = 2000): boolean => {
    if (state.lastUpdateTime === 0) return false;
    return (Date.now() - state.lastUpdateTime) < timeoutMs;
  }, [state.lastUpdateTime]);

  // 获取当前TDC的归一化坐标
  const getCurrentNormalizedCoordinate = useCallback((): [number, number] | null => {
    if (!state.lastTDCCoordinate) return null;
    return [state.lastTDCCoordinate.x, state.lastTDCCoordinate.y];
  }, [state.lastTDCCoordinate]);

  // 初始化连接
  useEffect(() => {
    connect();

    // 清理函数
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // 返回hook接口
  return {
    // 状态
    connected: state.connected,
    error: state.error,
    lastTDCCoordinate: state.lastTDCCoordinate,
    messageCount: state.messageCount,
    connectionAttempts: state.connectionAttempts,
    tdcPosition: state.tdcPosition,
    lastUpdateTime: state.lastUpdateTime,
    
    // 方法
    connect,
    disconnect,
    setChangeThreshold,
    sendTestMessage,
    setTDCPosition,
    isTDCControlActive,
    getCurrentNormalizedCoordinate,
    convertNormalizedToPixel,
    
    // 配置
    changeThreshold: changeThreshold.current,
    wsUrl,
    coordinateConfig
  };
};

export default useExternalTDCControl;
