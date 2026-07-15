import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";
import { api } from "./api";
import { PATHWAYS } from "./constants";
import {
  AdminLoginDialog,
  AdminPanelDialog,
  ConcentrationDialog,
  ErrorDialog,
  ParameterDialog,
  ResultDialog,
  UpdateDialog,
} from "./AppDialogs";
import {
  ActionDeck,
  AppHeader,
  CatalogPanel,
  MetricsPanel,
  SiteControls,
  SplashScreen,
  WorkspacePanel,
} from "./AppPanels";
import {
  adminRows,
  catalogRows,
  CATALOG_DISPLAY_LIMIT,
  CATALOG_SUGGESTION_LIMIT,
  cloneData,
  createEmptyPathways,
  createEmptyPollutantForm,
  normalizeLoadError,
  pollutantToAdminForm,
  workspaceRows,
  workspaceToConcentrationDraft,
} from "./appHelpers";
import {
  filenameFromPath,
  hasSupportedImportExtension,
  importContentType,
  pickWorkspaceImportFile,
  saveExcelBlob,
} from "./fileTransfers";
import { isTauriRuntime } from "./runtime";
import {
  checkForUpdates,
  getCurrentAppVersion,
  openReleasePage,
  PACKAGE_VERSION,
} from "./updateService";

