// Initialize Mermaid
mermaid.initialize({ startOnLoad: false, theme: 'dark' });

const form = document.getElementById('analyzeForm');
const ideaInput = document.getElementById('ideaInput');
const submitBtn = document.getElementById('submitBtn');
const loader = document.getElementById('loader');
const skeletonScreen = document.getElementById('skeletonScreen');
const results = document.getElementById('results');

// Global DOM elements for renderResults
const heatmapContainer = document.getElementById('heatmapContainer');
const fixesContainer = document.getElementById('fixesContainer');
const rawContent = document.getElementById('rawContent');
const rawContainer = document.getElementById('rawContainer');
const toggleRawBtn = document.getElementById('toggleRawBtn');
const flowchartCard = document.getElementById('flowchartCard');
const mermaidDiagram = document.getElementById('mermaidDiagram');

// Sidebar DOM elements
const historySidebar = document.getElementById('historySidebar');
const openHistoryBtn = document.getElementById('openHistoryBtn');
const closeHistoryBtn = document.getElementById('closeHistoryBtn');
const historyList = document.getElementById('historyList');

// Copy button
const copySummaryBtn = document.getElementById('copySummaryBtn');

// Toggle Sources Button handler
const toggleSourcesBtn = document.getElementById('toggleSourcesBtn');
const sourcesCollapse = document.getElementById('sourcesCollapse');
const sourcesArrow = document.getElementById('sourcesArrow');

if (toggleSourcesBtn) {
    toggleSourcesBtn.onclick = () => {
        const isHidden = sourcesCollapse.classList.contains('hidden');
        if (isHidden) {
            sourcesCollapse.classList.remove('hidden');
            sourcesArrow.style.transform = 'rotate(180deg)';
        } else {
            sourcesCollapse.classList.add('hidden');
            sourcesArrow.style.transform = 'rotate(0deg)';
        }
    };
}

const icons = {
    Cost: "💸",
    Tech: "💻",
    UX: "👥"
};

// Toggle Sidebar
openHistoryBtn.onclick = () => {
    historySidebar.classList.remove('translate-x-full');
    loadHistory();
};
closeHistoryBtn.onclick = () => {
    historySidebar.classList.add('translate-x-full');
};

// Clipboard Copy logic
copySummaryBtn.onclick = () => {
    const summaryText = document.getElementById('summaryContent').textContent;
    if (!summaryText) return;
    
    navigator.clipboard.writeText(summaryText).then(() => {
        const originalText = copySummaryBtn.innerHTML;
        copySummaryBtn.innerHTML = "✅ Copied!";
        copySummaryBtn.classList.add('border-emerald-500/30', 'text-emerald-400');
        setTimeout(() => {
            copySummaryBtn.innerHTML = originalText;
            copySummaryBtn.classList.remove('border-emerald-500/30', 'text-emerald-400');
        }, 2000);
    }).catch(err => {
        console.error("Clipboard copy failed: ", err);
    });
};

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const idea = ideaInput.value.trim();
    if (!idea) return;
    performAnalysis(idea);
});

