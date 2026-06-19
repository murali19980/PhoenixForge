// ============================================
// PHOENIXFORGE - script.js (IMPROVED v3.1)
// Better architecture, error handling, XSS protection, and UX
// ============================================

'use strict';

// ============================================
// CONFIGURATION
// ============================================
const CONFIG = {
    POLL_INTERVAL: 2000,
    MAX_POLL_ATTEMPTS: 150,
    API_BASE: '',
    TOAST_DURATION: 3000,
    MAX_INPUT_LENGTH: 150
};

// ============================================
// STATE MANAGEMENT
// ============================================
const AppState = {
    isAnalyzing: false,
    pollAttempts: 0,
    currentTaskId: null,
    abortController: null
};

// ============================================
// DOM ELEMENTS CACHE
// ============================================
const DOM = {};

function cacheDOM() {
    const ids = [
        'analyzeForm', 'ideaInput', 'submitBtn', 'btnText', 'btnSpinner',
        'loader', 'skeletonScreen', 'results', 'heatmapContainer', 'fixesContainer',
        'rawContent', 'rawContainer', 'toggleRawBtn', 'flowchartCard', 'mermaidDiagram',
        'historySidebar', 'openHistoryBtn', 'closeHistoryBtn', 'historyList',
        'copySummaryBtn', 'summaryCard', 'summaryContent',
        'toggleSourcesBtn', 'sourcesCollapse', 'sourcesArrow', 'sourcesCollapseContainer', 'sourceCount',
        'graveyardContent', 'graveyardContainer',
        'pipelineCard', 'stepGatherIcon', 'stepGatherDesc', 'stepCleanIcon', 'stepCleanDesc',
        'stepOrganizeIcon', 'stepOrganizeDesc', 'stepPresentIcon', 'stepPresentDesc',
        'exportPdfBtn', 'exportWordBtn', 'errorBanner', 'errorMessage', 'dismissError',
        'charCount', 'progressBar', 'progressPercent', 'toast', 'toastMessage', 'clearHistoryBtn',
        'coordinatorLearning', 'coordinatorScore'
    ];
    ids.forEach(id => { DOM[id] = document.getElementById(id); });
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'success') {
    if (!DOM.toast || !DOM.toastMessage) return;
    const colors = {
        success: { border: 'border-emerald-500/30', bg: 'bg-emerald-950/20', text: 'text-emerald-300', icon: '✅' },
        error: { border: 'border-red-500/30', bg: 'bg-red-950/20', text: 'text-red-300', icon: '❌' },
        warning: { border: 'border-yellow-500/30', bg: 'bg-yellow-950/20', text: 'text-yellow-300', icon: '⚠️' }
    };
    const style = colors[type] || colors.success;
    DOM.toast.className = `fixed bottom-6 right-6 z-50 glass rounded-xl px-4 py-3 flex items-center gap-2 border ${style.border} ${style.bg} toast-visible`;
    DOM.toastMessage.className = `text-sm font-medium ${style.text}`;
    DOM.toastMessage.textContent = message;
    DOM.toast.querySelector('span:first-child').textContent = style.icon;
    
    // Clear any previous transition classes
    DOM.toast.style.transform = 'translateY(0)';
    DOM.toast.style.opacity = '1';
    
    setTimeout(() => {
        DOM.toast.style.transform = 'translateY(20px)';
        DOM.toast.style.opacity = '0';
    }, CONFIG.TOAST_DURATION);
}

