"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

// Full-bleed neuron network hero — a living synaptic canvas filling the
// whole hero band, centered, dense, and lit with real bloom so it reads
// as a premium effect rather than a boxed decorative widget. Inspired by
// 21st.dev's "neurons hero" / "SynapseBackground" / "AI Hero Background"
// (InstancedMesh + Unreal Bloom): neurons wire up to their nearest
// neighbors and fire toward the cursor, pulses cascading through the net.
const NEURON_COUNT = 170;
const NEAREST_LINKS = 3;
const CORE_LINKS = 10;
const PULSE_POOL = 48;
const PULSE_DURATION = 0.7;
const FIRE_RADIUS = 0.1;
const FIRE_COOLDOWN = 350;

function makeGlowTexture(hex: string) {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, `${hex}ff`);
  gradient.addColorStop(0.4, `${hex}66`);
  gradient.addColorStop(1, `${hex}00`);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

type Neuron = {
  sprite: THREE.Sprite;
  material: THREE.SpriteMaterial;
  base: THREE.Vector3;
  drift: number;
  energy: number;
  lastFired: number;
  edges: number[];
};

type Pulse = {
  sprite: THREE.Sprite;
  active: boolean;
  from: number;
  to: number;
  t: number;
  intensity: number;
};

export function HeroCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = canvas?.parentElement;
    if (!canvas || !container) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0e130f);
    scene.fog = new THREE.Fog(0x0e130f, 6, 15);

    const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 100);
    camera.position.set(0, 0.2, 9.5);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.85, 0.55, 0.12);
    composer.addPass(bloomPass);

    function resize() {
      const rect = container!.getBoundingClientRect();
      renderer.setSize(rect.width, rect.height, false);
      composer.setSize(rect.width, rect.height);
      camera.aspect = rect.width / Math.max(rect.height, 1);
      camera.updateProjectionMatrix();
    }
    resize();
    window.addEventListener("resize", resize);

    // Compute the visible frustum size at the neuron field's depth so the
    // network always fills the actual rendered width — not a fixed
    // world-unit guess that only looked right at one viewport size.
    const vFov = (camera.fov * Math.PI) / 180;
    const visibleHeight = 2 * Math.tan(vFov / 2) * camera.position.z;
    const visibleWidth = visibleHeight * camera.aspect;
    const spreadX = visibleWidth * 0.62;
    const spreadY = visibleHeight * 0.62;

    const rig = new THREE.Group();
    scene.add(rig);

    // Core neuron — the "AI" hub, dead-center in the frame.
    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.5, 1),
      new THREE.MeshBasicMaterial({ color: 0xc084fc, wireframe: true, transparent: true, opacity: 0.95 })
    );
    rig.add(core);

    const coreGlowTexture = makeGlowTexture("#c084fc");
    const coreGlow = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: coreGlowTexture, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: true })
    );
    coreGlow.scale.set(3.6, 3.6, 1);
    rig.add(coreGlow);

    // Dense scattered neuron field spanning the full hero width.
    const neuronTexture = makeGlowTexture("#5eead4");
    const neurons: Neuron[] = Array.from({ length: NEURON_COUNT }, () => {
      const base = new THREE.Vector3(
        (Math.random() - 0.5) * 2 * spreadX,
        (Math.random() - 0.5) * 2 * spreadY,
        (Math.random() - 0.5) * 4.2
      );
      const material = new THREE.SpriteMaterial({
        map: neuronTexture,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        opacity: 0.62,
        fog: true,
      });
      const sprite = new THREE.Sprite(material);
      const size = 0.26 + Math.random() * 0.16;
      sprite.scale.set(size, size, 1);
      sprite.position.copy(base);
      rig.add(sprite);
      return { sprite, material, base, drift: Math.random() * Math.PI * 2, energy: 0, lastFired: -9999, edges: [] };
    });

    // Wire each neuron to its nearest neighbors (organic synapse graph).
    const CORE = NEURON_COUNT; // sentinel index for the core hub
    const edgeSet = new Set<string>();
    const edges: [number, number][] = [];
    function addEdge(a: number, b: number) {
      if (a === b) return;
      const key = a < b ? `${a}-${b}` : `${b}-${a}`;
      if (edgeSet.has(key)) return;
      edgeSet.add(key);
      edges.push([a, b]);
      neurons[a]?.edges.push(edges.length - 1);
      neurons[b]?.edges.push(edges.length - 1);
    }
    neurons.forEach((n, i) => {
      const dists = neurons
        .map((o, j) => ({ j, d: i === j ? Infinity : n.base.distanceTo(o.base) }))
        .sort((a, b) => a.d - b.d)
        .slice(0, NEAREST_LINKS);
      dists.forEach(({ j }) => addEdge(i, j));
    });
    const coreLinks = neurons
      .map((n, j) => ({ j, d: n.base.distanceTo(new THREE.Vector3(0, 0, 0)) }))
      .sort((a, b) => a.d - b.d)
      .slice(0, CORE_LINKS);
    coreLinks.forEach(({ j }) => addEdge(CORE, j));

    function positionOf(idx: number) {
      return idx === CORE ? core.position : neurons[idx].sprite.position;
    }

    const edgePositions = new Float32Array(edges.length * 2 * 3);
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
    const edgeLines = new THREE.LineSegments(
      edgeGeometry,
      new THREE.LineBasicMaterial({ color: 0x8b7cf6, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, fog: true })
    );
    rig.add(edgeLines);

    // Traveling pulse pool — small glow sprites reused across firings.
    const pulseTexture = makeGlowTexture("#f5f0ff");
    const pulses: Pulse[] = Array.from({ length: PULSE_POOL }, () => {
      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({ map: pulseTexture, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0, fog: true })
      );
      sprite.scale.set(0.28, 0.28, 1);
      rig.add(sprite);
      return { sprite, active: false, from: 0, to: 0, t: 0, intensity: 1 };
    });

    function spawnPulse(from: number, to: number, intensity: number) {
      const p = pulses.find((p) => !p.active);
      if (!p) return;
      p.active = true;
      p.from = from;
      p.to = to;
      p.t = 0;
      p.intensity = intensity;
      p.sprite.material.opacity = intensity;
    }

    function fire(idx: number, now: number, intensity = 1) {
      const n = neurons[idx];
      if (n) {
        if (now - n.lastFired < FIRE_COOLDOWN && intensity < 0.9) return;
        n.lastFired = now;
        n.energy = Math.max(n.energy, intensity);
      }
      const edgeIdxs =
        idx === CORE
          ? coreLinks.map(({ j }) => edges.findIndex((e) => e[0] === CORE && e[1] === j))
          : (n?.edges ?? []);
      edgeIdxs.forEach((ei) => {
        if (ei < 0) return;
        const [a, b] = edges[ei];
        const to = a === idx ? b : a;
        spawnPulse(idx, to, intensity);
      });
    }

    // Cursor tracking (drives ambient rig tilt + neuron firing).
    const pointer = { x: 0, y: 0 };
    const targetTilt = { x: 0, y: 0 };
    const ndc = new THREE.Vector2(-9, -9);
    function onPointerMove(e: PointerEvent) {
      const rect = container!.getBoundingClientRect();
      pointer.x = (e.clientX - rect.left) / rect.width - 0.5;
      pointer.y = (e.clientY - rect.top) / rect.height - 0.5;
      targetTilt.y = pointer.x * 0.3;
      targetTilt.x = -pointer.y * 0.2;
      ndc.set(pointer.x * 2, -pointer.y * 2);
    }
    function onPointerLeave() {
      targetTilt.x = 0;
      targetTilt.y = 0;
      ndc.set(-9, -9);
    }
    container.addEventListener("pointermove", onPointerMove);
    container.addEventListener("pointerleave", onPointerLeave);

    const projected = new THREE.Vector3();
    let raf = 0;
    let t = 0;
    let lastFrame = performance.now();

    function render(now: number) {
      const dt = Math.min((now - lastFrame) / 1000, 0.05);
      lastFrame = now;
      t += dt;

      neurons.forEach((n, i) => {
        n.sprite.position.set(
          n.base.x + Math.sin(t * 0.35 + n.drift) * 0.14,
          n.base.y + Math.cos(t * 0.3 + n.drift) * 0.14,
          n.base.z + Math.sin(t * 0.25 + n.drift * 1.7) * 0.1
        );

        if (ndc.x > -2) {
          projected.copy(n.sprite.position).project(camera);
          const dx = projected.x - ndc.x;
          const dy = projected.y - ndc.y;
          if (Math.sqrt(dx * dx + dy * dy) < FIRE_RADIUS) {
            fire(i, now);
          }
        }

        n.energy *= 0.9;
        const glow = Math.min(n.energy, 1);
        n.material.opacity = 0.62 + glow * 0.38;
        n.sprite.scale.setScalar(0.26 + glow * 0.4);
      });

      for (let i = 0; i < edges.length; i++) {
        const [a, b] = edges[i];
        const pa = positionOf(a);
        const pb = positionOf(b);
        const base = i * 6;
        edgePositions[base] = pa.x;
        edgePositions[base + 1] = pa.y;
        edgePositions[base + 2] = pa.z;
        edgePositions[base + 3] = pb.x;
        edgePositions[base + 4] = pb.y;
        edgePositions[base + 5] = pb.z;
      }
      edgeGeometry.attributes.position.needsUpdate = true;

      pulses.forEach((p) => {
        if (!p.active) return;
        p.t += dt / PULSE_DURATION;
        if (p.t >= 1) {
          p.active = false;
          p.sprite.material.opacity = 0;
          const nextIntensity = p.intensity * 0.65;
          if (nextIntensity > 0.18) fire(p.to, now, nextIntensity);
          else if (p.to !== CORE) neurons[p.to].energy = Math.max(neurons[p.to].energy, nextIntensity);
          return;
        }
        const pa = positionOf(p.from);
        const pb = positionOf(p.to);
        p.sprite.position.lerpVectors(pa, pb, p.t);
        p.sprite.material.opacity = p.intensity * (1 - p.t * 0.3);
      });

      core.rotation.y += 0.003;
      core.rotation.x += 0.0015;
      const corePulse = 1 + Math.sin(t * 1.6) * 0.05;
      core.scale.setScalar(corePulse);
      coreGlow.scale.setScalar(3.6 * (1 + Math.sin(t * 1.6) * 0.08));

      rig.rotation.y += (targetTilt.y - rig.rotation.y) * 0.05;
      rig.rotation.x += (targetTilt.x - rig.rotation.x) * 0.05;

      composer.render();
      if (!reduceMotion) raf = requestAnimationFrame(render);
    }

    if (reduceMotion) {
      render(performance.now());
    } else {
      raf = requestAnimationFrame(render);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", onPointerLeave);
      neuronTexture.dispose();
      neurons.forEach((n) => n.material.dispose());
      edgeGeometry.dispose();
      (edgeLines.material as THREE.Material).dispose();
      core.geometry.dispose();
      (core.material as THREE.Material).dispose();
      coreGlowTexture.dispose();
      (coreGlow.material as THREE.SpriteMaterial).dispose();
      pulseTexture.dispose();
      pulses.forEach((p) => (p.sprite.material as THREE.SpriteMaterial).dispose());
      composer.dispose();
      renderer.dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className="block h-full w-full" />;
}
