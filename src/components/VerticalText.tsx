import React from 'react';
import { Text } from 'react-konva';

interface VerticalTextProps {
  x: number;
  y: number;
  text: string;
  fontSize: number;
  spacing?: number;
  color: string;
}

const VerticalText: React.FC<VerticalTextProps> = ({ 
  x, 
  y, 
  text, 
  fontSize, 
  spacing = 15,
  color 
}) => {
  return (
    <>
      {text.split('').map((char, index) => (
        <Text
          key={`${text}-${index}`}
          text={char}
          x={x}
          y={y + index * spacing}
          fontSize={fontSize}
          fill={color}
        />
      ))}
    </>
  );
};

export default VerticalText; 