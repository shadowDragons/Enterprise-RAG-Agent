<template>
  <div class="login-page">
    <div class="login-page__panel">
      <div class="login-page__eyebrow">RAG Console</div>
      <h1 class="login-page__title">登录</h1>
      <p class="login-page__subtitle">请输入账号和密码。</p>

      <el-form class="login-form" label-position="top" @submit.prevent>
        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            autocomplete="username"
            placeholder="请输入用户名"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button
          type="primary"
          class="login-form__submit"
          :loading="authStore.loading"
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const form = reactive({
  username: "",
  password: "",
});

async function handleLogin() {
  if (!form.username.trim() || !form.password.trim()) {
    ElMessage.warning("请输入用户名和密码。");
    return;
  }

  try {
    await authStore.login(form.username.trim(), form.password);
    const redirect =
      typeof route.query.redirect === "string" && route.query.redirect.startsWith("/")
        ? route.query.redirect
        : "/chat";
    await router.replace(redirect);
    ElMessage.success("登录成功。");
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "登录失败，请检查用户名和密码。";
    ElMessage.error(message);
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at top left, rgba(14, 165, 233, 0.18), transparent 34%),
    radial-gradient(circle at bottom right, rgba(249, 115, 22, 0.18), transparent 30%),
    linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
}

.login-page__panel {
  width: min(480px, 100%);
  padding: 36px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(18px);
}

.login-page__eyebrow {
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.login-page__title {
  margin: 12px 0 8px;
  color: #0f172a;
  font-size: 38px;
  line-height: 1.05;
}

.login-page__subtitle {
  margin: 0 0 24px;
  color: #475569;
  line-height: 1.7;
}

.login-form {
  margin-top: 24px;
}

.login-form__submit {
  width: 100%;
  margin-top: 8px;
}
</style>
