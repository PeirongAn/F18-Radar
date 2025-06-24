import agentStore from '../stores/AgentStore';

const sounds = {
  missileUp: new Audio('/sounds/MissileLaunch.wav'),
  missileDown: new Audio('/sounds/MissileLaunch.wav'),
  threatUpgrade: new Audio('/sounds/Tracking.wav'),
  saInit: new Audio('/sounds/ThreatNew.wav'),
  radarRange: new Audio('/sounds/RadarRange.mp3'), // 使用 ThreatNew.wav 作为 test.wav 的替代品
  radarHeight: new Audio('/sounds/RadarHeight.mp3'),
};

type SoundType = keyof typeof sounds;

class AudioManager {
  play(type: SoundType) {
    if (!agentStore.audioEnabled) {
      console.log(`[AudioManager] 音频播放已禁用，跳过播放: ${type}`);
      return;
    }

    const audio = sounds[type];
    if (audio) {
      audio.currentTime = 0;
      audio.play().catch(err => console.error(`[AudioManager] 播放音频失败 (${type}):`, err));
    } else {
      console.warn(`[AudioManager] 未找到音效类型: ${type}`);
    }
  }
}

// 创建一个单例
const audioManager = new AudioManager();

export default audioManager; 