import { useEffect, useRef } from "react";

// 这个文件收口可复用的“基础展示组件”。
// App.jsx 会非常大，如果连弹窗、卡片、表格这些基础结构也全写在里面，
// 学习时会很难分清“页面业务逻辑”和“可复用 UI 组件”的边界。

export function Modal({ title, subtitle, size = "lg", onClose, children, actions }) {
  // Modal 组件只负责弹窗骨架，不负责具体业务内容。
  // children 由调用者自由传入，这样同一套弹窗结构可以被登录、参数设置、结果查看等多处复用。
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal-shell modal-${size}`} onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button className="ghost-icon" onClick={onClose} type="button">
            关闭
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {actions ? <div className="modal-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

export function MetricCard({ label, value, hint, tone = "neutral" }) {
  // 首页上方四个统计卡片都复用这个组件。
  // 这样数值卡片的样式和结构能够保持一致，页面看起来更整齐。
  return (
    <article className={`metric-card tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

export function DataTable({
  headers,
  rows,
  selectedKey,
  emphasizedKey,
  autoScrollKey,
  onSelect,
  emptyText = "暂无数据",
}) {
  // DataTable 本质上是一个“轻量级的可选中表格”。
  // 当前项目没有引入复杂表格库，原因是：
  // 1. 表格需求其实比较明确，不需要额外引入大依赖。
  // 2. 便于教学时看到最直接的数据渲染过程。
  const rowRefs = useRef(new Map());

  useEffect(() => {
    // 当外部传入 autoScrollKey 时，表格会自动滚到指定行。
    // 这个能力主要用于“刚加入工作区的污染物”自动定位，
    // 让用户不用手动在长表格里找新增项。
    if (autoScrollKey === undefined || autoScrollKey === null) {
      return;
    }
    const row = rowRefs.current.get(autoScrollKey);
    row?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [autoScrollKey, rows.length]);

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              // 部分结果表在同一行里有两个都叫“合计”的列。
              // 如果只用列名作为 React key，切换结果标签时 React 会把同名表头
              // 误认为同一个节点，导致旧的“合计”残留到风险控制值表中。
              // 加上列序号后，每一列都有稳定且唯一的身份。
              <th key={`${index}-${header}`}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td className="empty-cell" colSpan={headers.length}>
                {emptyText}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={row.key}
                ref={(element) => {
                  // 我们把每一行的 DOM 节点缓存起来，
                  // 这样外部给出某个 row.key 时，就能快速找到并滚动到该行。
                  if (element) {
                    rowRefs.current.set(row.key, element);
                    return;
                  }
                  rowRefs.current.delete(row.key);
                }}
                className={[
                  selectedKey === row.key ? "is-selected" : "",
                  emphasizedKey === row.key ? "is-emphasized" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                // onSelect 是可选的：
                // 有些表格只是展示结果，有些表格则需要点击选中某一行。
                onClick={onSelect ? () => onSelect(row.key) : undefined}
              >
                {row.cells.map((cell, index) => (
                  <td key={`${row.key}-${index}`}>{cell === "" ? "—" : cell}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
