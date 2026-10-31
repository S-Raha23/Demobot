// TypeScript mirror of backend/demobot/schemas.py and the run-directory contract
// (docs/run-artifacts.md). Units: table cm, seconds, USD.

export type Vec2 = [number, number];
export type Vec3 = [number, number, number];

export const STAGES = [
  "ingest",
  "calibrate",
  "listen",
  "watch",
  "perceive",
  "ground",
  "twin_build",
  "program",
  "verify",
  "stress",
  "harden",
  "card",
] as const;
export type Stage = (typeof STAGES)[number] | "supervise" | "correct";
export type StageStatus = "todo" | "running" | "done" | "failed" | "skipped";

export interface RunMeta {
  run_id: string;
  title: string;
  created_at: string;
  source: string;
  mode: string;
  status: string;
  fixture?: boolean;
  replay_of?: string | null;
  baked?: boolean;
  card?: SkillCard | null;
}

export interface RunState {
  cursor: string;
  stages: Record<string, StageStatus>;
}

export interface RunDetail {
  run: RunMeta;
  state: RunState | null;
  artifacts: string[];
}

// ---------- events ----------
export type EventType =
  | "stage_start"
  | "stage_end"
  | "model_call"
  | "tool_call"
  | "artifact"
  | "decision"
  | "metric"
  | "log"
  | "error"
  | "question";

export interface Tokens {
  in: number;
  cached: number;
  out: number;
}

export interface RunEvent {
  ts: string;
  run_id: string;
  seq: number;
  stage: string;
  type: EventType;
  model?: string | null;
  provider?: string | null;
  latency_ms?: number | null;
  tokens?: Tokens | null;
  cost_usd?: number | null;
  cached?: boolean | null;
  payload: Record<string, unknown>;
}

export interface StageEndPayload {
  ok: boolean;
  summary: string;
  duration_s: number;
}
export interface ModelCallPayload {
  purpose: string;
  open_weight: boolean;
  frames?: number;
  images?: number;
  audio_s?: number;
  note?: string;
  fixture?: boolean;
}
export interface ArtifactPayload {
  name: string;
  path: string;
  kind: "video" | "image" | "json" | "code" | "trajectory";
  label: string;
}
export interface ToolCallPayload {
  agent: string;
  iteration: number;
  tool: string;
  args: Record<string, unknown>;
  result: {
    ok: boolean;
    error?: string | null;
    clauses_passed?: number;
    clauses_total?: number;
    layout?: string;
  };
}
export interface MetricPayload {
  name: string;
  value: number | boolean | string;
  unit?: string;
  iteration?: number;
}
export interface QuestionPayload {
  id: string;
  text: string;
  options: string[];
}

// ---------- core contracts ----------
export interface IngestInfo {
  source_name: string;
  width: number;
  height: number;
  raw_duration_s: number;
  trim_start_s: number;
  trim_end_s: number;
  duration_s: number;
  analysis_fps: number;
  analysis_frames: number;
  has_audio: boolean;
  keyframes: string[];
  keyframe_times: number[];
}

export interface MarkerPose {
  id: number;
  center_cm: Vec2;
  theta_rad: number;
  corners_cm: Vec2[];
  corners_px: Vec2[];
}

export interface CameraPose {
  focal_px: number;
  principal_px: Vec2;
  focal_source: string;
  position_cm: Vec3;
  look_dir: Vec3;
  tilt_deg: number;
  nadir_cm: Vec2;
  rvec: Vec3;
  tvec: Vec3;
}

export interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface FrameCam {
  t: number;
  rvec: Vec3;
  tvec: Vec3;
  height_cm: number;
  markers_seen: number;
  blurred: boolean;
  interpolated: boolean;
}

export interface CameraTrack {
  fps: number;
  focal_px: number;
  principal_px: Vec2;
  frames: FrameCam[];
}

export type Role = "moved" | "container" | "reference" | "distractor";
export type Shape = "box" | "cylinder" | "sphere";

export interface SceneObject {
  name: string;
  kind: string;
  role: Role;
  shape: Shape;
  x: number;
  y: number;
  z: number;
  yaw: number;
  w: number;
  d: number;
  h: number;
  color: string;
  texture?: string | null;
  hollow?: boolean;
}

export interface Layout {
  id: string;
  source: string;
  description: string;
  seed?: number | null;
  objects: SceneObject[];
  work_area: Rect;
  robot_base_cm: Vec2;
}

export type Quant = "the" | "all" | "pair";
export type Pred =
  | "inside"
  | "left_of"
  | "right_of"
  | "in_front_of"
  | "behind"
  | "near"
  | "collinear"
  | "swapped";

export interface Selector {
  name?: string | null;
  kind?: string | null;
  role?: Role | null;
  names?: string[] | null;
}

export interface GoalClause {
  quant: Quant;
  select: Selector;
  pred: Pred;
  target?: Selector | null;
  point_cm?: Vec2 | null;
  order_by?: "x" | "y" | null;
  order?: string[] | null;
}

export interface ClauseResult {
  clause: GoalClause;
  holds: boolean;
  code?: string | null;
  objects: string[];
  measured: Record<string, number | boolean | string>;
  detail: string;
}

export interface SkillCall {
  skill: string;
  args: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
  t: number;
}

export interface SimResult {
  ok: boolean;
  error?: string | null;
  error_type?: string | null;
  layout_id: string;
  skill_calls: SkillCall[];
  logs: string[];
  final_state: SceneObject[];
  goal_results: ClauseResult[];
  goal_ok: boolean;
  collisions: string[];
  renders: Record<string, string>;
  twin_trajectory?: string | null;
  duration_s: number;
  wall_s: number;
}

