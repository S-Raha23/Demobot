// The 3D digital twin (three.js + urdf-loader). Everything lives inside `pb`, a group rotated
// -90° about X, so PyBullet coordinates (metres, Z up) are used directly (src/lib/frames.ts).

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { MTLLoader } from "three/examples/jsm/loaders/MTLLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import URDFLoader, { type URDFRobot } from "urdf-loader";
import { intrinsicProjection, phoneCamera, type V3 } from "../lib/frames";
import type { Rect, SceneObject, TwinObject, TwinTrajectory, Vec2 } from "../lib/types";
import { PANDA_HOME, PANDA_JOINTS, sampleTrajectory } from "./sample";

export type CameraMode = "orbit" | "real" | "top";

export interface PhoneCam {
  rvec: V3;
  tvec: V3;
  focal: number;
  principal: Vec2;
  imageSize: [number, number];
}

interface ObjSpec {
  name: string;
  shape: string;
  w: number;
  d: number;
  h: number;
  color: string;
  open: boolean;
}

interface ObjEntry {
  spec: ObjSpec;
  group: THREE.Group;
  label: CSS2DObject;
  body: THREE.Mesh[];
}

const PANDA_YAW = Math.PI / 2;

function specKey(s: ObjSpec) {
  return `${s.shape}|${s.w}|${s.d}|${s.h}|${s.color}|${s.open}`;
}

export interface TwinSceneOptions {
  editable?: boolean;
  labels?: boolean;
  onMove?: (name: string, x: number, y: number, yaw: number) => void;
  onSelect?: (name: string | null) => void;
}

export class TwinScene {
  readonly renderer: THREE.WebGLRenderer;
  readonly labelRenderer: CSS2DRenderer;
  readonly scene = new THREE.Scene();
  readonly pb = new THREE.Group();
  readonly camera: THREE.PerspectiveCamera;
  readonly controls: OrbitControls;
  private objects = new Map<string, ObjEntry>();
  private robot: URDFRobot | null = null;
  private robotBase: [number, number, number, number] | null = null;
  private table = new THREE.Group();
  private reachMesh: THREE.Mesh | null = null;
  private workArea: Rect | null = null;
  private traj: TwinTrajectory | null = null;
  private layout: SceneObject[] = [];
  private raf = 0;
  private ro: ResizeObserver;
  private mode: CameraMode = "orbit";
  private phone: PhoneCam | null = null;
  private orbitTarget = new THREE.Vector3(0.3, 0.0, 0.2);
  private selected: string | null = null;
  private dragging: { name: string; dx: number; dy: number } | null = null;
  private raycaster = new THREE.Raycaster();
  private disposed = false;
  private labelsOn: boolean;
  private texLoader = new THREE.TextureLoader();
  timeSource: (() => number | null) | null = null;
  onRobotLoaded: (() => void) | null = null;

  constructor(
    private host: HTMLElement,
    private opts: TwinSceneOptions = {},
  ) {
    this.labelsOn = opts.labels ?? true;
    const r = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance", preserveDrawingBuffer: true });
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.05;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.domElement.style.display = "block";
    r.domElement.style.width = "100%";
    r.domElement.style.height = "100%";
    r.domElement.style.touchAction = "none";
    host.appendChild(r.domElement);
    this.renderer = r;

    const lr = new CSS2DRenderer();
    lr.domElement.style.position = "absolute";
    lr.domElement.style.inset = "0";
    lr.domElement.style.pointerEvents = "none";
    host.appendChild(lr.domElement);
    this.labelRenderer = lr;

    const pmrem = new THREE.PMREMGenerator(r);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.background = new THREE.Color("#0a0f16");
    this.scene.fog = new THREE.Fog("#0a0f16", 3.2, 7);

    this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 30);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.minDistance = 0.3;
    this.controls.maxDistance = 4;

    this.pb.rotation.x = -Math.PI / 2;
    this.scene.add(this.pb);
    this.pb.add(this.table);

