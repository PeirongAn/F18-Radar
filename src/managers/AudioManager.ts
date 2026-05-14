import agentStore from '../stores/AgentStore';

type SoundType = 'missileUp' | 'missileDown' | 'threatUpgrade' | 'saInit' | 'radarRange' | 'radarHeight' | 'radarAISelect';
type RadarPromptType = 'radarRange' | 'radarHeight';

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
  private unlocked = false;
  private pendingSounds: SoundType[] = [];
  private playedKeys = new Set<string>();
  private radarPromptQueue: RadarPromptType[] = [];
  private radarPromptPlaying = false;

  constructor() {
    if (typeof window !== 'undefined') {
      const unlockOnUserGesture = () => this.unlock();
      window.addEventListener('pointerdown', unlockOnUserGesture, { once: true, capture: true });
      window.addEventListener('keydown', unlockOnUserGesture, { once: true, capture: true });
    }
  }

  unlock() {
    if (this.unlocked) return;

    const audio = new Audio(soundPaths.radarRange);
    audio.volume = 0;
    audio.play()
      .then(() => {
        audio.pause();
        audio.currentTime = 0;
        audio.volume = 1;
        this.unlocked = true;
        this.flushPendingSounds();
      })
      .catch(() => {
        this.unlocked = false;
      });
  }

  play(type: SoundType, queueOnFailure = false) {
    if (!agentStore.audioEnabled) return;

    const audio = new Audio(soundPaths[type]);
    audio.play().catch(() => {
      if (queueOnFailure) {
        this.pendingSounds.push(type);
      }
    });
  }

  playOnce(key: string, type: SoundType) {
    if (this.playedKeys.has(key)) return;
    this.playedKeys.add(key);
    this.play(type, false);
  }

  playRadarPrompt(type: RadarPromptType) {
    if (!agentStore.audioEnabled) return;
    this.radarPromptQueue.push(type);
    this.flushRadarPromptQueue();
  }

  playRadarPromptOnce(key: string, type: RadarPromptType) {
    if (this.playedKeys.has(key)) return;
    this.playedKeys.add(key);
    this.playRadarPrompt(type);
  }

  private flushPendingSounds() {
    const sounds = [...this.pendingSounds];
    this.pendingSounds = [];
    sounds.forEach(type => this.play(type));
  }

  private flushRadarPromptQueue() {
    if (this.radarPromptPlaying) return;

    const next = this.radarPromptQueue.shift();
    if (!next) return;

    this.radarPromptPlaying = true;
    const audio = new Audio(soundPaths[next]);
    let completed = false;
    let fallbackTimer: number | undefined;

    const complete = () => {
      if (completed) return;
      completed = true;
      if (fallbackTimer !== undefined) {
        window.clearTimeout(fallbackTimer);
      }
      audio.removeEventListener('ended', complete);
      audio.removeEventListener('error', complete);
      this.radarPromptPlaying = false;
      this.flushRadarPromptQueue();
    };

    audio.addEventListener('ended', complete);
    audio.addEventListener('error', complete);
    fallbackTimer = window.setTimeout(complete, 6000);
    audio.play().catch(complete);
  }
}

const audioManager = new AudioManager();
export default audioManager;