export interface Segment {
  t0: number;
  t1: number;
  text: string;
}

export interface Transcript {
  text: string;
  language: string;
  languages: string[];
  segments: Segment[];
  source: "narration" | "correction" | "none";
}

export interface SpecObject {
  name: string;
  kind: string;
  alt_names: string[];
  role: Role;
  color: string;
  est_height_cm: number;
  est_size_cm: Vec2;
}

export interface Step {
  action: "place_in" | "place_next_to" | "place_at";
  object: string;
  target?: string | null;
  relation?: "left_of" | "right_of" | "in_front_of" | "behind" | null;
  t_start: number;
  t_end: number;
  evidence: string;
}

export interface TaskSpec {
  summary: string;
  objects: SpecObject[];
  steps: Step[];
  goal: GoalClause[];
  generalization: string;
  uncertainties: string[];
}

export interface CrossWatch {
  spec: TaskSpec;
  agree: boolean;
  differences: string[];
  arbitration?: string | null;
}

export interface TrackFrame {
  t: number;
  bbox_px: [number, number, number, number] | null;
  centroid_px?: Vec2 | null;
  poly_px?: Vec2[] | null;
  score?: number | null;
}

export interface Track {
  name: string;
  phrase: string;
  track_id?: string | null;
  quality: number;
  frames: TrackFrame[];
  flags: string[];
}

export interface TracksFile {
  fps: number;
  size: [number, number];
  tracks: Track[];
}

export interface Contact {
  t: number;
  type: "grasp" | "release";
  object: string;
}

export interface MotionSegment {
  object: string;
  t0: number;
  t1: number;
  from_cm: Vec2;
  to_cm: Vec2;
}

export interface StepMatch {
  step: number;
  segment: number | null;
  confidence: number;
  timing_delta_s?: number | null;
}

export interface GroundedDemo {
  initial: SceneObject[];
  final: SceneObject[];
  segments: MotionSegment[];
  contacts: Contact[];
  matches: StepMatch[];
  real_world: ClauseResult[];
  flags: string[];
}

export interface CalibrationOverlay {
  markers: { id: number; corners_px: Vec2[] }[];
  axes_px: { origin: Vec2; x10cm: Vec2; y10cm: Vec2 };
  work_area_px: Vec2[];
}

export interface TwinScene {
  layout: Layout;
  markers: MarkerPose[];
  camera: CameraPose;
  image_size: [number, number];
  table_texture: string;
  rectify?: { origin_cm: Vec2; px_per_cm: number };
  reach: { x0: number; y0: number; step_cm: number; cells: boolean[][] };
}

export interface Program {
  version: number;
  parent_version?: number | null;
  code: string;
  explanation: string;
  author: "wonder" | "wonder-harden" | "wonder-correction" | "spark-open-draft" | "human";
  diff_from_parent: string;
  synthesis_trace_id?: string | null;
  passed_demo: boolean;
}

export interface JudgeVerdict {
  same_goal_achieved: boolean;
  confidence: number;
  differences: string[];
  suspected_error: string;
}

export interface CheckResult {
  ok: boolean;
  clauses: ClauseResult[];
  detail: string;
}

export interface Verification {
  program_version: number;
  symbolic: CheckResult;
  real_world: CheckResult;
  perceptual: CheckResult;
  judge?: JudgeVerdict | null;
  agree: boolean;
  failure_class?: string | null;
  renders: Record<string, string>;
}

export interface AgentDecision {
  agent: "supervisor" | "coder" | "redteam";
  step: number;
  observation: string;
  reasoning_summary: string;
  tool: string;
  args: Record<string, unknown>;
  result: string;
  cost_usd: number;
}

export interface StressCase {
  layout: Layout;
  persona: string;
  rationale: string;
  before?: SimResult | null;
  after?: SimResult | null;
}

export interface StressReport {
  cases: StressCase[];
  robustness_before: number;
  robustness_after?: number | null;
  clusters: Record<string, unknown>[];
  program_before: number;
  program_after?: number | null;
}

export interface SkillCard {
  skill_id: string;
  title: string;
  description: string;
  image?: string | null;
  goal_text: string;
  program_version: number;
  robustness?: number | null;
  cost_to_learn_usd: number;
  run_id: string;
  run_title?: string;
  fixture?: boolean;
}

export interface CostsFile {
  by_model: Record<string, number>;
  by_provider: Record<string, number>;
  total_usd: number;
  open_weight_share: number;
  fixture?: boolean;
}

// ---------- the digital twin (backend/demobot/sim/twin_export.py) ----------
export interface TwinObject {
  name: string;
  kind: string;
  role: string;
  shape: Shape;
  size: Vec3; // cm: w, d, h
  container: boolean;
  texture?: string | null;
  color: string;
}

export interface TwinFrame {
  t: number;
  q: number[]; // 7 arm joints + 2 fingers
  poses: Record<string, number[]>; // name -> [x, y, z, qx, qy, qz, qw] (PyBullet metres)
}

export interface TwinEvent {
  t: number;
  type: string;
  object?: string | null;
}

export interface TwinTrajectory {
  fps: number;
  robot: { urdf: string; base: [number, number, number, number] };
  table: { work_area_cm: [number, number, number, number]; top_z: number; margin_m: number };
  objects: TwinObject[];
  frames: TwinFrame[];
  events: TwinEvent[];
  duration_s: number;
}

export interface TryLayoutResponse {
  ok: boolean;
  problems?: string[];
  program_version?: number;
  layout?: Layout;
  result?: SimResult & { twin?: TwinTrajectory };
}

export interface Health {
  ok: boolean;
  mode: string;
  version: string;
  headroom_usd: Record<string, unknown>;
}
