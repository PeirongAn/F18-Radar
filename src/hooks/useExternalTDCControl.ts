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
  ForceSwitch: [number, number]; // TDC坐标数据（保留兼容性）
  PitchPos: number;
  RollPos: number;
  RudderPos: number;
  LeftBrake: number;
  RightBrake: number;
  ButtonK1: boolean;
  ButtonK2: boolean;
  ButtonK3: boolean; // 执行目标锁定（触发Enter效果）
  ButtonK5: boolean;
  ButtonK6: boolean;
  ButtonK7: boolean;
  ButtonK9: boolean;
  TriggerEasy: boolean;
  TriggerHard: boolean;
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
  configLoaded: boolean; // 配置是否已加载
  forceSwitchLocked: boolean; // ForceSwitch是否已锁定（锁定后忽略ForceSwitch变化，直到ButtonK3为true）
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
 * 
 * 工作流程：
 * 1. ForceSwitch: 力敏开关的模拟量坐标，提供TDC位置数据
 * 2. ForcePress: 力敏开关按下时，切换光标位置锁定状态
 *    - 第一次按下 → 锁定TDC光标位置，不再响应ForceSwitch变化
 *    - 第二次按下 → 解锁TDC光标，恢复响应ForceSwitch变化
 *    - 锁定期间，其他功能（如ButtonK3）仍然正常工作
 * 3. ButtonK3: 执行目标锁定效果（真正的目标锁定操作）
 */
