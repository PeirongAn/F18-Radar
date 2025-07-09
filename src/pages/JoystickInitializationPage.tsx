import React from 'react';
import JoystickInitializationPanel from '../components/JoystickInitializationPanel';

const JoystickInitializationPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-900 p-4">
      <div className="container mx-auto">
        <JoystickInitializationPanel />
      </div>
    </div>
  );
};

export default JoystickInitializationPage; 