function showError(message) {
    if (!DOM.errorBanner || !DOM.errorMessage) { showToast(message, 'error'); return; }
    DOM.errorMessage.textContent = message;
    DOM.errorBanner.classList.remove('hidden');
    DOM.errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideError() {
    if (DOM.errorBanner) DOM.errorBanner.classList.add('hidden');
}

function updateCharCount() {
    if (!DOM.ideaInput || !DOM.charCount) return;
    const len = DOM.ideaInput.value.length;
    DOM.charCount.textContent = `${len}/${CONFIG.MAX_INPUT_LENGTH}`;
    if (len > CONFIG.MAX_INPUT_LENGTH * 0.9) {
        DOM.charCount.className = 'text-xs mt-1 text-right text-red-500 font-semibold';
    } else {
        DOM.charCount.className = 'text-xs mt-1 text-right text-slate-600';
    }
}

function updateProgress(percent, text = '') {
    if (DOM.progressBar) {
        DOM.progressBar.style.width = `${Math.min(percent, 100)}%`;
        DOM.progressBar.setAttribute('aria-valuenow', Math.min(percent, 100));
    }
    if (DOM.progressPercent) {
        DOM.progressPercent.textContent = text || `${Math.round(percent)}%`;
    }
}

function resetPipeline() {
    const steps = [
        { icon: 'stepGatherIcon', desc: 'stepGatherDesc', text: '🔍', label: 'Scraping web signals' },
        { icon: 'stepCleanIcon', desc: 'stepCleanDesc', text: '🧹', label: 'Deduplicating inputs' },
        { icon: 'stepOrganizeIcon', desc: 'stepOrganizeDesc', text: '🧠', label: 'Extracting failure nodes' },
        { icon: 'stepPresentIcon', desc: 'stepPresentDesc', text: '📊', label: 'Compiling final report' }
    ];
    steps.forEach(step => {
        const iconEl = document.getElementById(step.icon);
        const descEl = document.getElementById(step.desc);
        if (iconEl) {
            iconEl.className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-slate-700 bg-slate-900 text-slate-400 text-sm font-bold mb-2 transition-all duration-300';
            iconEl.textContent = step.text;
        }
        if (descEl) descEl.textContent = step.label;
    });
    if (DOM.pipelineCard) DOM.pipelineCard.classList.add('hidden');
}

function completePipelineStep(stepName, detail) {
    const iconMap = { gather: 'stepGatherIcon', clean: 'stepCleanIcon', organize: 'stepOrganizeIcon', present: 'stepPresentIcon' };
    const descMap = { gather: 'stepGatherDesc', clean: 'stepCleanDesc', organize: 'stepOrganizeDesc', present: 'stepPresentDesc' };
    const iconEl = document.getElementById(iconMap[stepName]);
    const descEl = document.getElementById(descMap[stepName]);
    
    if (iconEl) {
        iconEl.className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-emerald-500 bg-emerald-950 text-emerald-400 text-sm font-bold mb-2 shadow-[0_0_15px_rgba(16,185,129,0.2)] transition-all duration-300';
        iconEl.textContent = '✅';
    }
    if (descEl && detail) {
        descEl.textContent = detail;
    }
}

// ============================================
// DATA LOADERS & API CALLS
// ============================================

async function loadCoordinatorStatus() {
    try {
        const response = await fetch('/api/coordinator/status');
        if (!response.ok) return;
        const data = await response.json();
        if (DOM.coordinatorLearning) DOM.coordinatorLearning.textContent = data.summary || '';
        if (DOM.coordinatorScore) DOM.coordinatorScore.textContent = data.best_score ? data.best_score.toFixed(2) : '0.00';
    } catch (e) {
        console.error("Failed to load coordinator status:", e);
    }
}

async function clearHistory() {
    if (!confirm("Are you sure you want to delete all historical analysis records? This cannot be undone.")) return;
    try {
        const response = await fetch('/api/history/clear', { method: 'POST' });
        if (response.ok) {
            showToast("History vault successfully cleared!");
            loadHistory();
            loadCoordinatorStatus();
            DOM.results.classList.add('hidden');
        } else {
            showToast("Failed to clear history vault.", "error");
        }
    } catch (e) {
        showError("Network error: " + e.message);
    }
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        if (!response.ok) return;
        const data = await response.json();
        const history = data.history || [];
        
        if (history.length === 0) {
            DOM.historyList.innerHTML = `<p class="text-xs text-slate-500 text-center py-4">No recent analyses found.</p>`;
            return;
        }
        
        DOM.historyList.innerHTML = '';
        history.forEach(item => {
            const dateStr = new Date(item.timestamp).toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'});
            const itemDiv = document.createElement('div');
            itemDiv.className = 'glass p-4 rounded-xl border border-white/5 space-y-2 hover:border-red-500/30 transition-all history-item';
            
            const escapedIdea = escapeHtml(item.idea);
            const escapedSummary = escapeHtml(item.summary || 'Click view to load results.');
            const scoreLabel = item.quality_score ? `<span class="bg-red-950/60 text-red-400 border border-red-900/30 text-[9px] px-1.5 py-0.5 rounded font-mono">Score: ${item.quality_score.toFixed(2)}</span>` : '';
            
            itemDiv.innerHTML = `
                <div class="flex justify-between items-start">
                    <span class="text-xs font-semibold text-slate-200 truncate max-w-[150px]" title="${escapedIdea}">${escapedIdea}</span>
                    <span class="text-[10px] text-slate-500">${dateStr}</span>
                </div>
                <p class="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">${escapedSummary}</p>
                <div class="flex gap-2 justify-between items-center pt-1">
                    <div>${scoreLabel}</div>
                    <div class="flex gap-2">
                        <button class="reanalyze-btn text-[10px] bg-red-950/40 hover:bg-red-900/40 text-red-400 px-2.5 py-1 rounded-lg border border-red-900/30 transition-colors focus:outline-none" data-idea="${escapedIdea}">🔄 Re-run</button>
                        <button class="load-btn text-[10px] bg-slate-900/80 hover:bg-slate-800 text-slate-300 px-2.5 py-1 rounded-lg border border-white/5 transition-colors focus:outline-none" data-id="${item.id}">👁️ View</button>
                    </div>
                </div>
            `;
            
            // Bind buttons
            itemDiv.querySelector('.reanalyze-btn').onclick = (e) => {
                const idea = e.target.getAttribute('data-idea');
                DOM.ideaInput.value = idea;
                DOM.historySidebar.classList.add('translate-x-full');
                DOM.historySidebar.setAttribute('aria-hidden', 'true');
                performAnalysis(idea);
            };
            
            itemDiv.querySelector('.load-btn').onclick = async (e) => {
                const id = e.target.getAttribute('data-id');
                DOM.historySidebar.classList.add('translate-x-full');
                DOM.historySidebar.setAttribute('aria-hidden', 'true');
                
                // Show loader and skeletons
                DOM.loader.classList.remove('hidden');
                DOM.skeletonScreen.classList.remove('hidden');
                DOM.results.classList.add('hidden');
                hideError();
                
                try {
                    const res = await fetch(`/api/history/${id}`);
                    if (!res.ok) throw new Error("Could not load history details");
                    const detail = await res.json();
                    DOM.ideaInput.value = detail.idea || DOM.ideaInput.value;
                    updateCharCount();
                    renderResults(detail);
                    DOM.results.classList.remove('hidden');
                } catch (err) {
                    showError("Error loading historical analysis: " + err.message);
                } finally {
                    DOM.loader.classList.add('hidden');
                    DOM.skeletonScreen.classList.add('hidden');
                }
            };
            
            DOM.historyList.appendChild(itemDiv);
        });
    } catch (err) {
        console.error("Failed to load history list: ", err);
    }
}

