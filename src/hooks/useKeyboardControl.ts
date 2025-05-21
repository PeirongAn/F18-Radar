import { useEffect } from 'react';

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
  moveStep: number;
  boundaries: {
    minY: number;
    maxY: number;
    minX?: number;
    maxX?: number;
  };
  controls?: {
    up?: string;
    down?: string;
    left?: string;
    right?: string;
  };
  onKeyAction: (action: 'up' | 'down' | 'left' | 'right') => void;
}

export const useKeyboardControl = ({ 
  moveStep, 
  boundaries, 
  controls, 
  onKeyAction 
}: UseKeyboardControlProps) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInputElement = 
        target.tagName === 'INPUT' || 
        target.tagName === 'TEXTAREA' || 
        target.isContentEditable;
      
      if (isInputElement) {
        return;
      }

      const key = e.key.toLowerCase();
      let actionHandled = false;
        
      switch (key) {
        case controls?.up?.toLowerCase() || 'arrowup':
          onKeyAction('up');
          actionHandled = true;
          break;
        case controls?.down?.toLowerCase() || 'arrowdown':
          onKeyAction('down');
          actionHandled = true;
          break;
        case controls?.left?.toLowerCase() || 'arrowleft':
          onKeyAction('left');
          actionHandled = true;
          break;
        case controls?.right?.toLowerCase() || 'arrowright':
          onKeyAction('right');
          actionHandled = true;
          break;
      }

      if (actionHandled) {
        e.preventDefault();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [controls, onKeyAction]);
}; 