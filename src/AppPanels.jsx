import { DataTable, MetricCard } from "./components";
import { CATALOG_PICKER_HEADERS, PATHWAYS, WORKSPACE_HEADERS } from "./constants";
import { countSelectedPathways } from "./appHelpers";

export function SplashScreen() {
  return (
    <div className="splash-screen">
      <div className="splash-card">
        <span>Risk Studio</span>
        <h1>正在启动本地桌面工作台</h1>
        <p>界面和 Python 计算服务正在建立连接，这一步通常只需要几秒。</p>
      </div>
    </div>
  );
}

export function ProjectStartScreen({
  version,
  busy,
  createOpen,
  projectName,
  projectPath,
  onOpenProject,
  onCreateProject,
  onProjectNameChange,
  onChooseProjectPath,
  onCancelCreate,
  onConfirmCreate,
}) {
  return (
    <div className="project-start-screen">
      <div className="project-start-glow project-start-glow-one" />
      <div className="project-start-glow project-start-glow-two" />
      <section className="project-start-card">
        <div className="project-start-brand">
          <span>Risk Studio</span>
          <small>v{version}</small>
        </div>
        <h1>污染场地风险评估系统</h1>
        <p className="project-start-lead">选择一个开始方式，进入你的风险评估工作区。</p>
        <div className="project-start-options">
          <button
            className="project-option project-option-primary"
            disabled={busy}
            onClick={onOpenProject}
            type="button"
          >
            <span className="project-option-icon">↗</span>
            <span>
              <strong>打开已有项目</strong>
              <small>选择 .riskproj 项目文件，继续之前的评估工作</small>
            </span>
          </button>
          <button
            className="project-option"
            disabled={busy}
            onClick={onCreateProject}
            type="button"
          >
            <span className="project-option-icon">＋</span>
            <span>
              <strong>新建项目</strong>
              <small>创建一个空白工作区，污染物库和参数设置会保留</small>
            </span>
          </button>
        </div>
        {busy ? <p className="project-start-status">正在准备项目，请稍候...</p> : null}
        <p className="project-start-tip">选择已有项目文件即可恢复之前的评估工作。</p>
      </section>
      {createOpen ? (
        <div className="project-create-overlay" role="presentation">
          <section
            aria-labelledby="project-create-title"
            aria-modal="true"
            className="project-create-dialog"
            role="dialog"
          >
            <div className="project-create-heading">
              <div>
                <span className="eyebrow">新建项目</span>
                <h2 id="project-create-title">创建一个风险评估项目</h2>
              </div>
              <button
                aria-label="取消新建项目"
                className="icon-button"
                onClick={onCancelCreate}
                type="button"
              >
                ×
              </button>
            </div>
            <label className="field-label" htmlFor="new-project-name">
              项目名称
            </label>
            <input
              autoFocus
              id="new-project-name"
              maxLength={120}
              onChange={(event) => onProjectNameChange(event.target.value)}
              placeholder="例如：某地块风险评估"
              value={projectName}
            />
            <label className="field-label" htmlFor="new-project-path">
              项目文件保存位置
            </label>
            <div className="project-path-picker">
              <input
                aria-readonly="true"
                id="new-project-path"
                placeholder="请点击右侧按钮选择保存位置"
                readOnly
                value={projectPath}
              />
              <button
                className="ghost-button"
                disabled={!projectName.trim() || busy}
                onClick={onChooseProjectPath}
                type="button"
              >
                选择位置
              </button>
            </div>
            <p className="project-create-hint">
              项目名称、工作区污染物、浓度、标准、暴露途径和参数都会自动保存到该文件。
            </p>
            <div className="project-create-actions">
              <button className="ghost-button" onClick={onCancelCreate} type="button">
                取消
              </button>
              <button
                className="primary-button"
                disabled={busy || !projectName.trim() || !projectPath}
                onClick={onConfirmCreate}
                type="button"
              >
                {busy ? "创建中..." : "创建项目"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

export function AppHeader({
  version,
  projectName,
  projectSaveState,
  checkingUpdate,
  onCheckUpdate,
  onOpenParameters,
  onOpenAdmin,
  onOpenResults,
  onOpenProject,
  onOpenLogs,
  onSaveProject,
}) {
  return (
    <header className="hero-panel">
      <div className="hero-title-row">
        <div>
          <h1>污染场地风险评估系统</h1>
          <span className="project-name-label">
            项目：{projectName || "未命名项目"} ·{" "}
            {projectSaveState === "saving"
              ? "自动保存中"
              : projectSaveState === "error"
                ? "自动保存失败"
                : "已自动保存"}
          </span>
        </div>
        <span className="version-badge" title="当前软件版本">
          v{version}
        </span>
      </div>
      <div className="hero-actions">
        <button
          className="ghost-button"
          disabled={checkingUpdate}
          onClick={onCheckUpdate}
          type="button"
        >
          {checkingUpdate ? "检查中..." : "检查更新"}
        </button>
        <button className="ghost-button" onClick={onOpenParameters} type="button">
          参数设置
        </button>
        <button className="ghost-button" onClick={onOpenAdmin} type="button">
          污染物数据库
        </button>
        <button className="ghost-button" onClick={onOpenProject} type="button">
          打开项目
        </button>
        <button className="ghost-button" onClick={onOpenLogs} type="button">
          操作日志
        </button>
        <button className="ghost-button" onClick={onSaveProject} type="button">
          保存项目
        </button>
        <button className="primary-button" onClick={onOpenResults} type="button">
          查看结果
        </button>
      </div>
    </header>
  );
}

export function MetricsPanel({ workspaceCount, catalogCount, pathways, health }) {
  return (
    <section className="metrics-grid">
      <MetricCard
        label="工作区污染物"
        value={workspaceCount}
        hint={workspaceCount ? "已接入浓度与结果联动" : "从左侧目录添加后开始计算"}
        tone="teal"
      />
      <MetricCard
        label="污染物总量"
        value={catalogCount}
        hint="内置数据库已嵌入本地运行目录"
        tone="amber"
      />
      <MetricCard
        label="暴露途径"
        value={countSelectedPathways(pathways)}
        hint="至少启用一个途径才会执行计算"
        tone="slate"
      />
      <MetricCard
        label="运行数据库"
        value={health?.status === "ok" ? "在线" : "未连接"}
        hint={health?.database || "等待初始化"}
        tone="teal"
      />
    </section>
  );
}

export function SiteControls({
  areaType,
  standard,
  pathways,
  allPathwaysSelected,
  onAreaTypeChange,
  onStandardChange,
  onPathwaysChange,
  onSelectAllPathways,
}) {
  return (
    <section className="control-stack">
      <div className="control-panel control-panel-top">
        <div className="control-card">
          <span>用地类型</span>
          <div className="segmented">
            <button
              className={areaType === "I" ? "segment active" : "segment"}
              onClick={() => onAreaTypeChange("I")}
              type="button"
            >
              第一类用地
            </button>
            <button
              className={areaType === "II" ? "segment active" : "segment"}
              onClick={() => onAreaTypeChange("II")}
              type="button"
            >
              第二类用地
            </button>
          </div>
        </div>
        <div className="control-card">
          <span>适用标准</span>
          <div className="segmented">
            <button
              className={standard === "G" ? "segment active" : "segment"}
              onClick={() => onStandardChange("G")}
              type="button"
            >
              国家标准
            </button>
            <button
              className={standard === "Z" ? "segment active" : "segment"}
              onClick={() => onStandardChange("Z")}
              type="button"
            >
              浙江标准
            </button>
          </div>
        </div>
      </div>

      <div className="control-panel control-panel-bottom">
        <div className="control-card control-card-full">
          <div className="control-card-head">
            <span>暴露途径</span>
            <button
              className="ghost-button compact-button"
              disabled={allPathwaysSelected}
              onClick={onSelectAllPathways}
              type="button"
            >
              {allPathwaysSelected ? "已全选" : "全选"}
            </button>
          </div>
          <div className="chip-grid">
            {PATHWAYS.map((item) => (
              <button
                key={item.key}
                className={pathways[item.key] ? "chip active" : "chip"}
                onClick={() =>
                  onPathwaysChange((current) => ({
                    ...current,
                    [item.key]: !current[item.key],
                  }))
                }
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function CatalogPanel({
  inputRef,
  keyword,
  hint,
  pickerOpen,
  suggestions,
  activeIndex,
  selectedItem,
  selectedId,
  selectionLabel,
  rows,
  emptyText,
  onKeywordChange,
  onPickerOpenChange,
  onActiveIndexChange,
  onInputKeyDown,
  onAddSuggestion,
  onSelectedIdChange,
  onRefresh,
  onAdd,
}) {
  return (
    <section className="panel-card">
      <div className="panel-head">
        <div>
          <h2>污染物目录</h2>
          <p>{hint}</p>
        </div>
        <button className="ghost-button" onClick={onRefresh} type="button">
          刷新
        </button>
      </div>
      <div className="catalog-search-stack">
        <div className="toolbar">
          <div className="search-combobox">
            <input
              ref={inputRef}
              className="text-input"
              placeholder="搜索污染物中文名或英文名"
              value={keyword}
              onChange={(event) => onKeywordChange(event.target.value)}
              onFocus={() => onPickerOpenChange(Boolean(keyword.trim()))}
              onBlur={() => window.setTimeout(() => onPickerOpenChange(false), 120)}
              onKeyDown={onInputKeyDown}
            />
            {pickerOpen && keyword.trim() ? (
              <div className="suggestion-popover">
                {suggestions.length ? (
                  suggestions.map((item, index) => (
                    <button
                      key={item.id}
                      className={`suggestion-item ${activeIndex === index ? "is-active" : ""}`}
                      onMouseDown={(event) => {
                        // Mouse down fires before the input blur closes the popover.
                        event.preventDefault();
                        void onAddSuggestion(item);
                      }}
                      onMouseEnter={() => onActiveIndexChange(index)}
                      type="button"
                    >
                      <span className="suggestion-title">{item.name}</span>
                      <span className="suggestion-meta">
                        <strong>#{item.id}</strong>
                        <span>{item.english_name || "暂无英文名"}</span>
                      </span>
                    </button>
                  ))
                ) : (
                  <div className="suggestion-empty">没有匹配的污染物</div>
                )}
              </div>
            ) : null}
          </div>
          <button className="secondary-button" onClick={onRefresh} type="button">
            查询
          </button>
          <button className="primary-button" onClick={onAdd} type="button">
            加入工作区
          </button>
        </div>
        <div className="catalog-selection-card">
          <div className="catalog-selection-header">
            <strong>当前已选</strong>
            <span>{selectedItem ? `编号 #${selectedItem.id}` : "未选择"}</span>
          </div>
          <div className="catalog-selection-main">{selectionLabel}</div>
          <div className="catalog-selection-sub">
            {selectedItem
              ? "点击按钮或回车即可加入工作区；加入后会自动清空搜索框，并把光标留在这里方便继续录入。"
              : "直接在输入框里键入关键词，点击建议项可直接加入；也支持上下选择和回车加入。"}
          </div>
        </div>
      </div>
      <div className="catalog-results-head">
        <strong>快速匹配结果</strong>
        <span>只显示编号、名称、英文名这三列</span>
      </div>
      <DataTable
        headers={CATALOG_PICKER_HEADERS}
        rows={rows}
        selectedKey={selectedId}
        onSelect={onSelectedIdChange}
        emptyText={emptyText}
      />
    </section>
  );
}

export function WorkspacePanel({
  importInputRef,
  items,
  rows,
  selectedNumber,
  highlightedNumber,
  onSelectedNumberChange,
  onImportFile,
  onRefresh,
  onSaveTemplate,
  onOpenImport,
  onEditConcentrations,
  onRemove,
  onReset,
}) {
  return (
    <section className="panel-card">
      <div className="panel-head">
        <div>
          <h2>工作区污染物</h2>
          <p>
            {items.length
              ? `当前已选 ${items.length} 个污染物，可继续编辑浓度、导入文件或直接计算。`
              : "工作区还没有污染物。先从左侧目录加入，或直接导入一份表格文件。"}
          </p>
        </div>
        <button className="ghost-button" onClick={onRefresh} type="button">
          同步
        </button>
      </div>
      <input
        ref={importInputRef}
        accept=".xlsx,.xls,.csv,.txt,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/plain"
        hidden
        type="file"
        onChange={(event) => void onImportFile(event)}
      />
      <DataTable
        headers={WORKSPACE_HEADERS}
        rows={rows}
        selectedKey={selectedNumber}
        emphasizedKey={highlightedNumber}
        autoScrollKey={highlightedNumber}
        onSelect={onSelectedNumberChange}
        emptyText="工作区为空"
      />
      <p className="panel-note">
        支持导入 <strong>.xlsx / .xls / .csv / .txt</strong>；至少填写“编号 / 污染物名称 / 英文名”
        其中之一；土壤浓度单位为 <strong>mg/kg</strong>，地下水浓度单位为 <strong>mg/L</strong>；
        浓度列留空按 0 处理，模板示例行即使保留也会自动忽略。
      </p>
      <div className="panel-footer">
        <button className="ghost-button" onClick={onSaveTemplate} type="button">
          保存模板
        </button>
        <button className="secondary-button" onClick={onOpenImport} type="button">
          文件导入
        </button>
        <button className="ghost-button" onClick={onEditConcentrations} type="button">
          编辑浓度
        </button>
        <button className="ghost-button" onClick={onRemove} type="button">
          移除选中
        </button>
        <button className="ghost-button danger" onClick={onReset} type="button">
          重置工作区
        </button>
      </div>
    </section>
  );
}

export function ActionDeck({ standard, areaType, pathways, onOpenResults, onCalculate }) {
  return (
    <footer className="action-deck">
      <div>
        <strong>当前选择</strong>
        <p>
          {standard === "G" ? "国家标准" : "浙江标准"} ·
          {areaType === "I" ? " 第一类用地" : " 第二类用地"} · 已勾选{" "}
          {countSelectedPathways(pathways)} 条暴露途径
        </p>
      </div>
      <div className="action-buttons">
        <button className="ghost-button" onClick={onOpenResults} type="button">
          查看现有结果
        </button>
        <button className="primary-button large" onClick={onCalculate} type="button">
          开始计算
        </button>
      </div>
    </footer>
  );
}
