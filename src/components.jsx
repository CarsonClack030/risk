import { useEffect, useRef } from "react";

export function Modal({ title, subtitle, size = "lg", onClose, children, actions }) {
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
  const rowRefs = useRef(new Map());

  useEffect(() => {
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
            {headers.map((header) => (
              <th key={header}>{header}</th>
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