async function performAnalysis(idea) {
    // Reset pipeline steps to default before submission
    const gatherIcon = document.getElementById('stepGatherIcon');
    if (gatherIcon) {
        gatherIcon.className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-slate-700 bg-slate-900 text-slate-400 text-sm font-bold mb-2';
        gatherIcon.textContent = '🔍';
        document.getElementById('stepGatherDesc').textContent = 'Scraping web signals';
        
        document.getElementById('stepCleanIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-slate-700 bg-slate-900 text-slate-400 text-sm font-bold mb-2';
        document.getElementById('stepCleanIcon').textContent = '🧹';
        document.getElementById('stepCleanDesc').textContent = 'Deduplicating inputs';
        
        document.getElementById('stepOrganizeIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-slate-700 bg-slate-900 text-slate-400 text-sm font-bold mb-2';
        document.getElementById('stepOrganizeIcon').textContent = '🧠';
        document.getElementById('stepOrganizeDesc').textContent = 'Extracting failure nodes';
        
        document.getElementById('stepPresentIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-slate-700 bg-slate-900 text-slate-400 text-sm font-bold mb-2';
        document.getElementById('stepPresentIcon').textContent = '📊';
        document.getElementById('stepPresentDesc').textContent = 'Compiling final report';
        
        document.getElementById('pipelineCard').classList.add('hidden');
    }

    // Show loader, skeletons and disable submit
    loader.classList.remove('hidden');
    skeletonScreen.classList.remove('hidden');
    results.classList.add('hidden');
    submitBtn.disabled = true;
    submitBtn.classList.add('opacity-50', 'cursor-not-allowed');

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ idea: idea })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Analysis failed');
        }

        const initialData = await response.json();
        const taskId = initialData.task_id;
        
        // Dynamic elements for loader updates
        const loaderTitle = document.getElementById('loaderTitle');
        const loaderSubtitle = document.getElementById('loaderSubtitle');
        const loaderProgress = document.getElementById('loaderProgress');

        // Reset elements in case they are collapsed
        if (sourcesCollapse && !sourcesCollapse.classList.contains('hidden')) {
            sourcesCollapse.classList.add('hidden');
            if (sourcesArrow) sourcesArrow.style.transform = 'rotate(0deg)';
        }

        let done = false;
        let finalData = null;

        while (!done) {
            // Wait 2 seconds between polls
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            const statusRes = await fetch(`/api/status/${taskId}`);
            if (!statusRes.ok) {
                throw new Error("Failed to fetch task status.");
            }
            const statusData = await statusRes.json();
            if (!statusData) continue;

            if (statusData.status === 'completed') {
                done = true;
                finalData = statusData.results;
            } else if (statusData.status === 'failed') {
                throw new Error(statusData.message || "Background analysis failed");
            } else {
                // Update live loader messages
                if (loaderTitle) loaderTitle.textContent = "Researching and Analyzing...";
                if (loaderSubtitle) loaderSubtitle.textContent = statusData.current_step || "Searching the web...";
                
                // Show progressive scrap stats if any
                if (statusData.total_articles > 0) {
                    if (loaderProgress) {
                        loaderProgress.textContent = `Scraped ${statusData.extracted_count}/${statusData.total_articles} pages. ${statusData.message}`;
                    }
                } else {
                    if (loaderProgress) loaderProgress.textContent = statusData.message || "";
                }
            }
        }

        if (finalData) {
            renderResults(finalData);
            results.classList.remove('hidden');
        }
    } catch (err) {
        alert('Analysis Error: ' + err.message);
    } finally {
        loader.classList.add('hidden');
        skeletonScreen.classList.add('hidden');
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        loadHistory(); // Refresh history list
    }
}

async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        if (!response.ok) return;
        const data = await response.json();
        const history = data.history || [];
        
        if (history.length === 0) {
            historyList.innerHTML = `<p class="text-xs text-slate-500 text-center py-4">No recent analyses found.</p>`;
            return;
        }
        
        historyList.innerHTML = '';
        history.forEach(item => {
            const dateStr = new Date(item.timestamp).toLocaleDateString(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit'});
            const itemDiv = document.createElement('div');
            itemDiv.className = 'glass p-4 rounded-xl border border-white/5 space-y-2 hover:border-red-500/30 transition-all';
            itemDiv.innerHTML = `
                <div class="flex justify-between items-start">
                    <span class="text-xs font-semibold text-slate-200 truncate max-w-[150px]" title="${item.idea}">${item.idea}</span>
                    <span class="text-[10px] text-slate-500">${dateStr}</span>
                </div>
                <p class="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">${item.summary || 'Click view to load results.'}</p>
                <div class="flex gap-2 justify-end pt-1">
                    <button class="reanalyze-btn text-[10px] bg-red-950/40 hover:bg-red-900/40 text-red-400 px-2.5 py-1 rounded-lg border border-red-900/30 transition-colors" data-idea="${item.idea}">🔄 Re-run</button>
                    <button class="load-btn text-[10px] bg-slate-900/80 hover:bg-slate-800 text-slate-300 px-2.5 py-1 rounded-lg border border-white/5 transition-colors" data-id="${item.id}">👁️ View</button>
                </div>
            `;
            
            // Bind buttons
            itemDiv.querySelector('.reanalyze-btn').onclick = (e) => {
                const idea = e.target.getAttribute('data-idea');
                ideaInput.value = idea;
                historySidebar.classList.add('translate-x-full');
                performAnalysis(idea);
            };
            
            itemDiv.querySelector('.load-btn').onclick = async (e) => {
                const id = e.target.getAttribute('data-id');
                historySidebar.classList.add('translate-x-full');
                
                // Show loader and skeletons
                loader.classList.remove('hidden');
                skeletonScreen.classList.remove('hidden');
                results.classList.add('hidden');
                
                try {
                    const res = await fetch(`/api/history/${id}`);
                    if (!res.ok) throw new Error("Could not load history details");
                    const detail = await res.json();
                    ideaInput.value = detail.raw_content.split('\n')[0].replace('# 🐦🔥 PhoenixForge Report:', '').trim() || ideaInput.value;
                    renderResults(detail);
                    results.classList.remove('hidden');
                } catch (err) {
                    alert("Error loading historical analysis: " + err.message);
                } finally {
                    loader.classList.add('hidden');
                    skeletonScreen.classList.add('hidden');
                }
            };
            
            historyList.appendChild(itemDiv);
        });
    } catch (err) {
        console.error("Failed to load history list: ", err);
    }
}

