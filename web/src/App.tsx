import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";

import { Layout } from "./components/Layout";
import { Empty, LinkButton } from "./components/ui";
import { EnvironmentsPage } from "./pages/EnvironmentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { GrowPage } from "./pages/GrowPage";
import { JobPage } from "./pages/JobPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RunsPage />} />
        <Route path="runs/:name" element={<RunPage />} />
        <Route path="grow" element={<GrowPage />} />
        <Route path="jobs/:id" element={<JobPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="environments" element={<EnvironmentsPage />} />
        <Route path="*" element={
          <Empty title="Nothing here">
            <LinkButton to="/" className="mt-2">Back to runs</LinkButton>
          </Empty>
        } />
      </Route>
    </Routes>
  );
}

export function App() {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } }));
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
