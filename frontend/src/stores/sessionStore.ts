import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  AnalysisStep,
  DataFormat,
  UploadFormat,
  UploadFile,
  AnalysisParams,
  AnalysisResult,
  FilterParams,
  NormalizationParams,
  AnalysisHistoryItem,
} from "@/types";

interface SessionState {
  currentStep: AnalysisStep;
  dataFormat: DataFormat | null;
  uploadFormat: UploadFormat | null;
  uploadedFiles: UploadFile[];
  analysisParams: AnalysisParams | null;
  filterParams: FilterParams | null;
  normalizationParams: NormalizationParams | null;
  analysisResults: AnalysisResult | null;
  analysisHistory: AnalysisHistoryItem[];
  selectedSpecies: string | null;
  sessionId: string | null;

  setCurrentStep: (step: AnalysisStep) => void;
  setDataFormat: (format: DataFormat | null) => void;
  setUploadFormat: (format: UploadFormat | null) => void;
  addUploadedFile: (file: UploadFile) => void;
  removeUploadedFile: (fileId: string) => void;
  updateFileProgress: (fileId: string, progress: number) => void;
  setAnalysisParams: (params: AnalysisParams | null) => void;
  setFilterParams: (params: FilterParams | null) => void;
  setNormalizationParams: (params: NormalizationParams | null) => void;
  setAnalysisResults: (results: AnalysisResult | null) => void;
  setAnalysisHistory: (history: AnalysisHistoryItem[]) => void;
  addAnalysisHistoryItem: (item: AnalysisHistoryItem) => void;
  updateAnalysisHistoryItem: (id: string, updates: Partial<AnalysisHistoryItem>) => void;
  removeAnalysisHistoryItem: (id: string) => void;
  setSelectedSpecies: (species: string | null) => void;
  setSessionId: (id: string | null) => void;
  resetSession: () => void;
}

const initialState = {
  currentStep: "home" as AnalysisStep,
  dataFormat: null,
  uploadFormat: null,
  uploadedFiles: [],
  analysisParams: null,
  filterParams: null,
  normalizationParams: null,
  analysisResults: null,
  analysisHistory: [],
  selectedSpecies: null,
  sessionId: null,
};

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      ...initialState,

      setCurrentStep: (step) => set({ currentStep: step }),
      setDataFormat: (format) => set({ dataFormat: format }),
      setUploadFormat: (format) => set({ uploadFormat: format }),

      addUploadedFile: (file) =>
        set((state) => ({
          uploadedFiles: [...state.uploadedFiles, file],
        })),

      removeUploadedFile: (fileId) =>
        set((state) => ({
          uploadedFiles: state.uploadedFiles.filter((f) => f.id !== fileId),
        })),

      updateFileProgress: (fileId, progress) =>
        set((state) => ({
          uploadedFiles: state.uploadedFiles.map((f) =>
            f.id === fileId ? { ...f, progress } : f
          ),
        })),

      setAnalysisParams: (params) => set({ analysisParams: params }),
      setFilterParams: (params) => set({ filterParams: params }),
      setNormalizationParams: (params) => set({ normalizationParams: params }),
      setAnalysisResults: (results) => set({ analysisResults: results }),

      setAnalysisHistory: (history) => set({ analysisHistory: history }),
      addAnalysisHistoryItem: (item) =>
        set((state) => ({
          analysisHistory: [item, ...state.analysisHistory],
        })),
      updateAnalysisHistoryItem: (id, updates) =>
        set((state) => ({
          analysisHistory: state.analysisHistory.map((item) =>
            item.id === id ? { ...item, ...updates } : item
          ),
        })),
      removeAnalysisHistoryItem: (id) =>
        set((state) => ({
          analysisHistory: state.analysisHistory.filter((item) => item.id !== id),
        })),

      setSelectedSpecies: (species) => set({ selectedSpecies: species }),
      setSessionId: (id) => set({ sessionId: id }),

      resetSession: () => set(initialState),
    }),
    {
      name: "meta2banalyst-session",
    }
  )
);
