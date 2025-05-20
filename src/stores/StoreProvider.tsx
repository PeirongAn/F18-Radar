import React, { createContext, useContext, useEffect } from 'react';
import { observer } from 'mobx-react-lite';
import radarStore from './RadarStore';
import useRadarData from '../hooks/useRadarData';

// 创建Store上下文
export const StoreContext = createContext({
  radarStore
});

// Store Provider组件
export const StoreProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // 获取雷达数据hook
  const radarDataHook = useRadarData();
  
  // 将雷达数据hook注入到store
  useEffect(() => {
    radarStore.setRadarDataHook(radarDataHook);
    
    const syncTaskId = () => {
      radarStore.setTaskId(radarDataHook.taskId);
    };
    
    const syncAntennaStatus = () => {
      radarStore.setAntennaAdjustmentRequired(radarDataHook.antennaAdjustmentRequired);
    };

    const syncUserId = () => {
      radarStore.setUserId(radarDataHook.userId);
    };
    
    // 初始同步
    syncTaskId();
    syncAntennaStatus();
    syncUserId();
    
    // 创建一个轮询同步的计时器
    const intervalId = setInterval(() => {
      syncTaskId();
      syncAntennaStatus();
      syncUserId();
    }, 1000); // 每秒同步一次
    
    return () => {
      clearInterval(intervalId); // 清理计时器
    };
  }, [radarDataHook]);
  
  return (
    <StoreContext.Provider value={{ radarStore }}>
      {children}
    </StoreContext.Provider>
  );
};

// 自定义hook，用于在组件中访问store
export const useStore = () => useContext(StoreContext);

// 导出一个ObserverComponent高阶组件，以便更容易地创建观察者组件
export const createObserver = <P extends object>(
  Component: React.ComponentType<P>
) => observer(Component as any) as React.FC<P>;

export default StoreProvider; 