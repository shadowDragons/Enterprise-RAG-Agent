import { defineStore } from "pinia";

import { fetchCurrentUser, login, type CurrentUser } from "@/api/auth";
import {
  clearStoredAccessToken,
  getStoredAccessToken,
  setStoredAccessToken,
} from "@/utils/auth";

interface AuthState {
  token: string;
  currentUser: CurrentUser | null;
  loading: boolean;
  initialized: boolean;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    token: "",
    currentUser: null,
    loading: false,
    initialized: false,
  }),
  getters: {
    isAuthenticated(state): boolean {
      return Boolean(state.token && state.currentUser);
    },
  },
  actions: {
    async initialize() {
      if (this.initialized) {
        return;
      }

      const token = getStoredAccessToken();
      if (!token) {
        this.initialized = true;
        return;
      }

      this.token = token;
      try {
        this.currentUser = await fetchCurrentUser();
      } catch {
        this.clearSession();
      } finally {
        this.initialized = true;
      }
    },
    async login(username: string, password: string) {
      this.loading = true;
      try {
        const response = await login({ username, password });
        this.token = response.access_token;
        this.currentUser = response.user;
        setStoredAccessToken(response.access_token);
        this.initialized = true;
      } finally {
        this.loading = false;
      }
    },
    async refreshCurrentUser() {
      if (!this.token) {
        this.currentUser = null;
        return;
      }
      this.currentUser = await fetchCurrentUser();
    },
    logout() {
      this.clearSession();
      this.initialized = true;
    },
    clearSession() {
      this.token = "";
      this.currentUser = null;
      clearStoredAccessToken();
    },
  },
});
