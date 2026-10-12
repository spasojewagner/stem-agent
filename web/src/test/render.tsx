import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router";

/** Render inside the app's providers, at `route`, matched against `path`. */
export function renderAt(ui: ReactElement, { route = "/", path = "*" }: { route?: string; path?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="/jobs/:id" element={<div>job page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export type Handler = (init?: RequestInit) => unknown;

/** Replace fetch with canned API responses, keyed by "METHOD /api/path". */
export function mockApi(routes: Record<string, unknown | Handler>) {
  const calls: { key: string; body?: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const key = `${init?.method ?? "GET"} ${url}`;
    calls.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (!(key in routes)) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
    const value = routes[key];
    const data = typeof value === "function" ? (value as Handler)(init) : value;
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}
