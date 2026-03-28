import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// 前端入口文件的职责非常单一：
// 1. 找到 HTML 中的 root 节点。
// 2. 挂载 React 应用。
// 3. 顺手加载全局样式。
//
// 这里保留 React.StrictMode，主要是为了在开发阶段更早发现副作用问题。
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