    // lights
    const hemi = new THREE.HemisphereLight("#cfe3ff", "#1a2230", 0.55);
    this.scene.add(hemi);
    const key = new THREE.DirectionalLight("#ffffff", 1.6);
    key.position.set(-0.4, 1.6, -0.2);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -0.8;
    key.shadow.camera.right = 0.8;
    key.shadow.camera.top = 0.8;
    key.shadow.camera.bottom = -0.8;
    key.shadow.camera.near = 0.2;
    key.shadow.camera.far = 4;
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.01;
    key.target.position.set(0.3, 0, 0.3);
    this.scene.add(key, key.target);
    const rim = new THREE.DirectionalLight("#7dd3fc", 0.35);
    rim.position.set(1.2, 0.8, -1.2);
    this.scene.add(rim);

    // floor grid far below the table, for depth
    const grid = new THREE.GridHelper(8, 80, "#1b2737", "#121a25");
    grid.position.y = -0.76;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.6;
    this.scene.add(grid);

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    this.resize();
    this.setCameraMode("orbit");
    if (opts.editable) this.bindEditing();
    this.loop();
  }

  // ---------- scene content ----------

  /** The table: a slab plus the rectified top-down photo of the human's table. */
  setTable(work: Rect, robotBaseCm: Vec2 | null, texture?: { url: string; originCm: Vec2; pxPerCm: number } | null) {
    this.workArea = work;
    this.table.clear();
    const x0 = Math.min(work.x0, -10) - 12;
    const x1 = Math.max(work.x1, 70) + 12;
    const y0 = Math.min(work.y0, -10) - 12;
    const y1 = Math.max(work.y1 + 15, (robotBaseCm?.[1] ?? work.y1) + 18);
    const thick = 0.04;
    const slab = new THREE.Mesh(
      new THREE.BoxGeometry((x1 - x0) / 100, (y1 - y0) / 100, thick),
      new THREE.MeshStandardMaterial({ color: "#1d2733", roughness: 0.85, metalness: 0.05 }),
    );
    slab.position.set((x0 + x1) / 200, -(y0 + y1) / 200, -thick / 2 - 0.0004);
    slab.receiveShadow = true;
    this.table.add(slab);
    // legs-like skirt for depth
    const skirt = new THREE.Mesh(
      new THREE.BoxGeometry((x1 - x0) / 100 - 0.06, (y1 - y0) / 100 - 0.06, 0.72),
      new THREE.MeshStandardMaterial({ color: "#121a24", roughness: 1 }),
    );
    skirt.position.set((x0 + x1) / 200, -(y0 + y1) / 200, -thick - 0.36);
    this.table.add(skirt);

    // work-area outline
    const wa = [
      [work.x0, work.y0],
      [work.x1, work.y0],
      [work.x1, work.y1],
      [work.x0, work.y1],
      [work.x0, work.y0],
    ].map(([x, y]) => new THREE.Vector3(x / 100, -y / 100, 0.0012));
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(wa),
      new THREE.LineDashedMaterial({ color: "#5eead4", dashSize: 0.012, gapSize: 0.008, transparent: true, opacity: 0.55 }),
    );
    line.computeLineDistances();
    this.table.add(line);

    if (texture) {
      this.texLoader.load(texture.url, (tex) => {
        if (this.disposed) return;
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
        const img = tex.image as { width: number; height: number };
        const wcm = img.width / texture.pxPerCm;
        const hcm = img.height / texture.pxPerCm;
        const [ox, oy] = texture.originCm;
        // the photo as-is (unlit, not tone-mapped) so it matches the real video, plus a
        // shadow-catcher on top so objects and the robot still cast soft shadows on it
        const geo = new THREE.PlaneGeometry(wcm / 100, hcm / 100);
        const plane = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, color: "#e9e9e9" }));
        plane.position.set((ox + wcm / 2) / 100, -(oy + hcm / 2) / 100, 0.0002);
        this.table.add(plane);
        const catcher = new THREE.Mesh(geo, new THREE.ShadowMaterial({ opacity: 0.32 }));
        catcher.position.copy(plane.position);
        catcher.position.z += 0.0003;
        catcher.receiveShadow = true;
        this.table.add(catcher);
      });
    }
  }

  setReach(reach: { x0: number; y0: number; step_cm: number; cells: boolean[][] } | null, visible: boolean) {
    if (this.reachMesh) {
      this.pb.remove(this.reachMesh);
      this.reachMesh.geometry.dispose();
      (this.reachMesh.material as THREE.MeshBasicMaterial).map?.dispose();
      this.reachMesh = null;
    }
    if (!reach || !visible || !reach.cells.length) return;
    const rows = reach.cells.length;
    const cols = reach.cells[0].length;
    const s = 8;
    const cv = document.createElement("canvas");
    cv.width = cols * s;
    cv.height = rows * s;
    const g = cv.getContext("2d")!;
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) {
        g.fillStyle = reach.cells[r][c] ? "rgba(45,212,191,0.30)" : "rgba(248,113,113,0.55)";
        g.fillRect(c * s, r * s, s, s);
        g.strokeStyle = "rgba(10,15,22,0.35)";
        g.strokeRect(c * s + 0.5, r * s + 0.5, s - 1, s - 1);
      }
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.magFilter = THREE.NearestFilter;
    const w = cols * reach.step_cm;
    const h = rows * reach.step_cm;
    const m = new THREE.Mesh(
      new THREE.PlaneGeometry(w / 100, h / 100),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }),
    );
    m.position.set((reach.x0 - reach.step_cm / 2 + w / 2) / 100, -(reach.y0 - reach.step_cm / 2 + h / 2) / 100, 0.0015);
    m.renderOrder = 2;
    this.reachMesh = m;
    this.pb.add(m);
  }

  private material(color: string) {
    return new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05, envMapIntensity: 0.6 });
  }

  private buildObject(spec: ObjSpec): ObjEntry {
    const g = new THREE.Group();
    const w = spec.w / 100;
    const d = spec.d / 100;
    const h = spec.h / 100;
    const mat = this.material(spec.color);
    const body: THREE.Mesh[] = [];
    const add = (geo: THREE.BufferGeometry, m: THREE.Material = mat) => {
      const mesh = new THREE.Mesh(geo, m);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      mesh.userData.objName = spec.name;
      g.add(mesh);
      body.push(mesh);
      return mesh;
    };
    if (spec.open) {
      const wall = Math.min(0.004, w / 10);
      const inner = this.material(new THREE.Color(spec.color).multiplyScalar(0.72).getStyle());
      if (spec.shape === "cylinder" || spec.shape === "sphere") {
        const r = Math.max(w, d) / 2;
        const side = new THREE.CylinderGeometry(r, r * 0.96, h, 40, 1, true);
        side.rotateX(Math.PI / 2);
        const sm = this.material(spec.color);
        sm.side = THREE.DoubleSide;
        add(side, sm);
        const floor = new THREE.CircleGeometry(r * 0.96, 40);
        floor.translate(0, 0, -h / 2 + 0.002);
        add(floor, inner);
        const rimGeo = new THREE.TorusGeometry(r, wall / 2, 8, 48);
        rimGeo.translate(0, 0, h / 2);
        add(rimGeo);
      } else {
        const floor = new THREE.BoxGeometry(w, d, wall);
        floor.translate(0, 0, -h / 2 + wall / 2);
        add(floor, inner);
        for (const [sx, sy, gw, gd] of [
          [0, -d / 2 + wall / 2, w, wall],
          [0, d / 2 - wall / 2, w, wall],
          [-w / 2 + wall / 2, 0, wall, d],
          [w / 2 - wall / 2, 0, wall, d],
        ]) {
          const geo = new THREE.BoxGeometry(gw, gd, h);
          geo.translate(sx, sy, 0);
          add(geo);
        }
      }
    } else if (spec.shape === "cylinder") {
      const r = Math.max(w, d) / 2;
      const geo = new THREE.CylinderGeometry(r, r, h, 36);
      geo.rotateX(Math.PI / 2);
      add(geo);
    } else if (spec.shape === "sphere") {
      add(new THREE.SphereGeometry(Math.max(w, d, h) / 2, 32, 20));
    } else {
      const r = Math.min(w, d, h) * 0.18;
      add(roundedBox(w, d, h, r));
    }
    const el = document.createElement("div");
    el.className = "twin-label";
    el.textContent = spec.name;
    Object.assign(el.style, {
      font: "600 10.5px Inter Variable, Inter, sans-serif",
      color: "#e6edf5",
      background: "rgba(10,15,22,0.72)",
      border: "1px solid rgba(91,107,128,0.5)",
      padding: "1px 6px",
      borderRadius: "999px",
      whiteSpace: "nowrap",
      transform: "translateY(-10px)",
      pointerEvents: "none",
    } as CSSStyleDeclaration);
    const label = new CSS2DObject(el);
    label.position.set(0, 0, h / 2 + 0.025);
    label.visible = this.labelsOn;
    g.add(label);
    g.userData.objName = spec.name;
    this.pb.add(g);
    return { spec, group: g, label, body };
  }

  private ensureObjects(specs: ObjSpec[]) {
    const want = new Set(specs.map((s) => s.name));
    for (const [name, e] of this.objects) {
      if (!want.has(name) || specKey(e.spec) !== specKey(specs.find((s) => s.name === name)!)) {
        this.pb.remove(e.group);
        e.label.element.remove();
        e.group.traverse((o) => {
          if (o instanceof THREE.Mesh) o.geometry.dispose();
        });
        this.objects.delete(name);
      }
    }
    for (const s of specs) if (!this.objects.has(s.name)) this.objects.set(s.name, this.buildObject(s));
  }

  /** Static stand-ins at layout positions (table cm). */
  setLayout(objects: SceneObject[]) {
    this.layout = objects;
    this.ensureObjects(
      objects.map((o) => ({ name: o.name, shape: o.shape, w: o.w, d: o.d, h: o.h, color: o.color, open: o.role === "container" || Boolean(o.hollow) })),
    );
    if (!this.traj) this.applyLayout();
  }

  private applyLayout() {
    for (const o of this.layout) {
      const e = this.objects.get(o.name);
      if (!e) continue;
      e.group.position.set(o.x / 100, -o.y / 100, (o.shape === "sphere" ? Math.max(o.w, o.d, o.h) : o.h) / 200);
      e.group.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), (-o.yaw * Math.PI) / 180);
    }
    this.setJoints(PANDA_HOME);
  }

  setTrajectory(traj: TwinTrajectory | null) {
    this.traj = traj;
    if (traj) {
      this.ensureObjects(
        traj.objects.map((o: TwinObject) => ({
          name: o.name,
          shape: o.shape,
          w: o.size[0],
          d: o.size[1],
          h: o.size[2],
          color: o.color,
          open: o.container,
        })),
      );
      this.setRobotBase(traj.robot.base);
      this.applyTime(0);
    } else {
      this.applyLayout();
    }
  }

  setRobotBase(base: [number, number, number, number]) {
    this.robotBase = base;
    if (this.robot) {
      this.robot.position.set(base[0], base[1], base[2]);
      this.robot.rotation.set(0, 0, base[3]);
    }
  }

  setRobotBaseCm(cm: Vec2) {
    this.setRobotBase([cm[0] / 100, -cm[1] / 100, 0, PANDA_YAW]);
  }

  loadRobot(url = "/assets/franka_panda/panda.urdf") {
    const manager = new THREE.LoadingManager();
    const loader = new URDFLoader(manager);
    loader.packages = url.replace(/\/[^/]+$/, "");
    // DoubleSide: some Panda visual meshes have mixed triangle winding
    const white = new THREE.MeshStandardMaterial({ color: "#eef1f5", roughness: 0.35, metalness: 0.1, side: THREE.DoubleSide });
    const dark = new THREE.MeshStandardMaterial({ color: "#20262e", roughness: 0.45, metalness: 0.25, side: THREE.DoubleSide });
    this.robotMaterials = [white, dark];
    this.applyGhost();
    loader.loadMeshCb = (path, mgr, done) => {
      const mtlPath = path.replace(/\.obj$/i, ".mtl");
      const loadObj = (materials?: MTLLoader.MaterialCreator) => {
        const ol = new OBJLoader(mgr);
        if (materials) ol.setMaterials(materials);
        // Some Panda OBJs carry edge records ("l ..."); OBJLoader would then turn the whole
        // object into line segments, so strip them before parsing.
        new THREE.FileLoader(mgr).load(
          path,
          (text) => {
            const obj = ol.parse(String(text).replace(/^l .*$/gm, ""));
            obj.traverse((c) => {
              if (c instanceof THREE.Mesh) {
                c.castShadow = true;
                c.receiveShadow = false; // avoids self-shadow acne on the glossy links
                // Use the MTL diffuse colours (white shells, dark joints); the shared texture atlas
                // (colors.png) maps badly onto some faces and shows stripes.
                const conv = (m: THREE.Material) => {
                  const src = m as THREE.MeshPhongMaterial;
                  const col = src.color ? src.color : new THREE.Color("#eef1f5");
                  return col.r + col.g + col.b < 1.5 ? dark : white;
                };
                c.material = Array.isArray(c.material) ? c.material.map(conv) : conv(c.material);
              }
            });
            done(obj);
          },
          undefined,
          (err) => done(null as unknown as THREE.Object3D, err as Error),
        );
      };
      if (path.includes("/visual/")) {
        new MTLLoader(mgr).setResourcePath(path.replace(/[^/]+$/, "")).load(
          mtlPath,
          (m) => {
            m.preload();
            loadObj(m);
          },
          undefined,
          () => loadObj(),
        );
      } else loadObj();
    };
    loader.load(
      url,
      (robot) => {
        if (this.disposed) return;
        this.robot = robot;

        this.pb.add(robot);
        robot.visible = this.mode !== "real";
        if (this.robotBase) this.setRobotBase(this.robotBase);
        this.setJoints(PANDA_HOME);
        if (this.traj) this.applyTime(this.timeSource?.() ?? 0);
        this.onRobotLoaded?.();
      },
      undefined,
      () => undefined,
    );
  }

  private setJoints(q: number[]) {
    if (!this.robot) return;
    PANDA_JOINTS.forEach((j, i) => {
      if (q[i] !== undefined) this.robot!.setJointValue(j, q[i]);
    });
  }

  private applyTime(t: number) {
    if (!this.traj) return;
    const s = sampleTrajectory(this.traj, t);
    if (!s) return;
    this.setJoints(s.q);
    for (const [name, p] of Object.entries(s.poses)) {
      const e = this.objects.get(name);
      if (!e) continue;
      e.group.position.set(p[0], p[1], p[2]);
      e.group.quaternion.set(p[3], p[4], p[5], p[6]);
    }
  }

  private ghost = false;
  private robotMaterials: THREE.Material[] = [];

  /** Fade the robot (Try it's edit mode: objects under the arm stay visible). */
  setRobotGhost(on: boolean) {
    this.ghost = on;
    this.applyGhost();
  }

  private applyGhost() {
    for (const m of this.robotMaterials) {
      m.transparent = this.ghost;
      m.opacity = this.ghost ? 0.22 : 1;
      m.depthWrite = !this.ghost;
      m.needsUpdate = true;
    }
  }

  setLabels(on: boolean) {
    this.labelsOn = on;
    for (const e of this.objects.values()) e.label.visible = on;
  }

  // ---------- cameras ----------

  setPhoneCamera(p: PhoneCam | null) {
    this.phone = p;
    if (this.mode === "real") this.setCameraMode("real");
  }

  get cameraMode(): CameraMode {
    return this.mode;
  }

  setCameraMode(mode: CameraMode) {
    this.mode = mode === "real" && !this.phone ? "orbit" : mode;
    const wa = this.workArea ?? { x0: 0, y0: 0, x1: 60, y1: 40 };
    const cx = (wa.x0 + wa.x1) / 200;
    const cz = (wa.y0 + wa.y1) / 200;
    this.orbitTarget.set(cx, 0.02, cz);
    if (this.robot) this.robot.visible = this.mode !== "real";
    if (this.mode === "real") {
      // The robot stands where the phone was, so it is hidden in the phone's view (as in the
      // verification render); held objects still move.
      this.controls.enabled = false;
    } else if (this.mode === "top") {
      this.controls.enabled = true;
      this.controls.enableRotate = false;
      this.camera.position.set(cx, 1.15, cz + 0.18);
      this.controls.target.copy(this.orbitTarget);
      this.camera.up.set(0, 1, 0);
      this.camera.fov = 38;
    } else {
      this.controls.enabled = true;
      this.controls.enableRotate = true;
      // a three-quarter view from the far right corner, looking across the table at the robot
      this.camera.position.set(cx + 1.05, 0.9, cz - 0.95);
      this.orbitTarget.set(cx, 0.26, cz + 0.18);
      this.controls.target.copy(this.orbitTarget);
      this.camera.up.set(0, 1, 0);
      this.camera.fov = 40;
    }
    this.resize();
  }

  private applyPhoneProjection(w: number, h: number) {
    const p = this.phone!;
    const f = phoneCamera(p.rvec, p.tvec);
    this.camera.position.set(...f.position);
    const m = new THREE.Matrix4().makeBasis(new THREE.Vector3(...f.right), new THREE.Vector3(...f.up), new THREE.Vector3(...f.back));
    this.camera.quaternion.setFromRotationMatrix(m);
    this.camera.updateMatrixWorld(true);
    const P = intrinsicProjection(p.focal, p.principal[0], p.principal[1], p.imageSize[0], p.imageSize[1], w, h, 0.01, 30);
    this.camera.projectionMatrix.fromArray(P);
    this.camera.projectionMatrixInverse.copy(this.camera.projectionMatrix).invert();
  }

  resize() {
    const w = Math.max(1, this.host.clientWidth);
    const h = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(w, h, false);
    this.labelRenderer.setSize(w, h);
    this.camera.aspect = w / h;
    if (this.mode === "real" && this.phone) this.applyPhoneProjection(w, h);
    else this.camera.updateProjectionMatrix();
  }

  // ---------- editing (Try it) ----------

  private tableHit(ev: PointerEvent): THREE.Vector3 | null {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const hit = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(plane, hit) ? hit : null;
  }

  private pickObject(ev: PointerEvent): string | null {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const meshes = [...this.objects.values()].flatMap((e) => e.body);
    const hit = this.raycaster.intersectObjects(meshes, false)[0];
    return (hit?.object.userData.objName as string) ?? null;
  }

  select(name: string | null) {
    this.selected = name;
    for (const [n, e] of this.objects) {
      const on = n === name;
      for (const m of e.body) {
        const mat = m.material as THREE.MeshStandardMaterial;
        mat.emissive = new THREE.Color(on ? "#2dd4bf" : "#000000");
        mat.emissiveIntensity = on ? 0.35 : 0;
      }
      e.label.element.style.borderColor = on ? "#2dd4bf" : "rgba(91,107,128,0.5)";
      e.label.element.style.color = on ? "#5eead4" : "#e6edf5";
    }
    this.opts.onSelect?.(name);
  }

  private bindEditing() {
    const el = this.renderer.domElement;
    el.addEventListener("pointerdown", (ev) => {
      if (this.traj) return; // editing only in layout mode
      const name = this.pickObject(ev);
      this.select(name);
      if (!name) return;
      const o = this.layout.find((x) => x.name === name);
      const hit = this.tableHit(ev);
      if (!o || !hit) return;
      this.dragging = { name, dx: o.x - hit.x * 100, dy: o.y - hit.z * 100 };
      this.controls.enabled = false;
      el.setPointerCapture(ev.pointerId);
      el.style.cursor = "grabbing";
    });
    el.addEventListener("pointermove", (ev) => {
      if (!this.dragging) {
        if (!this.traj) el.style.cursor = this.pickObject(ev) ? "grab" : "default";
        return;
      }
      const hit = this.tableHit(ev);
      const o = this.layout.find((x) => x.name === this.dragging!.name);
      if (!hit || !o) return;
      let x = hit.x * 100 + this.dragging.dx;
      let y = hit.z * 100 + this.dragging.dy;
      const wa = this.workArea;
      if (wa) {
        const [ex, ey] = footprint(o);
        x = Math.min(wa.x1 - ex, Math.max(wa.x0 + ex, x));
        y = Math.min(wa.y1 - ey, Math.max(wa.y0 + ey, y));
      }
      o.x = Math.round(x * 10) / 10;
      o.y = Math.round(y * 10) / 10;
      this.applyLayout();
      this.opts.onMove?.(o.name, o.x, o.y, o.yaw);
    });
    const end = (ev: PointerEvent) => {
      if (!this.dragging) return;
      this.dragging = null;
      this.controls.enabled = this.mode !== "real";
      el.releasePointerCapture(ev.pointerId);
      el.style.cursor = "grab";
    };
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
  }

  rotateSelected(deg: number) {
    if (!this.selected || this.traj) return;
    const o = this.layout.find((x) => x.name === this.selected);
    if (!o) return;
    o.yaw = (((o.yaw + deg) % 360) + 360) % 360;
    this.applyLayout();
    this.opts.onMove?.(o.name, o.x, o.y, o.yaw);
  }

  get selectedName() {
    return this.selected;
  }

  // ---------- loop ----------

  private loop = () => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.loop);
    if (this.traj && this.timeSource) {
      const t = this.timeSource();
      if (t != null) this.applyTime(t);
    }
    if (this.mode !== "real") this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
  };

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    this.controls.dispose();
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.geometry.dispose();
        const ms = Array.isArray(o.material) ? o.material : [o.material];
        ms.forEach((m) => m.dispose());
      }
    });
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labelRenderer.domElement.remove();
  }
}

