import { DataTable, Modal } from "./components";
import {
  CATALOG_HEADERS,
  CONCENTRATION_COLUMNS,
  PARAMETER_COLUMNS,
  POLLUTANT_FORM_FIELDS,
} from "./constants";

export function UpdateDialog({ update, onClose, onOpenRelease }) {
  if (!update) return null;

  return (
    <Modal
      title="发现新版本"
      subtitle="是否前往 Gitee 下载新版本安装包？"
      size="sm"
      onClose={onClose}
      actions={
        <>
          <button className="ghost-button" onClick={onClose} type="button">
            暂不下载
          </button>
          <button className="primary-button" onClick={onOpenRelease} type="button">
            前往下载
          </button>
        </>
      }
    >
      <div className="update-card">
        <div className="version-comparison">
          <div>
            <span>当前版本</span>
            <strong>v{update.currentVersion}</strong>
          </div>
          <div>
            <span>最新版本</span>
            <strong>v{update.latestVersion}</strong>
          </div>
        </div>
        <p className="update-release-name">{update.releaseName}</p>
        <div className={`update-notes ${update.releaseNotes ? "" : "muted"}`}>
          {update.releaseNotes || "本次发布暂未填写更新说明。"}
        </div>
        <small>确认后将使用系统默认浏览器打开 Gitee Release 页面。</small>
      </div>
    </Modal>
  );
}

export function ErrorDialog({ message, onClose }) {
  if (!message) return null;

  return (
    <Modal
      title="操作失败"
      subtitle="请根据提示检查当前输入、工作区或导入文件。"
      size="sm"
      onClose={onClose}
      actions={
        <button className="primary-button" onClick={onClose} type="button">
          知道了
        </button>
      }
    >
      <div className="error-modal-copy">{message}</div>
    </Modal>
  );
}