async function performAnalysis(idea) {
    if (AppState.isAnalyzing) return;
    AppState.isAnalyzing = true;
    hideError();
    resetPipeline();

    // Show loader, skeletons and disable submit
    DOM.loader.classList.remove('hidden');
    DOM.skeletonScreen.classList.remove('hidden');
    DOM.results.classList.add('hidden');
    DOM.submitBtn.disabled = true;
    DOM.btnSpinner.classList.remove('hidden');
    DOM.btnText.textContent = "Processing...";
    
    updateProgress(5, "Queueing task...");

    // Abort previous polling if any
    if (AppState.abortController) {
        AppState.abortController.abort();
    }
    AppState.abortController = new AbortController();

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idea: idea })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Analysis request rejected.');
        }

        const initialData = await response.json();
        const taskId = initialData.task_id;
        AppState.currentTaskId = taskId;

        // Reset elements in case they are collapsed
        if (DOM.sourcesCollapse && !DOM.sourcesCollapse.classList.contains('hidden')) {
            DOM.sourcesCollapse.classList.add('hidden');
            if (DOM.sourcesArrow) DOM.sourcesArrow.style.transform = 'rotate(0deg)';
        }

        let done = false;
        let finalData = null;
        let attempts = 0;

        while (!done) {
            if (attempts++ > CONFIG.MAX_POLL_ATTEMPTS) {
                throw new Error("Analysis timed out. Please try again.");
            }
            
            // Wait 2 seconds between polls
            await new Promise((resolve, reject) => {
                const timeoutId = setTimeout(resolve, CONFIG.POLL_INTERVAL);
                AppState.abortController.signal.addEventListener('abort', () => {
                    clearTimeout(timeoutId);
                    reject(new DOMException("Aborted", "AbortError"));
                });
            });
            
            const statusRes = await fetch(`/api/status/${taskId}`, { signal: AppState.abortController.signal });
            if (!statusRes.ok) {
                throw new Error("Failed to fetch background task status.");
            }
            const statusData = await statusRes.json();
            if (!statusData) continue;

            if (statusData.status === 'completed') {
                done = true;
                finalData = statusData.results;
            } else if (statusData.status === 'failed') {
                throw new Error(statusData.message || "Scraper or local LLM failed.");
            } else {
                // Update live loader messages
                const step = statusData.current_step || "Running research...";
                const msg = statusData.message || "";
                
                DOM.loaderTitle.textContent = "Researching and Analyzing...";
                DOM.loaderSubtitle.textContent = step;
                
                if (step.includes("Found") || step.includes("Scraping")) {
                    completePipelineStep('gather', step);
                    const total = statusData.total_articles || 15;
                    const cur = statusData.extracted_count || 0;
                    const percent = Math.min((cur / total) * 45 + 10, 55);
                    updateProgress(percent, `Extracted ${cur}/${total} sources. ${msg}`);
                } else if (step.includes("Analyzing")) {
                    completePipelineStep('gather', "Gathering complete");
                    completePipelineStep('clean', "Boilerplate and duplicates removed");
                    completePipelineStep('organize', "Running Coroner LLM...");
                    updateProgress(75, "Extracting Cost, Tech, and UX failure signals...");
                } else {
                    updateProgress(15, msg);
                }
            }
        }

        if (finalData) {
            updateProgress(100, "Done!");
            completePipelineStep('present', "Report compiled successfully");
            renderResults(finalData);
            DOM.results.classList.remove('hidden');
            showToast("Risk analysis complete!", "success");
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            showError('Analysis Error: ' + err.message);
        }
    } finally {
        AppState.isAnalyzing = false;
        DOM.loader.classList.add('hidden');
        DOM.skeletonScreen.classList.add('hidden');
        DOM.submitBtn.disabled = false;
        DOM.btnSpinner.classList.add('hidden');
        DOM.btnText.textContent = "🔥 Analyze Risks";
        loadHistory(); // Refresh history list
        loadCoordinatorStatus(); // Refresh coordinator learning card
    }
}

