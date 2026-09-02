import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { Home } from "@/pages/Home";
import { UploadPage } from "@/pages/Upload";
import { Inspection } from "@/pages/Inspection";
import { FilterPage } from "@/pages/Filter";
import { Normalize } from "@/pages/Normalize";
import { Microbiome } from "@/pages/Microbiome";
import { MultiOmics } from "@/pages/MultiOmics";
import { MultiSite } from "@/pages/MultiSite";
import { Agent } from "@/pages/Agent";
import { Results } from "@/pages/Results";
import { Login } from "@/pages/Login";
import { Account } from "@/pages/Account";
import WorkflowBuilder from "@/pages/WorkflowBuilder";
import { useAuthStore } from "@/stores/authStore";

function RequireAuth() {
  const token = useAuthStore((s) => s.token);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  useEffect(() => {
    if (token) fetchMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route element={<MainLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/upload" element={<UploadPage />} />
            <Route path="/inspection" element={<Inspection />} />
            <Route path="/filter" element={<FilterPage />} />
            <Route path="/normalize" element={<Normalize />} />
            <Route path="/microbiome" element={<Microbiome />} />
            <Route path="/multi-omics" element={<MultiOmics />} />
            <Route path="/multi-site" element={<MultiSite />} />
            <Route path="/agent" element={<Agent />} />
            <Route path="/results" element={<Results />} />
            <Route path="/account" element={<Account />} />
          </Route>
          <Route path="/workflow-builder" element={<WorkflowBuilder />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