const useExternalTDCControl = (
  wsUrl?: string, // 可选参数，如果不提供则从配置文件读取
  coordinateConfig?: CoordinateConfig,
  onTDCUpdate?: (coordinate: TDCCoordinateMessage, pixelPosition: TDCPosition) => void,
  onButtonK3Press?: () => void // ButtonK3回调，触发目标锁定（Enter效果）
) => {
  const [state, setState] = useState<ExternalTDCControlState>({
    connected: false,
    error: null,
    lastTDCCoordinate: null,
    messageCount: 0,
    connectionAttempts: 0,
    tdcPosition: null,
    lastUpdateTime: 0,
    configLoaded: false,
    forceSwitchLocked: false
  });

  // 实际使用的 WebSocket URL
  const [actualWsUrl, setActualWsUrl] = useState<string>(wsUrl || 'ws://localhost:8765');

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const lastForceSwitch = useRef<[number, number] | null>(null);
  const changeThreshold = useRef<number>(0.001); // ForceSwitch变化阈值
  const lastForcePressState = useRef<boolean>(false); // 上一次ForcePress状态，用于检测边缘触发
  const lastButtonK3State = useRef<boolean>(false); // 上一次ButtonK3状态，用于检测边缘触发
  const forceSwitchLockedRef = useRef<boolean>(false); // ForceSwitch锁定状态（使用ref实现同步更新）

  // 从配置文件加载 TDC Server URL
  useEffect(() => {
    // 如果用户提供了 wsUrl 参数，直接使用，不需要加载配置
    if (wsUrl) {
      console.log(`[useExternalTDCControl] 使用用户提供的 URL: ${wsUrl}`);
      setActualWsUrl(wsUrl);
      setState(prev => ({ ...prev, configLoaded: true }));
      return;
    }

    // 从网络加载配置文件
    const loadConfig = async () => {
      try {
        console.log('[useExternalTDCControl] 从配置文件加载 TDC Server URL...');
        const response = await fetch('/agent_level.json');
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const config = await response.json();
        const tdcServerUrl = config.tdcServer || 'ws://localhost:8765';
        console.log(`[useExternalTDCControl] 从配置文件读取到 TDC Server: ${tdcServerUrl}`);
        setActualWsUrl(tdcServerUrl);
        setState(prev => ({ ...prev, configLoaded: true }));
      } catch (error) {
        console.error('[useExternalTDCControl] 加载配置文件失败，使用默认 URL:', error);
        setActualWsUrl('ws://localhost:8765');
        setState(prev => ({ ...prev, configLoaded: true, error: '配置加载失败，使用默认地址' }));
      }
    };

    loadConfig();
  }, [wsUrl]);

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
      
      // 检查ForcePress状态变化（边缘触发：从false变为true时切换锁定状态）
      if (data.ForcePress === true && lastForcePressState.current === false) {
        // 检测到ForcePress按下（上升沿），切换锁定状态
        const newLocked = !forceSwitchLockedRef.current;
        forceSwitchLockedRef.current = newLocked;
        
        setState(prev => ({
          ...prev,
          forceSwitchLocked: newLocked
        }));
        
        console.log(`[useExternalTDCControl] 🎮 ForcePress按下，${newLocked ? '🔒 锁定光标位置' : '🔓 解锁光标位置'}`);
        // ForcePress不触发目标锁定回调
      }
      
      // 更新ForcePress状态
      lastForcePressState.current = data.ForcePress;
      
      // 检查ButtonK3状态变化（边缘触发：从false变为true时执行目标锁定）
      // ButtonK3功能不受ForceSwitch锁定影响，始终可用
      if (data.ButtonK3 === true && lastButtonK3State.current === false) {
        // ButtonK3触发，执行目标锁定效果
        console.log('[useExternalTDCControl] 🎯 ButtonK3按下，执行目标锁定');
        if (onButtonK3Press) {
          onButtonK3Press();
        }
      }
      
      // 更新ButtonK3状态
      lastButtonK3State.current = data.ButtonK3;
      
      // 如果ForceSwitch已锁定，只跳过ForceSwitch坐标处理，其他功能继续
      if (forceSwitchLockedRef.current) {
        // 静默跳过ForceSwitch处理，不输出日志避免刷屏
        return; // 只跳过后续的ForceSwitch坐标更新
      }
      
      // 以下是ForceSwitch坐标处理逻辑（只在未锁定时执行）
      
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
  }, [hasForceSwitchChanged, onTDCUpdate, convertNormalizedToPixel, onButtonK3Press]);

  // 连接WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[useExternalTDCControl] WebSocket已连接');
      return;
    }

    // 检查配置是否已加载
    if (!state.configLoaded) {
      console.log('[useExternalTDCControl] 等待配置加载完成...');
      return;
    }

    console.log(`[useExternalTDCControl] 尝试连接到: ${actualWsUrl}`);
    
    setState(prev => ({
      ...prev,
      connectionAttempts: prev.connectionAttempts + 1
    }));

    try {
      const ws = new WebSocket(actualWsUrl);
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
  }, [actualWsUrl, processExternalMessage, state.configLoaded]);

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
  const sendTestMessage = useCallback((forceSwitch: [number, number], buttonK3: boolean = false) => {
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
        PitchPos: 0.0,
        RollPos: 0.0,
        RudderPos: 0.0,
        LeftBrake: 0.0,
        RightBrake: 0.0,
        ButtonK1: false,
        ButtonK2: false,
        ButtonK3: buttonK3,
        ButtonK5: false,
        ButtonK6: false,
        ButtonK7: false,
        ButtonK9: false,
        TriggerEasy: false,
        TriggerHard: false,
        timestamp: Date.now()
      };

      wsRef.current.send(JSON.stringify(testMessage));
      console.log(`[useExternalTDCControl] 已发送测试消息: ForceSwitch=[${forceSwitch[0]}, ${forceSwitch[1]}], ButtonK3=${buttonK3}`);
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

  // 手动解锁ForceSwitch（通常由ButtonK3触发，这里提供手动方法）
  const unlockForceSwitch = useCallback(() => {
    forceSwitchLockedRef.current = false;
    setState(prev => ({ ...prev, forceSwitchLocked: false }));
    console.log('[useExternalTDCControl] 🔓 手动解锁ForceSwitch');
  }, []);

  // 初始化连接 - 等待配置加载完成后再连接
  useEffect(() => {
    if (state.configLoaded) {
      console.log('[useExternalTDCControl] 配置已加载，开始连接...');
      connect();
    }

    // 清理函数
    return () => {
      disconnect();
    };
  }, [state.configLoaded, connect, disconnect]);

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
    configLoaded: state.configLoaded,
    forceSwitchLocked: state.forceSwitchLocked,
    
    // 方法
    connect,
    disconnect,
    setChangeThreshold,
    sendTestMessage,
    setTDCPosition,
    isTDCControlActive,
    getCurrentNormalizedCoordinate,
    convertNormalizedToPixel,
    unlockForceSwitch,
    
    // 配置
    changeThreshold: changeThreshold.current,
    wsUrl: actualWsUrl,
    coordinateConfig
  };
};

export default useExternalTDCControl;
