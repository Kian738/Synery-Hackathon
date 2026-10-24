import { test, expect, type Browser, type Page } from "@playwright/test";
import react from "@vitejs/plugin-react";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { build } from "vite";
import { CompanionClient, type SocketLike } from "../src/companion/client";
import { MAX_DELTA_DEG, parseFrame, routeStateFromGuide, splitDelta, wrapDeg } from "../src/companion/protocol";
import { GyroLook, detectSensors, lookDelta, lookFromOrientation, pulse, type OrientationSample, type SensorEnv } from "../src/companion/sensors";

// Protocol, sensor and client tests need no browser. The last block drives two real browser contexts (laptop and phone)
// against the stand-alone demo server (server/companion.py) built from web/src/companion/demo.
test.beforeEach(({}, info) => { info.skip(info.project.name !== "desktop", "environment-independent: run once"); });

const frame = (t: string, extra: object = {}) => JSON.stringify({ v: 1, t, ...extra });
const STEP = { text: "Walk 20 metres along the corridor.", short: "Corridor", icon: "straight" as const };

// ---------------------------------------------------------------- protocol

test.describe("protocol", () => {
  test("accepts well-formed frames and rejects everything else", () => {
    expect(parseFrame(frame("hello_ok", { role: "phone", session: "s", last_seq: 3, peer_online: false, approved: true }))).toMatchObject({ t: "hello_ok", last_seq: 3 });
    expect(parseFrame(frame("heading", { seq: 1, dyaw: 4, dpitch: 0, mode: "touch" }))).toMatchObject({ dyaw: 4 });
    expect(parseFrame(frame("route_state", { seq: 2, status: "guiding", step_index: 0, step_count: 2, instruction: STEP }))).toBeTruthy();
    for (const bad of [
      "not json", "[]", "null", 5, undefined, JSON.stringify({ t: "pong" }), JSON.stringify({ v: 2, t: "pong" }), frame("nope"),
      frame("heading", { seq: 1, dyaw: "4", dpitch: 0, mode: "touch" }), frame("heading", { seq: 1, dyaw: 4, dpitch: 0, mode: "psychic" }),
      frame("heading", { dyaw: 4, dpitch: 0, mode: "touch" }), frame("step", { seq: 1, action: "teleport" }),
      frame("route_state", { seq: 1, status: "guiding", step_index: 5, step_count: 2, instruction: STEP }),
      frame("route_state", { seq: 1, status: "guiding", step_index: 0, step_count: 2, instruction: { ...STEP, icon: "rocket" } }),
      "x".repeat(20_000),
    ]) expect(parseFrame(bad as never), String(bad).slice(0, 60)).toBeNull();
  });

  test("turns are split to what the server accepts, angles wrap, and route state is built from guide steps", () => {
    expect(splitDelta(0, 0)).toEqual([[0, 0]]);
    const parts = splitDelta(200, -50);
    expect(parts.length).toBe(3);
    expect(parts.every(([y, p]) => Math.abs(y) <= MAX_DELTA_DEG && Math.abs(p) <= MAX_DELTA_DEG)).toBe(true);
    expect(parts.reduce((s, [y]) => s + y, 0)).toBeCloseTo(200);
    expect(splitDelta(Number.NaN, 1)).toEqual([]);
    expect(wrapDeg(190)).toBe(-170);
    expect(wrapDeg(-190)).toBe(170);
    const steps = [{ kind: "start", icon: "start", text: "Start here", short: "Start", metres: 0 }, { kind: "arrive", icon: "arrive", text: "You have arrived", short: "Arrived", metres: 3.04 }] as never[];
    expect(routeStateFromGuide([], 0)).toEqual({ status: "idle", route_id: null });
    expect(routeStateFromGuide(steps, 0, { routeId: "r" })).toMatchObject({ status: "guiding", step_index: 0, step_count: 2, next: { icon: "arrive", metres: 3 } });
    expect(routeStateFromGuide(steps, 99)).toMatchObject({ status: "arrived", step_index: 1 });
  });
});

// ---------------------------------------------------------------- sensors

const sample = (alpha: number, beta: number, gamma: number): OrientationSample => ({ alpha, beta, gamma });