// ============================================
// RESULT RENDERER
// ============================================

function renderResults(data) {
    const fixes = data.fixes || [];
    
    // Parse risks and pivots for human translation
    const costRisks = fixes.filter(f => f.category === 'Cost').map(f => f.issue);
    const techRisks = fixes.filter(f => f.category === 'Tech').map(f => f.issue);
    const uxRisks = fixes.filter(f => f.category === 'UX').map(f => f.issue);
    const pivots = fixes.filter(f => f.category === 'General').map(f => f.issue);

    // 1. RENDER EXECUTIVE SUMMARY
    const idea = escapeHtml(DOM.ideaInput.value.trim());
    
    let summaryText = "";
    const allRisksText = [...uxRisks, ...techRisks, ...costRisks].join(", ");
    if (allRisksText) {
        summaryText += `Your "${idea}" idea faces several critical threats: {allRisksText}. `.replace('{allRisksText}', allRisksText);
    } else {
        summaryText += `Your "${idea}" idea faces low direct market friction, but you should proceed with caution. `;
    }
    
    const pivotsText = pivots.map(p => p.replace(/Pivot Strategy \d+:\s*/i, '')).join(", and ");
    if (pivotsText) {
        summaryText += `To survive and capture value, consider these pivot options: ${pivotsText}.`;
    }
    
    DOM.summaryContent.textContent = summaryText;
    DOM.summaryCard.classList.remove('hidden');

    // RENDER PIPELINE PROGRESS TRACKER
    const pipeline = data.pipeline || {};
    if (DOM.pipelineCard && pipeline.gathered) {
        DOM.pipelineCard.classList.remove('hidden');
        completePipelineStep('gather', pipeline.gathered);
        completePipelineStep('clean', pipeline.cleaned);
        completePipelineStep('organize', pipeline.organized);
        completePipelineStep('present', pipeline.presented || "Report generated");
    }

    // 2. RENDER GRAVEYARD (NEGATIVE REVIEWS)
    const graveyardText = data.graveyard || 'No negative signals detected. Either this idea is perfect (unlikely) or the scrapers missed something.';
    DOM.graveyardContent.textContent = graveyardText;

    // RENDER SOURCES COLLAPSIBLE
    if (DOM.sourcesCollapseContainer && DOM.sourcesCollapse) {
        const urls = data.scraped_urls || [];
        if (urls.length > 0) {
            DOM.sourceCount.textContent = urls.length;
            DOM.sourcesCollapse.innerHTML = '';
            urls.forEach((url, index) => {
                let domain = 'Source';
                try {
                    domain = new URL(url).hostname;
                } catch(e) {}
                
                const link = document.createElement('a');
                link.href = url;
                link.target = '_blank';
                link.className = 'block text-xs text-red-400 hover:text-red-300 hover:underline py-1 truncate border-b border-white/5 last:border-0 source-link';
                link.innerHTML = `<span class="text-slate-500 mr-2 font-mono">[${index+1}]</span> <span class="font-semibold text-slate-300">${escapeHtml(domain)}</span> - <span class="text-slate-500 font-mono text-[10px]">${escapeHtml(url)}</span>`;
                DOM.sourcesCollapse.appendChild(link);
            });
            DOM.sourcesCollapseContainer.classList.remove('hidden');
        } else {
            DOM.sourcesCollapseContainer.classList.add('hidden');
        }
    }

    // 3. RENDER HEATMAP
    const displayNames = { Cost: "Financial & Scaling Risk", Tech: "Market & B2B Risk", UX: "UX & Retention Risk" };
    const categoryIcons = { Cost: "💸", Tech: "💼", UX: "👥" };

    DOM.heatmapContainer.innerHTML = '';
    const entries = Object.entries(data.heatmap || {});
    if (entries.length === 0) {
        DOM.heatmapContainer.innerHTML = `<div class="col-span-3 text-center text-gray-500">No risks detected.</div>`;
    } else {
        entries.forEach(([key, value]) => {
            const card = document.createElement('div');
            card.className = 'glass rounded-2xl p-6 border border-white/5 flex flex-col justify-between heatmap-card';
            
            const severityLabel = value >= 3 ? "Very High" : value === 2 ? "High" : value === 1 ? "Medium" : "Low";
            const severityColor = value >= 3 ? "text-red-500" : value === 2 ? "text-orange-500" : value === 1 ? "text-yellow-500" : "text-green-500";
            const intensity = value > 0 ? '🔥'.repeat(Math.min(value, 5)) : '✅';
            
            let desc = "";
            if (key === 'Cost') desc = costRisks[0] || "No financial or scaling bottlenecks detected.";
            else if (key === 'Tech') desc = techRisks[0] || "No market or validation bottlenecks detected.";
            else if (key === 'UX') desc = uxRisks[0] || "No retention or onboarding bottlenecks detected.";

            card.innerHTML = `
                <div>
                    <div class="text-2xl mb-2">${categoryIcons[key] || '📊'}</div>
                    <div class="text-sm font-semibold text-gray-400 uppercase tracking-wider">${displayNames[key] || key}</div>
                </div>
                <div class="mt-4">
                    <div class="text-2xl font-bold ${severityColor}">${severityLabel}</div>
                    <div class="text-xs text-gray-600 mt-1">${intensity} (${value} signals found)</div>
                    <p class="text-xs text-slate-400 mt-4 leading-relaxed border-t border-white/5 pt-3">${escapeHtml(desc)}</p>
                </div>
            `;
            DOM.heatmapContainer.appendChild(card);
        });
    }

    // RENDER VISUAL FLOWCHART
    const rawContentText = data.raw_content || '';
    const mermaidMatch = rawContentText.match(/```mermaid\s*([\s\S]*?)```/);
    if (mermaidMatch && mermaidMatch[1]) {
        const mermaidCode = mermaidMatch[1].trim();
        DOM.flowchartCard.classList.remove('hidden');
        DOM.mermaidDiagram.removeAttribute('data-processed');
        DOM.mermaidDiagram.textContent = mermaidCode;
        try {
            mermaid.run({ nodes: [DOM.mermaidDiagram] });
        } catch (e) {
            console.error("Mermaid rendering failed:", e);
        }
    } else {
        DOM.flowchartCard.classList.add('hidden');
    }

    // 4. RENDER FIXES
    DOM.fixesContainer.innerHTML = '';
    if (fixes.length === 0) {
        DOM.fixesContainer.innerHTML = `<div class="text-gray-500 text-center py-4">No specific fixes generated.</div>`;
    } else {
        fixes.forEach((fix, idx) => {
            const div = document.createElement('div');
            div.className = 'glass p-5 rounded-2xl border border-white/5 space-y-2 fix-card';
            
            let badgeText = '';
            let badgeColor = '';
            let title = '';
            let desc = fix.issue;
            
            if (fix.category === 'General') {
                badgeText = '💡 Pivot Strategy';
                badgeColor = 'bg-orange-500/20 text-orange-400';
                const parts = fix.issue.split(':');
                if (parts.length > 1) {
                    title = parts[0].trim();
                    desc = parts.slice(1).join(':').trim();
                } else {
                    title = `Strategy Option`;
                }
            } else {
                badgeText = `⚡ Quick Win (${fix.category})`;
                badgeColor = fix.category === 'Cost' ? 'bg-red-500/20 text-red-400' : fix.category === 'Tech' ? 'bg-amber-500/20 text-amber-400' : 'bg-yellow-500/20 text-yellow-400';
                title = `Mitigate ${fix.category} Failure`;
            }
            
            div.innerHTML = `
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold px-2.5 py-0.5 rounded-full ${badgeColor}">${badgeText}</span>
                    <span class="text-xs font-mono text-slate-600">Option ${idx + 1}</span>
                </div>
                <h4 class="text-base font-bold text-slate-100">${escapeHtml(title)}</h4>
                <p class="text-sm text-slate-400 leading-relaxed">${escapeHtml(desc)}</p>
            `;
            DOM.fixesContainer.appendChild(div);
        });
    }

    // RAW TOGGLE
    DOM.rawContent.textContent = data.raw_content || 'No raw content available.';
    DOM.rawContainer.classList.add('hidden');
    DOM.toggleRawBtn.textContent = '📄 View Raw Report';
    DOM.toggleRawBtn.onclick = () => {
        DOM.rawContainer.classList.toggle('hidden');
        DOM.toggleRawBtn.textContent = DOM.rawContainer.classList.contains('hidden') ? '📄 View Raw Report' : '📄 Hide Raw Report';
    };
}

