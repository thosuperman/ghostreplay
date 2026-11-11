import { useEffect, useState } from "react";
import type { LabId } from "../api/client";

export type DemoId = "refund" | "devops";
export type LegalPage = "terms" | "privacy" | "disclaimer";
const LEGAL: readonly string[] = ["terms", "privacy", "disclaimer"];

export type Route =
  | { name: "home" }
  | { name: "demo"; demo: DemoId }
  | { name: "connect" }
  | { name: "import" }
  | { name: "legal"; page: LegalPage }
  | { name: "story"; lab: LabId }
  | { name: "executions"; lab: LabId }
  | { name: "execution"; lab: LabId; id: string; focus?: string }
  | { name: "replay"; lab: LabId; id?: string }
  | { name: "failure-lab"; lab: LabId; id?: string }
  | { name: "diff"; lab: LabId; a?: string; b?: string }
  | { name: "regression"; lab: LabId; id?: string };

const isLab = (s: string | undefined): s is LabId => s === "support" || s === "devops";

export function parse(hash: string): Route {
  const [pathPart = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  const params = new URLSearchParams(query);
  const [lab, section, id] = pathPart.split("/").map(decodeURIComponent);
  if (lab === "demo") return section === "devops" ? { name: "demo", demo: "devops" } : { name: "demo", demo: "refund" };
  if (lab === "connect") return { name: "connect" };
  if (lab === "import") return { name: "import" };
  if (lab && LEGAL.includes(lab)) return { name: "legal", page: lab as LegalPage };
  if (!isLab(lab)) return { name: "home" };
  switch (section) {
    case "story":
      return { name: "story", lab };
    case "executions":
      return id ? { name: "execution", lab, id, focus: params.get("focus") ?? undefined } : { name: "executions", lab };
    case "replay":
      return { name: "replay", lab, id };
    case "failure-lab":
      return { name: "failure-lab", lab, id };
    case "diff":
      return { name: "diff", lab, a: params.get("a") ?? undefined, b: params.get("b") ?? undefined };
    case "regression":
      return { name: "regression", lab, id };
    default:
      return { name: "executions", lab };
  }
}

export function href(route: Route): string {
  switch (route.name) {
    case "home":
      return "#/";
    case "demo":
      return `#/demo/${route.demo}`;
    case "connect":
      return "#/connect";
    case "import":
      return "#/import";
    case "legal":
      return `#/${route.page}`;
    case "story":
      return `#/${route.lab}/story`;
    case "executions":
      return `#/${route.lab}/executions`;
    case "execution":
      return `#/${route.lab}/executions/${encodeURIComponent(route.id)}${route.focus ? `?focus=${encodeURIComponent(route.focus)}` : ""}`;
    case "replay":
      return `#/${route.lab}/replay${route.id ? `/${encodeURIComponent(route.id)}` : ""}`;
    case "failure-lab":
      return `#/${route.lab}/failure-lab${route.id ? `/${encodeURIComponent(route.id)}` : ""}`;
    case "diff": {
      const q = new URLSearchParams();
      if (route.a) q.set("a", route.a);
      if (route.b) q.set("b", route.b);
      const qs = q.toString();
      return `#/${route.lab}/diff${qs ? `?${qs}` : ""}`;
    }
    case "regression":
      return `#/${route.lab}/regression${route.id ? `/${encodeURIComponent(route.id)}` : ""}`;
  }
}

export function navigate(route: Route): void {
  window.location.hash = href(route);
}

/** Pretty paths (/demo/refund, /connect, /import) are served the dashboard by the proxy;
 *  map them onto the hash routes the app uses. */
function adoptPathname(): void {
  const m = window.location.pathname.match(/^\/(demo\/(?:refund|devops)|connect|import|terms|privacy|disclaimer)\/?$/);
  if (m && !window.location.hash) window.history.replaceState(null, "", `/#/${m[1]}`);
}

export function isGuided(route: Route): boolean {
  return route.name === "home" || route.name === "demo" || route.name === "connect" || route.name === "legal";
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => {
    adoptPathname();
    return parse(window.location.hash);
  });
  useEffect(() => {
    const on = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
