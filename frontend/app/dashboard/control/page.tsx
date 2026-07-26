"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  Check,
  DoorOpen,
  LogOut,
  MapPin,
  Play,
  RotateCcw,
  ShieldAlert,
  Square,
  Users,
  Video,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const configuredApiBase = process.env.NEXT_PUBLIC_CROWD_API;

function resolveApiBase() {
  if (typeof window === "undefined") {
    return configuredApiBase || "http://localhost:8000";
  }

  const frontendHost = window.location.hostname;
  if (
    configuredApiBase &&
    !(configuredApiBase.includes("localhost") && frontendHost !== "localhost")
  ) {
    return configuredApiBase;
  }

  return `${window.location.protocol}//${frontendHost}:8000`;
}

type SetupMode = "calibration" | "entry" | "exit";

type ScenePoint = {
  id: string;
  label: string;
  x: number;
  y: number;
};

type RiskPayload = {
  ready: boolean;
  ts?: number;
  people_count: number;
  risk_score: number;
  risk_level: "NORMAL" | "WARNING" | "HIGH" | "CRITICAL" | "ERROR";
  message: string;
  density?: {
    max_cell_density: number;
    average_occupied_cell_density: number;
    hotspots: { x: number; y: number; count: number }[];
  };
  movement?: {
    average_speed: number;
    low_speed_people: number;
    flow_score: number;
    congestion_score: number;
    growth_score: number;
  };
  exits?: {
    id: string;
    label: string;
    nearby_people: number;
    status: "clear" | "busy" | "congested";
  }[];
  alert?: RiskAlert;
};

type RiskAlert = {
  id: string;
  ts: number;
  level: string;
  score: number;
  message: string;
  acknowledged: boolean;
};

type SceneConfig = {
  calibration_points: ScenePoint[];
  entry_points: ScenePoint[];
  exit_points: ScenePoint[];
};

const EMPTY_RISK: RiskPayload = {
  ready: false,
  people_count: 0,
  risk_score: 0,
  risk_level: "NORMAL",
  message: "Backend is waiting for the camera worker.",
};

const modeMeta = {
  calibration: {
    label: "Calibration",
    icon: MapPin,
    color: "bg-sky-500",
    max: 4,
  },
  entry: {
    label: "Entry",
    icon: DoorOpen,
    color: "bg-amber-500",
    max: 99,
  },
  exit: {
    label: "Exit",
    icon: ShieldAlert,
    color: "bg-cyan-400",
    max: 99,
  },
} satisfies Record<SetupMode, unknown>;