// ============================================
// INITIALIZATION & BINDINGS
// ============================================

window.addEventListener('DOMContentLoaded', () => {
    cacheDOM();
    
    // Initialize Mermaid
    mermaid.initialize({ startOnLoad: false, theme: 'dark' });

    // Stdin char limits indicator
    if (DOM.ideaInput) {
        DOM.ideaInput.addEventListener('input', updateCharCount);
        updateCharCount();
    }

    // Dismiss Error Banner
    if (DOM.dismissError) {
        DOM.dismissError.onclick = hideError;
    }

    // Toggle Sidebar
    if (DOM.openHistoryBtn) {
        DOM.openHistoryBtn.onclick = () => {
            DOM.historySidebar.classList.remove('translate-x-full');
            DOM.historySidebar.setAttribute('aria-hidden', 'false');
            loadHistory();
        };
    }
    if (DOM.closeHistoryBtn) {
        DOM.closeHistoryBtn.onclick = () => {
            DOM.historySidebar.classList.add('translate-x-full');
            DOM.historySidebar.setAttribute('aria-hidden', 'true');
        };
    }

    // Clear History Button
    if (DOM.clearHistoryBtn) {
        DOM.clearHistoryBtn.onclick = clearHistory;
    }

    // Clipboard Copy logic
    if (DOM.copySummaryBtn) {
        DOM.copySummaryBtn.onclick = () => {
            const summaryText = DOM.summaryContent.textContent;
            if (!summaryText) return;
            
            navigator.clipboard.writeText(summaryText).then(() => {
                const originalText = DOM.copySummaryBtn.innerHTML;
                DOM.copySummaryBtn.innerHTML = "✅ Copied!";
                DOM.copySummaryBtn.classList.add('border-emerald-500/30', 'text-emerald-400');
                showToast("Summary copied to clipboard!");
                setTimeout(() => {
                    DOM.copySummaryBtn.innerHTML = originalText;
                    DOM.copySummaryBtn.classList.remove('border-emerald-500/30', 'text-emerald-400');
                }, 2000);
            }).catch(err => {
                console.error("Clipboard copy failed: ", err);
            });
        };
    }

    // Form submit listener
    if (DOM.analyzeForm) {
        DOM.analyzeForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const idea = DOM.ideaInput.value.trim();
            if (!idea) return;
            performAnalysis(idea);
        });
    }

    // Toggle Sources click binding
    if (DOM.toggleSourcesBtn && DOM.sourcesCollapse && DOM.sourcesArrow) {
        DOM.toggleSourcesBtn.onclick = () => {
            const isHidden = DOM.sourcesCollapse.classList.contains('hidden');
            if (isHidden) {
                DOM.sourcesCollapse.classList.remove('hidden');
                DOM.sourcesArrow.style.transform = 'rotate(180deg)';
            } else {
                DOM.sourcesCollapse.classList.add('hidden');
                DOM.sourcesArrow.style.transform = 'rotate(0deg)';
            }
        };
    }

    // Exports click bindings
    if (DOM.exportPdfBtn) {
        DOM.exportPdfBtn.onclick = () => { window.location.href = '/api/export/pdf'; };
    }
    if (DOM.exportWordBtn) {
        DOM.exportWordBtn.onclick = () => { window.location.href = '/api/export/word'; };
    }

    // Initial loads on boot
    loadHistory();
    loadCoordinatorStatus();
});
