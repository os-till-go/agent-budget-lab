"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const escapeHTML = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number = (n) => Number(n).toLocaleString("en-US");
const policyNames = {random:"随机整体验证",probe:"小试验一次排序",halving:"逐轮加测淘汰"};
const methodNames = {full:"完整输出",errors:"只留错误",context:"保留环境线索",custom:"自定义关键词"};
let cases = [], currentCompression = null, probeResult = null, requestVersion = 0, busyCompression = false, timer;

async function api(path, params) {
  const response = await fetch(path, params === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(params)});
  let data;
  try { data = await response.json(); } catch { throw new Error("服务返回了无法读取的结果。请检查启动窗口。"); }
  if (!response.ok) throw new Error(data.error || "实验没有完成。");
  return data;
}
function toast(message) {
  $("#toast").textContent = message; $("#toast").hidden = false;
  clearTimeout(timer); timer = setTimeout(() => { $("#toast").hidden = true; }, 5500);
}
function changeTab(name, updateHash = true) {
  const tab = ["probe", "model"].includes(name) ? name : "compression";
  $$(".experiment").forEach(el => { el.hidden = el.id !== tab; });
  $$(".tab").forEach(el => { el.classList.toggle("active", el.dataset.tab === tab); el.setAttribute("aria-selected", String(el.dataset.tab === tab)); });
  if (updateHash) history.replaceState(null, "", "#" + tab);
}
$$(".tab").forEach(el => el.addEventListener("click", () => changeTab(el.dataset.tab)));
window.addEventListener("hashchange", () => changeTab(location.hash.slice(1), false));
$("#guide-toggle").addEventListener("click", () => { $("#guide").hidden = !$("#guide").hidden; });
$("#guide-close").addEventListener("click", () => { $("#guide").hidden = true; });

function compressionParams() {
  return {case:$("#case-select").value,mode:$("input[name=method]:checked").value,noise:Number($("#noise").value),budget:Number($("#char-budget").value),patterns:$("#patterns").value};
}
function setMetrics(original, compressed) {
  $("#original-count").textContent = number([...original].length);
  $("#compressed-count").textContent = number([...compressed].length);
  $("#saved-percent").textContent = (100 * (1 - [...compressed].length / [...original].length)).toFixed(1) + "%";
}
function resetRepair() {
  $("#repair-result").className = "empty-state";
  $("#repair-result").innerHTML = '<span>↳</span><div><b>先观察，再验证。</b><p>点击“运行修复”，查看实际补丁与独立验收用例。</p></div>';
}
async function refreshCompression() {
  const version = ++requestVersion;
  $("#run-repair").disabled = true;
  $("#compare-all").disabled = true;
  $("#noise-value").textContent = $("#noise").value;
  $("#budget-value").textContent = $("#char-budget").value;
  const params = compressionParams();
  $("#custom-box").hidden = params.mode !== "custom";
  $$(".method").forEach(el => el.classList.toggle("selected", el.querySelector("input").checked));
  resetRepair(); $("#comparison").hidden = true;
  try {
    const data = await api("/api/compress", params);
    if (version !== requestVersion) return;
    currentCompression = data;
    $("#original-log").textContent = data.original;
    $("#compressed-log").value = data.compressed;
    setMetrics(data.original, data.compressed);
  } catch (err) { if (version === requestVersion) toast(err.message); }
  finally { if (version === requestVersion) { $("#run-repair").disabled = !currentCompression; $("#compare-all").disabled = !currentCompression; } }
}
function updateCase() {
  const selected = cases.find(c => c.id === $("#case-select").value);
  $("#case-task").textContent = selected.task;
  $("#patch-select").innerHTML = '<option value="auto">固定规则自动诊断</option>' + selected.options.map(o => `<option value="${escapeHTML(o.id)}">自己选：${escapeHTML(o.label)}</option>`).join("");
  refreshCompression();
}
$("#case-select").addEventListener("change", updateCase);
let refreshTimer;
for (const selector of ["#noise", "#char-budget", "#patterns"]) $(selector).addEventListener("input", () => { $("#noise-value").textContent = $("#noise").value; $("#budget-value").textContent = $("#char-budget").value; clearTimeout(refreshTimer); refreshTimer = setTimeout(refreshCompression, 140); });
$$("input[name=method]").forEach(el => el.addEventListener("change", refreshCompression));
$("#compressed-log").addEventListener("input", () => { if (currentCompression) setMetrics(currentCompression.original, $("#compressed-log").value); resetRepair(); });
$("#patch-select").addEventListener("change", resetRepair);
$("#jump-clue").addEventListener("click", () => {
  const pre = $("#original-log");
  const lines = pre.textContent.split("\n");
  const index = lines.findIndex(line => /\[(RUNTIME|CONFIG|SOURCE)\]/.test(line));
  pre.scrollTop = Math.max(0, (index - 3) * parseFloat(getComputedStyle(pre).lineHeight));
  pre.focus();
});

