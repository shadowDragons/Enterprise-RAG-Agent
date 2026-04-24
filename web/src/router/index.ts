import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { getStoredAccessToken } from "@/utils/auth";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      component: () => import("@/views/LoginView.vue"),
      meta: { public: true, title: "登录" },
    },
    {
      path: "/",
      component: () => import("@/components/AppShell.vue"),
      children: [
        { path: "", redirect: "/chat" },
        {
          path: "chat",
          component: () => import("@/views/ChatView.vue"),
          meta: { title: "聊天" },
        },
        {
          path: "assistants",
          component: () => import("@/views/AssistantsView.vue"),
          meta: { title: "助理管理" },
        },
        {
          path: "knowledge-bases",
          component: () => import("@/views/KnowledgeBasesView.vue"),
          meta: { title: "知识库管理" },
        },
        {
          path: "sessions",
          component: () => import("@/views/SessionsView.vue"),
          meta: { title: "会话管理" },
        },
        {
          path: "tasks",
          component: () => import("@/views/TasksView.vue"),
          meta: { title: "任务中心" },
        },
        {
          path: "review",
          component: () => import("@/views/ReviewView.vue"),
          meta: { title: "审核台" },
        },
        {
          path: "system",
          component: () => import("@/views/SystemView.vue"),
          meta: { title: "系统概览" },
        },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();
  if (!getStoredAccessToken() && authStore.token) {
    authStore.clearSession();
  }
  await authStore.initialize();

  const isPublic = Boolean(to.meta.public);
  if (!isPublic && !authStore.isAuthenticated) {
    return {
      path: "/login",
      query: to.fullPath ? { redirect: to.fullPath } : undefined,
    };
  }

  if (to.path === "/login" && authStore.isAuthenticated) {
    return "/chat";
  }

  return true;
});
