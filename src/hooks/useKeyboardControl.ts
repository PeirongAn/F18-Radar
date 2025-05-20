import { useState, useEffect } from 'react';

interface Position {
  x: number;
  y: number;
}

interface Boundaries {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

interface UseKeyboardControlProps {
  initialPosition: { x: number; y: number };
  moveStep: number;
  boundaries: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
  controls?: {
    up?: string;
    down?: string;
    left?: string;
    right?: string;
  };
}

export const useKeyboardControl = ({ 
  initialPosition, 
  moveStep, 
  boundaries, 
  controls 
}: UseKeyboardControlProps) => {
  const [position, setPosition] = useState<Position>(initialPosition);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 检查目标元素是否是输入元素
      const target = e.target as HTMLElement;
      const isInputElement = 
        target.tagName === 'INPUT' || 
        target.tagName === 'TEXTAREA' || 
        target.isContentEditable;
      
      // 如果不是输入元素，则阻止默认行为
      if (!isInputElement) {
        e.preventDefault();
      }
      
      setPosition(prev => {
        const newPos = { ...prev };
        const key = e.key.toLowerCase();
        
        switch (key) {
          case controls?.up || 'arrowup':
            newPos.y = Math.max(boundaries.minY, prev.y - moveStep);
            break;
          case controls?.down || 'arrowdown':
            newPos.y = Math.min(boundaries.maxY, prev.y + moveStep);
            break;
          case controls?.left || 'arrowleft':
            newPos.x = Math.max(boundaries.minX, prev.x - moveStep);
            break;
          case controls?.right || 'arrowright':
            newPos.x = Math.min(boundaries.maxX, prev.x + moveStep);
            break;
        }
        
        return newPos;
      });
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [moveStep, boundaries, controls]);

  return position;
}; 