$("#run-repair").addEventListener("click", async () => {
  if (busyCompression) return;
  busyCompression = true;
  const button = $("#run-repair"); button.disabled = true; button.textContent = "验收中…";
  const version = requestVersion;
  try {
    const result = await api("/api/repair", {...compressionParams(),override:$("#compressed-log").value,patch:$("#patch-select").value});
    if (version !== requestVersion) return;
    const box = $("#repair-result");
    box.className = "repair-result" + (result.success ? "" : " failed");
    box.innerHTML = `<div class="result-heading"><b>${result.success ? "✓ 验收通过" : "↳ 修复还不完整"} · ${escapeHTML(result.patch_label)}</b><span class="verdict">${result.passed} / ${result.total} passed</span></div><pre class="patch-code">${escapeHTML(result.patch_code)}</pre><div class="test-rows"><div class="test-row"><span></span><span>输入 → 实际输出</span><span>期望输出</span></div>${result.tests.map(t => `<div class="test-row ${t.passed ? "" : "bad"}"><span>${t.passed ? "✓" : "×"}</span><span>${escapeHTML(t.input)} → ${escapeHTML(t.actual)}</span><span>${escapeHTML(t.expected)}</span></div>`).join("")}</div><div class="evidence">${result.evidence.map(e => `<span>${e.retained ? "✓ 已保留" : "× 已丢失"}：<code>${escapeHTML(e.text)}</code></span>`).join("")}</div><p class="result-limit">${escapeHTML(result.executor)}</p>`;
  } catch (err) { toast(err.message); }
  finally { busyCompression = false; button.disabled = false; button.innerHTML = "运行修复 <span>→</span>"; }
});
$("#compare-all").addEventListener("click", async () => {
  const button = $("#compare-all"); button.disabled = true; button.textContent = "比较中…";
  const version = requestVersion;
  try {
    const params = compressionParams();
    const rows = await Promise.all(["full","errors","context"].map(mode => api("/api/repair", {...params,mode,patch:"auto"})));
    if (version !== requestVersion) return;
    const box = $("#comparison"); box.hidden = false; box.className = "comparison";
    box.innerHTML = `<h3>同一个诊断器，同一套验收</h3><table><thead><tr><th>方式</th><th>字符数</th><th>减少</th><th>验收</th></tr></thead><tbody>${rows.map(r => `<tr><td>${methodNames[r.mode]}</td><td>${number(r.compressed_chars)}</td><td>${r.saved_percent}%</td><td class="${r.success ? "success" : "failure"}">${r.passed}/${r.total} ${r.success ? "通过" : "未通过"}</td></tr>`).join("")}</tbody></table><p class="hint">比较重新生成的三种日志，使用当前字符上限；不使用右侧手动编辑内容。</p>`;
  } catch (err) { toast(err.message); }
  finally { button.disabled = false; button.textContent = "比较全部三种方式 ↗"; }
});

