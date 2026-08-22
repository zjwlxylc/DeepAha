import type { MetadataRoute } from "next";


export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "DeepAha 公开机会观测站",
    short_name: "DeepAha",
    description: "查看经治理的机会、官方证据与变化历史。",
    start_url: "/opportunities",
    display: "standalone",
    background_color: "#f7fafc",
    theme_color: "#0c3559",
    lang: "zh-CN",
  };
}