// App 只协调状态和用例；具体页面区块与弹窗分别位于 AppPanels/AppDialogs。
function App() {
  // ------------------------
  // 启动与全局反馈状态
  // ------------------------
  // booting: 首次启动遮罩是否显示
  // errorMessage: 错误弹窗文案
  // notice: 顶部成功提示
  // health: 后端健康检查及数据库统计
  const [booting, setBooting] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [notice, setNotice] = useState(null);
  const [health, setHealth] = useState(null);
  // 版本号由 Tauri 打包配置提供；启动自动检查和手动检查共用同一份状态。
  const [appVersion, setAppVersion] = useState(PACKAGE_VERSION);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [availableUpdate, setAvailableUpdate] = useState(null);

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
  const [pathways, setPathways] = useState(createEmptyPathways);

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
  const [adminForm, setAdminForm] = useState(createEmptyPollutantForm);
  const [passwordForm, setPasswordForm] = useState({
    old_password: "",
    new_password: "",
    confirm_password: "",
  });

  // 用于在成功加入工作区后，把光标重新送回搜索框，
  // 这样用户可以连续录入多个污染物。
  const catalogInputRef = useRef(null);
  const workspaceImportInputRef = useRef(null);
  const catalogRequestIdRef = useRef(0);
  const adminRequestIdRef = useRef(0);
  // 用 ref 标记正在进行的更新请求，避免启动检查和用户点击恰好同时发出两次请求。
  const updateCheckInFlightRef = useRef(false);

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
  const allPathwaysSelected = PATHWAYS.every((item) => pathways[item.key]);

  // Effect Events 始终读取最新状态，同时不会成为 useEffect 的依赖项。
  const runUpdateCheckEvent = useEffectEvent(runUpdateCheck);
  const waitForHealthEvent = useEffectEvent(waitForHealth);
  const refreshCatalogEvent = useEffectEvent(refreshCatalog);
  const refreshAdminCatalogEvent = useEffectEvent(refreshAdminCatalog);

  // 桌面运行时读取安装包中的真实版本，随后立即静默检查一次 Gitee Release。
  // “静默”只表示网络失败或没有更新时不打断启动；发现新版本仍会正常弹窗询问。
  useEffect(() => {
    let cancelled = false;
    async function initializeVersionAndUpdates() {
      const version = await getCurrentAppVersion();
      if (cancelled) {
        return;
      }
      setAppVersion(version);
      await runUpdateCheckEvent(version, {
        silent: true,
        isCancelled: () => cancelled,
      });
    }
    initializeVersionAndUpdates();
    return () => {
      cancelled = true;
    };
  }, []);

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
        const alive = await waitForHealthEvent();
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
          setErrorMessage(normalizeLoadError(loadError).message);
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
    refreshCatalogEvent(deferredCatalogKeyword);
  }, [booting, deferredCatalogKeyword]);

  // 管理员面板打开后，管理员搜索框的关键词变化也会触发查询。
  useEffect(() => {
    if (!adminPanelOpen) {
      return;
    }
    refreshAdminCatalogEvent(deferredAdminKeyword);
  }, [adminPanelOpen, deferredAdminKeyword]);

  // 这个 effect 专门处理搜索建议的“默认高亮项”。
  // 当建议框打开时：
  // - 如果之前已经有选中项，就尽量把它对应的建议高亮起来；
  // - 如果没有，就默认高亮第一项，方便用户直接回车。
  useEffect(() => {
    const suggestions = catalogItems.slice(0, CATALOG_SUGGESTION_LIMIT);
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
    setAdminForm(pollutantToAdminForm(selectedAdminItem));
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
    for (let index = 0; index < 60; index += 1) {
      try {
        return await api.health();
      } catch (healthError) {
        lastError = normalizeLoadError(healthError);
        await new Promise((resolve) => window.setTimeout(resolve, index < 10 ? 350 : 500));
      }
    }
    throw lastError;
  }

  // 成功继续用顶部绿色横幅；错误则改成弹窗提醒。
  function flash(kind, text) {
    if (kind === "error") {
      setErrorMessage(text);
      return;
    }
    setNotice({ kind, text });
  }

  // 启动自动检查与顶部按钮共用这一段逻辑。
  // silent=true 时，没有更新或网络失败都不打断启动；发现更新始终弹出下载确认窗口。
  async function runUpdateCheck(
    currentVersion,
    { silent = false, isCancelled = () => false } = {},
  ) {
    if (updateCheckInFlightRef.current) {
      return;
    }
    updateCheckInFlightRef.current = true;
    setCheckingUpdate(true);
    try {
      const update = await checkForUpdates(currentVersion);
      if (isCancelled()) {
        return;
      }
      if (update.status === "available") {
        setAvailableUpdate(update);
      } else if (!silent && update.status === "current") {
        flash("success", `当前已是最新版本 v${currentVersion}`);
      } else if (!silent && update.status === "ahead") {
        flash("success", `当前版本 v${currentVersion} 高于 Gitee 已发布版本`);
      } else if (!silent) {
        flash("success", "Gitee 暂无可读取的正式 Release，请确认仓库已公开并完成版本发布。");
      }
    } catch (loadError) {
      if (!silent && !isCancelled()) {
        flash("error", loadError.message);
      }
    } finally {
      updateCheckInFlightRef.current = false;
      if (!isCancelled()) {
        setCheckingUpdate(false);
      }
    }
  }

  async function handleCheckForUpdates() {
    await runUpdateCheck(appVersion);
  }

  // 用户在确认弹窗中选择下载后，再把 Release 页面交给系统默认浏览器。
  // 页面中可同时放置 Windows 与 macOS 安装包，让用户自行选择正确平台。
  async function handleOpenUpdatePage() {
    try {
      await openReleasePage(availableUpdate.releaseUrl);
      setAvailableUpdate(null);
      flash("success", "已打开 Gitee 下载页面");
    } catch (loadError) {
      flash("error", loadError.message);
    }
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
    catalogRequestIdRef.current += 1;
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
    const requestId = ++catalogRequestIdRef.current;
    try {
      const payload = await api.listCatalog(trimmed);
      if (requestId !== catalogRequestIdRef.current) {
        return;
      }
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

  async function handleRefreshWorkspace() {
    try {
      await refreshWorkspace();
      flash("success", "工作区已同步");
    } catch (loadError) {
      flash("error", loadError.message);
    }
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
    const requestId = ++adminRequestIdRef.current;
    try {
      const payload = await api.listCatalog(keyword);
      if (requestId !== adminRequestIdRef.current) {
        return;
      }
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
      // 这里不再每次都让后端回传整张工作区，
      // 而是只接收新增的那一条，然后在前端本地追加。
      // 当工作区已经有很多条记录时，这能明显减少重复序列化和传输开销。
      if (payload.item) {
        setWorkspaceItems((current) => [...current, payload.item]);
      } else {
        await refreshWorkspace();
      }
      const addedWorkspaceNumber =
        payload.added_workspace_number ?? payload.item?.workspace_number ?? null;
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

  // 打开系统文件选择器，让用户自己定位要导入的表格文件。
  // Tauri 桌面版直接读取所选路径；纯浏览器调试时回退到隐藏的 file input。
  async function openWorkspaceImport() {
    if (!isTauriRuntime()) {
      workspaceImportInputRef.current?.click();
      return;
    }

    try {
      const selectedFile = await pickWorkspaceImportFile();
      if (!selectedFile) {
        return;
      }
      await importWorkspaceSource(
        selectedFile.filename,
        selectedFile.content,
        selectedFile.contentType,
      );
    } catch (loadError) {
      flash("error", loadError.message);
    }
  }

  // 下载导入模板（默认导出为 xlsx），帮助用户直接按系统要求整理列名和示例。
  async function handleDownloadImportTemplate() {
    try {
      const blob = await api.downloadWorkspaceImportTemplate();
      const savedPath = await saveExcelBlob(blob, "污染物导入模板.xlsx");
      if (!savedPath) {
        return;
      }
      flash("success", `导入模板已保存：${filenameFromPath(savedPath)}`);
    } catch (loadError) {
      flash("error", loadError.message);
    }
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
      setCatalogActiveIndex((current) => (current <= 0 ? 0 : Math.max(current - 1, 0)));
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

  // 从表格文件批量导入工作区。
  // 导入规则会尽量贴近真实业务整理习惯：
  // - 至少提供“编号 / 污染物名称 / 英文名”其中之一
  // - 四类浓度列允许留空，留空会按 0 处理
  // - 导入成功后，前端直接把新增条目追加进本地工作区状态
  async function importWorkspaceSource(filename, content, contentType) {
    if (!hasSupportedImportExtension(filename)) {
      flash("error", "当前仅支持导入 .xlsx、.xls、.csv、.txt 文件");
      return;
    }
    const payload = await api.importWorkspaceFile(filename, content, contentType);
    if (payload.items?.length) {
      setWorkspaceItems((current) => [...current, ...payload.items]);
    } else {
      await refreshWorkspace();
    }
    const lastImported = payload.items?.[payload.items.length - 1]?.workspace_number ?? null;
    setSelectedWorkspaceNumber(lastImported);
    setHighlightedWorkspaceNumber(lastImported);
    setHealth((current) => ({ ...(current || {}), workspace_count: payload.total }));
    flash(
      "success",
      `已从 ${filename} 导入 ${payload.imported || payload.items?.length || 0} 条污染物`,
    );
  }

  // 浏览器调试模式的文件输入回调。桌面应用不会走这里，
  // 但保留它能让前端脱离 Tauri 时仍可独立联调后端。
  async function handleWorkspaceFileImport(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    try {
      await importWorkspaceSource(file.name, file, file.type || importContentType(file.name));
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
      setPathways(createEmptyPathways());
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
    setConcentrationDraft(cloneData(workspaceToConcentrationDraft(workspaceItems)));
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

  // 导出结果表为 Excel。后端负责生成内容，前端负责弹出“另存为”窗口，
  // 文件只有在用户选定的位置写入成功后，才提示导出完成。
  async function handleExportResults() {
    try {
      const blob = await api.exportResults();
      const savedPath = await saveExcelBlob(blob, "风险评估结果.xlsx");
      if (!savedPath) {
        return;
      }
      flash("success", `结果文件已保存：${filenameFromPath(savedPath)}`);
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
      setAdminForm(createEmptyPollutantForm());
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
      setAdminForm(createEmptyPollutantForm());
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

  // 一键勾选全部暴露途径。
  function handleSelectAllPathways() {
    setPathways(createEmptyPathways(true));
  }

  const visibleCatalogRows = catalogRows(catalogItems).slice(0, CATALOG_DISPLAY_LIMIT);
  const catalogSuggestions = catalogItems.slice(0, CATALOG_SUGGESTION_LIMIT);
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

  if (booting) {
    return <SplashScreen />;
  }

  return (
    <div className="app-shell">
      <div className="bg-orb orb-one" />
      <div className="bg-orb orb-two" />

      <AppHeader
        version={appVersion}
        checkingUpdate={checkingUpdate}
        onCheckUpdate={handleCheckForUpdates}
        onOpenParameters={openParameterModal}
        onOpenAdmin={handleOpenAdmin}
        onOpenResults={() => setResultModalOpen(true)}
      />

      {notice ? <section className={`banner ${notice.kind}-banner`}>{notice.text}</section> : null}

      <MetricsPanel
        workspaceCount={workspaceItems.length}
        catalogCount={health?.catalog_count || catalogItems.length}
        pathways={pathways}
        health={health}
      />

      <SiteControls
        areaType={areaType}
        standard={standard}
        pathways={pathways}
        allPathwaysSelected={allPathwaysSelected}
        onAreaTypeChange={setAreaType}
        onStandardChange={setStandard}
        onPathwaysChange={setPathways}
        onSelectAllPathways={handleSelectAllPathways}
      />

      <main className="workspace-grid">
        <CatalogPanel
          inputRef={catalogInputRef}
          keyword={catalogKeyword}
          hint={catalogHint}
          pickerOpen={catalogPickerOpen}
          suggestions={catalogSuggestions}
          activeIndex={catalogActiveIndex}
          selectedItem={selectedCatalogItem}
          selectedId={selectedCatalogId}
          selectionLabel={catalogSelectionLabel}
          rows={visibleCatalogRows}
          emptyText={catalogEmptyText}
          onKeywordChange={(value) => {
            setCatalogKeyword(value);
            setCatalogPickerOpen(true);
            setCatalogActiveIndex(-1);
          }}
          onPickerOpenChange={setCatalogPickerOpen}
          onActiveIndexChange={setCatalogActiveIndex}
          onInputKeyDown={handleCatalogInputKeyDown}
          onAddSuggestion={addCatalogItemToWorkspace}
          onSelectedIdChange={setSelectedCatalogId}
          onRefresh={() => refreshCatalog(catalogKeyword)}
          onAdd={handleAddToWorkspace}
        />
        <WorkspacePanel
          importInputRef={workspaceImportInputRef}
          items={workspaceItems}
          rows={workspaceRows(workspaceItems)}
          selectedNumber={selectedWorkspaceNumber}
          highlightedNumber={highlightedWorkspaceNumber}
          onSelectedNumberChange={setSelectedWorkspaceNumber}
          onImportFile={handleWorkspaceFileImport}
          onRefresh={handleRefreshWorkspace}
          onSaveTemplate={handleDownloadImportTemplate}
          onOpenImport={() => void openWorkspaceImport()}
          onEditConcentrations={openConcentrationModal}
          onRemove={handleRemoveWorkspace}
          onReset={handleResetWorkspace}
        />
      </main>

      <ActionDeck
        standard={standard}
        areaType={areaType}
        pathways={pathways}
        onOpenResults={() => setResultModalOpen(true)}
        onCalculate={handleCalculate}
      />
      <UpdateDialog
        update={availableUpdate}
        onClose={() => setAvailableUpdate(null)}
        onOpenRelease={handleOpenUpdatePage}
      />
      <ErrorDialog message={errorMessage} onClose={() => setErrorMessage("")} />

      <ParameterDialog
        open={parameterModalOpen}
        groups={parameterDraft}
        activeGroupId={activeParameterGroupId}
        onActiveGroupChange={setActiveParameterGroupId}
        onGroupsChange={setParameterDraft}
        onClose={() => setParameterModalOpen(false)}
        onReset={handleResetParameters}
        onSave={handleSaveParameters}
      />

      <ConcentrationDialog
        open={concentrationModalOpen}
        items={concentrationDraft}
        onItemsChange={setConcentrationDraft}
        onClose={() => setConcentrationModalOpen(false)}
        onSave={handleSaveConcentrations}
      />

      <ResultDialog
        open={resultModalOpen}
        tables={results}
        activeKey={activeResultKey}
        onActiveKeyChange={setActiveResultKey}
        onClose={() => setResultModalOpen(false)}
        onExport={handleExportResults}
      />

      <AdminLoginDialog
        open={adminLoginOpen}
        form={loginForm}
        onFormChange={setLoginForm}
        onClose={() => setAdminLoginOpen(false)}
        onLogin={handleAdminLogin}
      />

      <AdminPanelDialog
        open={adminPanelOpen}
        username={adminUser}
        keyword={adminKeyword}
        rows={adminRows(adminItems)}
        selectedId={selectedAdminId}
        pollutantForm={adminForm}
        passwordForm={passwordForm}
        onKeywordChange={setAdminKeyword}
        onSelectedIdChange={setSelectedAdminId}
        onPollutantFormChange={setAdminForm}
        onPasswordFormChange={setPasswordForm}
        onClear={() => {
          setSelectedAdminId(null);
          setAdminForm(createEmptyPollutantForm());
        }}
        onSearch={() => refreshAdminCatalog(adminKeyword)}
        onCreate={() => handleAdminSave("create")}
        onUpdate={() => handleAdminSave("update")}
        onDelete={handleAdminDelete}
        onPasswordUpdate={handlePasswordUpdate}
        onClose={() => setAdminPanelOpen(false)}
      />
    </div>
  );
}

export default App;
