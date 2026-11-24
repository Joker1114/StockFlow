import { defineConfig, loadEnv } from "vite";
import uni from "@dcloudio/vite-plugin-uni";
import { DEFAULT_API_BASE_URL } from "./src/api/defaults";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), ['VITE_API_BASE_URL', 'VITE_API_PROXY_TARGET']);
  const apiBase = env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  const target = env.VITE_API_PROXY_TARGET?.trim() || apiBase;
  for (const [key, value] of [['VITE_API_BASE_URL', apiBase], ['VITE_API_PROXY_TARGET', target]]) {
    let url: URL;
    try {
      url = new URL(value);
    } catch {
      throw new Error(`${key} 必须是有效的 HTTP(S) URL`);
    }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error(`${key} 必须是有效的 HTTP(S) URL，且不含凭证、查询参数或片段`);
    }
  }

  return {
    plugins: [uni()],
    server: {
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  };
});