test.describe("sensor maths", () => {
  test("upright phone looks along the back camera; turning left or right changes yaw the right way", () => {
    const north = lookFromOrientation(sample(0, 90, 0), 0)!;
    expect(north.basis).toBe("camera");
    expect(north.yaw).toBeCloseTo(0, 5);
    expect(north.pitch).toBeCloseTo(0, 5);
    expect(lookFromOrientation(sample(30, 90, 0), 0)!.yaw).toBeCloseTo(-30, 4);   // device turns anticlockwise: look turns left
    expect(lookFromOrientation(sample(350, 90, 0), 0)!.yaw).toBeCloseTo(10, 4);
    expect(lookFromOrientation(sample(0, 60, 0), 0)!.pitch).toBeCloseTo(-30, 4);   // tilting the top toward you looks down
    const a = lookFromOrientation(sample(359, 90, 0), 0)!, b = lookFromOrientation(sample(1, 90, 0), 0)!;
    expect(lookDelta(a, b)!.dyaw).toBeCloseTo(-2, 4);                                 // across north, no 358-degree jump
  });

  test("rolling the phone between portrait and landscape does not read as turning", () => {
    const portrait = lookFromOrientation(sample(0, 90, 0), 0)!;
    const landscape = lookFromOrientation(sample(90, 0, -90), 90)!;                  // same look direction, phone rolled a quarter turn
    expect(landscape.basis).toBe("camera");
    expect(Math.abs(lookDelta(portrait, landscape)!.dyaw)).toBeLessThan(1e-6);
    expect(Math.abs(lookDelta(portrait, landscape)!.dpitch)).toBeLessThan(1e-6);
  });

  test("held flat, the top of the screen is the look direction and screen rotation is accounted for", () => {
    const flat = lookFromOrientation(sample(40, 0, 0), 0)!;
    expect(flat.basis).toBe("screen-top");
    expect(flat.yaw).toBeCloseTo(-40, 4);
    const landscapeFlat = lookFromOrientation(sample(40, 0, 0), 90)!;               // same device pose, screen rotated: the UI's top is elsewhere
    expect(wrapDeg(landscapeFlat.yaw - flat.yaw)).toBeCloseTo(90, 4);
    // The OS rotates the UI by 90 degrees while the device is turned 90 degrees: the UI's top direction is unchanged.
    const before = lookFromOrientation(sample(0, 0, 0), 0)!;
    const after = lookFromOrientation(sample(90, 0, 0), 90)!;
    expect(Math.abs(wrapDeg(after.yaw - before.yaw))).toBeLessThan(1e-4);
  });

  test("samples that cannot be compared or trusted yield nothing", () => {
    expect(lookFromOrientation({ alpha: null, beta: null, gamma: null }, 0)).toBeNull();
    expect(lookFromOrientation({ alpha: Number.NaN, beta: 1, gamma: 1 }, 0)).toBeNull();
    expect(lookDelta(lookFromOrientation(sample(0, 90, 0), 0)!, lookFromOrientation(sample(0, 0, 0), 0)!)).toBeNull();   // camera -> screen-top
  });
});

// ---------------------------------------------------------------- gyro controller (permissions, secure context, rotation)

interface Rig { env: SensorEnv; emit(s: OrientationSample): void; rotate(angle: number): void; advance(ms: number): void; calls: { permission: number; add: number; remove: number }; angle: number }
function rig(over: Partial<SensorEnv> & { permission?: "granted" | "denied" | "throws" | "absent" } = {}): Rig {
  const calls = { permission: 0, add: 0, remove: 0 };
  let listener: ((s: OrientationSample) => void) | null = null;
  let rotateFn: (() => void) | null = null;
  const timers: { at: number; fn: () => void }[] = [];
  let now = 0;
  const r: Rig = {
    calls, angle: 0,
    emit: s => listener?.(s),
    rotate: angle => { r.angle = angle; rotateFn?.(); },
    advance: ms => { now += ms; timers.filter(t => t.at <= now).forEach(t => { timers.splice(timers.indexOf(t), 1); t.fn(); }); },
    env: {
      isSecureContext: true, hasOrientationEvent: true,
      requestPermission: over.permission === "absent" ? undefined : async () => { calls.permission++; if (over.permission === "throws") throw new Error("NotAllowedError"); return over.permission ?? "granted"; },
      addOrientationListener: fn => { calls.add++; listener = fn; },
      removeOrientationListener: () => { calls.remove++; listener = null; },
      screenAngle: () => r.angle,
      onScreenRotate: fn => { rotateFn = fn; return () => { rotateFn = null; }; },
      setTimeout: (fn, ms) => { const t = { at: now + ms, fn }; timers.push(t); return t; },
      clearTimeout: id => { const i = timers.indexOf(id as never); if (i >= 0) timers.splice(i, 1); },
      ...over,
    },
  };
  return r;
}
const gyro = (r: Rig) => { const deltas: [number, number][] = [], statuses: string[] = []; return { g: new GyroLook(r.env, { onDelta: (y, p) => deltas.push([y, p]), onStatus: s => statuses.push(s) }), deltas, statuses }; };

