import { BrowserRouter, Routes, Route } from "react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { Home } from "@/pages/Home";
import { UploadPage } from "@/pages/Upload";
import { Microbiome } from "@/pages/Microbiome";
import { MultiOmics } from "@/pages/MultiOmics";
import { MultiSite } from "@/pages/MultiSite";
import { Agent } from "@/pages/Agent";
import { Results } from "@/pages/Results";
import WorkflowBuilder from "@/pages/WorkflowBuilder";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/microbiome" element={<Microbiome />} />
          <Route path="/multi-omics" element={<MultiOmics />} />
          <Route path="/multi-site" element={<MultiSite />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/results" element={<Results />} />
        </Route>
        <Route path="/workflow-builder" element={<WorkflowBuilder />} />
      </Routes>
    </BrowserRouter>
  );
}"react-router-dom";
import { MainLayout } from "@/components/layout/MainLayout";
import { Home } from "@/pages/Home";
import { UploadPage } from "@/pages/Upload";
import { Microbiome } from "@/pages/Microbiome";
import { MultiOmics } from "@/pages/MultiOmics";
import { MultiSite } from "@/pages/MultiSite";
import { Agent } from "@/pages/Agent";
import { Results } from "@/pages/Results";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/microbiome" element={<Microbiome />} />
          <Route path="/multi-omics" element={<MultiOmics />} />
          <Route path="/multi-site" element={<MultiSite />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/results" element={<Results />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
