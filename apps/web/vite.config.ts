import http from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Resolve the FastAPI origin.
 * Nemesis uses 8001 (vLLM often owns 8000). Local Windows default is 8000.
 * VITE_API_PROXY / INSTANTIMPACT_PORT win; otherwise the first origin that
 * answers GET /api/system/health is locked in.
 */
function candidates(): string[] {
  const listed = [
    process.env.VITE_API_PROXY,
    process.env.INSTANTIMPACT_PORT
      ? `http://127.0.0.1:${process.env.INSTANTIMPACT_PORT}`
      : undefined,
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8000",
  ].filter((x): x is string => Boolean(x));
  return [...new Set(listed.map((u) => u.replace(/\/$/, "")))];
}

function healthOk(base: string): Promise<boolean> {
  return new Promise((resolve) => {
    const url = new URL("/api/system/health", base);
    const req = http.get(url, { timeout: 600 }, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function proxyTo(target: string, req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url || "/", target);
  const headers = { ...req.headers, host: url.host };
  const preq = http.request(
    {
      protocol: url.protocol,
      hostname: url.hostname,
      port: url.port,
      path: `${url.pathname}${url.search}`,
      method: req.method,
      headers,
    },
    (pres) => {
      res.writeHead(pres.statusCode || 502, pres.headers);
      pres.pipe(res);
    }
  );
  preq.on("error", (err) => {
    if (!res.headersSent) {
      res.statusCode = 502;
      res.setHeader("content-type", "application/json");
      res.end(
        JSON.stringify({
          detail: `API proxy failed (${target}): ${err.message}. Tried ${candidates().join(", ")}`,
        })
      );
    }
  });
  req.pipe(preq);
}

function apiProxyPlugin(): Plugin {
  let locked: string | null = process.env.VITE_API_PROXY?.replace(/\/$/, "") || null;
  const handler = async (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    if (!req.url?.startsWith("/api")) {
      next();
      return;
    }
    if (!locked) {
      for (const c of candidates()) {
        if (await healthOk(c)) {
          locked = c;
          console.log(`[instantimpact] API proxy → ${c}`);
          break;
        }
      }
    }
    const target = locked || candidates()[0];
    if (!locked) {
      console.warn(`[instantimpact] API not healthy yet; proxying to ${target}`);
    }
    proxyTo(target, req, res);
  };
  return {
    name: "instantimpact-api-proxy",
    configureServer(server) {
      server.middlewares.use(handler);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handler);
    },
  };
}

export default defineConfig({
  plugins: [react(), apiProxyPlugin()],
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  preview: {
    host: "0.0.0.0",
    port: 5173,
  },
});