function renderResults(data) {
    const fixes = data.fixes || [];
    
    // Parse risks and pivots for human translation
    const costRisks = fixes.filter(f => f.category === 'Cost').map(f => f.issue);
    const techRisks = fixes.filter(f => f.category === 'Tech').map(f => f.issue);
    const uxRisks = fixes.filter(f => f.category === 'UX').map(f => f.issue);
    const pivots = fixes.filter(f => f.category === 'General').map(f => f.issue);

    // 1. RENDER EXECUTIVE SUMMARY
    const summaryCard = document.getElementById('summaryCard');
    const summaryContent = document.getElementById('summaryContent');
    const idea = ideaInput.value.trim();
    
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
    
    summaryContent.textContent = summaryText;
    summaryCard.classList.remove('hidden');

    // 1.5 RENDER PIPELINE PROGRESS TRACKER
    const pipeline = data.pipeline || {};
    const pipelineCard = document.getElementById('pipelineCard');
    if (pipelineCard && pipeline.gathered) {
        pipelineCard.classList.remove('hidden');
        
        document.getElementById('stepGatherIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-emerald-500 bg-emerald-950 text-emerald-400 text-sm font-bold mb-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]';
        document.getElementById('stepGatherIcon').textContent = '✅';
        document.getElementById('stepGatherDesc').textContent = pipeline.gathered;
        
        document.getElementById('stepCleanIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-emerald-500 bg-emerald-950 text-emerald-400 text-sm font-bold mb-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]';
        document.getElementById('stepCleanIcon').textContent = '✅';
        document.getElementById('stepCleanDesc').textContent = pipeline.cleaned;
        
        document.getElementById('stepOrganizeIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-emerald-500 bg-emerald-950 text-emerald-400 text-sm font-bold mb-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]';
        document.getElementById('stepOrganizeIcon').textContent = '✅';
        document.getElementById('stepOrganizeDesc').textContent = pipeline.organized;
        
        document.getElementById('stepPresentIcon').className = 'w-10 h-10 rounded-full flex items-center justify-center border-2 border-emerald-500 bg-emerald-950 text-emerald-400 text-sm font-bold mb-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]';
        document.getElementById('stepPresentIcon').textContent = '✅';
        document.getElementById('stepPresentDesc').textContent = pipeline.presented || "Report generated";
    }

    // 2. RENDER GRAVEYARD (NEGATIVE REVIEWS) - TOP PRIORITY
    const graveyardContent = document.getElementById('graveyardContent');
    const graveyardText = data.graveyard || 'No negative signals detected. Either this idea is perfect (unlikely) or the scrapers missed something.';
    graveyardContent.textContent = graveyardText;

    // 2.5 RENDER SOURCES COLLAPSIBLE
    const sourcesCollapseContainer = document.getElementById('sourcesCollapseContainer');
    const sourcesCollapseElement = document.getElementById('sourcesCollapse');
    const sourceCountElement = document.getElementById('sourceCount');
    
    if (sourcesCollapseContainer && sourcesCollapseElement) {
        const urls = data.scraped_urls || [];
        if (urls.length > 0) {
            if (sourceCountElement) sourceCountElement.textContent = urls.length;
            sourcesCollapseElement.innerHTML = '';
            urls.forEach((url, index) => {
                let domain = 'Source';
                try {
                    domain = new URL(url).hostname;
                } catch(e) {}
                
                const link = document.createElement('a');
                link.href = url;
                link.target = '_blank';
                link.className = 'block text-xs text-red-400 hover:text-red-300 hover:underline py-1 truncate border-b border-white/5 last:border-0';
                link.innerHTML = `<span class="text-slate-500 mr-2 font-mono">[${index+1}]</span> <span class="font-semibold text-slate-300">${domain}</span> - <span class="text-slate-500 font-mono text-[10px]">${url}</span>`;
                sourcesCollapseElement.appendChild(link);
            });
            sourcesCollapseContainer.classList.remove('hidden');
        } else {
            sourcesCollapseContainer.classList.add('hidden');
        }
    }

    // 3. RENDER HEATMAP
    const displayNames = {
        Cost: "Financial & Scaling Risk",
        Tech: "Market & B2B Risk",
        UX: "UX & Retention Risk"
    };
    const categoryIcons = {
        Cost: "💸",
        Tech: "💼",
        UX: "👥"
    };

    heatmapContainer.innerHTML = '';
    const entries = Object.entries(data.heatmap || {});
    if (entries.length === 0) {
        heatmapContainer.innerHTML = `<div class="col-span-3 text-center text-gray-500">No risks detected.</div>`;
    } else {
        entries.forEach(([key, value]) => {
            const card = document.createElement('div');
            card.className = 'glass rounded-2xl p-6 border border-white/5 flex flex-col justify-between';
            
            // Map severity based on signal count
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
                    <p class="text-xs text-slate-400 mt-4 leading-relaxed border-t border-white/5 pt-3">${desc}</p>
                </div>
            `;
            heatmapContainer.appendChild(card);
        });
    }

    // 3.5 RENDER VISUAL FLOWCHART
    const rawContentText = data.raw_content || '';
    const mermaidMatch = rawContentText.match(/```mermaid\s*([\s\S]*?)```/);
    if (mermaidMatch && mermaidMatch[1]) {
        const mermaidCode = mermaidMatch[1].trim();
        flowchartCard.classList.remove('hidden');
        mermaidDiagram.removeAttribute('data-processed');
        mermaidDiagram.textContent = mermaidCode;
        try {
            mermaid.run({
                nodes: [mermaidDiagram]
            });
        } catch (e) {
            console.error("Mermaid rendering failed:", e);
        }
    } else {
        flowchartCard.classList.add('hidden');
    }

    // 4. RENDER FIXES
    fixesContainer.innerHTML = '';
    if (fixes.length === 0) {
        fixesContainer.innerHTML = `<div class="text-gray-500 text-center py-4">No specific fixes generated.</div>`;
    } else {
        fixes.forEach((fix, idx) => {
            const div = document.createElement('div');
            div.className = 'glass p-5 rounded-2xl border border-white/5 space-y-2';
            
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
                <h4 class="text-base font-bold text-slate-100">${title}</h4>
                <p class="text-sm text-slate-400 leading-relaxed">${desc}</p>
            `;
            fixesContainer.appendChild(div);
        });
    }

    // 4. RAW TOGGLE
    rawContent.textContent = data.raw_content || 'No raw content available.';
    rawContainer.classList.add('hidden');
    toggleRawBtn.textContent = rawContainer.classList.contains('hidden') ? '📄 View Raw Report' : '📄 Hide Raw Report';
    toggleRawBtn.onclick = () => {
        rawContainer.classList.toggle('hidden');
        toggleRawBtn.textContent = rawContainer.classList.contains('hidden') ? '📄 View Raw Report' : '📄 Hide Raw Report';
    };
}

// Bind Export Buttons
document.getElementById('exportPdfBtn').onclick = () => {
    window.location.href = '/api/export/pdf';
};
document.getElementById('exportWordBtn').onclick = () => {
    window.location.href = '/api/export/word';
};

// Initial History load on startup
loadHistory();
