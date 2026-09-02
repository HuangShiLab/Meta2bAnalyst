import { create } from "zustand";
import { persist } from "zustand/middleware";
import api from "@/utils/api";

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  quota_mb: number | null;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
}

// Token is mirrored to localStorage["token"] because utils/api.ts (and the
// bare fetch() calls via authHeaders()) read it from there.
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: localStorage.getItem("token"),
      user: null,

      login: async (username, password) => {
        const res = await api.post("/auth/login", { username, password });
        const { token, user } = res.data as { token: string; user: AuthUser };
        localStorage.setItem("token", token);
        set({ token, user });
      },

      logout: () => {
        localStorage.removeItem("token");
        set({ token: null, user: null });
      },

      fetchMe: async () => {
        if (!get().token) return;
        try {
          const res = await api.get("/auth/me");
          set({ user: res.data as AuthUser });
        } catch {
          // 401 is handled by the api interceptor (redirects to /login).
        }
      },
    }),
    {
      name: "meta2banalyst-auth",
      partialize: (state) => ({ token: state.token, user: state.user }),
    }
  )
);