test.describe("motion look", () => {
  test("detection alone never prompts or listens", () => {
    const r = rig();
    const { g } = gyro(r);
    expect(g.status).toBe("needs-permission");
    expect(r.calls).toEqual({ permission: 0, add: 0, remove: 0 });
    expect(detectSensors({ ...r.env, hasOrientationEvent: false })).toBe("unsupported");
    expect(detectSensors({ ...r.env, isSecureContext: false })).toBe("insecure");
    expect(detectSensors({ ...r.env, requestPermission: undefined })).toBe("ready");
  });

  test("an insecure page or a missing API is explained, never attempted", async () => {
    for (const [over, expected] of [[{ isSecureContext: false }, "insecure"], [{ hasOrientationEvent: false }, "unsupported"]] as const) {
      const r = rig(over);
      const { g, statuses } = gyro(r);
      expect(await g.start()).toBe(expected);
      expect(statuses).toEqual([expected]);
      expect(r.calls).toEqual({ permission: 0, add: 0, remove: 0 });
    }
  });

  test("permission denied, or the prompt failing, leaves touch as the only control", async () => {
    for (const permission of ["denied", "throws"] as const) {
      const r = rig({ permission });
      const { g, statuses } = gyro(r);
      expect(await g.start()).toBe("denied");
      expect(statuses).toEqual(["denied"]);
      expect(r.calls).toEqual({ permission: 1, add: 0, remove: 0 });
    }
  });

  test("granted: deltas flow, noise is ignored, and a screen rotation never reads as a turn", async () => {
    const r = rig();
    const { g, deltas, statuses } = gyro(r);
    expect(await g.start()).toBe("starting");
    r.emit(sample(null as never, null as never, null as never));   // desktop-style empty event: ignored
    expect(statuses).toEqual(["starting"]);
    r.emit(sample(0, 90, 0));
    expect(statuses).toContain("active");
    r.emit(sample(0.05, 90, 0));                                    // below the dead zone
    expect(deltas).toEqual([]);
    r.emit(sample(10, 90, 0));
    expect(deltas.length).toBe(1);
    expect(deltas[0][0]).toBeCloseTo(-10, 3);
    r.rotate(90);                                                   // screen rotates: next sample is a new zero
    r.emit(sample(50, 90, 0));
    expect(deltas.length).toBe(1);
    r.emit(sample(60, 90, 0));
    expect(deltas.length).toBe(2);
    g.recenter();
    r.emit(sample(120, 90, 0));
    expect(deltas.length).toBe(2);
    g.stop();
    expect(r.calls.remove).toBe(1);
    expect(g.status).toBe("needs-permission");
  });

  test("browsers without a permission API (Android Chrome) start directly, and a sensorless device times out cleanly", async () => {
    const direct = rig({ permission: "absent" });
    const a = gyro(direct);
    expect(await a.g.start()).toBe("starting");
    expect(direct.calls.permission).toBe(0);
    direct.advance(1000);
    expect(a.g.status).toBe("starting");
    direct.advance(1500);
    expect(a.g.status).toBe("no-data");
    expect(a.statuses.at(-1)).toBe("no-data");
    expect(direct.calls.remove).toBe(1);
    const live = rig({ permission: "absent" });
    const b = gyro(live);
    await b.g.start();
    live.emit(sample(0, 90, 0));
    live.advance(5000);
    expect(b.g.status).toBe("active");                              // the timeout is cancelled by the first real sample
  });

  test("starting twice does not double-register; vibration is capability-detected", async () => {
    const r = rig();
    const { g } = gyro(r);
    await g.start(); await g.start();
    expect(r.calls.add).toBe(1);
    expect(pulse(30, undefined)).toBe(false);
    expect(pulse(30, {})).toBe(false);
    expect(pulse([10, 20], { vibrate: () => true })).toBe(true);
    expect(pulse(30, { vibrate: () => { throw new Error("blocked"); } })).toBe(false);
  });
});

// ---------------------------------------------------------------- client (fake socket, fetch and clock)

