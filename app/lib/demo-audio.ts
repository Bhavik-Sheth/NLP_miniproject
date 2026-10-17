// Pre-rendered Rime clips for the public /demo replay. public/demo-audio/manifest.json maps the
// exact reply text (as it appears in demo-data.json) to a relative clip path. Everything here
// degrades to "no clip" when the manifest or a file is missing, so the demo still works silently.

type Manifest = Record<string, string>;

let manifestPromise: Promise<Manifest> | null = null;

const siteUrl = (path: string) => new URL(path, window.location.origin + "/").href;

/** Fetch (once) the text → clip-path manifest. Resolves to {} if it is not there yet. */
export function loadManifest(): Promise<Manifest> {
  if (typeof window === "undefined") return Promise.resolve({});
  if (!manifestPromise) {
    manifestPromise = fetch(siteUrl("demo-audio/manifest.json"), { cache: "no-cache" })
      .then((r) => (r.ok ? (r.json() as Promise<unknown>) : {}))
      .then((m) => (m && typeof m === "object" && !Array.isArray(m) ? (m as Manifest) : {}))
      .catch(() => ({}) as Manifest)
      .then((m) => {
        // clips are generated separately; don't pin an empty result, retry on the next call
        if (!Object.keys(m).length) manifestPromise = null;
        return m;
      });
  }
  return manifestPromise;
}

/** Absolute URL of the clip for this exact reply text, or null if there is none. */
export async function clipUrl(text: string): Promise<string | null> {
  const m = await loadManifest();
  const rel = m[text] ?? m[text.trim()];
  return rel ? siteUrl(rel.replace(/^\/+/, "")) : null;
}

// 10 ms of 8-bit silence; playing it inside a click unlocks the element on iOS/Safari.
const SILENCE =
  "data:audio/wav;base64,UklGRnQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVAAAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==";

/**
 * Create one audio element and unlock it. Call synchronously inside a user gesture, then reuse
 * the element for every clip via playClip(url, { audio }).
 */
export function unlockAudio(): HTMLAudioElement {
  const audio = new Audio();
  audio.preload = "auto";
  audio.src = SILENCE;
  audio.play().then(
    () => {
      if (audio.src === SILENCE) audio.pause(); // a real clip may already have taken over
    },
    () => undefined,
  );
  return audio;
}

export type ClipHandlers = {
  /** element to reuse (from unlockAudio); a new one is created otherwise */
  audio?: HTMLAudioElement | null;
  muted?: boolean;
  /** duration in seconds, once metadata is known */
  onStart?: (duration: number) => void;
  /** fired exactly once: clip ended, failed to load, or playback was refused */
  onEnd?: (failed: boolean) => void;
};

// which playClip call currently owns each element, so a superseded call never reports back
const owner = new WeakMap<HTMLAudioElement, object>();

/** Play a clip; returns the element it plays on. Call stopClip(audio) to cut it off. */
export function playClip(url: string, { audio, muted = false, onStart, onEnd }: ClipHandlers = {}): HTMLAudioElement {
  const el = audio ?? new Audio();
  stopClip(el);
  const token = {};
  owner.set(el, token);
  const done = (failed: boolean) => {
    if (owner.get(el) !== token) return;
    owner.delete(el);
    el.onended = el.onerror = el.onloadedmetadata = null;
    onEnd?.(failed);
  };
  el.onloadedmetadata = () => {
    el.onloadedmetadata = null;
    onStart?.(Number.isFinite(el.duration) ? el.duration : 0);
  };
  el.onended = () => done(false);
  el.onerror = () => done(true);
  el.muted = muted;
  el.preload = "auto";
  el.src = url;
  el.play().catch(() => done(true));
  return el;
}

export function stopClip(audio: HTMLAudioElement | null | undefined) {
  if (!audio) return;
  owner.delete(audio);
  audio.onended = audio.onerror = audio.onloadedmetadata = null;
  audio.pause();
}
