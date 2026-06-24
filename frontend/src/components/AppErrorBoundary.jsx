import React from "react";

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.props.reportError?.({
      title: "页面显示失败",
      message: error?.message || "页面渲染异常，已停止空白页。",
      details: info?.componentStack || error?.stack || "",
      source: "AppErrorBoundary",
    });
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-fallback" translate="no">
          <section className="app-fallback__panel">
            <h1>页面加载失败</h1>
            <p>{this.state.error?.message || "页面渲染异常，请返回加入页或刷新重试。"}</p>
            <div className="app-fallback__actions">
              <button type="button" onClick={() => window.location.assign("/welcome")}>
                返回首页
              </button>
              <button type="button" onClick={() => window.location.reload()}>
                刷新页面
              </button>
            </div>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
