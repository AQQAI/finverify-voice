// signs.js — DEMO ONLY: teach-by-example hand signs that drive the conversation.
// Not Indian Sign Language translation. Static hand shapes only (no movement).
//
// How it works:
//  1. MediaPipe Hand Landmarker (Google) finds 21 points on your hand in each webcam frame.
//  2. Each frame becomes a 42-number "shape" (x,y of each point, relative to the wrist, size-normalised,
//     mirrored so left and right hands look the same).
//  3. You teach each sign by holding it for ~2 s (40 frames). Stored only in this browser.
//  4. Recognition = nearest neighbours (k=5) + a distance limit to reject unknown shapes,
//     and the same sign must hold steady for ~0.5 s before it counts. Then a 2 s cooldown.
import { FilesetResolver, HandLandmarker } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const WASM = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const STORE_KEY = "fv-signs-v1";
const SAMPLES_PER_SIGN = 40, K = 5, STABLE_FRAMES = 14, COOLDOWN_MS = 2000;

export const SIGNS = [
  { id: "yes",     en: "Yes",            hi: "हाँ",          say: { en: "yes", hi: "हाँ" } },
  { id: "no",      en: "No",             hi: "नहीं",         say: { en: "no", hi: "नहीं" } },
  { id: "repeat",  en: "Repeat",         hi: "फिर से",       say: { en: "repeat that", hi: "फिर से" } },
  { id: "stop",    en: "Stop",           hi: "रुको",         say: { en: "stop", hi: "बंद करो" } },
  { id: "checkup", en: "Start checkup",  hi: "चेकअप शुरू",   say: { en: "start tax checkup", hi: "टैक्स चेकअप" } },
];
const CONNECTIONS = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];

let landmarker = null, video = null, canvas = null, ctx = null, running = false, stream = null;
let data = load();                 // { signId: [[42 numbers], ...] }
let teaching = null;               // { id, left }
let streak = { id: null, n: 0 }, lastFired = 0;
let onSign = () => {}, onStatus = () => {};

function load(){ try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch(e) { return {}; } }
function save(){ try { localStorage.setItem(STORE_KEY, JSON.stringify(data)); } catch(e) {} }

// ---- features: wrist-relative, scale-normalised, mirrored for left hands ----
export function features(points, isLeft){
  const w = points[0];
  let pts = points.map(p => [(p.x - w.x) * (isLeft ? -1 : 1), p.y - w.y]);
  const scale = Math.max(...pts.map(([x, y]) => Math.hypot(x, y))) || 1;
  return pts.flatMap(([x, y]) => [x / scale, y / scale]);
}
const dist = (a, b) => Math.sqrt(a.reduce((s, v, i) => s + (v - b[i]) ** 2, 0));

// Typical distance between samples of the same sign -> how far away a new frame may be.
function limits(){
  const out = {};
  for (const [id, xs] of Object.entries(data)){
    if (xs.length < 2) continue;
    let sum = 0, n = 0;
    for (let i = 0; i < xs.length; i += 4){
      let best = Infinity;
      for (let j = 0; j < xs.length; j++) if (j !== i) best = Math.min(best, dist(xs[i], xs[j]));
      sum += best; n++;
    }
    out[id] = Math.max(0.12, 4 * (sum / n));
  }
  return out;
}
let LIMITS = limits();

export function classify(f){
  const all = [];
  for (const [id, xs] of Object.entries(data)) for (const x of xs) all.push([dist(f, x), id]);
  if (all.length < K) return null;
  all.sort((a, b) => a[0] - b[0]);
  const votes = {};
  for (const [, id] of all.slice(0, K)) votes[id] = (votes[id] || 0) + 1;
  const [id, v] = Object.entries(votes).sort((a, b) => b[1] - a[1])[0];
  const nearest = all.find(([, i]) => i === id)[0];
  if (v < Math.ceil(K / 2) + 1 || nearest > (LIMITS[id] ?? 0.2)) return null;   // unsure -> nothing
  return id;
}

function draw(hands){
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.lineWidth = 3;
  for (const pts of hands){
    ctx.strokeStyle = "rgba(31,122,77,.9)"; ctx.fillStyle = "#fff";
    for (const [a, b] of CONNECTIONS){
      ctx.beginPath();
      ctx.moveTo((1 - pts[a].x) * canvas.width, pts[a].y * canvas.height);   // mirrored like a selfie
      ctx.lineTo((1 - pts[b].x) * canvas.width, pts[b].y * canvas.height);
      ctx.stroke();
    }
    for (const p of pts){ ctx.beginPath(); ctx.arc((1 - p.x) * canvas.width, p.y * canvas.height, 4, 0, 7); ctx.fill(); ctx.stroke(); }
  }
}

function loop(){
  if (!running) return;
  if (video.readyState >= 2){
    const r = landmarker.detectForVideo(video, performance.now());
    const hands = r.landmarks || [];
    draw(hands);
    if (hands.length){
      const isLeft = ((r.handedness?.[0]?.[0]?.categoryName) || "Right") === "Left";
      const f = features(hands[0], isLeft);
      if (teaching){
        (data[teaching.id] ||= []).push(f);
        teaching.left--;
        onStatus({ teaching: teaching.id, progress: 1 - teaching.left / SAMPLES_PER_SIGN });
        if (teaching.left <= 0){ save(); LIMITS = limits(); onStatus({ taught: teaching.id }); teaching = null; }
      } else {
        const id = classify(f);
        streak = id === streak.id ? { id, n: streak.n + 1 } : { id, n: 1 };
        onStatus({ seeing: id, steady: Math.min(1, streak.n / STABLE_FRAMES) });
        const now = performance.now();
        if (id && streak.n === STABLE_FRAMES && now - lastFired > COOLDOWN_MS){
          lastFired = now; onSign(SIGNS.find(s => s.id === id));
        }
      }
    } else if (!teaching){
      streak = { id: null, n: 0 }; onStatus({ seeing: null, steady: 0 });
    }
  }
  requestAnimationFrame(loop);
}

export async function start(videoEl, canvasEl, handlers){
  video = videoEl; canvas = canvasEl; ctx = canvas.getContext("2d");
  onSign = handlers.onSign || onSign; onStatus = handlers.onStatus || onStatus;
  onStatus({ loading: true });
  if (!landmarker){
    const vision = await FilesetResolver.forVisionTasks(WASM);
    landmarker = await HandLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: MODEL, delegate: "GPU" }, runningMode: "VIDEO", numHands: 1 });
  }
  stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
  video.srcObject = stream; await video.play();
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  running = true; onStatus({ ready: true }); requestAnimationFrame(loop);
}

export function stop(){
  running = false; teaching = null;
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
}
export function teach(id){ data[id] = []; teaching = { id, left: SAMPLES_PER_SIGN }; }
export function taught(){ return Object.fromEntries(SIGNS.map(s => [s.id, (data[s.id] || []).length >= SAMPLES_PER_SIGN])); }
export function forget(){ data = {}; save(); LIMITS = limits(); }
