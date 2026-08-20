// Substrate Control Panel - Interactive Dashboard
// Modern UI with real-time updates and OpenClaw-inspired design

function escapeHtml(value) {
    // Escape dynamic values before interpolation into innerHTML to prevent
    // XSS via repository names, run metadata, learning commands, or chat text.
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

class ControlPanel {
    constructor() {
        this.currentPage = 'overview';
        this.theme = localStorage.getItem('substrate-theme') || 'dark';
        this.sidebarCollapsed = false;
        this.eventSource = null;
        this.commands = [];
        
        this.init();
    }

    async init() {
        this.applyTheme();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.buildCommandPalette();
        await this.loadInitialData();
        this.startRealtimeUpdates();
    }

    // Theme Management
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.theme);
        localStorage.setItem('substrate-theme', this.theme);
    }

    toggleTheme() {
        this.theme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme();
    }

    // Sidebar Management
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        this.sidebarCollapsed = !this.sidebarCollapsed;
        sidebar.classList.toggle('collapsed', this.sidebarCollapsed);
        localStorage.setItem('substrate-sidebar-collapsed', this.sidebarCollapsed);
    }

    // Page Navigation
    navigateTo(page) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        
        // Show target page
        const targetPage = document.getElementById(`page-${page}`);
        if (targetPage) {
            targetPage.classList.add('active');
            this.currentPage = page;
            
            // Update breadcrumb
            document.getElementById('currentPage').textContent = this.getPageTitle(page);
            
            // Update active nav item
            document.querySelectorAll('.nav-item').forEach(item => {
                const isActive = item.dataset.page === page;
                item.classList.toggle('active', isActive);
                if (isActive) {
                    item.setAttribute('aria-current', 'page');
                } else {
                    item.removeAttribute('aria-current');
                }
            });
            
            // Load page-specific data
            this.loadPageData(page);
            
            // Load WhatsApp config if navigating to setup page
            if (page === 'whatsapp-setup') {
                this.loadWhatsAppConfig();
            }
            // Bind the vault filter once when the vault page is opened
            if (page === 'vault') {
                this.initVaultSearch();
            }
        }
    }

    getPageTitle(page) {
        const titles = {
            'overview': 'Dashboard',
            'metrics': 'Metrics',
            'repositories': 'Repositories',
            'runs': 'Runs',
            'tasks': 'Tasks',
            'learning': 'Learning',
            'kilo': 'Kilo Code',
            'automations': 'Automations',
            'system': 'System',
            'terminal': 'Terminal',
            'integrations': 'Integrations',
            'vault': 'Vault',
            'whatsapp-setup': 'WhatsApp Setup',
            'proton': 'Proton Mail & Drive',
            'config': 'Configuration',
            'agents': 'Agents',
            'pipelines': 'Pipelines'
        };
        return titles[page] || 'Dashboard';
    }

    // Command Palette
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // ⌘K or Ctrl+K to open command palette
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                this.toggleCommandPalette();
            }
            
            // Escape to close command palette
            if (e.key === 'Escape') {
                this.closeCommandPalette();
            }
        });
    }

    toggleCommandPalette() {
        const palette = document.getElementById('commandPalette');
        palette.classList.toggle('hidden');
        
        if (!palette.classList.contains('hidden')) {
            const input = document.getElementById('commandSearch');
            input.value = '';
            input.focus();
            this.filterCommands('');
        }
    }

    closeCommandPalette() {
        document.getElementById('commandPalette').classList.add('hidden');
    }

    buildCommandPalette() {
        this.commands = [
            { id: 'scan', title: 'Scan Repositories', description: 'Scan all workspace repositories', icon: 'search', action: () => this.executeAction('scan') },
            { id: 'refresh', title: 'Refresh Sources', description: 'Refresh upstream source data', icon: 'refresh', action: () => this.executeAction('refresh') },
            { id: 'run-task', title: 'Run Task', description: 'Execute a workspace task', icon: 'play', action: () => this.navigateTo('tasks') },
            { id: 'run-chain', title: 'Run Chain', description: 'Execute a task chain', icon: 'link', action: () => this.navigateTo('tasks') },
            { id: 'overview', title: 'Go to Dashboard', description: 'View system overview', icon: 'grid', action: () => this.navigateTo('overview') },
            { id: 'metrics', title: 'Go to Metrics', description: 'View live metrics', icon: 'bar-chart', action: () => this.navigateTo('metrics') },
            { id: 'repositories', title: 'Go to Repositories', description: 'Manage repositories', icon: 'book', action: () => this.navigateTo('repositories') },
            { id: 'runs', title: 'Go to Runs', description: 'View execution history', icon: 'play-circle', action: () => this.navigateTo('runs') },
            { id: 'kilo', title: 'Open Kilo Code', description: 'AI assistant integration', icon: 'message-circle', action: () => this.navigateTo('kilo') },
            { id: 'theme', title: 'Toggle Theme', description: 'Switch between dark and light mode', icon: 'moon', action: () => this.toggleTheme() }
        ];
    }

    filterCommands(query) {
        const results = document.getElementById('commandResults');
        const filtered = this.commands.filter(cmd => 
            cmd.title.toLowerCase().includes(query.toLowerCase()) ||
            cmd.description.toLowerCase().includes(query.toLowerCase())
        );

        results.innerHTML = filtered.map(cmd => `
            <div class="command-result-item" data-command="${cmd.id}">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    ${this.getIconPath(cmd.icon)}
                </svg>
                <div class="command-result-text">
                    <div class="command-result-title">${cmd.title}</div>
                    <div class="command-result-description">${cmd.description}</div>
                </div>
            </div>
        `).join('');

        // Add click handlers
        results.querySelectorAll('.command-result-item').forEach(item => {
            item.addEventListener('click', () => {
                const cmd = this.commands.find(c => c.id === item.dataset.command);
                if (cmd) {
                    this.closeCommandPalette();
                    cmd.action();
                }
            });
        });
    }

    getIconPath(iconName) {
        const icons = {
            'search': '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
            'refresh': '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
            'play': '<polygon points="5 3 19 12 5 21 5 3"/>',
            'link': '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
            'grid': '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
            'bar-chart': '<path d="M18 20V10M12 20V4M6 20v-6"/>',
            'book': '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
            'play-circle': '<circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>',
            'message-circle': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
            'moon': '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        };
        return icons[iconName] || icons['search'];
    }

    // Event Listeners
    setupEventListeners() {
        // Sidebar navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const page = item.dataset.page;
                if (page) {
                    this.navigateTo(page);
                    // Close mobile menu if open
                    document.getElementById('sidebar').classList.remove('open');
                }
            });
        });

        // Sidebar toggle
        document.getElementById('sidebarToggle').addEventListener('click', () => {
            this.toggleSidebar();
        });

        // Mobile menu toggle
        document.getElementById('mobileMenuToggle').addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });

        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => {
            this.toggleTheme();
        });

        // Command palette
        document.getElementById('commandPaletteTrigger').addEventListener('click', () => {
            this.toggleCommandPalette();
        });

        // Command search
        document.getElementById('commandSearch').addEventListener('input', (e) => {
            this.filterCommands(e.target.value);
        });

        // Refresh button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshData();
        });

        // Quick actions
        document.querySelectorAll('.action-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                this.executeAction(action);
            });
        });

        // Task form
        document.getElementById('taskForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitTask();
        });

        // Kilo chat
        document.getElementById('sendBtn').addEventListener('click', () => {
            this.sendKiloMessage();
        });

        document.getElementById('chatInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendKiloMessage();
            }
        });
    }

    // Data Loading
    async loadInitialData() {
        try {
            const [dashboard, repos, runs] = await Promise.all([
                this.fetchAPI('/api/dashboard'),
                this.fetchAPI('/api/dashboard').then(d => d.repositories || {}),
                this.fetchAPI('/api/dashboard').then(d => d.runs || [])
            ]);

            this.updateMetrics(dashboard);
            this.renderRepositories(repos);
            this.renderRuns(runs);
            this.renderActivity(runs);
        } catch (error) {
            console.error('Failed to load initial data:', error);
            this.showToast('Failed to load dashboard data', 'error');
        }
    }

    async loadPageData(page) {
        try {
            switch (page) {
                case 'metrics':
                    await this.loadMetrics();
                    break;
                case 'repositories':
                    await this.loadRepositories();
                    break;
                case 'runs':
                    await this.loadRuns();
                    break;
                case 'tasks':
                    await this.loadTasks();
                    break;
                case 'learning':
                    await this.loadLearning();
                    break;
                case 'automations':
                    await this.loadAutomations();
                    break;
                case 'system':
                    this.startSystemStream();
                    break;
                case 'terminal':
                    break;
                case 'integrations':
                    await this.loadIntegrations();
                    break;
                case 'vault':
                    await this.loadVault();
                    break;
                case 'proton':
                    await this.loadProton();
                    break;
                case 'config':
                    await this.loadConfig();
                    break;
                case 'agents':
                    await this.loadAgents();
                    break;
                case 'pipelines':
                    await this.loadPipelines();
                    break;
            }
        } catch (error) {
            console.error(`Failed to load ${page} data:`, error);
        }
    }

    async loadMetrics() {
        // Load metrics data and render charts
        // Placeholder for chart rendering
        console.log('Loading metrics...');
    }

    async loadRepositories() {
        const data = await this.fetchAPI('/api/dashboard');
        this.renderRepositories(data.repositories || {});
    }

    async loadRuns() {
        const data = await this.fetchAPI('/api/dashboard');
        this.renderRuns(data.runs || []);
    }

    async loadTasks() {
        const data = await this.fetchAPI('/api/dashboard');
        const repos = data.repositories || {};
        
        // Populate repository dropdown
        const repoSelect = document.getElementById('taskRepo');
        repoSelect.innerHTML = '<option value="">Select repository...</option>';
        Object.keys(repos).forEach(slug => {
            const option = document.createElement('option');
            option.value = slug;
            option.textContent = slug;
            repoSelect.appendChild(option);
        });

        // Update task dropdown when repo changes
        repoSelect.addEventListener('change', () => {
            const slug = repoSelect.value;
            if (slug && repos[slug]) {
                const taskSelect = document.getElementById('taskName');
                taskSelect.innerHTML = '<option value="">Select task...</option>';
                (repos[slug].tasks || []).forEach(task => {
                    const option = document.createElement('option');
                    option.value = task.id;
                    option.textContent = task.id;
                    taskSelect.appendChild(option);
                });
            }
        });
    }

    async loadLearning() {
        const data = await this.fetchAPI('/api/learning');
        this.renderLearning(data);
    }

    // --- iPhone panel: Automations, System, Terminal ---

    async loadAutomations() {
        const grid = document.getElementById('automationGrid');
        const data = await this.fetchAPI('/api/iphone/automations');
        const actions = data.actions || [];
        if (!actions.length) {
            grid.innerHTML = '<div class="automation-loading">No actions registered.</div>';
            return;
        }
        grid.innerHTML = actions.map(a => `
            <button class="automation-card glass" data-action="${escapeHtml(a.name)}" ${a.takes_input ? 'data-input="1"' : ''}>
                <div class="automation-card__name">${escapeHtml(a.name.replace(/_/g, ' '))}</div>
                <div class="automation-card__desc">${escapeHtml(a.description || '')}</div>
            </button>
        `).join('');

        grid.querySelectorAll('.automation-card').forEach(btn => {
            btn.addEventListener('click', () => this.runAutomation(btn));
        });
    }

    async runAutomation(btn) {
        const name = btn.dataset.action;
        const needsInput = btn.dataset.input === '1';
        const resultBox = document.getElementById('automationResult');
        const title = document.getElementById('automationResultTitle');
        const body = document.getElementById('automationResultBody');

        resultBox.style.display = 'block';
        title.textContent = name.replace(/_/g, ' ') + ' — running…';
        body.textContent = '';

        let payload = {};
        if (needsInput) {
            const prompt = window.prompt('Prompt for the agent:');
            if (prompt === null) return;
            payload = { prompt };
        }

        try {
            const res = await fetch(`/api/iphone/automations/${name}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            title.textContent = name.replace(/_/g, ' ') + ' — done';
            const out = data.stdout || '';
            const err = data.stderr || '';
            const rc = data.returncode;
            body.textContent = `${out}${err ? '\n[stderr]\n' + err : ''}${rc !== 0 ? `\n[exit ${rc}]` : ''}`.trim() || '(no output)';
        } catch (e) {
            title.textContent = name.replace(/_/g, ' ') + ' — error';
            body.textContent = String(e);
        }
    }

    startSystemStream() {
        if (this._systemStream) return;
        const el = document.getElementById('systemLive');
        this._systemStream = new EventSource('/api/iphone/system/stream');
        this._systemStream.addEventListener('system_snapshot', (e) => {
            el.innerHTML = e.data;
        });
        this._systemStream.onerror = () => {
            el.innerHTML = 'Connection lost. Reconnecting…';
        };
    }

    async loadIntegrations() {
        const data = await this.fetchAPI('/api/integrations');
        this.renderIntegrations(data);
    }

    async loadConfig() {
        // Load configuration data
        console.log('Loading config...');
    }

    async loadVaultSearch() {
        if (this._vaultData) this.renderVault(this._vaultData.services || []);
    }

    // --- Agents & Pipelines pages ---

    async loadAgents() {
        const el = document.getElementById('agents-content');
        if (!el) return;
        el.innerHTML = '<div class="loading">Loading agents...</div>';
        try {
            const res = await fetch('/api/agents');
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const agents = data.agents || data || [];
            if (!agents.length) {
                el.innerHTML = '<div class="empty">No agents configured.</div>';
                return;
            }
            el.innerHTML = agents.map(a => `
                <div class="card agent-card">
                    <div class="card-header">
                        <strong>${escapeHtml(a.agent_id || a.id)}</strong>
                        <span class="badge ${a.enabled ? 'badge-ok' : 'badge-off'}">${a.enabled ? 'enabled' : 'disabled'}</span>
                        <span class="badge">Tier ${escapeHtml(String(a.autonomy_tier ?? a.tier ?? '-'))}</span>
                    </div>
                    <div class="card-body">
                        <div class="meta">Role: ${escapeHtml(a.role)} · Repo: ${escapeHtml(a.repo_slug || a.repo || '-')}</div>
                        <div class="meta">Cadence: ${escapeHtml(a.cadence)} · Next: ${escapeHtml(a.next_due_at || '-')}</div>
                        <div class="meta">Last: ${escapeHtml(a.last_run_at || 'never')} · Status: ${escapeHtml(a.last_status || '-')}</div>
                    </div>
                    <div class="card-actions">
                        <button class="btn btn-sm" onclick="panel.runAgent('${escapeHtml(a.agent_id || a.id)}')">Run now</button>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            el.innerHTML = `<div class="error">Failed to load agents: ${escapeHtml(e.message)}</div>`;
        }
    }

    async runAgent(agentId) {
        try {
            const body = new URLSearchParams();
            body.append('agent_id', agentId);
            const res = await fetch('/api/agents/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Bearer ' + (window.PANEL_AUTH_TOKEN || '') },
                body: body.toString()
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
            this.showToast('Agent ' + agentId + ' triggered', 'success');
            setTimeout(() => this.loadAgents(), 1000);
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        }
    }

    async loadPipelines() {
        const el = document.getElementById('pipelines-content');
        if (!el) return;
        el.innerHTML = '<div class="loading">Loading pipelines...</div>';
        try {
            const res = await fetch('/api/pipelines');
            if (!res.ok) throw new Error(res.statusText);
            const data = await res.json();
            const pipes = data.pipelines || data.items || [];
            if (!pipes.length) {
                el.innerHTML = '<div class="empty">No pipelines defined.</div>';
                return;
            }
            el.innerHTML = pipes.map(p => `
                <div class="card">
                    <div class="card-header"><strong>${escapeHtml(p.id || p.name)}</strong></div>
                    <div class="card-body"><span class="meta">${escapeHtml(p.description || '')}</span></div>
                </div>
            `).join('');
        } catch (e) {
            el.innerHTML = `<div class="error">Failed to load pipelines: ${escapeHtml(e.message)}</div>`;
        }
    }

    refreshAgents() { this.loadAgents(); }
    refreshPipelines() { this.loadPipelines(); }

    initVaultSearch() {
        const search = document.getElementById('vaultSearch');
        if (search && !search.dataset.bound) {
            search.dataset.bound = '1';
            search.addEventListener('input', () => this.loadVaultSearch());
        }
    }

    // Rendering
    updateMetrics(dashboard) {
        // Update metric cards
        const repoCount = Object.keys(dashboard.repositories || {}).length;
        const runCount = (dashboard.runs || []).length;
        const successRate = this.calculateSuccessRate(dashboard.runs || []);

        document.getElementById('metricRepos').textContent = repoCount;
        document.getElementById('metricRuns').textContent = runCount;
        document.getElementById('metricSuccess').textContent = `${successRate}%`;
        document.getElementById('repoCount').textContent = repoCount;
        document.getElementById('runCount').textContent = runCount;
    }

    calculateSuccessRate(runs) {
        if (runs.length === 0) return 0;
        const successful = runs.filter(r => r.status === 'success').length;
        return Math.round((successful / runs.length) * 100);
    }

    renderRepositories(repos) {
        const grid = document.getElementById('repoGrid');
        grid.innerHTML = Object.entries(repos).map(([slug, repo]) => `
            <div class="repo-card glass">
                <div class="repo-header">
                    <div class="repo-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                        </svg>
                    </div>
                    <div class="repo-name">${escapeHtml(slug)}</div>
                </div>
                <div class="repo-meta">
                    <div class="repo-meta-item">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="6" y1="3" x2="6" y2="15"/>
                            <circle cx="18" cy="6" r="3"/>
                            <circle cx="6" cy="18" r="3"/>
                            <path d="M18 9a9 9 0 0 1-9 9"/>
                        </svg>
                        <span>${escapeHtml(repo.branch || 'main')}</span>
                    </div>
                    <div class="repo-meta-item">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12 6 12 12 16 14"/>
                        </svg>
                        <span>${repo.tasks?.length || 0} tasks</span>
                    </div>
                    <div class="repo-meta-item">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                            <circle cx="12" cy="10" r="3"/>
                        </svg>
                        <span>${escapeHtml(repo.path || '.')}</span>
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderRuns(runs) {
        const table = document.getElementById('runsTable');
        if (runs.length === 0) {
            table.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-tertiary);">No runs found</div>';
            return;
        }

        table.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Run ID</th>
                        <th>Task</th>
                        <th>Repository</th>
                        <th>Stage</th>
                        <th>Status</th>
                        <th>Started</th>
                    </tr>
                </thead>
                <tbody>
                    ${runs.slice(0, 20).map(run => `
                        <tr>
                            <td><code>${escapeHtml(run.run_id?.substring(0, 8) || 'N/A')}</code></td>
                            <td>${escapeHtml(run.task_id || 'N/A')}</td>
                            <td>${escapeHtml(run.repo_slug || 'N/A')}</td>
                            <td>${escapeHtml(run.stage || 'local')}</td>
                            <td><span class="status-badge ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></td>
                            <td>${this.formatTime(run.started_at)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    renderActivity(runs) {
        const list = document.getElementById('activityList');
        const recentRuns = runs.slice(0, 5);
        
        list.innerHTML = recentRuns.map(run => `
            <div class="activity-item">
                <div class="activity-icon ${run.status === 'success' ? 'success' : 'running'}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        ${run.status === 'success' 
                            ? '<polyline points="20 6 9 17 4 12"/>'
                            : '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'}
                    </svg>
                </div>
                <div class="activity-content">
                    <div class="activity-title">Task ${escapeHtml(run.status)}: ${escapeHtml(run.task_id || 'unknown')}</div>
                    <div class="activity-meta">${escapeHtml(run.repo_slug || 'unknown')} • ${this.timeAgo(run.started_at)}</div>
                </div>
            </div>
        `).join('');
    }

    renderLearning(data) {
        const knownGood = document.getElementById('knownGoodList');
        const errorPatterns = document.getElementById('errorPatternsList');

        const knownGoodEntries = Object.entries(data.known_good || {}).slice(0, 10);
        const errorEntries = Object.entries(data.errors || {}).slice(0, 10);

        knownGood.innerHTML = knownGoodEntries.length > 0
            ? knownGoodEntries.map(([cmd, info]) => `
                <div class="learning-item">
                    <div>${escapeHtml(cmd)}</div>
                    <div style="margin-top: 4px; font-size: 0.8rem; color: var(--text-tertiary);">
                        ${info.success_count || 0} successes
                    </div>
                </div>
            `).join('')
            : '<div style="color: var(--text-tertiary);">No known good paths yet</div>';

        errorPatterns.innerHTML = errorEntries.length > 0
            ? errorEntries.map(([sig, info]) => `
                <div class="learning-item">
                    <div>${escapeHtml(info.command || sig)}</div>
                    <div style="margin-top: 4px; font-size: 0.8rem; color: var(--text-tertiary);">
                        ${info.count || 0} occurrences
                    </div>
                </div>
            `).join('')
            : '<div style="color: var(--text-tertiary);">No error patterns yet</div>';
    }

    renderIntegrations(data) {
        const grid = document.getElementById('integrationsGrid');
        const services = data.services || [];

        grid.innerHTML = services.map(service => `
            <div class="integration-card glass">
                <div class="integration-header">
                    <div class="integration-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="2" y1="12" x2="22" y2="12"/>
                            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                        </svg>
                    </div>
                    <div class="integration-name">${escapeHtml(service.name)}</div>
                </div>
                <div class="integration-status">
                    <div class="status-dot ${service.connected ? 'online' : 'offline'}"></div>
                    <span>${service.connected ? 'Connected' : 'Disconnected'}</span>
                </div>
            </div>
        `).join('');
    }

    // Actions
    async executeAction(action) {
        try {
            this.showToast(`Executing ${action}...`, 'info');
            
            const endpoints = {
                'scan': '/api/actions/scan',
                'refresh': '/api/actions/refresh-sources'
            };

            if (endpoints[action]) {
                await this.fetchAPI(endpoints[action], { method: 'POST' });
                this.showToast(`${action} completed successfully`, 'success');
                await this.refreshData();
            }
        } catch (error) {
            console.error(`Action ${action} failed:`, error);
            this.showToast(`Action failed: ${error.message}`, 'error');
        }
    }

    async submitTask() {
        const repo = document.getElementById('taskRepo').value;
        const task = document.getElementById('taskName').value;
        const stage = document.getElementById('taskStage').value;
        const mode = document.getElementById('taskMode').value;

        if (!repo || !task) {
            this.showToast('Please select a repository and task', 'warning');
            return;
        }

        try {
            this.showToast('Executing task...', 'info');
            await this.fetchAPI('/api/actions/run-task', {
                method: 'POST',
                body: JSON.stringify({
                    repo_slug: repo,
                    task_id: task,
                    stage: stage,
                    mode: mode
                })
            });
            this.showToast('Task executed successfully', 'success');
            await this.loadRuns();
        } catch (error) {
            console.error('Task execution failed:', error);
            this.showToast(`Task failed: ${error.message}`, 'error');
        }
    }

    async sendKiloMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        
        if (!message) return;

        // Add user message
        this.addChatMessage(message, 'user');
        input.value = '';

        // Simulate AI response (placeholder)
        setTimeout(() => {
            this.addChatMessage('I understand you want help with your substrate. Could you provide more details about what you\'d like to accomplish?', 'assistant');
        }, 1000);
    }

    addChatMessage(text, role) {
        const messages = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${role}`;
        
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    ${role === 'user' 
                        ? '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'
                        : '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'}
                </svg>
            </div>
            <div class="message-content">
                <div class="message-text">${escapeHtml(text)}</div>
            </div>
        `;
        
        messages.appendChild(messageDiv);
        messages.scrollTop = messages.scrollHeight;
    }

    // Real-time Updates
    startRealtimeUpdates() {
        // Use Server-Sent Events for real-time updates
        if (typeof EventSource !== 'undefined') {
            this.eventSource = new EventSource('/stream/metrics');
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleRealtimeUpdate(data);
                } catch (error) {
                    console.error('Failed to parse SSE data:', error);
                }
            };

            this.eventSource.onerror = () => {
                console.error('SSE connection error');
                this.eventSource.close();
                // Reconnect after 5 seconds
                setTimeout(() => this.startRealtimeUpdates(), 5000);
            };
        } else {
            // Fallback to polling
            setInterval(() => {
                if (this.currentPage !== 'agents' && this.currentPage !== 'pipelines') {
                    this.refreshData();
                }
            }, 10000);
        }
    }

    handleRealtimeUpdate(data) {
        // Update metrics in real-time
        if (data.metrics) {
            this.updateMetrics(data.metrics);
        }
    }

    async refreshData() {
        await this.loadInitialData();
        await this.loadPageData(this.currentPage);
    }

    // Utilities
    async fetchAPI(endpoint, options = {}) {
        const { headers: optionHeaders, ...rest } = options;
        const headers = {
            'Content-Type': 'application/json',
            ...optionHeaders
        };
        if (window.PANEL_AUTH_TOKEN) {
            headers['Authorization'] = 'Bearer ' + window.PANEL_AUTH_TOKEN;
        }
        const response = await fetch(endpoint, {
            ...rest,
            headers
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return response.json();
    }

    formatTime(timestamp) {
        if (!timestamp) return 'N/A';
        const date = new Date(timestamp);
        return date.toLocaleString();
    }

    timeAgo(timestamp) {
        if (!timestamp) return 'unknown';
        const date = new Date(timestamp);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);

        if (seconds < 60) return 'just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
        return `${Math.floor(seconds / 86400)} days ago`;
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // --- Vault: secure secrets UX (no plaintext at rest) ---

    async loadVault() {
        const grid = document.getElementById('vaultGrid');
        const summary = document.getElementById('vaultSummary');
        const badge = document.getElementById('vaultBadge');
        if (!grid) return;
        grid.innerHTML = '<div class="vault-loading">Loading vault…</div>';
        try {
            const data = await this.fetchAPI('/api/vault/status');
            this._vaultData = data;
            const s = data.summary || {};
            const backendLabel = s.backend === 'keyring' ? 'OS keyring' : 'encrypted file (Fernet)';
            summary.innerHTML = `
                <span class="vault-pill">${s.services_total ?? 0} services</span>
                <span class="vault-pill ok">${s.secured_total ?? 0} secured</span>
                <span class="vault-pill warn">${s.missing_total ?? 0} missing</span>
                <span class="vault-pill">backend: ${backendLabel}</span>
            `;
            if (badge) badge.textContent = String(s.missing_total ?? 0);
            this.renderVault((data.services || []));
        } catch (e) {
            grid.innerHTML = `<div class="error">Failed to load vault: ${escapeHtml(e.message)}</div>`;
        }
    }

    renderVault(services) {
        const grid = document.getElementById('vaultGrid');
        const q = (document.getElementById('vaultSearch')?.value || '').toLowerCase().trim();
        const filtered = q
            ? services.filter(s => (s.name || s.id).toLowerCase().includes(q) || (s.category || '').toLowerCase().includes(q))
            : services;
        if (!filtered.length) {
            grid.innerHTML = '<div class="empty">No services match.</div>';
            return;
        }
        grid.innerHTML = filtered.map(s => {
            const secured = !!s.has_secret;
            const conn = !!s.connected;
            return `
            <div class="vault-card glass" data-service="${escapeHtml(s.id)}">
                <div class="vault-card__head">
                    <div class="vault-card__icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                    </div>
                    <div style="flex:1">
                        <div class="vault-card__title">${escapeHtml(s.name)}</div>
                        <div class="vault-card__sub">${escapeHtml(s.id)} · ${escapeHtml(s.category || '')}${s.availability ? ' · ' + escapeHtml(s.availability) : ''}</div>
                    </div>
                    <span class="status-dot ${conn ? 'online' : 'offline'}" title="${conn ? 'Connected' : 'Disconnected'}"></span>
                </div>
                <div class="vault-card__meta">
                    <span class="pill ${secured ? 'secured' : 'missing'}">${secured ? '✓ Secret stored' : 'No secret yet'}</span>
                    <span class="pill">${secured ? escapeHtml(s.backend || 'keyring') : '—'}</span>
                    ${s.fingerprint ? `<span class="pill">fp:${escapeHtml(s.fingerprint)}</span>` : ''}
                    ${s.mode ? `<span class="pill">${escapeHtml(s.mode)} mode</span>` : ''}
                </div>
                <div class="vault-card__secret-row">
                    <input type="password" value="${secured ? '••••••••••' : ''}" readonly aria-label="Stored secret preview" style="opacity:.6">
                </div>
                <div class="vault-card__actions">
                    <button class="btn-primary btn-sm" onclick="panel.openVaultModal('${escapeHtml(s.id)}')">${secured ? 'Rotate' : 'Store secret'}</button>
                    ${secured ? `<button class="btn-secondary btn-sm" onclick="panel.confirmVaultDelete('${escapeHtml(s.id)}')">Remove</button>` : ''}
                    ${s.id === 'proton_mail' || s.id === 'proton_drive'
                        ? `<button class="btn-secondary btn-sm" onclick="panel.navigateTo('proton')">Open setup wizard</button>`
                        : (s.login_url ? `<a class="btn-secondary btn-sm" href="${escapeHtml(s.login_url)}" target="_blank" rel="noopener">Get token</a>` : '')}
                </div>
            </div>`;
        }).join('');

// TODO(dev-agent,vault-setup-wizard): The vault setup wizard button (navigateTo('proton')) was broken
// by a missing </div> that nested page-proton inside page-vault. The structural fix is in
// tests/test_control_panel_structure.py + the template, but we need deeper coverage:
//   1. Headless browser test (Playwright/puppeteer) that clicks 'Open setup wizard' from the
//      Vault page and asserts page-proton becomes visible (catches nesting regressions).
//   2. Same test for 'page-whatsapp-setup', 'page-config', 'page-agents', 'page-pipelines'.
//   3. Verify all nav-item sidebar clicks cycle through every .page div (no dead nav links).
//   4. Test the vault modal (openVaultModal, confirmVaultDelete) round-trips in headless mode.
//   5. Test that the Proton wizard 3-step flow completes (or at least advances) without console errors.
// See chains/local-agent-chain.yaml for the patch generation chain; use the free kilo-auto model.
// Tests belong in tests/test_panel_integration.py; keep all state isolated (no real keyring writes).
    }

    openVaultModal(serviceId) {
        const svc = (this._vaultData?.services || []).find(s => s.id === serviceId);
        if (!svc) return;
        const existing = document.getElementById('vaultModal');
        if (existing) existing.remove();
        const methods = (svc.auth_methods || []).map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m.replace(/_/g, ' '))}</option>`).join('');
        const root = document.getElementById('vaultModalRoot');
        const modeSel = svc.connected && svc.mode === 'write'
            ? `<option value="write" selected>write</option><option value="read">read</option>`
            : `<option value="read" selected>read</option><option value="write">write</option>`;
        root.innerHTML = `
        <div class="vault-modal-backdrop" id="vaultModal" role="dialog" aria-modal="true" aria-label="Store secret for ${escapeHtml(svc.name)}">
            <div class="vault-modal" onclick="event.stopPropagation()">
                <h3>${svc.has_secret ? 'Rotate secret' : 'Store secret'} — ${escapeHtml(svc.name)}</h3>
                <p class="hint">The value is written only to the OS keyring. It is never saved to config files, logs, or the audit trail, and this page will not show it again.</p>
                <div class="form-field">
                    <label for="vaultSecretInput">Secret / API token / password</label>
                    <input type="password" id="vaultSecretInput" placeholder="Paste the token…" autocomplete="new-password" autocapitalize="off" spellcheck="false">
                </div>
                ${methods ? `
                <div class="form-field">
                    <label for="vaultAuthMethod">Auth method</label>
                    <select id="vaultAuthMethod"><option value="">Default</option>${methods}</select>
                </div>` : ''}
                <div class="form-field">
                    <label for="vaultAccessMode">Access mode</label>
                    <select id="vaultAccessMode">${modeSel}</select>
                </div>
                <div class="form-field" id="vaultDirectiveField" style="display:none">
                    <label for="vaultDirective">Write directive (required for write mode)</label>
                    <input type="text" id="vaultDirective" placeholder="Describe the approved write scope…" autocomplete="off">
                </div>
                <div class="form-actions">
                    <button class="btn-secondary" onclick="document.getElementById('vaultModal').remove()">Cancel</button>
                    <button class="btn-primary" id="vaultSaveBtn" onclick="panel.submitVaultSecret('${escapeHtml(serviceId)}')">Save to keyring</button>
                </div>
            </div>
        </div>`;
        const modeSelEl = document.getElementById('vaultAccessMode');
        modeSelEl.addEventListener('change', () => {
            document.getElementById('vaultDirectiveField').style.display =
                modeSelEl.value === 'write' ? 'block' : 'none';
        });
        const input = document.getElementById('vaultSecretInput');
        input.focus();
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.submitVaultSecret(serviceId);
            if (e.key === 'Escape') document.getElementById('vaultModal')?.remove();
        });
    }

    async submitVaultSecret(serviceId) {
        const input = document.getElementById('vaultSecretInput');
        const secret = input ? input.value : '';
        if (!secret.trim()) {
            this.showToast('Secret value is required', 'warning');
            return;
        }
        const authMethod = document.getElementById('vaultAuthMethod')?.value || '';
        const mode = document.getElementById('vaultAccessMode')?.value || 'read';
        const directive = document.getElementById('vaultDirective')?.value || '';
        const btn = document.getElementById('vaultSaveBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
        try {
            const body = new URLSearchParams();
            body.append('service_id', serviceId);
            body.append('secret', secret);
            body.append('auth_method', authMethod);
            body.append('access_mode', mode);
            body.append('write_directive', directive);
            const res = await fetch('/api/vault/put', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': 'Bearer ' + (window.PANEL_AUTH_TOKEN || '')
                },
                body: body.toString()
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error?.message || data.detail || res.statusText);
            // Wipe the secret from the DOM immediately.
            if (input) { input.value = ''; input.type = 'text'; input.value = ''; }
            document.getElementById('vaultModal')?.remove();
            this.showToast('Secret stored in keyring for ' + serviceId, 'success');
            await this.loadVault();
        } catch (e) {
            if (btn) { btn.disabled = false; btn.textContent = 'Save to keyring'; }
            this.showToast('Failed: ' + e.message, 'error');
        }
    }

    async confirmVaultDelete(serviceId) {
        if (!window.confirm(`Remove the stored secret for ${serviceId} from the keyring and disconnect the integration?`)) return;
        try {
            const body = new URLSearchParams();
            body.append('service_id', serviceId);
            const res = await fetch('/api/vault/delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': 'Bearer ' + (window.PANEL_AUTH_TOKEN || '')
                },
                body: body.toString()
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error?.message || data.detail || res.statusText);
            this.showToast('Secret removed for ' + serviceId, 'success');
            await this.loadVault();
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        }
    }

    // --- Proton Mail & Drive setup (keyring-backed; no terminal secrets) ---
    async loadProton() {
        const statusEl = document.getElementById('protonStatus');
        if (!statusEl) return;
        statusEl.innerHTML = '<div class="proton-loading">Checking status…</div>';
        try {
            const data = await this.fetchAPI('/api/proton/status');
            this._protonData = data;
            this.renderProton(data);
            // Show the step that matches current state.
            const stored = !!(data.mail?.email_stored && data.mail?.password_stored);
            const connected = !!(data.mail?.connected);
            this._showProtonStep(connected ? 3 : (stored ? 2 : 1));
        } catch (e) {
            statusEl.innerHTML = `<div class="error">Failed to load Proton status: ${escapeHtml(e.message)}</div>`;
        }
    }

    renderProton(data) {
        const statusEl = document.getElementById('protonStatus');
        const m = data.mail || {};
        const d = data.drive || {};
        if (statusEl) statusEl.innerHTML = `
            <div class="proton-status-pills">
                <span class="vault-pill ${m.bridge_active ? 'ok' : ''}">Bridge: ${m.bridge_active ? 'running' : 'stopped'}</span>
                <span class="vault-pill ${m.email_stored ? 'ok' : ''}">Email stored: ${m.email_stored ? 'yes' : 'no'}</span>
                <span class="vault-pill ${m.password_stored ? 'ok' : ''}">Password stored: ${m.password_stored ? 'yes' : 'no'}</span>
                <span class="vault-pill ${m.connected ? 'ok' : ''}">Connected: ${m.connected ? 'yes' : 'no'}</span>
                <span class="vault-pill">IMAP: ${escapeHtml(m.imap || '')}</span>
            </div>
            <p class="muted" style="margin-top:8px">${escapeHtml(m.note || '')}</p>
        `;
        const mailState = document.getElementById('protonMailState');
        if (mailState) mailState.innerHTML = m.connected
            ? `<span class="pill secured">✓ Bridge account connected (${escapeHtml(m.email || '')})</span>`
            : `<span class="pill missing">Not authenticated — click Connect to re-login via the bridge CLI.</span>`;
        const storedState = document.getElementById('protonStoredState');
        if (storedState) storedState.innerHTML = `
            <span class="pill ${m.email_stored ? 'secured' : 'missing'}">Email: ${m.email_stored ? escapeHtml(m.email || 'stored') : 'not stored'}</span>
            <span class="pill ${m.password_stored ? 'secured' : 'missing'}">Password: ${m.password_stored ? 'stored in keyring' : 'not stored'}</span>
            <span class="pill ${m.connected ? 'secured' : 'missing'}">Bridge: ${m.connected ? 'connected' : 'not connected'}</span>
        `;
        const driveState = document.getElementById('protonDriveState');
        if (driveState) {
            const remotes = (d.remotes || []).map(r => escapeHtml(r.name)).join(', ') || 'none';
            driveState.innerHTML = `<span class="pill ${d.remotes && d.remotes.length ? 'secured' : 'missing'}">Drive remotes: ${remotes}</span>`;
        }
        const lastRun = document.getElementById('protonLastRun');
        if (lastRun) {
            const lr = data.last_run || {};
            lastRun.textContent = JSON.stringify(lr, null, 2);
        }
    }

    async _protonStoreInputs() {
        const email = document.getElementById('protonEmail')?.value.trim() || '';
        const password = document.getElementById('protonPassword')?.value || '';
        const totp = document.getElementById('protonTotp')?.value || '';
        return { email, password, totp };
    }

    async _wipeProtonSecrets() {
        const pw = document.getElementById('protonPassword');
        const tp = document.getElementById('protonTotp');
        if (pw) { pw.value = ''; pw.type = 'text'; pw.value = ''; pw.type = 'password'; }
        if (tp) { tp.value = ''; tp.type = 'text'; tp.value = ''; tp.type = 'password'; }
    }

    async _protonPost(endpoint, params) {
        const body = new URLSearchParams();
        if (params) {
            for (const [k, v] of Object.entries(params)) {
                if (v) body.append(k, v);
            }
        }
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Bearer ' + (window.PANEL_AUTH_TOKEN || '')
            },
            body: body.toString()
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error?.message || data.detail || res.statusText);
        return data;
    }

    async _showProtonStep(n) {
        for (let i = 1; i <= 3; i++) {
            const el = document.getElementById(`proton-step-${i}`);
            if (el) el.style.display = (i === n) ? '' : 'none';
        }
        document.querySelectorAll('#page-proton .setup-progress .progress-step').forEach((s, idx) => {
            s.classList.toggle('active', (idx + 1) === n);
        });
    }

    protonBackTo1() { this._showProtonStep(1); }
    protonBackTo2() { this._showProtonStep(2); }

    async protonStore() {
        const { email, password, totp } = await this._protonStoreInputs();
        if (!email || !password) { this.showToast('Email and password are required', 'warning'); return; }
        const btn = event?.target;
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
        try {
            await this._protonPost('/api/proton/store', { email, password, totp });
            this._wipeProtonSecrets();
            this.showToast('Credentials stored in the OS keyring', 'success');
            this._showProtonStep(2);
            await this.loadProton();
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Save securely & continue'; }
        }
    }

    async protonConnect() {
        const { email } = await this._protonStoreInputs();
        if (!window.confirm('Start the Proton Bridge re-login now? This runs the local bridge CLI using your stored keyring credentials (no secrets are shown).')) return;
        this._showProtonStep(3);
        const btn = event?.target || document.getElementById('protonConnectBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Connecting…'; }
        try {
            await this._protonPost('/api/proton/connect', { email });
            this.showToast('Bridge login started in the background — polling result…', 'info');
            this.pollProtonResult();
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Connect Bridge'; }
        }
    }

    async pollProtonResult() {
        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 2000));
            try {
                const data = await this.fetchAPI('/api/proton/last-run');
                const s = data.status;
                if (s === 'ok' || s === 'partial' || s === 'failed') {
                    this.renderProton({ ...this._protonData, last_run: data });
                    this.showToast('Bridge connect finished: ' + s, s === 'ok' ? 'success' : 'warning');
                    await this.loadProton();
                    return;
                }
            } catch (e) { /* transient */ }
        }
        this.showToast('Still connecting — check the Last run panel.', 'info');
    }

    async protonVerify() {
        if (!window.confirm('Run a one-time verification probe (IMAP login + Drive remote check)?')) return;
        const btn = document.getElementById('protonVerifyBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Verifying…'; }
        try {
            const res = await this._protonPost('/api/proton/verify', {});
            const el = document.getElementById('protonLastRun');
            if (el) el.textContent = JSON.stringify(res, null, 2);
            this.showToast(res.ok ? 'Proton is reachable ✔' : 'Proton verification incomplete', res.ok ? 'success' : 'warning');
            await this.loadProton();
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
        }
    }

    async protonTestEmail() {
        if (!window.confirm('Send a test email now? (outbound — human-initiated)')) return;
        const btn = document.getElementById('protonTestEmailBtn');
        if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
        try {
            const res = await this._protonPost('/api/proton/test-email', {});
            const el = document.getElementById('protonLastRun');
            if (el) el.textContent = JSON.stringify(res, null, 2);
            this.showToast(res.ok ? 'Test email sent ✔' : 'Test email failed', res.ok ? 'success' : 'error');
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Send test email'; }
        }
    }

    async protonDisconnect() {
        if (!window.confirm('Remove Proton credentials from the keyring and mark disconnected? Services will idle without retrying.')) return;
        const btn = document.getElementById('protonDisconnectBtn');
        if (btn) { btn.disabled = true; }
        try {
            await this._protonPost('/api/proton/disconnect', {});
            this.showToast('Proton disconnected', 'success');
            await this.loadProton();
        } catch (e) {
            this.showToast('Failed: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; }
        }
    }

    // WhatsApp Setup Methods
    currentStep = 1;
    qrTimerInterval = null;
    connectionCheckInterval = null;

    nextStep(step) {
        this.currentStep = step;
        this.updateStepDisplay();
    }

    prevStep(step) {
        this.currentStep = step;
        this.updateStepDisplay();
    }

    updateStepDisplay() {
        // Hide all steps
        document.querySelectorAll('.setup-step').forEach(step => {
            step.classList.add('hidden');
        });

        // Show current step
        const currentStepEl = document.getElementById(`step-${this.currentStep}`);
        if (currentStepEl) {
            currentStepEl.classList.remove('hidden');
        }

        // Update progress indicators
        document.querySelectorAll('.progress-step').forEach(stepEl => {
            const stepNum = parseInt(stepEl.dataset.step);
            stepEl.classList.remove('active', 'completed');
            
            if (stepNum < this.currentStep) {
                stepEl.classList.add('completed');
            } else if (stepNum === this.currentStep) {
                stepEl.classList.add('active');
            }
        });
    }

    async saveConfig() {
        const verifyField = document.getElementById('whatsappVerifyToken');
        const tokenField = document.getElementById('whatsappAccessToken');
        const appField = document.getElementById('whatsappAppSecret');
        const isMasked = (v) => v === '••••••••••' || v.startsWith('••');
        const cfg = {
            phone_number_id: document.getElementById('whatsappPhoneId').value,
            access_token: tokenField.value,
            app_secret: appField.value,
            verify_token: verifyField.value,
            webhook_url: document.getElementById('whatsappWebhookUrl').value
        };
        // If the user didn't rotate a secret, null it so the server reuses the keyring value.
        if (cfg.access_token && isMasked(cfg.access_token)) cfg.access_token = '';
        if (cfg.app_secret && isMasked(cfg.app_secret)) cfg.app_secret = '';
        if (cfg.verify_token && isMasked(cfg.verify_token)) cfg.verify_token = '';

        // Validate required fields
        if (!cfg.phone_number_id || !cfg.access_token || !cfg.app_secret || !cfg.verify_token) {
            this.showToast('Please fill in all required fields (re-enter a secret if it shows •••)', 'error');
            return;
        }

        try {
            await this.fetchAPI('/api/gateway/whatsapp/config', {
                method: 'POST',
                body: JSON.stringify(cfg)
            });

            this.showToast('Configuration saved successfully', 'success');
            this.nextStep(3);
        } catch (error) {
            this.showToast(`Failed to save configuration: ${error.message}`, 'error');
        }
    }

    async generateQR() {
        try {
            const response = await this.fetchAPI('/api/gateway/whatsapp/qr', {
                method: 'POST'
            });

            const qrContainer = document.getElementById('qrContainer');
            qrContainer.innerHTML = `<img src="${escapeHtml(response.qr_code)}" alt="WhatsApp QR Code">`;

            document.getElementById('generateQrBtn').classList.add('hidden');
            document.getElementById('refreshQrBtn').classList.remove('hidden');

            // Start QR timer
            this.startQRTimer(response.expires_in || 300);

            // Start connection polling
            this.startConnectionPolling();

            this.showToast('QR code generated. Scan with WhatsApp to connect.', 'info');
        } catch (error) {
            this.showToast(`Failed to generate QR code: ${error.message}`, 'error');
        }
    }

    async refreshQR() {
        if (this.qrTimerInterval) {
            clearInterval(this.qrTimerInterval);
        }
        await this.generateQR();
    }

    startQRTimer(seconds) {
        const countdownEl = document.getElementById('qrCountdown');
        let remaining = seconds;

        this.qrTimerInterval = setInterval(() => {
            remaining--;
            const minutes = Math.floor(remaining / 60);
            const secs = remaining % 60;
            countdownEl.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;

            if (remaining <= 0) {
                clearInterval(this.qrTimerInterval);
                countdownEl.textContent = 'Expired';
                this.showToast('QR code expired. Please refresh.', 'warning');
            }
        }, 1000);
    }

    startConnectionPolling() {
        this.connectionCheckInterval = setInterval(async () => {
            try {
                const status = await this.fetchAPI('/api/gateway/whatsapp/status');
                this.updateConnectionStatus(status);

                if (status.connected) {
                    clearInterval(this.connectionCheckInterval);
                    this.nextStep(4);
                    this.showToast('WhatsApp connected successfully!', 'success');
                }
            } catch (error) {
                console.error('Connection check failed:', error);
            }
        }, 3000);
    }

    updateConnectionStatus(status) {
        const statusEl = document.getElementById('connectionStatus');
        const indicator = document.getElementById('connectionIndicator');
        const titleEl = document.getElementById('connectionTitle');
        const messageEl = document.getElementById('connectionMessage');

        if (status.connected) {
            statusEl.textContent = 'Connected';
            statusEl.className = 'step-status connected';
            indicator.querySelector('.status-icon').className = 'status-icon success';
            titleEl.textContent = 'Connection Established';
            messageEl.textContent = 'Your WhatsApp is now connected to the Substrate';
        } else if (status.error) {
            statusEl.textContent = 'Error';
            statusEl.className = 'step-status error';
            indicator.querySelector('.status-icon').className = 'status-icon error';
            titleEl.textContent = 'Connection Failed';
            messageEl.textContent = status.error_message || 'An error occurred during connection';
        } else {
            statusEl.textContent = 'Pending';
            statusEl.className = 'step-status';
            indicator.querySelector('.status-icon').className = 'status-icon pending';
            titleEl.textContent = 'Waiting for Connection';
            messageEl.textContent = 'Scan the QR code with WhatsApp to establish connection';
        }
    }

    async sendTestMessage() {
        const message = document.getElementById('testMessage').value;
        const resultEl = document.getElementById('testResult');

        if (!message) {
            this.showToast('Please enter a test message', 'warning');
            return;
        }

        try {
            const response = await this.fetchAPI('/api/gateway/whatsapp/test', {
                method: 'POST',
                body: JSON.stringify({ message })
            });

            resultEl.classList.remove('hidden', 'error');
            resultEl.classList.add('success');
            resultEl.innerHTML = `
                <strong>✓ Test message sent successfully!</strong>
                <p>Check your WhatsApp for the test message.</p>
            `;

            this.showToast('Test message sent', 'success');
        } catch (error) {
            resultEl.classList.remove('hidden', 'success');
            resultEl.classList.add('error');
            resultEl.innerHTML = `
                <strong>✗ Failed to send test message</strong>
                <p>Error: ${escapeHtml(error.message)}</p>
            `;

            this.showToast(`Failed to send test: ${error.message}`, 'error');
        }
    }

    async completeSetup() {
        try {
            await this.fetchAPI('/api/gateway/whatsapp/complete', {
                method: 'POST'
            });

            this.showToast('WhatsApp setup completed successfully!', 'success');
            
            // Navigate to integrations page
            setTimeout(() => {
                this.navigateTo('integrations');
            }, 1500);
        } catch (error) {
            this.showToast(`Failed to complete setup: ${error.message}`, 'error');
        }
    }

    toggleTroubleshooting() {
        const content = document.getElementById('troubleshootingContent');
        const toggle = document.getElementById('troubleshootingToggle');
        
        content.classList.toggle('hidden');
        toggle.textContent = content.classList.contains('hidden') ? 'Show' : 'Hide';
    }

    async viewLogs() {
        try {
            const response = await this.fetchAPI('/api/gateway/whatsapp/logs');
            
            // Create a modal or new window to display logs
            const logWindow = window.open('', 'GatewayLogs', 'width=800,height=600');
            logWindow.document.write(`
                <html>
                <head>
                    <title>WhatsApp Gateway Logs</title>
                    <style>
                        body { font-family: monospace; background: #1a1a2e; color: #e8e8f0; padding: 20px; }
                        pre { white-space: pre-wrap; word-wrap: break-word; }
                    </style>
                </head>
                <body>
                    <h1>WhatsApp Gateway Logs</h1>
                    <pre>${escapeHtml(response.logs)}</pre>
                </body>
                </html>
            `);
        } catch (error) {
            this.showToast(`Failed to load logs: ${error.message}`, 'error');
        }
    }

    async loadWhatsAppConfig() {
        try {
            const config = await this.fetchAPI('/api/gateway/whatsapp/config');
            
            if (config.phone_number_id) {
                document.getElementById('whatsappPhoneId').value = config.phone_number_id;
            }
            // Secrets are never returned to the browser; only configured flags.
            if (config.verify_token_configured) {
                document.getElementById('whatsappVerifyToken').value = '••••••••••';
                document.getElementById('whatsappVerifyToken').dataset.configured = '1';
            }
            if (config.webhook_url) {
                document.getElementById('whatsappWebhookUrl').value = config.webhook_url;
            }
        } catch (error) {
            // Config not loaded yet, that's okay
            console.log('No existing config found');
        }
    }
}

// Initialize control panel when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.controlPanel = new ControlPanel();
    window.panel = window.controlPanel;
});