for (const [input,output] of [["#probe-size","#probe-size-value"],["#eval-budget","#eval-budget-value"]]) $(input).addEventListener("input", () => {
  $(output).textContent = $(input).value;
  if (probeResult) $("#probe-run-note").textContent = "参数已变更，点击运行生成新结果。当前图表仍是上一轮。";
});
for (const input of ["#probe-setting", "#probe-seed"]) $(input).addEventListener("change", () => { if (probeResult) $("#probe-run-note").textContent = "参数已变更，当前图表仍是上一轮。"; });
$("#new-seed").addEventListener("click", () => { $("#probe-seed").value = (Number($("#probe-seed").value) + 1) % 100000; if (probeResult) $("#probe-run-note").textContent = "随机种子已变更，点击运行。"; });
function modelName(id) { return probeResult?.scores.find(s => s.id === id)?.name || id; }
function renderProbe(data) {
  probeResult = data;
  $("#probe-empty").hidden = true; $("#probe-results").hidden = false;
  $("#probe-dataset").innerHTML = `<strong>${data.train_n}</strong> 训练 / <strong>${data.dev_n}</strong> 开发 / <strong>${data.test_n}</strong> 测试 <span>· 种子 ${data.seed}</span>`;
  const best = Math.max(...data.policies.map(p => p.test_score));
  $("#policy-cards").innerHTML = data.policies.map(p => `<article class="policy-card ${p.test_score === best ? "best" : ""}"><h3>${policyNames[p.id]}</h3><div class="chosen">锁定：${escapeHTML(modelName(p.selected))}</div><div class="policy-score">${p.test_score.toFixed(1)}<small>%</small></div><small>独立测试正确率</small><div class="budget-track"><span style="width:${p.spent / p.budget * 100}%"></span></div><div class="budget-label">${p.spent} / ${p.budget} 预算</div><p class="hint">选择依据：${p.selection_n} 个开发样本</p></article>`).join("");
  $("#score-chart").innerHTML = data.scores.map(s => `<div class="score-row"><div class="score-name">${escapeHTML(s.name)}<small>训练 ${s.fit_ms.toFixed(0)} ms</small></div><div class="bars">${[["probe",s.probe_score,"小试验"],["dev",s.dev_score,"完整开发集"],["test",s.test_score,"独立测试集"]].map(([kind,score,label]) => `<div class="bar-track" aria-label="${escapeHTML(s.name)} ${label} ${score}%"><div class="bar ${kind}" style="width:${score}%"></div><span class="bar-label">${score.toFixed(1)}%</span></div>`).join("")}</div></div>`).join("");
  $("#probe-sample-count").textContent = data.probe_n + " 条";
  $("#probe-samples").innerHTML = data.probe_samples.map(r => `<div class="ticket"><p>${escapeHTML(r.text)}</p><small>${escapeHTML(r.true_name)} · ${escapeHTML(r.kind)}</small></div>`).join("");
  $("#test-examples").innerHTML = data.test_examples.map(r => `<div class="ticket"><p>${escapeHTML(r.text)}</p><small>正确：${escapeHTML(r.true_name)} <span class="bad-label">／捷径预测：${escapeHTML(r.predictions?.keywords || "—")}</span></small></div>`).join("");
  $("#protocol").textContent = data.protocol;
  renderTrace();
  $("#probe-run-note").textContent = `已完成本轮真实计算 · ${(data.elapsed_ms / 1000).toFixed(2)} 秒。相同种子复用已训练模型。`;
}
function renderTrace() {
  if (!probeResult) return;
  const policy = probeResult.policies.find(p => p.id === $("#trace-policy").value);
  $("#trace").innerHTML = policy.trace.map((t,i) => `<div class="trace-row"><span class="trace-step">${String(i+1).padStart(2,"0")}</span><strong>${escapeHTML(modelName(t.candidate))}</strong><span>${t.n} 样本 · ${t.score.toFixed(1)}%</span><span class="trace-cost">+${t.cost} → ${t.spent}</span></div>`).join("");
}
$("#trace-policy").addEventListener("change", renderTrace);
$("#run-probe").addEventListener("click", async () => {
  const button = $("#run-probe"); button.disabled = true; button.textContent = "训练与评价中…";
  const controls = $$("#probe .control-panel input, #probe .control-panel select, #new-seed");
  controls.forEach(control => { control.disabled = true; });
  $("#probe-run-note").textContent = "正在本地训练候选、分配开发评价预算，并在锁定方案后评分测试集…";
  const params = {seed:Number($("#probe-seed").value),setting:$("#probe-setting").value,probe_n:Number($("#probe-size").value),budget:Number($("#eval-budget").value)};
  try { renderProbe(await api("/api/probe", params)); }
  catch (err) { toast(err.message); $("#probe-run-note").textContent = "本轮没有完成，请检查提示后重试。"; }
  finally { controls.forEach(control => { control.disabled = false; }); button.disabled = false; button.textContent = "训练并运行三种策略 →"; }
});
$("#export-probe").addEventListener("click", () => {
  if (!probeResult) return;
  const blob = new Blob([JSON.stringify(probeResult,null,2)], {type:"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `agent-budget-lab-${probeResult.setting}-seed${probeResult.seed}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function boot() {
  changeTab(location.hash.slice(1), false);
  $("#run-repair").disabled = true; $("#compare-all").disabled = true;
  try {
    cases = (await api("/api/cases")).cases;
    $("#case-select").innerHTML = cases.map((c,i) => `<option value="${escapeHTML(c.id)}">${i+1}. ${escapeHTML(c.title)}</option>`).join("");
    updateCase();
  } catch (err) { toast(err.message); }
}
boot();
