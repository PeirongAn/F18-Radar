import React, { useState, useEffect, useCallback, useRef } from 'react';
import { globalWS } from '../hooks/useRadarData';

interface JoystickData {
  main_x: number;      // 主轴X坐标 (-1 到 1)
  main_y: number;      // 主轴Y坐标 (-1 到 1)
  sub_y: number;       // 副轴Y坐标 (-1 到 1)
  button1: boolean;    // 按钮1状态
  button2: boolean;    // 按钮2状态
  button7: boolean;    // 按钮7状态
}

interface RawData {
  x_axis: number;
  y_axis: number;
  ry_axis: number;
}

interface JoystickOffset {
  x: number;
  y: number;
  ry: number;
}

const JoystickInitializationPanel: React.FC = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [joystickData, setJoystickData] = useState<JoystickData>({
    main_x: 0.0,
    main_y: 0.0,
    sub_y: 0.0,
    button1: false,
    button2: false,
    button7: false
  });
  const [rawData, setRawData] = useState<RawData>({
    x_axis: 0,
    y_axis: 0,
    ry_axis: 0
  });
  const [offset, setOffset] = useState<JoystickOffset>({
    x: 0,
    y: 0,
    ry: 0
  });
  const [status, setStatus] = useState('未连接');
  const [isBoundaryDetecting, setIsBoundaryDetecting] = useState(false);
  const [deviceStatus, setDeviceStatus] = useState('disconnected');
  const [wsConnected, setWsConnected] = useState(false);
  
  // 消息去重相关状态
  const lastProcessedMessageIdRef = useRef<string>('');
  
      // 防抖相关状态

  // 监听WebSocket连接状态
  useEffect(() => {
    const handleWebSocketState = (state: any) => {
      setWsConnected(state.connected);
      if (!state.connected) {
        setIsConnected(false);
        setIsSubscribed(false);
        setStatus('WebSocket未连接');
      } else {
        setStatus('WebSocket已连接');
      }
    };

    // 订阅WebSocket状态变化
    globalWS.subscribe(handleWebSocketState);
    
    // 获取初始状态
    const initialState = globalWS.getState();
    handleWebSocketState(initialState);
    
    // WebSocket 连接由 App.tsx 自动启动逻辑处理，此处不再单独连接
    


    // 监听操纵杆相关消息
    const handleMessage = (message: any) => {
      if (!message || !message.type) return;

      // 只处理操纵杆相关消息
      if (!message.type.startsWith('joystick_') && message.type !== 'joystick_status' && message.type !== 'error') {
        return;
      }

      // 对操纵杆数据使用简化日志
      if (message.type === 'joystick_data') {
        console.log('[操纵杆面板] 数据更新:', {
          main_x: message.data?.main_x?.toFixed(3),
          main_y: message.data?.main_y?.toFixed(3),
          buttons: message.data?.buttons
        });
      } else {
        console.log('[操纵杆面板] 收到消息:', message);
      }

      switch (message.type) {
        case 'joystick_data':
          if (message.data) {
            setJoystickData({
              main_x: message.data.main_x,
              main_y: message.data.main_y,
              sub_y: message.data.sub_y,
              button1: message.data.buttons.button1,
              button2: message.data.buttons.button2,
              button7: message.data.buttons.button7
            });
          }
          if (message.raw_data) {
            setRawData({
              x_axis: message.raw_data.x_axis,
              y_axis: message.raw_data.y_axis,
              ry_axis: message.raw_data.ry_axis
            });
          }
          if (message.device_status) {
            setDeviceStatus(message.device_status);
          }
          break;

        case 'joystick_connect_response':
          if (message.success) {
            setIsConnected(true);
            setStatus('操纵杆已连接');
            // 连接成功后自动订阅数据流
            if (wsConnected) {
              globalWS.sendMessage({
                type: 'joystick_subscribe',
                timestamp: Date.now()
              });
            }
          } else {
            setStatus(`连接失败: ${message.message}`);
          }
          break;

        case 'joystick_disconnect_response':
          setIsConnected(false);
          setIsSubscribed(false);
          setStatus('操纵杆已断开');
          break;

        case 'joystick_reset_center_response':
          if (message.success) {
            setStatus('中心已重置');
            if (message.center_position) {
              console.log('中心位置:', message.center_position);
            }
          } else {
            setStatus(`重置失败: ${message.message}`);
          }
          break;
        case 'joystick_status':
          console.log('操纵杆状态消息:', message);
          if (message.event) {
            switch (message.event) {
              case 'boundary_detection_started':
                console.log('[操纵杆面板] 边界检测启动事件:', message.data);
                setIsBoundaryDetecting(true);
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                } else {
                  setStatus('边界检测已启动');
                }
                break;
              
              case 'boundary_detection_completed':
                console.log('[操纵杆面板] 边界检测停止事件:', message.data);
                setIsBoundaryDetecting(false);
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                } else {
                  setStatus(`边界检测完成`);
                }
                break;
              
              case 'device_connected':
                setIsConnected(true);
                setDeviceStatus('connected');
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                } else {
                  setStatus('操纵杆已连接');
                }
                break;
              
              case 'device_disconnected':
                setIsConnected(false);
                setIsSubscribed(false);
                setDeviceStatus('disconnected');
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                } else {
                  setStatus('操纵杆已断开');
                }
                break;
              
              case 'center_reset':
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                } else {
                  setStatus('中心已重置');
                }
                break;
              
              default:
                console.log('未处理的操纵杆状态事件:', message.event);
                if (message.data && message.data.message) {
                  setStatus(message.data.message);
                }
                break;
            }
          }
          break;

        case 'joystick_subscribe_response':
          if (message.success) {
            setIsSubscribed(true);
            setStatus('已订阅操纵杆数据流');
          } else {
            setStatus(`订阅失败: ${message.message}`);
          }
          break;

       

        case 'error':
          setStatus(`错误: ${message.message}`);
          break;
      }
    };

    // 使用事件驱动的消息监听机制，避免轮询
    const handleWebSocketStateChange = (state: any) => {
      // 获取最新消息
      const lastMessage = globalWS.getLastMessage();
      
      // 只处理操纵杆相关消息
      if (lastMessage && 
          (lastMessage.type?.startsWith('joystick_') || lastMessage.type === 'joystick_status' || lastMessage.type === 'error')) {
        
        // 生成消息ID用于去重
        const messageId = `${lastMessage.type}_${lastMessage.timestamp || 0}_${lastMessage.event || ''}_${JSON.stringify(lastMessage.data || {})}`;
        
        console.log('[操纵杆面板] 消息去重检查:', {
          messageId,
          lastProcessedId: lastProcessedMessageIdRef.current,
          isNew: messageId !== lastProcessedMessageIdRef.current
        });
        
        // 只处理新消息
        if (messageId !== lastProcessedMessageIdRef.current) {
          lastProcessedMessageIdRef.current = messageId;
          handleMessage(lastMessage);
        }
      }
    };

    // 订阅WebSocket状态变化，当有新消息时会触发回调
    const unsubscribe = globalWS.subscribe(handleWebSocketStateChange);

    return () => {
      // 取消订阅
      unsubscribe();
    };
  }, [isBoundaryDetecting, wsConnected]);

  // 连接操纵杆
  const connectJoystick = useCallback(() => {
    if (!wsConnected) {
      setStatus('WebSocket未连接');
      return;
    }

    setStatus('正在连接操纵杆...');
    globalWS.sendMessage({
      type: 'joystick_connect',
      timestamp: Date.now()
    });
  }, [wsConnected]);

  // 断开操纵杆
  const disconnectJoystick = useCallback(() => {
    if (!wsConnected) {
      setStatus('WebSocket未连接');
      return;
    }

    globalWS.sendMessage({
      type: 'joystick_disconnect',
      timestamp: Date.now()
    });
    
    // 同时取消订阅
    if (isSubscribed) {
      globalWS.sendMessage({
        type: 'joystick_unsubscribe',
        timestamp: Date.now()
      });
    }
  }, [wsConnected, isSubscribed]);

  // 订阅操纵杆数据流
  const subscribeToJoystickData = useCallback(() => {
    if (!wsConnected) {
      setStatus('WebSocket未连接');
      return;
    }

    globalWS.sendMessage({
      type: 'joystick_subscribe',
      timestamp: Date.now()
    });
  }, [wsConnected]);

  // 重置中心位置
  const resetCenter = useCallback(() => {
    if (!wsConnected) {
      setStatus('WebSocket未连接');
      return;
    }

    if (!isConnected) {
      setStatus('请先连接操纵杆');
      return;
    }

    globalWS.sendMessage({
      type: 'joystick_reset_center',
      timestamp: Date.now()
    });
  }, [wsConnected, isConnected]);

  // 切换边界检测模式
  const toggleBoundaryDetection = useCallback(() => {
    if (!wsConnected) {
      setStatus('WebSocket未连接');
      return;
    }

    if (!isConnected) {
      setStatus('请先连接操纵杆');
      return;
    }

    if (!isBoundaryDetecting) {
      globalWS.sendMessage({
        type: 'joystick_start_boundary',
        timestamp: Date.now()
      });
    } else {
      globalWS.sendMessage({
        type: 'joystick_stop_boundary',
        timestamp: Date.now()
      });
    }
  }, [wsConnected, isConnected, isBoundaryDetecting]);

  // 格式化数值显示
  const formatValue = (value: number): string => {
    return value >= 0 ? `+${value.toFixed(3)}` : `${value.toFixed(3)}`;
  };

  return (
    <div className="bg-gray-900 text-white p-6 rounded-lg shadow-lg max-w-4xl mx-auto">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-center mb-2">操纵杆初始化面板</h2>
        <div className="text-center text-sm text-gray-400">
          WebSocket: <span className={`font-semibold ${wsConnected ? 'text-green-400' : 'text-red-400'}`}>
            {wsConnected ? '已连接' : '未连接'}
          </span>
          {' | '}
          操纵杆: <span className={`font-semibold ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
            {isConnected ? '已连接' : '未连接'}
          </span>
          {' | '}
          数据流: <span className={`font-semibold ${isSubscribed ? 'text-green-400' : 'text-red-400'}`}>
            {isSubscribed ? '已订阅' : '未订阅'}
          </span>
        </div>
        <div className="text-center text-sm text-gray-400 mt-1">
          状态: <span className={`font-semibold ${status.includes('错误') || status.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>
            {status}
          </span>
        </div>
      </div>

      {/* 数据显示区域 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* 主轴坐标显示 */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <h3 className="text-lg font-semibold mb-4 text-blue-400">主轴坐标 (X, Y)</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-2xl font-mono mb-2">
                X: <span className="text-cyan-400">{formatValue(joystickData.main_x)}</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div 
                  className="bg-cyan-400 h-2 rounded-full transition-all duration-100"
                  style={{ 
                    width: `${(joystickData.main_x + 1) * 50}%`,
                    marginLeft: joystickData.main_x < 0 ? `${(joystickData.main_x + 1) * 50}%` : '50%'
                  }}
                />
              </div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-mono mb-2">
                Y: <span className="text-cyan-400">{formatValue(joystickData.main_y)}</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div 
                  className="bg-cyan-400 h-2 rounded-full transition-all duration-100"
                  style={{ 
                    width: `${(joystickData.main_y + 1) * 50}%`,
                    marginLeft: joystickData.main_y < 0 ? `${(joystickData.main_y + 1) * 50}%` : '50%'
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* 副轴坐标显示 */}
        <div className="bg-gray-800 p-4 rounded-lg">
          <h3 className="text-lg font-semibold mb-4 text-green-400">副轴坐标 (Y)</h3>
          <div className="text-center">
            <div className="text-2xl font-mono mb-2">
              Y: <span className="text-green-400">{formatValue(joystickData.sub_y)}</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div 
                className="bg-green-400 h-2 rounded-full transition-all duration-100"
                style={{ 
                  width: `${(joystickData.sub_y + 1) * 50}%`,
                  marginLeft: joystickData.sub_y < 0 ? `${(joystickData.sub_y + 1) * 50}%` : '50%'
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 按钮状态显示 */}
      <div className="bg-gray-800 p-4 rounded-lg mb-6">
        <h3 className="text-lg font-semibold mb-4 text-yellow-400">按钮状态</h3>
        <div className="flex justify-center gap-4">
          <div className={`px-4 py-2 rounded-lg font-semibold transition-all duration-100 ${
            joystickData.button1 
              ? 'bg-green-600 text-white shadow-lg' 
              : 'bg-gray-700 text-gray-400'
          }`}>
            按钮1
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold transition-all duration-100 ${
            joystickData.button2 
              ? 'bg-green-600 text-white shadow-lg' 
              : 'bg-gray-700 text-gray-400'
          }`}>
            按钮2
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold transition-all duration-100 ${
            joystickData.button7 
              ? 'bg-green-600 text-white shadow-lg' 
              : 'bg-gray-700 text-gray-400'
          }`}>
            按钮7
          </div>
        </div>
      </div>

      {/* 控制按钮 */}
      <div className="flex flex-wrap justify-center gap-4 mb-6">
        <button
          onClick={connectJoystick}
          disabled={!wsConnected || isConnected}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
        >
          连接操纵杆
        </button>
        <button
          onClick={resetCenter}
          disabled={!wsConnected || !isConnected}
          className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
        >
          重置中心
        </button>
        <button
          onClick={toggleBoundaryDetection}
          disabled={!wsConnected || !isConnected}
          className={`px-6 py-2 rounded-lg font-semibold transition-colors ${
            isBoundaryDetecting
              ? 'bg-red-600 hover:bg-red-700'
              : 'bg-yellow-600 hover:bg-yellow-700'
          } disabled:bg-gray-600 disabled:cursor-not-allowed`}
        >
          {isBoundaryDetecting ? '停止检测' : '检测边界'}
        </button>
        <button
          onClick={disconnectJoystick}
          disabled={!wsConnected || !isConnected}
          className="px-6 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
        >
          断开连接
        </button>
      </div>

      {/* 原始数据显示 */}
      <div className="bg-gray-800 p-4 rounded-lg">
        <h3 className="text-lg font-semibold mb-2 text-purple-400">原始数据（调试）</h3>
        <div className="font-mono text-sm text-gray-300">
          原始数据: X={rawData.x_axis.toString(16).toUpperCase().padStart(4, '0')} 
          Y={rawData.y_axis.toString(16).toUpperCase().padStart(4, '0')} 
          RY={rawData.ry_axis.toString(16).toUpperCase().padStart(4, '0')}
        </div>
      </div>
    </div>
  );
};

export default JoystickInitializationPanel; 