/** Half-extents of the axis-aligned footprint (cm), as SceneObject.extents() in schemas.py. */
function footprint(o: SceneObject): [number, number] {
  if (o.shape !== "box") {
    const r = Math.max(o.w, o.d) / 2;
    return [r, r];
  }
  const c = Math.abs(Math.cos((o.yaw * Math.PI) / 180));
  const s = Math.abs(Math.sin((o.yaw * Math.PI) / 180));
  return [(o.w * c + o.d * s) / 2, (o.w * s + o.d * c) / 2];
}

function roundedBox(w: number, d: number, h: number, r: number): THREE.BufferGeometry {
  // a box with softened edges (cheap: a box whose normals are nudged by a slight bevel)
  if (r < 0.0015) return new THREE.BoxGeometry(w, d, h);
  const shape = new THREE.Shape();
  const x = -w / 2;
  const y = -d / 2;
  const rr = Math.min(r, w / 2, d / 2);
  shape.moveTo(x + rr, y);
  shape.lineTo(x + w - rr, y);
  shape.quadraticCurveTo(x + w, y, x + w, y + rr);
  shape.lineTo(x + w, y + d - rr);
  shape.quadraticCurveTo(x + w, y + d, x + w - rr, y + d);
  shape.lineTo(x + rr, y + d);
  shape.quadraticCurveTo(x, y + d, x, y + d - rr);
  shape.lineTo(x, y + rr);
  shape.quadraticCurveTo(x, y, x + rr, y);
  const bevel = Math.min(rr * 0.6, h / 4);
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth: Math.max(0.0005, h - 2 * bevel),
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel * 0.6,
    bevelSegments: 2,
    curveSegments: 4,
  });
  geo.translate(0, 0, -h / 2 + bevel);
  return geo;
}
