<script lang="ts">
  import { createEventDispatcher } from "svelte";

  const dispatch = createEventDispatcher();

  let token = "";
  let loading = false;
  let error = "";

  async function login() {
    if (!token.trim()) return;
    loading = true;
    error = "";
    try {
      const r = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token.trim() }),
      });
      if (r.ok) {
        dispatch("login");
      } else {
        error = "Token 错误，请重试";
      }
    } catch (e) {
      error = "网络错误，请重试";
    } finally {
      loading = false;
    }
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") login();
  }
</script>

<div class="login-bg">
  <div class="login-card">
    <div class="logo">🏠</div>
    <h1 class="title">SynapseOS</h1>
    <p class="subtitle">请输入访问 Token</p>

    <input
      type="password"
      bind:value={token}
      on:keydown={onKeydown}
      placeholder="Token"
      class="token-input"
      disabled={loading}
      autocomplete="current-password"
    />

    {#if error}
      <p class="error-msg">{error}</p>
    {/if}

    <button class="login-btn" on:click={login} disabled={loading || !token.trim()}>
      {loading ? "验证中..." : "登录"}
    </button>
  </div>
</div>

<style>
  .login-bg {
    position: fixed;
    inset: 0;
    background: #0A0E1A;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }

  .login-card {
    background: rgba(17, 24, 39, 0.8);
    border: 1px solid rgba(0, 229, 255, 0.2);
    border-radius: 16px;
    padding: 40px 36px;
    width: 320px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    box-shadow: 0 0 40px rgba(0, 229, 255, 0.1);
  }

  .logo {
    font-size: 40px;
    line-height: 1;
  }

  .title {
    font-size: 22px;
    font-weight: 700;
    color: #00E5FF;
    letter-spacing: 2px;
    text-shadow: 0 0 12px rgba(0, 229, 255, 0.5);
    margin: 0;
  }

  .subtitle {
    font-size: 14px;
    color: #94A3B8;
    margin: 0;
  }

  .token-input {
    width: 100%;
    padding: 12px 14px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(0, 229, 255, 0.2);
    border-radius: 8px;
    color: #F0F9FF;
    font-size: 16px;
    outline: none;
    transition: border-color 0.2s;
  }

  .token-input:focus {
    border-color: rgba(0, 229, 255, 0.5);
  }

  .token-input::placeholder {
    color: #475569;
  }

  .error-msg {
    color: #FF3860;
    font-size: 13px;
    margin: 0;
    text-align: center;
  }

  .login-btn {
    width: 100%;
    padding: 12px;
    border-radius: 8px;
    background: linear-gradient(135deg, rgba(0,229,255,0.2), rgba(0,229,255,0.1));
    border: 1px solid rgba(0, 229, 255, 0.4);
    color: #00E5FF;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    min-height: 44px;
  }

  .login-btn:hover:not(:disabled) {
    background: rgba(0, 229, 255, 0.15);
    box-shadow: 0 0 16px rgba(0, 229, 255, 0.2);
  }

  .login-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
