import React from 'react';

interface ConnectionStatusProps {
  connected: boolean;
  error: string | null;
  style?: React.CSSProperties;
}

const ConnectionStatus: React.FC<ConnectionStatusProps> = ({ connected, error, style }) => {
  return (
    <div style={{ ...style }}>
      {connected ? (
        <div style={{ 
          backgroundColor: 'rgba(0, 128, 0, 0.3)', 
          color: '#00ff00',
          padding: '4px 8px',
          borderRadius: '4px',
          fontSize: '12px',
          display: 'flex',
          alignItems: 'center'
        }}>
          <div style={{ 
            width: '8px', 
            height: '8px', 
            borderRadius: '50%', 
            backgroundColor: '#00ff00',
            marginRight: '6px'
          }} />
          已连接
        </div>
      ) : (
        <div style={{ 
          backgroundColor: 'rgba(220, 0, 0, 0.3)', 
          color: '#ff6666',
          padding: '4px 8px',
          borderRadius: '4px',
          fontSize: '12px',
          display: 'flex',
          alignItems: 'center'
        }}>
          <div style={{ 
            width: '8px', 
            height: '8px', 
            borderRadius: '50%', 
            backgroundColor: '#ff6666',
            marginRight: '6px'
          }} />
          {error ? `错误: ${error}` : '未连接'}
        </div>
      )}
    </div>
  );
};

export default ConnectionStatus; 