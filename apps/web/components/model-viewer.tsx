"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { Bounds, OrbitControls, useGLTF } from "@react-three/drei";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";
import { materialName, partLabel } from "@/lib/i18n";

export interface PickedPart {
  key: string;
  label: string;
  role: string;
  material: string;
  size_mm: [number, number, number];
  cut_mm: [number, number];
}

const FRONT_ROLES = new Set(["door", "drawer_front", "sliding_door"]);
const EDGE_COLOUR = new THREE.Color("#3f3f46");
const HIGHLIGHT = new THREE.Color("#2563eb");

function Furniture({ url, hideFronts, selectedKey, onPick }: {
  url: string; hideFronts: boolean; selectedKey: string | null; onPick: (p: PickedPart | null) => void;
}) {
  const { scene } = useGLTF(url);

  // Clone so materials can be tinted per part without touching the cached glTF; add panel outlines.
  const model = useMemo(() => {
    const root = scene.clone(true);
    root.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.material = (obj.material as THREE.MeshStandardMaterial).clone();
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(obj.geometry), new THREE.LineBasicMaterial({ color: EDGE_COLOUR }));
        edges.raycast = () => {}; // clicks go to the panel, not its outline
        obj.add(edges);
      }
    });
    return root;
  }, [scene]);

  useEffect(() => {
    model.traverse((obj) => {
      if (!(obj instanceof THREE.Mesh)) return;
      obj.visible = !(hideFronts && FRONT_ROLES.has(obj.userData.role));
      // three.js raycasts invisible meshes too: hidden fronts must not swallow clicks meant for the interior.
      obj.raycast = obj.visible ? THREE.Mesh.prototype.raycast : () => {};
      const mat = obj.material as THREE.MeshStandardMaterial;
      mat.emissive = obj.name === selectedKey ? HIGHLIGHT : new THREE.Color(0);
      mat.emissiveIntensity = obj.name === selectedKey ? 0.35 : 0;
    });
  }, [model, hideFronts, selectedKey]);

  function onClick(e: ThreeEvent<MouseEvent>) {
    e.stopPropagation();
    const obj = e.object;
    const d = obj.userData as Partial<PickedPart> & { size_mm?: [number, number, number]; cut_mm?: [number, number] };
    onPick({ key: obj.name, label: d.label ?? obj.name, role: d.role ?? "", material: d.material ?? "",
             size_mm: d.size_mm ?? [0, 0, 0], cut_mm: d.cut_mm ?? [0, 0] });
  }

  return <primitive object={model} onClick={onClick} onPointerMissed={() => onPick(null)} />;
}

export default function ModelViewer({ url }: { url: string }) {
  const [hideFronts, setHideFronts] = useState(false);
  const [picked, setPicked] = useState<PickedPart | null>(null);
  const { t } = useI18n();

  return (
    <div className="relative h-[480px] w-full overflow-hidden rounded-lg border bg-gradient-to-b from-stone-100 to-stone-200 dark:from-stone-900 dark:to-stone-800">
      <Suspense fallback={<div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="animate-spin" /></div>}>
        <Canvas camera={{ position: [2.2, 1.6, 3.2], fov: 35 }} dpr={[1, 2]} shadows={false}>
          <ambientLight intensity={0.7} />
          <directionalLight position={[3, 5, 4]} intensity={1.6} />
          <directionalLight position={[-4, 2, -3]} intensity={0.4} />
          <Bounds fit clip observe margin={1.15}>
            <Furniture url={url} hideFronts={hideFronts} selectedKey={picked?.key ?? null} onPick={setPicked} />
          </Bounds>
          <gridHelper args={[10, 20, "#a8a29e", "#d6d3d1"]} position={[0, -0.001, 0]} />
          <OrbitControls makeDefault enableDamping />
        </Canvas>
      </Suspense>
      <div className="absolute left-3 top-3 flex gap-2">
        <Button size="sm" variant="secondary" onClick={() => {
          setHideFronts((v) => !v);
          if (picked && FRONT_ROLES.has(picked.role)) setPicked(null); // a hidden door can't stay selected
        }}>
          {hideFronts ? <Eye /> : <EyeOff />} {hideFronts ? t("viewer.show_fronts") : t("viewer.hide_fronts")}
        </Button>
      </div>
      {picked ? (
        <div className="absolute bottom-3 left-3 rounded-md border bg-card/95 px-3 py-2 text-sm shadow">
          <div className="font-medium">{partLabel(t, picked.label)}</div>
          <div className="text-muted-foreground">
            {picked.size_mm.join(" × ")} mm · {t("viewer.cut")} {picked.cut_mm.join(" × ")} · {materialName(t, picked.material)}
          </div>
        </div>
      ) : (
        <div className="absolute bottom-3 left-3 text-xs text-muted-foreground">{t("viewer.hint")}</div>
      )}
    </div>
  );
}
