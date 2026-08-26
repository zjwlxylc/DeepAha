export default function DataManagement() {
  return (
    <section className="human-test-panel human-test-danger-zone" aria-labelledby="data-management-title">
      <h2 id="data-management-title">本地数据管理</h2>
      <p>停止服务不会删除数据库、人工决定、审计证据或加密 Provider 配置。</p>
      <p className="field-help">精确清空必须先停止活动运行，再使用一次性 challenge；Provider 密钥删除始终是独立动作。</p>
      <button className="button button-danger" type="button" disabled>
        当前运行环境尚未启用精确清空
      </button>
    </section>
  );
}
