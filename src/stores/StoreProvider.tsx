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
  const radarDataHook = useRadarData();
  const { taskId, userId } = radarDataHook;

  // hook 注入：仅在挂载时执行一次，store 持有 hook 引用
  useEffect(() => {
    radarStore.setRadarDataHook(radarDataHook);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // taskId 变化时同步（响应式，无需轮询）
  useEffect(() => {
    radarStore.setTaskId(taskId);
  }, [taskId]);

  // userId 变化时同步（响应式，无需轮询）
  useEffect(() => {
    if (userId) {
      radarStore.setUserId(userId);
    }
  }, [userId]);

  // 注意：antennaAdjustmentRequired 已在 useRadarData 内部直接写入 radarStore，
  // 不在此处同步，避免 StoreProvider 实例的本地 state 覆盖其他实例的重置操作。
  
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