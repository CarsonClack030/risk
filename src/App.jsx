import { startTransition, useDeferredValue, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Modal, MetricCard, DataTable } from "./components";
import {
  CATALOG_HEADERS,
  CATALOG_PICKER_HEADERS,
  PARAMETER_COLUMNS,
  PATHWAYS,
  POLLUTANT_FORM_FIELDS,
  WORKSPACE_HEADERS,
} from "./constants";

// App 是整个前端的主控组件。
// 这个文件同时承担了几件事：
// 1. 页面首次启动时，向后端拉取工作区、参数和结果。
// 2. 维护目录搜索、工作区、参数弹窗、结果弹窗、管理员弹窗等状态。
// 3. 在用户点击按钮后，调用 api.js 中封装好的后端接口。
//
// 也就是说，如果把前端比作一个办公室：
// - constants.js 提供“表格表头和静态配置”
// - api.js 提供“对外联络电话”
// - components.jsx 提供“可复用家具”
// - App.jsx 则像“总协调人”，负责让所有环节按顺序运转。
const CATALOG_DISPLAY_LIMIT = 20;

// 深拷贝工具：
// 参数弹窗、浓度弹窗里编辑的是“草稿数据”，不能直接改原始状态，
// 否则用户一边输入、一边就把正式数据改掉了。
// 因此这里统一做一次深拷贝，保证“编辑”和“保存”这两个动作彼此独立。
function cloneData(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

// 管理员面板里新增污染物时，需要准备一份空白表单。
// 这里把默认值集中定义，后面“清空表单”和“新建表单初始化”都直接复用。
function emptyPollutantForm() {
  return {
    name: "",
    english_name: "",
    henry: 0,
    da: 0,
    dw: 0,
    koc: 0,
    solubility: 0,
    sfo: 0,
    iur: 0,
    rfdo: 0,
    rfc: 0,
    absgi: 0,
    absd: 0,
    saf: 1,
    kp: 0,
  };
}

// 统计当前启用了多少条暴露途径。
// 首页指标卡和底部汇总文案都会用到这个数字。
function summarizePathways(pathways) {
  return PATHWAYS.filter((item) => pathways[item.key]).length;
}

// DataTable 组件期望收到统一结构的 rows，
// 因此这里用一个轻量工具把业务对象转成表格行。
function toRows(items, mapper) {
  return items.map(mapper);
}

function App() {
  // ------------------------
  // 启动与全局反馈状态
  // ------------------------
  // booting: 首次启动遮罩是否显示
  // error:  顶部错误横幅
  // notice: 顶部成功/失败提示
  // health: 后端健康检查及数据库统计
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [health, setHealth] = useState(null);

  // ------------------------
  // 目录搜索相关状态
  // ------------------------
  // catalogKeyword: 用户当前输入的关键词
  // catalogItems:   当前搜索命中的污染物列表
  // selectedCatalogId: 当前在目录结果里选中的污染物 ID
  // catalogHasSearched / catalogMatchCount: 用来驱动提示文案
  // catalogPickerOpen / catalogActiveIndex: 搜索建议下拉的开关和键盘高亮项
  const [catalogKeyword, setCatalogKeyword] = useState("");
  const [catalogItems, setCatalogItems] = useState([]);
  const [selectedCatalogId, setSelectedCatalogId] = useState(null);
  const [catalogHasSearched, setCatalogHasSearched] = useState(false);
  const [catalogMatchCount, setCatalogMatchCount] = useState(0);
  const [catalogPickerOpen, setCatalogPickerOpen] = useState(false);
  const [catalogActiveIndex, setCatalogActiveIndex] = useState(-1);

  // ------------------------
  // 工作区状态
  // ------------------------
  // workspaceItems: 当前已加入工作区的污染物
  // selectedWorkspaceNumber: 当前选中的工作区行号
  // highlightedWorkspaceNumber: 最近一次新增/强调的行号，用于高亮动画
  const [workspaceItems, setWorkspaceItems] = useState([]);
  const [selectedWorkspaceNumber, setSelectedWorkspaceNumber] = useState(null);
  const [highlightedWorkspaceNumber, setHighlightedWorkspaceNumber] = useState(null);

  // ------------------------
  // 计算条件状态
  // ------------------------
  // standard: G=国家标准，Z=浙江标准
  // areaType: I/II 两类用地
  // pathways: 暴露途径勾选矩阵
  const [standard, setStandard] = useState("G");
  const [areaType, setAreaType] = useState("I");
  const [pathways, setPathways] = useState(
    Object.fromEntries(PATHWAYS.map((item) => [item.key, false])),
  );

  // ------------------------
  // 参数弹窗状态
  // ------------------------
  // parameterGroups: 正式参数
  // parameterDraft:  弹窗中的编辑草稿
  // activeParameterGroupId: 当前正在编辑哪一组参数
  const [parameterGroups, setParameterGroups] = useState([]);
  const [parameterDraft, setParameterDraft] = useState([]);
  const [parameterModalOpen, setParameterModalOpen] = useState(false);
  const [activeParameterGroupId, setActiveParameterGroupId] = useState(1);

  // 浓度弹窗草稿状态。
  const [concentrationDraft, setConcentrationDraft] = useState([]);
  const [concentrationModalOpen, setConcentrationModalOpen] = useState(false);

  // 结果弹窗状态。
  const [results, setResults] = useState([]);
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [activeResultKey, setActiveResultKey] = useState("db_exposure_ca");

  // 管理员面板状态。
  const [adminLoginOpen, setAdminLoginOpen] = useState(false);
  const [adminPanelOpen, setAdminPanelOpen] = useState(false);
  const [adminUser, setAdminUser] = useState("");
  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [adminKeyword, setAdminKeyword] = useState("");
  const [adminItems, setAdminItems] = useState([]);
  const [selectedAdminId, setSelectedAdminId] = useState(null);
  const [adminForm, setAdminForm] = useState(emptyPollutantForm());
  const [passwordForm, setPasswordForm] = useState({
    old_password: "",
    new_password: "",
    confirm_password: "",
  });

  // 用于在成功加入工作区后，把光标重新送回搜索框，
  // 这样用户可以连续录入多个污染物。
  const catalogInputRef = useRef(null);

  // useDeferredValue 可以把“用户输入”和“真正触发查询”稍微错开。
  // 好处是：用户快速敲字时，界面不会因为每个字符都立即请求后端而发抖。
  const deferredCatalogKeyword = useDeferredValue(catalogKeyword);
  const deferredAdminKeyword = useDeferredValue(adminKeyword);

  // 下面这些是“派生数据”，它们不是独立状态，
  // 而是从已有状态中计算出来，避免重复存储。
  const selectedCatalogItem = catalogItems.find((item) => item.id === selectedCatalogId) || null;
  const selectedWorkspaceItem =
    workspaceItems.find((item) => item.workspace_number === selectedWorkspaceNumber) || null;
  const selectedAdminItem = adminItems.find((item) => item.id === selectedAdminId) || null;

  // 顶部 notice 横幅显示一段时间后自动消失。
  useEffect(() => {
    if (!notice) {
      return undefined;
    }
    const timer = window.setTimeout(() => setNotice(null), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // 启动流程：
  // 1. 先轮询 health，等待 Python 后端真正起来。
  // 2. 再并行拉取工作区、参数、结果表。
  // 3. 最后一次性写入前端状态，减少首屏抖动。
  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const alive = await waitForHealth();
        if (cancelled) {
          return;
        }
        setHealth(alive);
        const [workspace, parameters, resultTables] = await Promise.all([
          api.listWorkspace(),
          api.listParameters(),
          api.listResults(),
        ]);
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setWorkspaceItems(workspace.items);
          setParameterGroups(parameters.groups);
          setResults(resultTables.tables);
        });
        setActiveParameterGroupId(parameters.groups[0]?.id || 1);
        setActiveResultKey(resultTables.tables[0]?.key || "db_exposure_ca");
        setBooting(false);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message);
          setBooting(false);
        }
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  // 目录关键词变化后刷新污染物目录。
  useEffect(() => {
    if (booting) {
      return;
    }
    refreshCatalog(deferredCatalogKeyword);
  }, [booting, deferredCatalogKeyword]);

  // 管理员面板打开后，管理员搜索框的关键词变化也会触发查询。
  useEffect(() => {
    if (!adminPanelOpen) {
      return;
    }
    refreshAdminCatalog(deferredAdminKeyword);
  }, [adminPanelOpen, deferredAdminKeyword]);

  // 这个 effect 专门处理搜索建议的“默认高亮项”。
  // 当建议框打开时：
  // - 如果之前已经有选中项，就尽量把它对应的建议高亮起来；
  // - 如果没有，就默认高亮第一项，方便用户直接回车。
  useEffect(() => {
    const suggestions = catalogItems.slice(0, 8);
    if (!catalogPickerOpen || suggestions.length === 0) {
      setCatalogActiveIndex(-1);
      return;
    }
    const selectedIndex = suggestions.findIndex((item) => item.id === selectedCatalogId);
    setCatalogActiveIndex((current) => {
      if (current >= 0 && current < suggestions.length) {
        return current;
      }
      return selectedIndex >= 0 ? selectedIndex : 0;
    });
  }, [catalogItems, catalogPickerOpen, selectedCatalogId]);

  // 当管理员在列表中选中某个污染物时，
  // 右侧表单自动带出该污染物的当前属性，进入“编辑模式”。
  useEffect(() => {
    if (!selectedAdminItem) {
      return;
    }
    setAdminForm({
      name: selectedAdminItem.name,
      english_name: selectedAdminItem.english_name,
      henry: selectedAdminItem.henry,
      da: selectedAdminItem.da,
      dw: selectedAdminItem.dw,
      koc: selectedAdminItem.koc,
      solubility: selectedAdminItem.solubility,
      sfo: selectedAdminItem.sfo,
      iur: selectedAdminItem.iur,
      rfdo: selectedAdminItem.rfdo,
      rfc: selectedAdminItem.rfc,
      absgi: selectedAdminItem.absgi,
      absd: selectedAdminItem.absd,
      saf: selectedAdminItem.saf,
      kp: selectedAdminItem.kp,
    });
  }, [selectedAdminItem]);

  // 工作区新增高亮只保留短短一段时间，
  // 避免长期高亮影响表格阅读。
  useEffect(() => {
    if (highlightedWorkspaceNumber === null) {
      return undefined;
    }
    const timer = window.setTimeout(() => setHighlightedWorkspaceNumber(null), 1800);
    return () => window.clearTimeout(timer);
  }, [highlightedWorkspaceNumber]);

  // 启动初期后端可能还没监听端口，因此这里采用“带重试的健康检查”。
  // Tauri 前端通常启动比 Python sidecar 稍快，这个等待过程很常见。
  async function waitForHealth() {
    let lastError = new Error("后端尚未启动");
    for (let index = 0; index < 24; index += 1) {
      try {
        return await api.health();
      } catch (healthError) {
        lastError = healthError;
        await new Promise((resolve) => window.setTimeout(resolve, 450));
      }
    }
    throw lastError;
  }

  // 统一弹横幅通知。
  function flash(kind, text) {
    setNotice({ kind, text });
  }

  // 让搜索框重新拿到焦点，用于连续录入。
  function focusCatalogInput() {
    window.setTimeout(() => {
      catalogInputRef.current?.focus();
    }, 0);
  }

  // 重置目录搜索态。
  // 这里不仅清空关键词，也会把建议框、高亮项、已选污染物一起复位。
  function resetCatalogSearch({ focus = false } = {}) {
    startTransition(() => {
      setCatalogItems([]);
    });
    setCatalogKeyword("");
    setCatalogHasSearched(false);
    setCatalogMatchCount(0);
    setSelectedCatalogId(null);
    setCatalogPickerOpen(false);
    setCatalogActiveIndex(-1);
    if (focus) {
      focusCatalogInput();
    }
  }

  // 查询污染物目录。
  // 这里刻意要求“有关键词才查询”，避免把近千条污染物默认全铺开。
  async function refreshCatalog(keyword = "") {
    const trimmed = keyword.trim();
    if (!trimmed) {
      resetCatalogSearch();
      return;
    }
    try {
      const payload = await api.listCatalog(trimmed);
      startTransition(() => {
        setCatalogItems(payload.items);
      });
      setCatalogHasSearched(true);
      setCatalogMatchCount(payload.total);
      if (!payload.items.some((item) => item.id === selectedCatalogId)) {
        setSelectedCatalogId(null);
      }
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 从后端重新同步工作区，常用于：
  // - 手动点击“同步”
  // - 执行删除/重置后刷新前端状态
  async function refreshWorkspace() {
    const payload = await api.listWorkspace();
    startTransition(() => {
      setWorkspaceItems(payload.items);
    });
    if (!payload.items.some((item) => item.workspace_number === selectedWorkspaceNumber)) {
      setSelectedWorkspaceNumber(null);
    }
    if (!payload.items.some((item) => item.workspace_number === highlightedWorkspaceNumber)) {
      setHighlightedWorkspaceNumber(null);
    }
    setHealth((current) => ({ ...(current || {}), workspace_count: payload.total }));
  }

  // 重新读取结果表。
  // 因为后端的计算结果最终落在数据库结果表中，前端只负责重新显示。
  async function refreshResults() {
    const payload = await api.listResults();
    setResults(payload.tables);
    if (!payload.tables.some((table) => table.key === activeResultKey)) {
      setActiveResultKey(payload.tables[0]?.key || "db_exposure_ca");
    }
  }

  // 管理员污染物库查询。
  async function refreshAdminCatalog(keyword = "") {
    try {
      const payload = await api.listCatalog(keyword);
      startTransition(() => {
        setAdminItems(payload.items);
      });
      if (!payload.items.some((item) => item.id === selectedAdminId)) {
        setSelectedAdminId(null);
      }
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 用户从建议项或表格里点中某个污染物时，
  // 同步“输入框内容 + 选中项 + 建议框状态”。
  function syncCatalogSelection(item) {
    setSelectedCatalogId(item.id);
    setCatalogKeyword(item.name || item.english_name || String(item.id));
    setCatalogPickerOpen(false);
    setCatalogActiveIndex(-1);
  }

  // 把目录中的某个污染物加入工作区。
  // 这是左侧搜索区最核心的动作链：
  // 1. 先向后端插入一条工作区记录；
  // 2. 再用返回的新行号选中并高亮它；
  // 3. 最后清空搜索框，准备连续录入下一条。
  async function addCatalogItemToWorkspace(item) {
    if (!item) {
      flash("error", "请先选择一个污染物");
      return;
    }
    try {
      syncCatalogSelection(item);
      const payload = await api.addWorkspaceItem(item.id);
      setWorkspaceItems(payload.items);
      const addedWorkspaceNumber = payload.added_workspace_number ?? null;
      setSelectedWorkspaceNumber(addedWorkspaceNumber);
      setHighlightedWorkspaceNumber(addedWorkspaceNumber);
      resetCatalogSearch({ focus: true });
      flash("success", `${item.name} 已加入工作区`);
      setHealth((current) => ({ ...(current || {}), workspace_count: payload.total }));
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 按钮版“加入工作区”，底层仍复用统一入口。
  async function handleAddToWorkspace() {
    await addCatalogItemToWorkspace(selectedCatalogItem);
  }

  // 点击表格行时，仅同步选中状态，不直接写工作区。
  function selectCatalogItem(item) {
    syncCatalogSelection(item);
  }

  // 搜索框键盘交互：
  // Esc: 关闭建议
  // ↑/↓: 移动高亮项
  // Enter: 把当前高亮项直接加入工作区
  async function handleCatalogInputKeyDown(event) {
    if (event.key === "Escape") {
      setCatalogPickerOpen(false);
      setCatalogActiveIndex(-1);
      return;
    }

    if (event.key === "ArrowDown") {
      if (!catalogSuggestions.length) {
        return;
      }
      event.preventDefault();
      setCatalogPickerOpen(true);
      setCatalogActiveIndex((current) =>
        current < 0 ? 0 : Math.min(current + 1, catalogSuggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      if (!catalogSuggestions.length) {
        return;
      }
      event.preventDefault();
      setCatalogPickerOpen(true);
      setCatalogActiveIndex((current) =>
        current <= 0 ? 0 : Math.max(current - 1, 0),
      );
      return;
    }

    if (event.key !== "Enter") {
      return;
    }

    if (catalogPickerOpen && catalogKeyword.trim()) {
      if (!catalogSuggestions.length) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      const nextItem = catalogSuggestions[catalogActiveIndex >= 0 ? catalogActiveIndex : 0];
      await addCatalogItemToWorkspace(nextItem);
      return;
    }

    if (selectedCatalogItem) {
      event.preventDefault();
      await addCatalogItemToWorkspace(selectedCatalogItem);
    }
  }

  // 删除当前工作区选中项。
  async function handleRemoveWorkspace() {
    if (!selectedWorkspaceItem) {
      flash("error", "请先在工作区选择一条记录");
      return;
    }
    try {
      const payload = await api.removeWorkspaceItem(selectedWorkspaceItem.workspace_number);
      setWorkspaceItems(payload.items);
      setSelectedWorkspaceNumber(null);
      setHighlightedWorkspaceNumber(null);
      await refreshResults();
      flash("success", "已移除选中的工作区污染物");
      setHealth((current) => ({ ...(current || {}), workspace_count: payload.total }));
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 清空工作区，同时把前端勾选的暴露途径也复位。
  // 这样用户会得到一个真正“从头开始”的空白现场。
  async function handleResetWorkspace() {
    try {
      const payload = await api.resetWorkspace();
      setWorkspaceItems(payload.items);
      setSelectedWorkspaceNumber(null);
      setHighlightedWorkspaceNumber(null);
      setPathways(Object.fromEntries(PATHWAYS.map((item) => [item.key, false])));
      await refreshResults();
      flash("success", "工作区已重置");
      setHealth((current) => ({ ...(current || {}), workspace_count: payload.total }));
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 打开参数弹窗时，正式参数会被复制成草稿。
  function openParameterModal() {
    setParameterDraft(cloneData(parameterGroups));
    setActiveParameterGroupId(parameterGroups[0]?.id || 1);
    setParameterModalOpen(true);
  }

  // 打开浓度弹窗时，把当前工作区浓度复制成可编辑草稿。
  function openConcentrationModal() {
    if (workspaceItems.length === 0) {
      flash("error", "工作区为空，先添加污染物");
      return;
    }
    setConcentrationDraft(
      cloneData(
        workspaceItems.map((item) => ({
          workspace_number: item.workspace_number,
          pollutant_id: item.concentration.pollutant_id,
          name: item.concentration.name,
          english_name: item.concentration.english_name,
          surface_concentration: item.concentration.surface_concentration,
          lower_soil_concentration: item.concentration.lower_soil_concentration,
          groundwater_concentration: item.concentration.groundwater_concentration,
          groundwater_protection_concentration:
            item.concentration.groundwater_protection_concentration,
        })),
      ),
    );
    setConcentrationModalOpen(true);
  }

  // 保存参数到数据库。
  async function handleSaveParameters() {
    try {
      const payload = await api.saveParameters(parameterDraft);
      setParameterGroups(payload.groups);
      setParameterModalOpen(false);
      flash("success", "参数已经更新");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 恢复默认参数，并同时刷新正式参数和草稿。
  async function handleResetParameters() {
    try {
      const payload = await api.resetParameters();
      setParameterDraft(payload.groups);
      setParameterGroups(payload.groups);
      flash("success", "参数已恢复默认值");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 保存浓度草稿。
  async function handleSaveConcentrations() {
    try {
      const payload = await api.updateConcentrations(concentrationDraft);
      setWorkspaceItems(payload.items);
      setConcentrationModalOpen(false);
      flash("success", "污染物浓度已经写入工作区");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 触发核心风险计算。
  // 前端只负责收集“标准/用地/路径”这三个条件，
  // 真正公式计算发生在 Python 后端。
  async function handleCalculate() {
    try {
      const payload = await api.calculate({
        standard,
        area_type: areaType,
        pathways,
      });
      setResults(payload.tables);
      setActiveResultKey(payload.tables[0]?.key || "db_exposure_ca");
      setResultModalOpen(true);
      flash("success", "计算完成，结果已刷新");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 导出结果表为 Excel。
  // 后端返回的是二进制 Blob，前端临时创建一个下载链接来触发保存。
  async function handleExportResults() {
    try {
      const blob = await api.exportResults();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "风险评估结果.xlsx";
      anchor.click();
      URL.revokeObjectURL(url);
      flash("success", "结果文件已生成");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 打开管理员登录框时，默认带上上次登录名，方便重复登录。
  function handleOpenAdmin() {
    setLoginForm({ username: adminUser || "", password: "" });
    setAdminLoginOpen(true);
  }

  // 管理员登录成功后，立即打开污染物库管理面板。
  async function handleAdminLogin() {
    try {
      const payload = await api.login(loginForm.username, loginForm.password);
      if (!payload.success) {
        flash("error", "用户名或密码错误");
        return;
      }
      setAdminUser(payload.username);
      setAdminLoginOpen(false);
      setAdminPanelOpen(true);
      await refreshAdminCatalog("");
      flash("success", `管理员 ${payload.username} 已登录`);
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 管理员保存污染物。
  // mode=create 表示新增，mode=update 表示更新当前选中项。
  async function handleAdminSave(mode) {
    try {
      if (mode === "create") {
        await api.addPollutant({ ...adminForm, keyword: adminKeyword });
        flash("success", "污染物已新增");
      } else {
        if (!selectedAdminItem) {
          flash("error", "请先选择一条污染物记录");
          return;
        }
        await api.updatePollutant(selectedAdminItem.id, { ...adminForm, keyword: adminKeyword });
        flash("success", "污染物已更新");
      }
      setAdminForm(emptyPollutantForm());
      setSelectedAdminId(null);
      await Promise.all([refreshAdminCatalog(adminKeyword), refreshCatalog(catalogKeyword)]);
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 删除管理员当前选中的污染物。
  async function handleAdminDelete() {
    if (!selectedAdminItem) {
      flash("error", "请先选择要删除的污染物");
      return;
    }
    if (!window.confirm(`确定删除 ${selectedAdminItem.name} 吗？`)) {
      return;
    }
    try {
      await api.deletePollutant(selectedAdminItem.id, adminKeyword);
      setAdminForm(emptyPollutantForm());
      setSelectedAdminId(null);
      await Promise.all([refreshAdminCatalog(adminKeyword), refreshCatalog(catalogKeyword)]);
      flash("success", "污染物已删除");
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 管理员修改密码。
  async function handlePasswordUpdate() {
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      flash("error", "两次新密码输入不一致");
      return;
    }
    try {
      const payload = await api.updatePassword({
        username: adminUser,
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password,
      });
      if (payload.success) {
        setPasswordForm({ old_password: "", new_password: "", confirm_password: "" });
        flash("success", "密码修改成功");
      }
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // ------------------------
  // 下面开始构造表格显示数据
  // ------------------------
  const catalogRows = toRows(catalogItems, (item) => ({
    key: item.id,
    cells: [item.id, item.name, item.english_name],
  }));
  const visibleCatalogRows = catalogRows.slice(0, CATALOG_DISPLAY_LIMIT);
  const catalogSuggestions = catalogItems.slice(0, 8);
  const showingLimitedCatalog = catalogMatchCount > CATALOG_DISPLAY_LIMIT;
  const catalogHint = !catalogKeyword.trim()
    ? "输入中文名或英文名后再查询，这里不会默认列出全部污染物。"
    : showingLimitedCatalog
      ? `共匹配 ${catalogMatchCount} 条，当前仅显示前 ${CATALOG_DISPLAY_LIMIT} 条，请继续缩小关键词。`
      : catalogHasSearched
        ? `当前匹配 ${catalogMatchCount} 条污染物。`
        : "支持按中文名或英文名检索，再加入当前工作区。";
  const catalogEmptyText = !catalogKeyword.trim()
    ? "请输入关键词后再查询污染物"
    : "没有匹配的污染物";

  const catalogSelectionLabel = selectedCatalogItem
    ? `${selectedCatalogItem.name} / ${selectedCatalogItem.english_name || "暂无英文名"}`
    : "还没有选中污染物";

  const workspaceRows = toRows(workspaceItems, (item) => ({
    key: item.workspace_number,
    cells: [
      item.workspace_number,
      item.pollutant.id,
      item.pollutant.name,
      item.pollutant.english_name,
      item.concentration.surface_concentration,
      item.concentration.lower_soil_concentration,
      item.concentration.groundwater_concentration,
      item.concentration.groundwater_protection_concentration,
    ],
  }));

  const adminRows = toRows(adminItems, (item) => ({
    key: item.id,
    cells: [
      item.id,
      item.name,
      item.english_name,
      item.henry,
      item.da,
      item.dw,
      item.koc,
      item.solubility,
      item.sfo,
      item.iur,
      item.rfdo,
      item.rfc,
      item.absgi,
      item.absd,
      item.saf,
      item.kp,
    ],
  }));

  const activeResult = results.find((table) => table.key === activeResultKey) || results[0];

  // 启动遮罩：只在最开始健康检查和初次数据加载期间显示。
  if (booting) {
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

  return (
    <div className="app-shell">
      <div className="bg-orb orb-one" />
      <div className="bg-orb orb-two" />

      {/* 顶部标题区：保留了桌面工作台常用的“标题 + 快捷操作”结构。 */}
      <header className="hero-panel">
        <div>
          <h1>污染场地风险评估系统</h1>
        </div>
        <div className="hero-actions">
          <button className="ghost-button" onClick={openParameterModal} type="button">
            参数设置
          </button>
          <button className="ghost-button" onClick={handleOpenAdmin} type="button">
            污染物数据库
          </button>
          <button className="primary-button" onClick={() => setResultModalOpen(true)} type="button">
            查看结果
          </button>
        </div>
      </header>

      {error ? <section className="banner error-banner">{error}</section> : null}
      {notice ? <section className={`banner ${notice.kind}-banner`}>{notice.text}</section> : null}

      {/* 指标卡区：帮助用户快速确认当前运行状态。 */}
      <section className="metrics-grid">
        <MetricCard
          label="工作区污染物"
          value={workspaceItems.length}
          hint={workspaceItems.length ? "已接入浓度与结果联动" : "从左侧目录添加后开始计算"}
          tone="teal"
        />
        <MetricCard
          label="污染物总量"
          value={health?.catalog_count || catalogItems.length}
          hint="内置数据库已嵌入本地运行目录"
          tone="amber"
        />
        <MetricCard
          label="暴露途径"
          value={summarizePathways(pathways)}
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

      {/* 控制区：标准、用地类型、暴露途径都属于“计算前条件”。 */}
      <section className="control-panel">
        <div className="control-card">
          <span>用地类型</span>
          <div className="segmented">
            <button
              className={areaType === "I" ? "segment active" : "segment"}
              onClick={() => setAreaType("I")}
              type="button"
            >
              第一类用地
            </button>
            <button
              className={areaType === "II" ? "segment active" : "segment"}
              onClick={() => setAreaType("II")}
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
              onClick={() => setStandard("G")}
              type="button"
            >
              国家标准
            </button>
            <button
              className={standard === "Z" ? "segment active" : "segment"}
              onClick={() => setStandard("Z")}
              type="button"
            >
              浙江标准
            </button>
          </div>
        </div>

        <div className="control-card wide">
          <span>暴露途径</span>
          <div className="chip-grid">
            {PATHWAYS.map((item) => (
              <button
                key={item.key}
                className={pathways[item.key] ? "chip active" : "chip"}
                onClick={() =>
                  setPathways((current) => ({
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
      </section>

      {/* 主工作台：左边是目录搜索，右边是工作区。 */}
      <main className="workspace-grid">
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <h2>污染物目录</h2>
              <p>{catalogHint}</p>
            </div>
            <button className="ghost-button" onClick={() => refreshCatalog(catalogKeyword)} type="button">
              刷新
            </button>
          </div>
          <div className="catalog-search-stack">
            <div className="toolbar">
              <div className="search-combobox">
                <input
                  ref={catalogInputRef}
                  className="text-input"
                  placeholder="搜索污染物中文名或英文名"
                  value={catalogKeyword}
                  onChange={(event) => {
                    setCatalogKeyword(event.target.value);
                    setCatalogPickerOpen(true);
                    setCatalogActiveIndex(-1);
                  }}
                  onFocus={() => setCatalogPickerOpen(Boolean(catalogKeyword.trim()))}
                  onBlur={() => {
                    window.setTimeout(() => setCatalogPickerOpen(false), 120);
                  }}
                  onKeyDown={handleCatalogInputKeyDown}
                />
                {catalogPickerOpen && catalogKeyword.trim() ? (
                  <div className="suggestion-popover">
                    {catalogSuggestions.length ? (
                      catalogSuggestions.map((item, index) => (
                        <button
                          key={item.id}
                          className={`suggestion-item ${catalogActiveIndex === index ? "is-active" : ""}`}
                          onMouseDown={(event) => {
                            event.preventDefault();
                            // 这里用 onMouseDown 而不是 onClick，
                            // 是为了避免 input 先失焦、建议框提前关闭，导致点击失效。
                            void addCatalogItemToWorkspace(item);
                          }}
                          onMouseEnter={() => setCatalogActiveIndex(index)}
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
              <button className="secondary-button" onClick={() => refreshCatalog(catalogKeyword)} type="button">
                查询
              </button>
              <button className="primary-button" onClick={handleAddToWorkspace} type="button">
                加入工作区
              </button>
            </div>
            <div className="catalog-selection-card">
              <div className="catalog-selection-header">
                <strong>当前已选</strong>
                <span>{selectedCatalogItem ? `编号 #${selectedCatalogItem.id}` : "未选择"}</span>
              </div>
              <div className="catalog-selection-main">{catalogSelectionLabel}</div>
              <div className="catalog-selection-sub">
                {selectedCatalogItem
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
            rows={visibleCatalogRows}
            selectedKey={selectedCatalogId}
            onSelect={setSelectedCatalogId}
            emptyText={catalogEmptyText}
          />
        </section>

        <section className="panel-card">
          <div className="panel-head">
            <div>
              <h2>工作区污染物</h2>
              <p>
                {workspaceItems.length
                  ? `当前已选 ${workspaceItems.length} 个污染物，可继续编辑浓度或直接计算。`
                  : "工作区还没有污染物。先从左侧目录加入至少一项。"}
              </p>
            </div>
            <button className="ghost-button" onClick={refreshWorkspace} type="button">
              同步
            </button>
          </div>
          <DataTable
            headers={WORKSPACE_HEADERS}
            rows={workspaceRows}
            selectedKey={selectedWorkspaceNumber}
            emphasizedKey={highlightedWorkspaceNumber}
            autoScrollKey={highlightedWorkspaceNumber}
            onSelect={setSelectedWorkspaceNumber}
            emptyText="工作区为空"
          />
          <div className="panel-footer">
            <button className="ghost-button" onClick={openConcentrationModal} type="button">
              编辑浓度
            </button>
            <button className="ghost-button" onClick={handleRemoveWorkspace} type="button">
              移除选中
            </button>
            <button className="ghost-button danger" onClick={handleResetWorkspace} type="button">
              重置工作区
            </button>
          </div>
        </section>
      </main>

      {/* 底部操作条：在用户准备好条件后，通常会从这里发起计算。 */}
      <footer className="action-deck">
        <div>
          <strong>当前选择</strong>
          <p>
            {standard === "G" ? "国家标准" : "浙江标准"} ·
            {areaType === "I" ? " 第一类用地" : " 第二类用地"} ·
            已勾选 {summarizePathways(pathways)} 条暴露途径
          </p>
        </div>
        <div className="action-buttons">
          <button className="ghost-button" onClick={() => setResultModalOpen(true)} type="button">
            查看现有结果
          </button>
          <button className="primary-button large" onClick={handleCalculate} type="button">
            开始计算
          </button>
        </div>
      </footer>

      {/* 参数弹窗：编辑原有四组参数模板。 */}
      {parameterModalOpen ? (
        <Modal
          title="参数设置"
          subtitle="四组模板参数仍然写回原有数据表，但编辑方式已经统一。"
          size="xl"
          onClose={() => setParameterModalOpen(false)}
          actions={
            <>
              <button className="ghost-button" onClick={handleResetParameters} type="button">
                恢复默认
              </button>
              <button className="primary-button" onClick={handleSaveParameters} type="button">
                保存参数
              </button>
            </>
          }
        >
          <div className="tab-strip">
            {parameterDraft.map((group) => (
              <button
                key={group.id}
                className={activeParameterGroupId === group.id ? "tab-chip active" : "tab-chip"}
                onClick={() => setActiveParameterGroupId(group.id)}
                type="button"
              >
                {group.title}
              </button>
            ))}
          </div>
          {parameterDraft
            .filter((group) => group.id === activeParameterGroupId)
            .map((group) => (
              <div className="editable-grid" key={group.id}>
                <table className="editor-table">
                  <thead>
                    <tr>
                      <th>符号</th>
                      <th>参数名称</th>
                      {PARAMETER_COLUMNS.map((column) => (
                        <th key={column.key}>{column.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((row, rowIndex) => (
                      <tr key={row.name}>
                        <td>{row.name}</td>
                        <td>{row.label}</td>
                        {PARAMETER_COLUMNS.map((column) => (
                          <td key={column.key}>
                            <input
                              className="table-input"
                              type="number"
                              step="any"
                              value={row[column.key]}
                              onChange={(event) =>
                                setParameterDraft((current) =>
                                  current.map((item) =>
                                    item.id !== group.id
                                      ? item
                                      : {
                                          ...item,
                                          rows: item.rows.map((entry, entryIndex) =>
                                            entryIndex !== rowIndex
                                              ? entry
                                              : { ...entry, [column.key]: event.target.value },
                                          ),
                                        },
                                  ),
                                )
                              }
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </Modal>
      ) : null}

      {/* 浓度弹窗：批量维护工作区里每条记录的浓度。 */}
      {concentrationModalOpen ? (
        <Modal
          title="污染物浓度设置"
          subtitle="地表、下层土壤、地下水和地下水保护浓度统一在这里维护。"
          size="xl"
          onClose={() => setConcentrationModalOpen(false)}
          actions={
            <button className="primary-button" onClick={handleSaveConcentrations} type="button">
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
                  <th>地表浓度</th>
                  <th>下层土壤浓度</th>
                  <th>地下水浓度</th>
                  <th>地下水保护浓度</th>
                </tr>
              </thead>
              <tbody>
                {concentrationDraft.map((item, index) => (
                  <tr key={item.workspace_number}>
                    <td>{item.workspace_number}</td>
                    <td>{item.pollutant_id}</td>
                    <td>{item.name}</td>
                    <td>{item.english_name}</td>
                    {[
                      "surface_concentration",
                      "lower_soil_concentration",
                      "groundwater_concentration",
                      "groundwater_protection_concentration",
                    ].map((field) => (
                      <td key={field}>
                        <input
                          className="table-input"
                          type="number"
                          step="any"
                          value={item[field]}
                          onChange={(event) =>
                            setConcentrationDraft((current) =>
                              current.map((entry, entryIndex) =>
                                entryIndex === index ? { ...entry, [field]: event.target.value } : entry,
                              ),
                            )
                          }
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      ) : null}

      {/* 结果弹窗：把后端结果表格式化后展示为桌面表格。 */}
      {resultModalOpen ? (
        <Modal
          title="计算结果"
          subtitle="各结果表沿用原有运行逻辑，当前展示的是格式化后的桌面视图。"
          size="xl"
          onClose={() => setResultModalOpen(false)}
          actions={
            <>
              <button className="ghost-button" onClick={handleExportResults} type="button">
                导出 Excel
              </button>
              <button className="primary-button" onClick={() => setResultModalOpen(false)} type="button">
                完成
              </button>
            </>
          }
        >
          <div className="tab-strip">
            {results.map((table) => (
              <button
                key={table.key}
                className={activeResultKey === table.key ? "tab-chip active" : "tab-chip"}
                onClick={() => setActiveResultKey(table.key)}
                type="button"
              >
                {table.title}
              </button>
            ))}
          </div>
          {activeResult ? (
            <DataTable
              headers={activeResult.headers}
              rows={activeResult.rows.map((row, index) => ({
                key: `${activeResult.key}-${index}`,
                cells: row,
              }))}
              emptyText="还没有结果数据"
            />
          ) : null}
        </Modal>
      ) : null}

      {/* 管理员登录弹窗：进入污染物库维护前的身份校验。 */}
      {adminLoginOpen ? (
        <Modal
          title="管理员登录"
          subtitle="通过原有用户表校验后才进入污染物库维护。"
          size="sm"
          onClose={() => setAdminLoginOpen(false)}
          actions={
            <button className="primary-button" onClick={handleAdminLogin} type="button">
              登录
            </button>
          }
        >
          <div className="form-grid single">
            <label>
              <span>用户名</span>
              <input
                className="text-input"
                value={loginForm.username}
                onChange={(event) =>
                  setLoginForm((current) => ({ ...current, username: event.target.value }))
                }
              />
            </label>
            <label>
              <span>密码</span>
              <input
                className="text-input"
                type="password"
                value={loginForm.password}
                onChange={(event) =>
                  setLoginForm((current) => ({ ...current, password: event.target.value }))
                }
              />
            </label>
          </div>
        </Modal>
      ) : null}

      {/* 管理员面板：查询、增删改污染物，并可修改密码。 */}
      {adminPanelOpen ? (
        <Modal
          title="污染物数据库管理"
          subtitle={`当前管理员：${adminUser || "未登录"}`}
          size="xl"
          onClose={() => setAdminPanelOpen(false)}
          actions={
            <>
              <button
                className="ghost-button"
                onClick={() => {
                  setSelectedAdminId(null);
                  setAdminForm(emptyPollutantForm());
                }}
                type="button"
              >
                清空表单
              </button>
              <button className="ghost-button" onClick={() => handleAdminSave("create")} type="button">
                新增
              </button>
              <button className="ghost-button" onClick={() => handleAdminSave("update")} type="button">
                更新
              </button>
              <button className="ghost-button danger" onClick={handleAdminDelete} type="button">
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
                  value={adminKeyword}
                  onChange={(event) => setAdminKeyword(event.target.value)}
                />
                <button className="secondary-button" onClick={() => refreshAdminCatalog(adminKeyword)} type="button">
                  查询
                </button>
              </div>
              <DataTable
                headers={CATALOG_HEADERS}
                rows={adminRows}
                selectedKey={selectedAdminId}
                onSelect={setSelectedAdminId}
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
                      value={adminForm[field.key]}
                      onChange={(event) =>
                        setAdminForm((current) => ({ ...current, [field.key]: event.target.value }))
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
                      onChange={(event) =>
                        setPasswordForm((current) => ({ ...current, old_password: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    <span>新密码</span>
                    <input
                      className="text-input"
                      type="password"
                      value={passwordForm.new_password}
                      onChange={(event) =>
                        setPasswordForm((current) => ({ ...current, new_password: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    <span>确认新密码</span>
                    <input
                      className="text-input"
                      type="password"
                      value={passwordForm.confirm_password}
                      onChange={(event) =>
                        setPasswordForm((current) => ({
                          ...current,
                          confirm_password: event.target.value,
                        }))
                      }
                    />
                  </label>
                </div>
                <button className="primary-button" onClick={handlePasswordUpdate} type="button">
                  保存新密码
                </button>
              </div>
            </section>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

export default App;