export function ParameterDialog({
  open,
  groups,
  activeGroupId,
  onActiveGroupChange,
  onGroupsChange,
  onClose,
  onReset,
  onSave,
}) {
  if (!open) return null;

  function updateValue(groupId, rowIndex, columnKey, value) {
    onGroupsChange((current) =>
      current.map((group) =>
        group.id !== groupId
          ? group
          : {
              ...group,
              rows: group.rows.map((row, index) =>
                index === rowIndex ? { ...row, [columnKey]: value } : row,
              ),
            },
      ),
    );
  }

  const activeGroup = groups.find((group) => group.id === activeGroupId);
  return (
    <Modal
      title="参数设置"
      subtitle="四组模板参数仍然写回原有数据表，但编辑方式已经统一。"
      size="xl"
      onClose={onClose}
      actions={
        <>
          <button className="ghost-button" onClick={onReset} type="button">
            恢复默认
          </button>
          <button className="primary-button" onClick={onSave} type="button">
            保存参数
          </button>
        </>
      }
    >
      <div className="tab-strip">
        {groups.map((group) => (
          <button
            key={group.id}
            className={activeGroupId === group.id ? "tab-chip active" : "tab-chip"}
            onClick={() => onActiveGroupChange(group.id)}
            type="button"
          >
            {group.title}
          </button>
        ))}
      </div>
      {activeGroup ? (
        <div className="editable-grid">
          <table className="editor-table parameter-editor-table">
            <thead>
              <tr>
                <th>符号</th>
                <th>参数名称</th>
                <th>单位</th>
                {PARAMETER_COLUMNS.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {activeGroup.rows.map((row, rowIndex) => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td>{row.label}</td>
                  <td className="parameter-unit">{row.unit || "—"}</td>
                  {PARAMETER_COLUMNS.map((column) => (
                    <td key={column.key}>
                      <input
                        className="table-input"
                        type="number"
                        step="any"
                        value={row[column.key]}
                        onChange={(event) =>
                          updateValue(activeGroup.id, rowIndex, column.key, event.target.value)
                        }
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Modal>
  );
}

export function ConcentrationDialog({ open, items, onItemsChange, onClose, onSave }) {
  if (!open) return null;

  function updateValue(index, columnKey, value) {
    onItemsChange((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [columnKey]: value } : item,
      ),
    );
  }

  return (
    <Modal
      title="污染物浓度设置"
      subtitle="土壤浓度使用 mg/kg，地下水及地下水保护浓度使用 mg/L。"
      size="xl"
      onClose={onClose}
      actions={
        <button className="primary-button" onClick={onSave} type="button">
          保存浓度
        </button>
      }
    >
      <div className="editable-grid">
        <table className="editor-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>污染物编号</th>
              <th>污染物名称</th>
              <th>污染物英文名</th>
              {CONCENTRATION_COLUMNS.map((column) => (
                <th key={column.key}>{`${column.label}（${column.unit}）`}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.workspace_number}>
                <td>{item.workspace_number}</td>
                <td>{item.pollutant_id}</td>
                <td>{item.name}</td>
                <td>{item.english_name}</td>
                {CONCENTRATION_COLUMNS.map((column) => (
                  <td key={column.key}>
                    <input
                      className="table-input"
                      type="number"
                      step="any"
                      aria-label={`${column.label}，单位 ${column.unit}`}
                      value={item[column.key]}
                      onChange={(event) => updateValue(index, column.key, event.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  );
}

export function ResultDialog({ open, tables, activeKey, onActiveKeyChange, onClose, onExport }) {
  if (!open) return null;
  const activeTable = tables.find((table) => table.key === activeKey) || tables[0];

  return (
    <Modal
      title="计算结果"
      subtitle="各结果表沿用原有运行逻辑，当前展示的是格式化后的桌面视图。"
      size="xl"
      onClose={onClose}
      actions={
        <>
          <button className="ghost-button" onClick={onExport} type="button">
            导出 Excel
          </button>
          <button className="primary-button" onClick={onClose} type="button">
            完成
          </button>
        </>
      }
    >
      <div className="tab-strip">
        {tables.map((table) => (
          <button
            key={table.key}
            className={activeKey === table.key ? "tab-chip active" : "tab-chip"}
            onClick={() => onActiveKeyChange(table.key)}
            type="button"
          >
            {table.title}
          </button>
        ))}
      </div>
      {activeTable ? (
        <DataTable
          key={activeTable.key}
          headers={activeTable.headers}
          rows={activeTable.rows.map((row, index) => ({
            key: `${activeTable.key}-${index}`,
            cells: row,
          }))}
          emptyText="还没有结果数据"
        />
      ) : null}
    </Modal>
  );
}

export function AdminLoginDialog({ open, form, onFormChange, onClose, onLogin }) {
  if (!open) return null;

  function updateField(field, value) {
    onFormChange((current) => ({ ...current, [field]: value }));
  }

  return (
    <Modal
      title="管理员登录"
      subtitle="通过用户表校验后才可进入污染物库维护。"
      size="sm"
      onClose={onClose}
      actions={
        <button className="primary-button" onClick={onLogin} type="button">
          登录
        </button>
      }
    >
      <div className="form-grid single">
        <label>
          <span>用户名</span>
          <input
            className="text-input"
            value={form.username}
            onChange={(event) => updateField("username", event.target.value)}
          />
        </label>
        <label>
          <span>密码</span>
          <input
            className="text-input"
            type="password"
            value={form.password}
            onChange={(event) => updateField("password", event.target.value)}
          />
        </label>
      </div>
    </Modal>
  );
}

export function AdminPanelDialog({
  open,
  username,
  keyword,
  rows,
  selectedId,
  pollutantForm,
  passwordForm,
  onKeywordChange,
  onSelectedIdChange,
  onPollutantFormChange,
  onPasswordFormChange,
  onClear,
  onSearch,
  onCreate,
  onUpdate,
  onDelete,
  onPasswordUpdate,
  onClose,
}) {
  if (!open) return null;

  function updatePasswordField(field, value) {
    onPasswordFormChange((current) => ({ ...current, [field]: value }));
  }

  return (
    <Modal
      title="污染物数据库管理"
      subtitle={`当前管理员：${username || "未登录"}`}
      size="xl"
      onClose={onClose}
      actions={
        <>
          <button className="ghost-button" onClick={onClear} type="button">
            清空表单
          </button>
          <button className="ghost-button" onClick={onCreate} type="button">
            新增
          </button>
          <button className="ghost-button" onClick={onUpdate} type="button">
            更新
          </button>
          <button className="ghost-button danger" onClick={onDelete} type="button">
            删除
          </button>
        </>
      }
    >
      <div className="admin-layout">
        <section className="panel-subcard">
          <div className="toolbar">
            <input
              className="text-input"
              placeholder="按污染物名称或英文名搜索"
              value={keyword}
              onChange={(event) => onKeywordChange(event.target.value)}
            />
            <button className="secondary-button" onClick={onSearch} type="button">
              查询
            </button>
          </div>
          <DataTable
            headers={CATALOG_HEADERS}
            rows={rows}
            selectedKey={selectedId}
            onSelect={onSelectedIdChange}
            emptyText="没有匹配的污染物"
          />
        </section>
        <section className="panel-subcard">
          <div className="form-grid">
            {POLLUTANT_FORM_FIELDS.map((field) => (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  className="text-input"
                  type={field.key === "name" || field.key === "english_name" ? "text" : "number"}
                  step="any"
                  value={pollutantForm[field.key]}
                  onChange={(event) =>
                    onPollutantFormChange((current) => ({
                      ...current,
                      [field.key]: event.target.value,
                    }))
                  }
                />
              </label>
            ))}
          </div>
          <div className="password-card">
            <h3>修改密码</h3>
            <div className="form-grid single">
              <label>
                <span>原密码</span>
                <input
                  className="text-input"
                  type="password"
                  value={passwordForm.old_password}
                  onChange={(event) => updatePasswordField("old_password", event.target.value)}
                />
              </label>
              <label>
                <span>新密码</span>
                <input
                  className="text-input"
                  type="password"
                  value={passwordForm.new_password}
                  onChange={(event) => updatePasswordField("new_password", event.target.value)}
                />
              </label>
              <label>
                <span>确认新密码</span>
                <input
                  className="text-input"
                  type="password"
                  value={passwordForm.confirm_password}
                  onChange={(event) => updatePasswordField("confirm_password", event.target.value)}
                />
              </label>
            </div>
            <button className="primary-button" onClick={onPasswordUpdate} type="button">
              保存新密码
            </button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