export default function ControlDashboard() {
  const router = useRouter();
  const apiBase = useMemo(resolveApiBase, []);
  const rawImageRef = useRef<HTMLImageElement | null>(null);
  const [user, setUser] = useState<{ name: string } | null>(null);
  const [backendRunning, setBackendRunning] = useState(false);
  const [risk, setRisk] = useState<RiskPayload>(EMPTY_RISK);
  const [riskHistory, setRiskHistory] = useState<
    { time: string; risk: number; people: number }[]
  >([]);
  const [alerts, setAlerts] = useState<RiskAlert[]>([]);
  const [sceneConfig, setSceneConfig] = useState<SceneConfig>({
    calibration_points: [],
    entry_points: [],
    exit_points: [],
  });
  const [setupMode, setSetupMode] = useState<SetupMode>("calibration");
  const [imageSize, setImageSize] = useState({ width: 1280, height: 720 });
  const [statusMessage, setStatusMessage] = useState("");

  const [cameraSource, setCameraSource] = useState("");

  const allPoints = useMemo(
    () => [
      ...sceneConfig.calibration_points.map((p) => ({
        ...p,
        kind: "calibration" as const,
      })),
      ...sceneConfig.entry_points.map((p) => ({
        ...p,
        kind: "entry" as const,
      })),
      ...sceneConfig.exit_points.map((p) => ({ ...p, kind: "exit" as const })),
    ],
    [sceneConfig],
  ); 

  const fetchSceneConfig = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/scene/config`);
      const data = await res.json();
      setSceneConfig({
        calibration_points: data.calibration_points ?? [],
        entry_points: data.entry_points ?? [],
        exit_points: data.exit_points ?? [],
      });
    } catch {
      setStatusMessage("Could not load scene setup from " + apiBase);
    }
  }, [apiBase]);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/alerts`);
      const data = await res.json();
      setAlerts(data.items ?? []);
    } catch {
      setStatusMessage("Could not load alerts from " + apiBase);
    }
  }, [apiBase]);

  const updateRisk = useCallback((payload: RiskPayload) => {
    setRisk(payload);
    if (payload.ts) {
      setRiskHistory((prev) => {
        const next = [
          ...prev,
          {
            time: new Date(payload.ts! * 1000).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            risk: payload.risk_score,
            people: payload.people_count,
          },
        ];
        return next.slice(-40);
      });
    }
  }, []);

  useEffect(() => {
    async function init() {
      try {
        const authRes = await fetch("/api/auth/me");
        if (!authRes.ok) {
          router.push("/signin");
          return;
        }
        const auth = await authRes.json();
        setUser(auth.user);

        const healthRes = await fetch(`${apiBase}/health`);
        const health = await healthRes.json();
        setBackendRunning(Boolean(health.running));
        updateRisk(health.latest ?? EMPTY_RISK);
        await fetchSceneConfig();
        await fetchAlerts();
      } catch {
        setStatusMessage("Backend is not reachable at " + apiBase);
      }
    }

    init();
  }, [apiBase, fetchAlerts, fetchSceneConfig, router, updateRisk]);

  useEffect(() => {
    const wsUrl = apiBase.replace(/^http/, "ws") + "/ws/risk";
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (event) => {
      updateRisk(JSON.parse(event.data));
    };
    socket.onerror = () => {
      setStatusMessage("Live risk socket disconnected.");
    };

    const alertTimer = window.setInterval(fetchAlerts, 5000);

    return () => {
      socket.close();
      window.clearInterval(alertTimer);
    };
  }, [apiBase, fetchAlerts, updateRisk]);

  const startBackend = async () => {
    setStatusMessage("");
    const parsedSource = cameraSource.trim();
    const body = parsedSource
      ? {
          source: /^\d+$/.test(parsedSource)
            ? Number(parsedSource)
            : parsedSource,
        }
      : {};

    const res = await fetch(`${apiBase}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      setStatusMessage("Could not start camera worker.");
      return;
    }
    setBackendRunning(true);
  };

  const stopBackend = async () => {
    await fetch(`${apiBase}/stop`, { method: "POST" });
    setBackendRunning(false);
  };

  const saveSceneConfig = async (nextConfig: SceneConfig) => {
    const res = await fetch(`${apiBase}/scene/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nextConfig),
    });
    if (!res.ok) {
      setStatusMessage("Could not save scene setup.");
      return;
    }
    const saved = await res.json();
    setSceneConfig({
      calibration_points: saved.calibration_points ?? [],
      entry_points: saved.entry_points ?? [],
      exit_points: saved.exit_points ?? [],
    });
    setStatusMessage("Scene setup saved.");
  };

  const clearModePoints = async () => {
    const key = pointKey(setupMode);
    await saveSceneConfig({ ...sceneConfig, [key]: [] });
  };

  const handleFeedClick = async (event: React.MouseEvent<HTMLDivElement>) => {
    const img = rawImageRef.current;
    if (!img) return;

    const point = imagePointFromClick(event, img, imageSize);
    if (!point) return;

    const key = pointKey(setupMode);
    const existing = sceneConfig[key];
    const max = modeMeta[setupMode].max as number;
    const nextPoint: ScenePoint = {
      id: `${setupMode}_${existing.length + 1}`,
      label:
        setupMode === "calibration"
          ? `Cal ${existing.length + 1}`
          : `${modeMeta[setupMode].label} ${existing.length + 1}`,
      x: Math.round(point.x),
      y: Math.round(point.y),
    };
    const nextPoints = [...existing, nextPoint].slice(0, max);
    await saveSceneConfig({ ...sceneConfig, [key]: nextPoints });
  };

  const acknowledgeAlert = async (id: string) => {
    await fetch(`${apiBase}/alerts/${id}/ack`, { method: "POST" });
    await fetchAlerts();
  };

  const handleLogout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/signin");
  };

  const riskTone = riskToneClass(risk.risk_level);

  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-100 text-neutral-950">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div>
            <h1 className="text-xl font-semibold">CrowdResQ Control Room</h1>
            <p className="text-sm text-muted-foreground">
              Event authority dashboard
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={backendRunning ? "default" : "outline"}>
              {backendRunning ? "Camera running" : "Camera stopped"}
            </Badge>
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {user.name}
            </span>
            <Button variant="ghost" size="icon" onClick={handleLogout}>
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-5">
        {statusMessage && (
          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Status</AlertTitle>
            <AlertDescription>{statusMessage}</AlertDescription>
          </Alert>
        )}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1.35fr_0.65fr]">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Video className="h-4 w-4" />
                  Raw Feed
                </CardTitle>
                <CardDescription>
                  {modeMeta[setupMode].label} point setup is active.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div
                  className="relative aspect-video overflow-hidden rounded-md bg-black"
                  onClick={handleFeedClick}
                >
                  <img
                    ref={rawImageRef}
                    src={`${apiBase}/stream/raw.mjpg`}
                    alt="Raw live camera feed"
                    className="h-full w-full object-contain"
                    onLoad={(event) => {
                      const img = event.currentTarget;
                      if (img.naturalWidth && img.naturalHeight) {
                        setImageSize({
                          width: img.naturalWidth,
                          height: img.naturalHeight,
                        });
                      }
                    }}
                  />
                  {allPoints.map((point) => (
                    <PointMarker
                      key={`${point.kind}-${point.id}`}
                      point={point}
                      imageRef={rawImageRef}
                      imageSize={imageSize}
                    />
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  {(["calibration", "entry", "exit"] as SetupMode[]).map(
                    (mode) => {
                      const Icon = modeMeta[mode].icon;
                      return (
                        <Button
                          key={mode}
                          size="sm"
                          variant={setupMode === mode ? "default" : "outline"}
                          onClick={() => setSetupMode(mode)}
                        >
                          <Icon className="mr-2 h-4 w-4" />
                          {modeMeta[mode].label}
                        </Button>
                      );
                    },
                  )}
                  <Button size="sm" variant="outline" onClick={clearModePoints}>
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Clear
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity className="h-4 w-4" />
                  Processed Feed
                </CardTitle>
                <CardDescription>
                  Heatmap, tracking, and risk overlay
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="aspect-video overflow-hidden rounded-md bg-black">
                  <img
                    src={`${apiBase}/stream/processed.mjpg`}
                    alt="Processed feed with crowd heatmap"
                    className="h-full w-full object-contain"
                  />
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <Input
                    value={cameraSource}
                    onChange={(event) => setCameraSource(event.target.value)}
                    placeholder="Camera source: 0, 1, or stream URL"
                    disabled={backendRunning}
                  />
                  {!backendRunning ? (
                    <Button size="sm" onClick={startBackend}>
                      <Play className="mr-2 h-4 w-4" />
                      Start
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={stopBackend}
                    >
                      <Square className="mr-2 h-4 w-4" />
                      Stop
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Backend: {apiBase}
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            <Card className={riskTone.panel}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldAlert className="h-4 w-4" />
                  Stampede Risk
                </CardTitle>
                <CardDescription>{risk.message}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-end justify-between">
                  <div>
                    <div className={`text-3xl font-bold ${riskTone.text}`}>
                      {risk.risk_level}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      Score {risk.risk_score}/100
                    </div>
                  </div>
                  <Users className={`h-10 w-10 ${riskTone.text}`} />
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 gap-3">
              <Metric title="People" value={risk.people_count} />
              <Metric
                title="Max density"
                value={risk.density?.max_cell_density ?? 0}
              />
              <Metric
                title="Avg speed"
                value={risk.movement?.average_speed ?? 0}
              />
              <Metric
                title="Slow crowd"
                value={risk.movement?.low_speed_people ?? 0}
              />
            </div>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Exit Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {(risk.exits ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No exits set.</p>
                ) : (
                  risk.exits?.map((exit) => (
                    <div
                      key={exit.id}
                      className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                    >
                      <span>{exit.label}</span>
                      <Badge
                        variant={
                          exit.status === "congested"
                            ? "destructive"
                            : "outline"
                        }
                      >
                        {exit.status} · {exit.nearby_people}
                      </Badge>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_0.8fr]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Risk Trend</CardTitle>
              <CardDescription>
                Risk score and people count over time
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={riskHistory}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" minTickGap={28} />
                    <YAxis />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="risk"
                      stroke="#dc2626"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="people"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Automatic Alerts</CardTitle>
              <CardDescription>High and critical risk events</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No alerts yet.</p>
              ) : (
                alerts.slice(0, 6).map((alert) => (
                  <Alert
                    key={alert.id}
                    variant={alert.acknowledged ? "default" : "destructive"}
                  >
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle className="flex items-center justify-between gap-2">
                      <span>
                        {alert.level} · Score {alert.score}
                      </span>
                      {!alert.acknowledged && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => acknowledgeAlert(alert.id)}
                        >
                          <Check className="mr-1 h-3.5 w-3.5" />
                          Ack
                        </Button>
                      )}
                    </AlertTitle>
                    <AlertDescription>{alert.message}</AlertDescription>
                  </Alert>
                ))
              )}
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}

function Metric({ title, value }: { title: string; value: number | string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm text-muted-foreground">{title}</div>
        <div className="text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function PointMarker({
  point,
  imageRef,
  imageSize,
}: {
  point: ScenePoint & { kind: SetupMode };
  imageRef: React.RefObject<HTMLImageElement>;
  imageSize: { width: number; height: number };
}) {
  const rect = getDisplayedImageRect(imageRef.current, imageSize);
  if (!rect) return null;

  const left = rect.left + (point.x / imageSize.width) * rect.width;
  const top = rect.top + (point.y / imageSize.height) * rect.height;
  const meta = modeMeta[point.kind];

  return (
    <div
      className="pointer-events-none absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-1"
      style={{ left, top }}
    >
      <span
        className={`h-3 w-3 rounded-full ring-2 ring-white ${meta.color}`}
      />
      <span className="rounded bg-black/70 px-1.5 py-0.5 text-[11px] text-white">
        {point.label}
      </span>
    </div>
  );
}

function pointKey(mode: SetupMode) {
  if (mode === "calibration") return "calibration_points" as const;
  if (mode === "entry") return "entry_points" as const;
  return "exit_points" as const;
}

function imagePointFromClick(
  event: React.MouseEvent<HTMLDivElement>,
  img: HTMLImageElement,
  imageSize: { width: number; height: number },
) {
  const containerRect = event.currentTarget.getBoundingClientRect();
  const display = getDisplayedImageRect(img, imageSize);
  if (!display) return null;

  const xInContainer = event.clientX - containerRect.left;
  const yInContainer = event.clientY - containerRect.top;

  if (
    xInContainer < display.left ||
    xInContainer > display.left + display.width ||
    yInContainer < display.top ||
    yInContainer > display.top + display.height
  ) {
    return null;
  }

  return {
    x: ((xInContainer - display.left) / display.width) * imageSize.width,
    y: ((yInContainer - display.top) / display.height) * imageSize.height,
  };
}

function getDisplayedImageRect(
  img: HTMLImageElement | null,
  imageSize: { width: number; height: number },
) {
  if (!img?.parentElement) return null;

  const parent = img.parentElement.getBoundingClientRect();
  const scale = Math.min(
    parent.width / Math.max(1, imageSize.width),
    parent.height / Math.max(1, imageSize.height),
  );
  const width = imageSize.width * scale;
  const height = imageSize.height * scale;

  return {
    left: (parent.width - width) / 2,
    top: (parent.height - height) / 2,
    width,
    height,
  };
}

function riskToneClass(level: RiskPayload["risk_level"]) {
  if (level === "CRITICAL") {
    return { panel: "border-red-300 bg-red-50", text: "text-red-700" };
  }
  if (level === "HIGH") {
    return { panel: "border-orange-300 bg-orange-50", text: "text-orange-700" };
  }
  if (level === "WARNING") {
    return { panel: "border-amber-300 bg-amber-50", text: "text-amber-700" };
  }
  if (level === "ERROR") {
    return { panel: "border-red-300 bg-red-50", text: "text-red-700" };
  }
  return {
    panel: "border-emerald-300 bg-emerald-50",
    text: "text-emerald-700",
  };
}
