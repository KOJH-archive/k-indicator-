// ==========================================================================
// K-Indicator App Dashboard Script
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
    // App State
    let currentTab = "dashboard";
    let articlesData = [];
    let cpiChartInstance = null;
    let tradeChartInstance = null;
    let selectedFilter = "all";
    let searchQuery = "";

    // API base URL (empty string represents current origin)
    const API_BASE = "";

    // DOM Elements
    const navItems = document.querySelectorAll(".nav-item");
    const tabContents = document.querySelectorAll(".tab-content");
    const pageTitle = document.getElementById("pageTitle");
    const pageDescription = document.getElementById("pageDescription");
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const themeLabel = themeToggleBtn.querySelector(".theme-label");
    const scraperStatusBadge = document.getElementById("scraperStatusBadge");
    const scraperStatusText = scraperStatusBadge.querySelector(".status-text");
    const syncNowBtn = document.getElementById("syncNowBtn");
    const systemSyncBtn = document.getElementById("systemSyncBtn");

    // Tab 2: Releases Elements
    const searchInput = document.getElementById("searchInput");
    const filterButtons = document.querySelectorAll(".filter-btn");
    const articlesTableBody = document.getElementById("articlesTableBody");

    // Tab 3: Settings Elements
    const settingsForm = document.getElementById("settingsForm");
    const geminiApiKeyInput = document.getElementById("geminiApiKeyInput");
    const apiKeyStatus = document.getElementById("apiKeyStatus");
    const toggleApiKeyBtn = document.getElementById("toggleApiKeyBtn");

    // Modal Elements
    const articleModal = document.getElementById("articleModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const modalTabs = document.querySelectorAll(".modal-tab-btn");
    const modalTabContents = document.querySelectorAll(".modal-tab-content");
    const modalSourceBadge = document.getElementById("modalSourceBadge");
    const modalTitle = document.getElementById("modalTitle");
    const modalDateInfo = document.getElementById("modalDateInfo");
    const modalSummaryText = document.getElementById("modalSummaryText");
    const modalImpactText = document.getElementById("modalImpactText");
    const modalIndicatorsBody = document.getElementById("modalIndicatorsBody");
    const modalRawText = document.getElementById("modalRawText");
    const modalAttachmentsList = document.getElementById("modalAttachmentsList");
    const reAnalyzeBtn = document.getElementById("reAnalyzeBtn");
    let activeModalArticleId = null;

    // Initialize Lucide Icons
    lucide.createIcons();

    // ==========================================================================
    // Theme Management (Light / Dark)
    // ==========================================================================

    const savedTheme = localStorage.getItem("theme") || "dark";
    if (savedTheme === "light") {
        document.body.classList.remove("dark-theme");
        document.body.classList.add("light-theme");
        themeLabel.textContent = "다크 모드";
    } else {
        document.body.classList.remove("light-theme");
        document.body.classList.add("dark-theme");
        themeLabel.textContent = "라이트 모드";
    }

    themeToggleBtn.addEventListener("click", () => {
        if (document.body.classList.contains("dark-theme")) {
            document.body.classList.remove("dark-theme");
            document.body.classList.add("light-theme");
            localStorage.setItem("theme", "light");
            themeLabel.textContent = "다크 모드";
        } else {
            document.body.classList.remove("light-theme");
            document.body.classList.add("dark-theme");
            localStorage.setItem("theme", "dark");
            themeLabel.textContent = "라이트 모드";
        }

        // Re-render charts to adjust text colors for light/dark mode
        fetchAndRenderCharts();
    });

    // ==========================================================================
    // Tab Navigation
    // ==========================================================================

    navItems.forEach(item => {
        item.addEventListener("click", () => {
            const tabName = item.getAttribute("data-tab");
            switchTab(tabName);

            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");
        });
    });

    function switchTab(tabName) {
        currentTab = tabName;

        // Toggle tab content visibility
        tabContents.forEach(tab => {
            tab.classList.remove("active");
            if (tab.id === `tab-${tabName}`) {
                tab.classList.add("active");
            }
        });

        // Update header details based on active tab
        if (tabName === "dashboard") {
            pageTitle.textContent = "종합 대시보드";
            pageDescription.textContent = "실시간 국가 경제지표 추이 및 AI 분석 동향을 파악합니다.";
            fetchDashboardData();
        } else if (tabName === "releases") {
            pageTitle.textContent = "보도자료 목록";
            pageDescription.textContent = "수집된 공식기관 보도자료 리스트 및 심층 AI 분석 내역입니다.";
            fetchArticles();
        } else if (tabName === "settings") {
            pageTitle.textContent = "환경 설정";
            pageDescription.textContent = "API Key 설정 및 데이터베이스 강제 동기화 처리를 수행합니다.";
            fetchSettings();
        }
    }

    // ==========================================================================
    // Scraper Status and Run Sync
    // ==========================================================================

    async function checkScraperStatus() {
        try {
            const res = await fetch(`${API_BASE}/api/collect/status`);
            const data = await res.json();

            if (data.is_collecting) {
                scraperStatusBadge.classList.add("collecting");
                scraperStatusText.textContent = "수집 및 분석 중";
                syncNowBtn.disabled = true;
                systemSyncBtn.disabled = true;
            } else {
                scraperStatusBadge.classList.remove("collecting");
                scraperStatusText.textContent = "대기 중";
                syncNowBtn.disabled = false;
                systemSyncBtn.disabled = false;
            }
        } catch (err) {
            console.error("Error checking scraper status:", err);
        }
    }

    // Poll scraper status every 3 seconds
    setInterval(checkScraperStatus, 3000);
    checkScraperStatus();

    async function triggerCollection() {
        try {
            scraperStatusBadge.classList.add("collecting");
            scraperStatusText.textContent = "수집 및 분석 중";
            syncNowBtn.disabled = true;
            systemSyncBtn.disabled = true;

            const res = await fetch(`${API_BASE}/api/collect`, { method: "POST" });
            const data = await res.json();
            alert(data.message);

            // Reload data
            if (currentTab === "dashboard") fetchDashboardData();
            if (currentTab === "releases") fetchArticles();
        } catch (err) {
            console.error("Error triggering collection:", err);
            alert("수집 작업 시작 중 오류가 발생했습니다.");
            checkScraperStatus();
        }
    }

    syncNowBtn.addEventListener("click", triggerCollection);
    systemSyncBtn.addEventListener("click", triggerCollection);

    // ==========================================================================
    // Tab 1: Dashboard API Loading & Chart rendering
    // ==========================================================================

    function fetchDashboardData() {
        fetchKPIValues();
        fetchAndRenderCharts();
    }

    async function fetchKPIValues() {
        try {
            const res = await fetch(`${API_BASE}/api/indicators`);
            const data = await res.json();

            // Group by key
            const grouped = {};
            data.forEach(item => {
                const key = item.indicator_key;
                if (!grouped[key]) grouped[key] = [];
                grouped[key].push(item);
            });

            // Find latest value for each indicator
            const keys = ["base_rate", "cpi_yoy", "trade_balance", "export_growth"];
            keys.forEach(k => {
                const card = document.getElementById(`kpi-${k.replace('_', '-')}`);
                const valElem = card.querySelector(".kpi-value");
                const periodElem = card.querySelector(".kpi-trend");

                if (grouped[k] && grouped[k].length > 0) {
                    // Sort by period descending
                    grouped[k].sort((a, b) => b.period.localeCompare(a.period));
                    const latest = grouped[k][0];
                    valElem.textContent = latest.value;
                    periodElem.textContent = `대상 기간: ${latest.period}`;
                } else {
                    valElem.textContent = "-";
                    periodElem.textContent = "데이터 없음";
                }
            });
        } catch (err) {
            console.error("Error loading KPI values:", err);
        }
    }

    async function fetchAndRenderCharts() {
        try {
            const res = await fetch(`${API_BASE}/api/indicators`);
            const data = await res.json();

            const isDark = document.body.classList.contains("dark-theme");
            const textColor = isDark ? "#94a3b8" : "#475569";
            const gridColor = isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)";

            // Group data by period for chronological alignment
            const periodsSet = new Set();
            const values = {
                base_rate: {},
                cpi_yoy: {},
                trade_balance: {},
                export_growth: {}
            };

            data.forEach(item => {
                periodsSet.add(item.period);
                if (item.indicator_key in values) {
                    values[item.indicator_key][item.period] = item.value;
                }
            });

            // Convert to sorted list of periods
            const sortedPeriods = Array.from(periodsSet).sort();

            // Generate lists aligning values to sorted periods.
            // Fill forward missing base rate values (since interest rates remain at the last set value).
            let lastBaseRate = null;
            const baseRates = sortedPeriods.map(p => {
                if (values.base_rate[p] !== undefined) {
                    lastBaseRate = values.base_rate[p];
                }
                return lastBaseRate;
            });
            const cpiYoYs = sortedPeriods.map(p => values.cpi_yoy[p] !== undefined ? values.cpi_yoy[p] : null);
            const tradeBalances = sortedPeriods.map(p => values.trade_balance[p] !== undefined ? values.trade_balance[p] : null);
            const exportGrowths = sortedPeriods.map(p => values.export_growth[p] !== undefined ? values.export_growth[p] : null);

            // 1. Render BOK Interest Rate and CPI Chart (Dual Axis)
            if (cpiChartInstance) cpiChartInstance.destroy();
            const ctxCpi = document.getElementById("cpiRateChart").getContext("2d");
            cpiChartInstance = new Chart(ctxCpi, {
                type: "line",
                data: {
                    labels: sortedPeriods,
                    datasets: [
                        {
                            label: "소비자물가상승률 (%)",
                            data: cpiYoYs,
                            borderColor: "#a855f7",
                            backgroundColor: "rgba(168, 85, 247, 0.1)",
                            yAxisID: "y",
                            tension: 0.3,
                            fill: true
                        },
                        {
                            label: "한국은행 기준금리 (%)",
                            data: baseRates,
                            borderColor: "#60a5fa",
                            backgroundColor: "transparent",
                            borderDash: [5, 5],
                            yAxisID: "y1",
                            tension: 0.1,
                            stepped: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: textColor }
                        },
                        y: {
                            type: "linear",
                            display: true,
                            position: "left",
                            grid: { color: gridColor },
                            ticks: { color: textColor },
                            title: { display: true, text: "물가상승률 (%)", color: textColor }
                        },
                        y1: {
                            type: "linear",
                            display: true,
                            position: "right",
                            grid: { drawOnChartArea: false },
                            ticks: { color: textColor },
                            title: { display: true, text: "기준금리 (%)", color: textColor }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: textColor } }
                    }
                }
            });

            // 2. Render Export and Trade Balance Chart (Combination)
            if (tradeChartInstance) tradeChartInstance.destroy();
            const ctxTrade = document.getElementById("tradeChart").getContext("2d");

            // Generate colors for trade balance bars (positive: green/blue, negative: red)
            const barColors = tradeBalances.map(v => v >= 0 ? "rgba(16, 185, 129, 0.6)" : "rgba(239, 68, 68, 0.6)");
            const barBorderColors = tradeBalances.map(v => v >= 0 ? "#10b981" : "#ef4444");

            tradeChartInstance = new Chart(ctxTrade, {
                data: {
                    labels: sortedPeriods,
                    datasets: [
                        {
                            type: "bar",
                            label: "무역수지 (억 달러)",
                            data: tradeBalances,
                            backgroundColor: barColors,
                            borderColor: barBorderColors,
                            borderWidth: 1,
                            yAxisID: "y"
                        },
                        {
                            type: "line",
                            label: "수출증가율 (%)",
                            data: exportGrowths,
                            borderColor: "#f97316",
                            backgroundColor: "transparent",
                            yAxisID: "y1",
                            tension: 0.3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { color: textColor }
                        },
                        y: {
                            type: "linear",
                            display: true,
                            position: "left",
                            grid: { color: gridColor },
                            ticks: { color: textColor },
                            title: { display: true, text: "무역수지 (억 달러)", color: textColor }
                        },
                        y1: {
                            type: "linear",
                            display: true,
                            position: "right",
                            grid: { drawOnChartArea: false },
                            ticks: { color: textColor },
                            title: { display: true, text: "수출증가율 (%)", color: textColor }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: textColor } }
                    }
                }
            });

        } catch (err) {
            console.error("Error loading charts indicator data:", err);
        }
    }

    // Render initially
    fetchDashboardData();

    // ==========================================================================
    // Tab 2: Press Releases Management & Filters
    // ==========================================================================

    async function fetchArticles() {
        try {
            const res = await fetch(`${API_BASE}/api/articles`);
            articlesData = await res.json();
            renderArticlesTable();
        } catch (err) {
            console.error("Error loading articles list:", err);
            articlesTableBody.innerHTML = `<tr><td colspan="6" class="text-center" style="color:var(--danger)">보도자료를 불러오는 도중 오류가 발생했습니다.</td></tr>`;
        }
    }

    function renderArticlesTable() {
        // Filter elements
        const filtered = articlesData.filter(art => {
            const matchesFilter = selectedFilter === "all" ||
                art.source === selectedFilter ||
                (selectedFilter === "산업통상부" && art.source === "산업통상자원부") ||
                (selectedFilter === "국가데이터처" && art.source === "통계청") ||
                (selectedFilter === "재정경제부" && art.source === "기획재정부");
            const matchesSearch = searchQuery === "" ||
                art.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                (art.summary && art.summary.toLowerCase().includes(searchQuery.toLowerCase()));
            return matchesFilter && matchesSearch;
        });

        if (filtered.length === 0) {
            articlesTableBody.innerHTML = `<tr><td colspan="6" class="text-center">해당 조건에 만족하는 보도자료가 없습니다.</td></tr>`;
            return;
        }

        articlesTableBody.innerHTML = "";

        filtered.forEach(art => {
            const tr = document.createElement("tr");
            tr.dataset.id = art.id;

            // 1. Pub Date
            const tdDate = document.createElement("td");
            tdDate.textContent = art.pub_date;
            tr.appendChild(tdDate);

            // 2. Agency badge
            const tdSource = document.createElement("td");
            const badgeClass = getAgencyBadgeClass(art.source);
            tdSource.innerHTML = `<span class="badge ${badgeClass}">${art.source}</span>`;
            tr.appendChild(tdSource);

            // 3. Title
            const tdTitle = document.createElement("td");
            tdTitle.innerHTML = `<span class="article-title-link" style="font-weight:500; cursor:pointer;">${art.title}</span>`;
            tdTitle.addEventListener("click", () => openArticleModal(art.id));
            tr.appendChild(tdTitle);

            // 4. Status Badge
            const tdStatus = document.createElement("td");
            const statusClass = art.status === "completed" ? "completed" : art.status === "pending" ? "pending" : "failed";
            const statusText = art.status === "completed" ? "완료" : art.status === "pending" ? "분석 대기" : "실패";
            tdStatus.innerHTML = `<span class="status-badge ${statusClass}">${statusText}</span>`;
            tr.appendChild(tdStatus);

            // 5. Attachments
            const tdAttachments = document.createElement("td");
            const wrapper = document.createElement("div");
            wrapper.className = "attachments-wrapper";

            art.attachments.forEach(att => {
                const icon = att.filename.toLowerCase().endswith && att.filename.toLowerCase().endswith("pdf") ? "file" : "file-text";
                const fileLink = document.createElement("a");
                fileLink.className = "attachment-badge";
                fileLink.href = `file:///${att.local_path}`;
                fileLink.target = "_blank";
                fileLink.innerHTML = `<i data-lucide="file" style="width:12px; height:12px;"></i> ${att.original_name.substring(0, 15)}...`;
                wrapper.appendChild(fileLink);
            });

            tdAttachments.appendChild(wrapper);
            tr.appendChild(tdAttachments);

            // 6. Actions (Delete button)
            const tdActions = document.createElement("td");
            const delBtn = document.createElement("button");
            delBtn.className = "btn-icon";
            delBtn.innerHTML = `<i data-lucide="trash-2" style="width:14px; height:14px;"></i>`;
            delBtn.title = "삭제";
            delBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                if (confirm(`보도자료를 정말 삭제하시겠습니까? 관련 다운로드 파일도 영구 삭제됩니다.\n[${art.title}]`)) {
                    deleteArticle(art.id);
                }
            });
            tdActions.appendChild(delBtn);
            tr.appendChild(tdActions);

            // Clicking row (except links/buttons) opens the modal
            tr.addEventListener("click", (e) => {
                if (e.target.tagName !== "A" && e.target.tagName !== "BUTTON" && !e.target.closest("a") && !e.target.closest("button")) {
                    openArticleModal(art.id);
                }
            });

            articlesTableBody.appendChild(tr);
        });

        lucide.createIcons();
    }

    function getAgencyBadgeClass(source) {
        if (source === "한국은행") return "badge-bok";
        if (source === "산업통상부" || source === "산업통상자원부") return "badge-motie";
        if (source === "관세청") return "badge-customs";
        if (source === "국가데이터처" || source === "통계청") return "badge-statistics";
        return "badge-moef";
    }

    async function deleteArticle(articleId) {
        try {
            const res = await fetch(`${API_BASE}/api/articles/${articleId}`, { method: "DELETE" });
            const data = await res.json();
            alert(data.message);
            fetchArticles();
        } catch (err) {
            console.error("Error deleting article:", err);
            alert("보도자료 삭제 도중 오류가 발생했습니다.");
        }
    }

    // Search Box Listener
    searchInput.addEventListener("input", (e) => {
        searchQuery = e.target.value.trim();
        renderArticlesTable();
    });

    // Filter Buttons Listener
    filterButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedFilter = btn.getAttribute("data-filter");
            renderArticlesTable();
        });
    });

    // ==========================================================================
    // Tab 3: Settings API
    // ==========================================================================

    async function fetchSettings() {
        try {
            const res = await fetch(`${API_BASE}/api/settings`);
            const data = await res.json();

            if (data.gemini_api_key_configured) {
                geminiApiKeyInput.value = data.gemini_api_key_masked;
                apiKeyStatus.textContent = "구성됨 (활성화 상태)";
                apiKeyStatus.className = "status-msg configured";
            } else {
                geminiApiKeyInput.value = "";
                apiKeyStatus.textContent = "설정되지 않음 (수집 시 간이 분석만 사용됨)";
                apiKeyStatus.className = "status-msg";
            }
        } catch (err) {
            console.error("Error loading settings:", err);
        }
    }

    settingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const apiKey = geminiApiKeyInput.value.trim();

        if (!apiKey) {
            alert("API Key를 입력해 주세요.");
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ gemini_api_key: apiKey })
            });
            const data = await res.json();
            alert(data.message);
            fetchSettings();
        } catch (err) {
            console.error("Error saving API key settings:", err);
            alert("설정 저장에 실패했습니다.");
        }
    });

    // Toggle API Key visibility
    toggleApiKeyBtn.addEventListener("click", () => {
        const type = geminiApiKeyInput.getAttribute("type") === "password" ? "text" : "password";
        geminiApiKeyInput.setAttribute("type", type);
        const icon = type === "password" ? "eye" : "eye-off";
        toggleApiKeyBtn.innerHTML = `<i data-lucide="${icon}" style="width:16px; height:16px;"></i>`;
        lucide.createIcons();
    });

    // ==========================================================================
    // Modal Interaction (Detail View & AI Re-Analysis)
    // ==========================================================================

    async function openArticleModal(articleId) {
        activeModalArticleId = articleId;
        articleModal.classList.add("open");

        // Reset contents
        modalSourceBadge.textContent = "...";
        modalTitle.textContent = "데이터를 불러오는 중...";
        modalDateInfo.textContent = "";
        modalSummaryText.textContent = "AI 핵심 요약을 작성 중입니다. 잠시만 기다려 주세요...";
        modalImpactText.textContent = "지표 통계 및 시장 영향을 분석하는 중입니다...";
        modalIndicatorsBody.innerHTML = `<tr><td colspan="5" class="text-center">데이터를 불러오는 중입니다...</td></tr>`;
        modalRawText.textContent = "문서 텍스트 로딩 중...";
        modalAttachmentsList.innerHTML = "";

        // Modal navigation default tab
        switchModalTab("summary");

        try {
            const res = await fetch(`${API_BASE}/api/articles/${articleId}`);
            const art = await res.json();

            // Set details
            modalSourceBadge.textContent = art.source;
            modalSourceBadge.className = "modal-source " + getAgencyBadgeClass(art.source);
            modalTitle.textContent = art.title;
            modalDateInfo.textContent = `발표일: ${art.pub_date} | 수집시간: ${art.fetch_date}`;

            // Set summary and impact
            modalSummaryText.textContent = art.summary || "분석 완료 요약 정보가 없습니다. 아래 'AI 재분석' 버튼을 클릭해 분석을 수행할 수 있습니다.";
            modalImpactText.textContent = art.impact || "시장 분석 정보가 존재하지 않습니다.";

            // Render Indicators Table
            if (art.indicators && art.indicators.length > 0) {
                modalIndicatorsBody.innerHTML = "";
                art.indicators.forEach(ind => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="font-weight: 500;">${ind.indicator_name}</td>
                        <td style="font-size: 15px; font-weight: 700; color: var(--primary);">${ind.value}</td>
                        <td>${ind.unit || ""}</td>
                        <td>${ind.period}</td>
                        <td style="font-family: monospace; font-size:11px; color: var(--text-muted);">${ind.indicator_key}</td>
                    `;
                    modalIndicatorsBody.appendChild(tr);
                });
            } else {
                modalIndicatorsBody.innerHTML = `<tr><td colspan="5" class="text-center">추출된 지표 수치가 데이터베이스에 기록되지 않았습니다.</td></tr>`;
            }

            // Set Raw text
            modalRawText.textContent = art.raw_text || "추출된 파일 텍스트가 없습니다. 첨부파일 다운로드에 실패했거나 파싱할 수 없는 포맷일 수 있습니다.";

            // Set Attachments List
            if (art.attachments && art.attachments.length > 0) {
                modalAttachmentsList.innerHTML = "";
                art.attachments.forEach(att => {
                    const a = document.createElement("a");
                    a.href = `file:///${att.local_path}`;
                    a.className = "attachment-badge";
                    a.target = "_blank";
                    a.innerHTML = `<i data-lucide="download" style="width:12px; height:12px;"></i> ${att.original_name}`;
                    modalAttachmentsList.appendChild(a);
                });
                lucide.createIcons();
            } else {
                modalAttachmentsList.innerHTML = `<span style="font-size:12px; color:var(--text-muted);">다운로드된 첨부파일이 존재하지 않습니다.</span>`;
            }

        } catch (err) {
            console.error("Error loading article details:", err);
            modalTitle.textContent = "세부 데이터를 읽어오지 못했습니다.";
        }
    }

    function switchModalTab(tabName) {
        modalTabs.forEach(btn => {
            btn.classList.remove("active");
            if (btn.getAttribute("data-modal-tab") === tabName) {
                btn.classList.add("active");
            }
        });

        modalTabContents.forEach(content => {
            content.classList.remove("active");
            if (content.id === `modal-tab-${tabName}`) {
                content.classList.add("active");
            }
        });
    }

    modalTabs.forEach(btn => {
        btn.addEventListener("click", () => {
            switchModalTab(btn.getAttribute("data-modal-tab"));
        });
    });

    closeModalBtn.addEventListener("click", () => {
        articleModal.classList.remove("open");
        activeModalArticleId = null;

        // Refresh grid and charts to show any modified values
        if (currentTab === "dashboard") fetchDashboardData();
        if (currentTab === "releases") fetchArticles();
    });

    // Close modal when clicking outside modal card
    articleModal.addEventListener("click", (e) => {
        if (e.target === articleModal) {
            articleModal.classList.remove("open");
            activeModalArticleId = null;

            if (currentTab === "dashboard") fetchDashboardData();
            if (currentTab === "releases") fetchArticles();
        }
    });

    // Re-run AI Analysis
    reAnalyzeBtn.addEventListener("click", async () => {
        if (!activeModalArticleId) return;

        reAnalyzeBtn.disabled = true;
        const origContent = reAnalyzeBtn.innerHTML;
        reAnalyzeBtn.innerHTML = `<i data-lucide="refresh-cw" class="collecting" style="animation: pulse 1s infinite;"></i> <span>분석 중...</span>`;
        lucide.createIcons();

        try {
            const res = await fetch(`${API_BASE}/api/analyze/${activeModalArticleId}`, { method: "POST" });
            const data = await res.json();
            alert("AI 분석이 성공적으로 실행되었습니다.");

            // Reopen details
            openArticleModal(activeModalArticleId);
        } catch (err) {
            console.error("Error trigger manually analysis:", err);
            alert("AI 분석 실행 도중 오류가 발생했습니다. API Key 설정을 확인하세요.");
        } finally {
            reAnalyzeBtn.disabled = false;
            reAnalyzeBtn.innerHTML = origContent;
            lucide.createIcons();
        }
    });
});
