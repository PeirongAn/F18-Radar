import agentStore from '../stores/AgentStore';

type SoundType = 'missileUp' | 'missileDown' | 'threatUpgrade' | 'saInit' | 'radarRange' | 'radarHeight' | 'radarAISelect';

const soundPaths: Record<SoundType, string> = {
  missileUp: '/sounds/MissileLaunch.wav',
  missileDown: '/sounds/MissileLaunch.wav',
  threatUpgrade: '/sounds/Tracking.wav',
  saInit: '/sounds/ThreatNew.wav',
  radarRange: '/sounds/RadarRange.mp3',
  radarHeight: '/sounds/RadarHeight.mp3',
  radarAISelect: '/sounds/RadarAISelect.mp3',
};

class AudioManager {
  play(type: SoundType) {
    if (!agentStore.audioEnabled) return;

    const audio = new Audio(soundPaths[type]);
    audio.play().catch(() => {});
  }
}

const audioManager = new AudioManager();
export default audioManager;