class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  closedWith: number | undefined;
  onopen: SocketLike["onopen"] = null; onmessage: SocketLike["onmessage"] = null; onclose: SocketLike["onclose"] = null; onerror: SocketLike["onerror"] = null;
  constructor(public url: string) { FakeSocket.all.push(this); }
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close(code?: number) { this.closedWith = code; this.readyState = 3; }
  open() { this.readyState = 1; this.onopen?.({}); }
  serve(t: string, extra: object = {}) { this.onmessage?.({ data: frame(t, extra) }); }
  drop(code = 1006) { this.readyState = 3; this.onclose?.({ code }); }
}
function clock() {
  let now = 0; const timers: { id: number; at: number; fn: () => void }[] = []; let next = 1;
  return {
    scheduler: { set: (fn: () => void, ms: number) => { const t = { id: next++, at: now + ms, fn }; timers.push(t); return t.id; }, clear: (id: unknown) => { const i = timers.findIndex(t => t.id === id); if (i >= 0) timers.splice(i, 1); } },
    advance(ms: number) { now += ms; for (const t of timers.filter(t => t.at <= now).sort((a, b) => a.at - b.at)) { const i = timers.indexOf(t); if (i >= 0) { timers.splice(i, 1); t.fn(); } } },
    pending: () => timers.length,
  };
}
const json = (body: unknown, status = 200) => Promise.resolve({ ok: status < 400, status, json: async () => body } as Response);
function phone(opts: { reconnect?: { minMs: number; maxMs: number; maxAttempts: number } } = {}) {
  FakeSocket.all = [];
  const c = clock();
  const urls: string[] = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    urls.push(`${init?.method ?? "GET"} ${url}`);
    if (url.endsWith("/pair")) return json(JSON.parse(String(init?.body)).code === "123456" ? { session: "sess1", request_id: "rq", phone_secret: "SECRET-PHONE", verify: 47 } : { detail: "That code is not valid." }, JSON.parse(String(init?.body)).code === "123456" ? 200 : 400);
    return json({ session: "sess1", laptop_token: "SECRET-LAPTOP", code: "654321", code_expires_in: 120 });
  }) as unknown as typeof fetch;
  const client = new CompanionClient({ role: "phone", baseUrl: "http://192.168.1.20:8000", fetchImpl, scheduler: c.scheduler, socketFactory: url => new FakeSocket(url), ...opts });
  const states: string[] = [];
  client.on("state", s => states.push(s));
  return { client, c, urls, states, socket: () => FakeSocket.all.at(-1)! };
}

