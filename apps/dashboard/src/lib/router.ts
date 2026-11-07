import { useEffect, useState } from "react";
import type { LabId } from "../api/client";

export type Route =
  | { name: "home" }
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

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
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
