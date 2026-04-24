<template>
  <el-container class="shell">
    <el-aside width="240px" class="shell__aside">
      <div class="shell__brand">
        <div class="shell__title">企业级RAG</div>
      </div>
      <el-menu :default-active="route.path" router class="shell__menu">
        <el-menu-item index="/chat">聊天</el-menu-item>
        <el-menu-item index="/assistants">助理管理</el-menu-item>
        <el-menu-item index="/knowledge-bases">知识库管理</el-menu-item>
        <el-menu-item index="/sessions">会话管理</el-menu-item>
        <el-menu-item index="/tasks">任务中心</el-menu-item>
        <el-menu-item index="/review">审核台</el-menu-item>
        <el-menu-item index="/system">系统概览</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="shell__header">
        <div>
          <div class="shell__header-title">{{ currentTitle }}</div>
        </div>
        <div class="shell__user">
          <div class="shell__user-meta">
            <div class="shell__user-name">
              {{ authStore.currentUser?.display_name ?? "未登录" }}
            </div>
            <div class="shell__user-role">
              {{ authStore.currentUser?.roles.join(" / ") ?? "" }}
            </div>
          </div>
          <el-button plain @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="shell__main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const currentTitle = computed(
  () => String(route.meta.title ?? "RAG 管理台"),
);

async function handleLogout() {
  authStore.logout();
  await router.replace("/login");
}
</script>

<style scoped>
.shell {
  min-height: 100vh;
}

.shell__aside {
  border-right: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
}

.shell__brand {
  padding: 24px 20px 16px;
}

.shell__title {
  font-size: 22px;
  font-weight: 700;
}

.shell__menu {
  border-right: 0;
  background: transparent;
}

.shell__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e5e7eb;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(16px);
}

.shell__header-title {
  font-size: 20px;
  font-weight: 700;
}

.shell__main {
  padding: 24px;
}

.shell__user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.shell__user-meta {
  text-align: right;
}

.shell__user-name {
  font-weight: 600;
}

.shell__user-role {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
  text-transform: uppercase;
}
</style>