test.describe("client", () => {
  test("pairing keeps secrets out of URLs and walks waiting -> paired", async () => {
    const { client, urls, states, socket } = phone();
    await expect(client.pair("000000")).rejects.toThrow("That code is not valid.");
    expect(client.state).toBe("idle");
    expect(await client.pair("123456")).toBe(47);
    const s = socket();
    expect(s.url).toBe("ws://192.168.1.20:8000/companion/ws");
    s.open();
    expect(s.sent[0]).toEqual({ v: 1, t: "hello", role: "phone", session: "sess1", token: "SECRET-PHONE" });
    s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 0, peer_online: true, approved: false });
    expect(client.state).toBe("waiting");
    s.serve("approved", { last_seq: 0 });
    expect(client.state).toBe("paired");
    expect(states).toContain("pairing");
    expect([...urls, s.url].some(u => u.includes("SECRET") || u.includes("123456"))).toBe(false);
  });

  test("look deltas are coalesced to 20 per second, split to the limit, and numbered in order", async () => {
    const { client, c, socket } = phone();
    await client.pair("123456");
    const s = socket(); s.open(); s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 7, peer_online: true, approved: true });
    for (let i = 0; i < 100; i++) client.look(0.5, 0.1, "touch");
    expect(s.sent.length).toBe(1);                                  // only hello so far
    c.advance(50);
    const headings = s.sent.filter(m => m.t === "heading");
    expect(headings.length).toBe(1);
    expect(headings[0]).toMatchObject({ dyaw: 50, dpitch: 10, mode: "touch", seq: 8 });
    client.look(200, 0, "gyro"); c.advance(50);
    const split = s.sent.filter(m => m.t === "heading").slice(1);
    expect(split.length).toBe(3);
    expect(split.every(m => Math.abs(m.dyaw as number) <= MAX_DELTA_DEG)).toBe(true);
    client.step("next"); client.recenter();
    const seqs = s.sent.slice(1).map(m => m.seq as number);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
    expect(new Set(seqs).size).toBe(seqs.length);
    client.look(Number.NaN, 0, "touch"); c.advance(100);
    expect(s.sent.filter(m => m.t === "heading").length).toBe(4);
  });

  test("a dropped connection reconnects with backoff, resumes numbering and re-announces itself", async () => {
    const { client, c, states, socket } = phone();
    await client.pair("123456");
    let s = socket(); s.open(); s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 0, peer_online: true, approved: true });
    client.step("next");                                           // seq 1
    s.drop();
    expect(client.state).toBe("reconnecting");
    expect(FakeSocket.all.length).toBe(1);
    c.advance(799); expect(FakeSocket.all.length).toBe(1);
    c.advance(1); expect(FakeSocket.all.length).toBe(2);           // first retry after 800 ms
    s = socket(); s.drop();                                        // fails before opening
    c.advance(1599); expect(FakeSocket.all.length).toBe(2);
    c.advance(1); expect(FakeSocket.all.length).toBe(3);           // then 1600 ms
    s = socket(); s.open();
    expect(s.sent[0]).toMatchObject({ t: "hello", token: "SECRET-PHONE" });
    s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 4, peer_online: true, approved: true });   // the server saw more than we did
    expect(client.state).toBe("paired");
    client.step("repeat");
    expect(s.sent.at(-1)).toMatchObject({ t: "step", action: "repeat", seq: 5 });
    expect(states.filter(x => x === "reconnecting").length).toBe(1);
    s.drop();
    c.advance(800); expect(FakeSocket.all.length).toBe(4);         // backoff restarts after a successful connection
  });

  test("final closes end the session without retrying, with the reason in plain words", async () => {
    for (const [code, reason, bye] of [[4410, "revoked", "revoked"], [4409, "replaced", "replaced"], [1008, "denied", "denied"], [4401, "auth_failed", undefined]] as const) {
      const { client, c, socket } = phone();
      const ended: string[] = [];
      client.on("ended", r => ended.push(r));
      await client.pair("123456");
      const s = socket(); s.open();
      s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 0, peer_online: true, approved: true });
      if (bye) s.serve("bye", { reason: bye });
      s.drop(code);
      expect(client.state).toBe("ended");
      expect(ended).toEqual([reason]);
      c.advance(60_000);
      expect(FakeSocket.all.length).toBe(1);                       // never reconnects
      client.step("next");                                         // and sending after the end is a no-op
      expect(s.sent.length).toBe(1);
    }
  });

  test("gives up after the configured attempts; disconnect() cancels pending timers", async () => {
    const { client, c, socket } = phone({ reconnect: { minMs: 100, maxMs: 200, maxAttempts: 3 } });
    const ended: string[] = [];
    client.on("ended", r => ended.push(r));
    await client.pair("123456");
    socket().open(); socket().serve("hello_ok", { role: "phone", session: "sess1", last_seq: 0, peer_online: true, approved: true });
    socket().drop();
    for (let i = 0; i < 3; i++) { c.advance(300); socket().drop(); }
    expect(ended).toEqual(["connection_lost"]);
    const second = phone();
    await second.client.pair("123456");
    second.socket().open();
    second.client.look(5, 0, "touch");
    second.client.disconnect();
    expect(second.c.pending()).toBe(0);
    expect(second.socket().closedWith).toBe(1000);
  });

  test("route state is replayed after reconnect but a stale snapshot never overwrites a newer one", async () => {
    const { client, socket } = phone();
    const seen: [number | undefined, boolean][] = [];
    client.on("route_state", (r, replay) => seen.push([r.step_index, replay]));
    await client.pair("123456");
    const s = socket(); s.open(); s.serve("hello_ok", { role: "phone", session: "sess1", last_seq: 0, peer_online: true, approved: true });
    const state = (seq: number, i: number, extra: object = {}) => s.serve("route_state", { seq, status: "guiding", step_index: i, step_count: 5, instruction: STEP, ...extra });
    state(10, 2); state(9, 1); state(11, 3); state(11, 3, { replay: true });
    s.serve("route_state", { seq: 12, status: "guiding", step_index: 9, step_count: 5, instruction: STEP });   // invalid: ignored by the parser
    expect(seen).toEqual([[2, false], [3, false], [3, true]]);
  });

  test("laptop side: session, pending confirmation, approval and publishing", async () => {
    FakeSocket.all = [];
    const c = clock();
    const sent: string[] = [];
    const client = new CompanionClient({ role: "laptop", baseUrl: "http://localhost:8000", scheduler: c.scheduler, socketFactory: url => new FakeSocket(url),
      fetchImpl: (async (url: string, init?: RequestInit) => { sent.push(`${init?.method} ${url}`); return json({ session: "L1", laptop_token: "SECRET-LAPTOP", code: "654321", code_expires_in: 120 }); }) as never });
    const requests: unknown[] = [];
    client.on("pair_request", r => requests.push(r));
    expect(await client.startSession()).toEqual({ code: "654321", expiresIn: 120 });
    const s = FakeSocket.all[0]; s.open();
    expect(s.sent[0]).toMatchObject({ t: "hello", role: "laptop", token: "SECRET-LAPTOP" });
    expect(s.url).not.toContain("SECRET");
    s.serve("hello_ok", { role: "laptop", session: "L1", last_seq: 0, peer_online: false, approved: true, pending: [{ request_id: "r0", verify: 12, expires_in: 90 }] });
    s.serve("pair_request", { request_id: "r1", verify: 47, expires_in: 120 });
    expect(requests.map(r => (r as { verify: number }).verify)).toEqual([12, 47]);
    client.approve("r1");
    client.publish({ status: "guiding", step_index: 0, step_count: 2, instruction: STEP });
    expect(s.sent.slice(1).map(m => [m.t, m.seq])).toEqual([["approve", 1], ["route_state", 2]]);
    const heard: string[] = [];
    client.on("heading", (y, p, m) => heard.push(`${y},${p},${m}`)); client.on("step", a => heard.push(a)); client.on("recenter", () => heard.push("recenter"));
    s.serve("heading", { seq: 1, dyaw: 5, dpitch: -1, mode: "gyro" }); s.serve("step", { seq: 2, action: "back" }); s.serve("recenter", { seq: 3 });
    expect(heard).toEqual(["5,-1,gyro", "back", "recenter"]);
  });
});

