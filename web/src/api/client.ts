import axios from "axios";
import { ElMessage } from "element-plus";

import { router } from "@/router";
import { clearStoredAccessToken, getStoredAccessToken } from "@/utils/auth";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
});

let handlingUnauthorized = false;

apiClient.interceptors.request.use((config) => {
  const token = getStoredAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const statusCode = error?.response?.status;
    if (statusCode === 401) {
      clearStoredAccessToken();
      const currentPath = router.currentRoute.value.fullPath;
      if (!handlingUnauthorized && router.currentRoute.value.path !== "/login") {
        handlingUnauthorized = true;
        ElMessage.error("登录已失效，请重新登录。");
        await router.push({
          path: "/login",
          query: currentPath ? { redirect: currentPath } : undefined,
        });
        handlingUnauthorized = false;
      }
    }

    const detail = error?.response?.data?.detail;
    if (typeof detail === "string" && detail) {
      error.message = detail;
    }
    return Promise.reject(error);
  },
);