// ---------------------------------------------------------------- two real browsers against the demo server

const repoRoot = path.resolve(process.cwd(), "..");
let server: ChildProcess | undefined;
let outDir = "";
let origin = "";

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = (s.address() as net.AddressInfo).port; s.close(() => resolve(p)); }); s.on("error", reject); });
}

test.describe("paired demo in two browser contexts", () => {
  test.skip(process.env.COMPANION_SKIP_BROWSER === "1", "COMPANION_SKIP_BROWSER=1 (the demo server needs uv and the websockets package)");
  test.describe.configure({ mode: "serial" });
  test.setTimeout(90_000);

  test.beforeAll(async () => {
    test.setTimeout(180_000);
    outDir = mkdtempSync(path.join(os.tmpdir(), "fw-companion-"));
    await build({ configFile: false, root: path.resolve(process.cwd(), "src/companion/demo"), base: "./", logLevel: "silent", plugins: [react()], build: { outDir, emptyOutDir: true, minify: false } });
    const port = await freePort();
    origin = `http://127.0.0.1:${port}`;
    server = spawn("uv", ["run", "--with", "websockets", "python", "-m", "server.companion", "--port", String(port), "--static", outDir], { cwd: repoRoot, stdio: "ignore", detached: process.platform !== "win32" });
    const deadline = Date.now() + 60_000;
    for (;;) {
      try { if ((await fetch(`${origin}/companion/info`)).ok) break; } catch { /* not up yet */ }
      if (Date.now() > deadline) throw new Error("companion demo server did not start");
      await new Promise(r => setTimeout(r, 300));
    }
  });
  test.afterAll(() => {
    // `uv run` starts python as a child: end the whole tree, not just uv, or the server keeps its port.
    if (server?.pid) { if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"]); else try { process.kill(-server.pid); } catch { server.kill(); } }
    if (outDir) rmSync(outDir, { recursive: true, force: true });
  });

  async function contexts(browser: Browser, phoneInit?: string) {
    const laptopContext = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const phoneContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    if (phoneInit) await phoneContext.addInitScript(phoneInit);
    const laptop = await laptopContext.newPage(), mobile = await phoneContext.newPage();
    return { laptop, mobile, close: async () => { await laptopContext.close(); await phoneContext.close(); } };
  }
  async function pairUp(laptop: Page, mobile: Page) {
    await laptop.goto(`${origin}/?role=laptop`);
    await laptop.getByRole("button", { name: "Pair a phone" }).click();
    const code = (await laptop.locator(".cmp-code").textContent())!.trim();
    expect(code).toMatch(/^\d{6}$/);
    await mobile.goto(`${origin}/?role=phone#code=${code}`);
    await expect(mobile.getByLabel("Pairing code")).toHaveValue(code);
    expect(mobile.url()).not.toContain(code);                       // the code left the address bar
    await mobile.getByRole("button", { name: "Pair", exact: true }).click();
    await expect(mobile.getByRole("heading", { name: "Confirm on the laptop" })).toBeVisible();
    const number = (await mobile.locator(".cmp-verify").textContent())!.trim();
    await expect(laptop.getByRole("alertdialog").locator(".cmp-verify")).toHaveText(number);
    await laptop.getByRole("button", { name: "Allow" }).click();
    await expect(mobile.getByText("Connected to laptop")).toBeVisible();
    await expect(laptop.getByText("Phone connected")).toBeVisible();
    return code;
  }
  const heading = async (laptop: Page) => Number((await laptop.getByTestId("heading").locator("b").textContent())!.replace("°", ""));

  test("touch-only pairing, controls, recenter, reconnect and revoke, with the laptop usable throughout", async ({ browser }) => {
    const { laptop, mobile, close } = await contexts(browser);
    const sockets: string[] = [];
    laptop.on("websocket", ws => sockets.push(ws.url())); mobile.on("websocket", ws => sockets.push(ws.url()));
    const requests: string[] = [];
    mobile.on("request", r => requests.push(r.url()));
    const errors: string[] = [];
    laptop.on("pageerror", e => errors.push(e.message)); mobile.on("pageerror", e => errors.push(e.message));
    try {
      const code = await pairUp(laptop, mobile);
      expect([...sockets, ...requests].some(u => u.includes(code) || /token|secret/i.test(u))).toBe(false);

      // The phone shows the laptop's instruction large; the phone's buttons are requests the laptop acts on.
      await expect(mobile.locator(".cmp-instruction")).toHaveText(/main entrance/);
      if (process.env.COMPANION_SHOTS) {   // opt-in review screenshots
        await laptop.screenshot({ path: path.join(process.env.COMPANION_SHOTS, "laptop-paired.png") });
        await mobile.screenshot({ path: path.join(process.env.COMPANION_SHOTS, "phone-controller.png"), fullPage: true });
      }
      await mobile.getByRole("button", { name: "Next" }).click();
      await expect(mobile.locator(".cmp-instruction")).toHaveText(/18 metres/);
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/18 metres/);
      await expect(laptop.getByTestId("log")).toContainText("phone asked: next");
      await mobile.getByRole("button", { name: "Back" }).click();
      await expect(mobile.locator(".cmp-instruction")).toHaveText(/main entrance/);
      await mobile.getByRole("button", { name: "Repeat" }).click();
      await expect(laptop.getByTestId("log")).toContainText("phone asked: repeat");
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/main entrance/);

      // Look: drag and buttons change the laptop camera heading only.
      const pad = mobile.getByRole("group", { name: /Look pad/ });
      const box = (await pad.boundingBox())!;
      await mobile.mouse.move(box.x + 40, box.y + 60); await mobile.mouse.down();
      await mobile.mouse.move(box.x + 140, box.y + 60, { steps: 5 }); await mobile.mouse.up();
      await expect.poll(() => heading(laptop)).toBe(30);
      await mobile.getByRole("button", { name: "Look left 15 degrees" }).click();
      await expect.poll(() => heading(laptop)).toBe(15);
      await mobile.getByRole("button", { name: "Recenter view" }).click();
      await expect.poll(() => heading(laptop)).toBe(0);
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/main entrance/);   // looking never advances progress

      // Reload the phone tab: it reconnects without pairing again and numbering continues.
      await mobile.reload();
      await expect(mobile.getByText("Connected to laptop")).toBeVisible();
      await mobile.getByRole("button", { name: "Next" }).click();
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/18 metres/);

      // Phone disappears: the laptop carries on.
      await mobile.close();
      await expect(laptop.getByText("Waiting for a phone")).toBeVisible();
      await laptop.getByRole("button", { name: "Next (laptop)" }).click();
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/notice board/);

      // A fresh phone pairs, then the laptop revokes: the phone says so and the laptop remains usable.
      const phone2Context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
      const mobile2 = await phone2Context.newPage();
      await laptop.getByRole("button", { name: "New code" }).click();
      await expect(laptop.locator(".cmp-code")).not.toHaveText(code);
      const code2 = (await laptop.locator(".cmp-code").textContent())!.trim();
      await mobile2.goto(`${origin}/?role=phone`);
      await mobile2.getByLabel("Pairing code").fill(code2);
      await mobile2.getByRole("button", { name: "Pair", exact: true }).click();
      await laptop.getByRole("button", { name: "Allow" }).click();
      await expect(mobile2.getByText("Connected to laptop")).toBeVisible();
      await mobile2.getByRole("button", { name: "Next" }).click();
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/Lift 2/);
      await laptop.getByRole("button", { name: "End pairing" }).click();
      await expect(mobile2.getByText("The laptop ended this pairing.")).toBeVisible();
      await expect(mobile2.getByRole("heading", { name: "Pair with the laptop" })).toBeVisible();
      await laptop.getByRole("button", { name: "Previous (laptop)" }).click();
      await expect(laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/notice board/);
      await phone2Context.close();
      expect(errors).toEqual([]);
    } finally { await close().catch(() => undefined); }
  });

  test("a wrong code is refused, a denied phone is told, and a code cannot be reused", async ({ browser }) => {
    const { laptop, mobile, close } = await contexts(browser);
    try {
      await laptop.goto(`${origin}/?role=laptop`);
      await laptop.getByRole("button", { name: "Pair a phone" }).click();
      const code = (await laptop.locator(".cmp-code").textContent())!.trim();
      await mobile.goto(`${origin}/?role=phone`);
      await mobile.getByLabel("Pairing code").fill(code === "000000" ? "111111" : "000000");
      await mobile.getByRole("button", { name: "Pair", exact: true }).click();
      await expect(mobile.getByRole("alert")).toContainText("not valid");
      await mobile.getByLabel("Pairing code").fill(code);
      await mobile.getByRole("button", { name: "Pair", exact: true }).click();
      await expect(laptop.getByRole("alertdialog")).toBeVisible();
      await laptop.getByRole("button", { name: "Deny" }).click();
      await expect(mobile.getByText("The laptop did not accept this phone.")).toBeVisible();
      await mobile.getByLabel("Pairing code").fill(code);
      await mobile.getByRole("button", { name: "Pair", exact: true }).click();
      await expect(mobile.getByRole("alert")).toContainText("not valid");   // single use
    } finally { await close(); }
  });

  test("motion look needs a tap, survives denial with touch intact, and turns only the camera when granted", async ({ browser }) => {
    const denied = await contexts(browser, "window.__asked = 0; DeviceOrientationEvent.requestPermission = () => { window.__asked++; return Promise.resolve('denied'); };");
    try {
      await pairUp(denied.laptop, denied.mobile);
      expect(await denied.mobile.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(0);   // nothing asked on load or on pairing
      await denied.mobile.getByText("Motion & connection",{exact:true}).click();
      await expect(denied.mobile.getByText(/Motion look is off/)).toBeVisible();
      await denied.mobile.getByRole("button", { name: "Turn on motion look" }).click();
      await expect(denied.mobile.getByText(/Motion access was declined/)).toBeVisible();
      expect(await denied.mobile.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(1);
      await denied.mobile.getByRole("button", { name: "Look right 15 degrees" }).click();
      await expect.poll(() => heading(denied.laptop)).toBe(15);
      await denied.mobile.getByRole("button", { name: "Next" }).click();
      await expect(denied.laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/18 metres/);
    } finally { await denied.close(); }

    const granted = await contexts(browser, "DeviceOrientationEvent.requestPermission = () => Promise.resolve('granted');");
    try {
      await pairUp(granted.laptop, granted.mobile);
      await granted.mobile.getByText("Motion & connection",{exact:true}).click();
      await granted.mobile.getByRole("button", { name: "Turn on motion look" }).click();
      await expect(granted.mobile.getByText(/Waiting for motion data|Motion look is on/)).toBeVisible();
      const fire = (alpha: number, beta: number, gamma: number) => granted.mobile.evaluate(([a, b, g]) => window.dispatchEvent(new DeviceOrientationEvent("deviceorientation", { alpha: a, beta: b, gamma: g })), [alpha, beta, gamma]);
      await fire(0, 90, 0);
      await expect(granted.mobile.getByText(/Motion look is on/)).toBeVisible();
      await fire(25, 90, 0);                                         // phone turns 25 degrees anticlockwise: view turns left
      await expect.poll(() => heading(granted.laptop)).toBe(335);
      await expect(granted.laptop.getByTestId("steps").locator("[aria-current=step]")).toHaveText(/main entrance/);   // progress untouched
      await granted.mobile.getByRole("button", { name: "Turn off motion look" }).click();
      await fire(80, 90, 0);
      await granted.mobile.waitForTimeout(300);
      expect(await heading(granted.laptop)).toBe(335);               // listener removed: no further movement
    } finally { await granted.close(); }
  });
});
