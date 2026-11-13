"use strict";
let modelResult = null, modelRunning = false;
const realMethodNames = {full:"完整输出",errors:"简单错误过滤",structured:"保留配置与错误",no_log:"无日志对照",oracle:"人工关键行参考"};
const realTaskNames = {"threshold-0":"阈值 · 0 是有效输入","threshold-1":"阈值 · 0 代表默认值","unicode-0":"文字 · NFC 约定","unicode-1":"文字 · NFKC 约定","delimiter-0":"CSV · 逗号分栏","delimiter-1":"CSV · 分号分栏"};
const tokenLabel = value => value === null || value === undefined ? "未知" : number(value);
async function checkModel() {
  const el = $("#model-status");
  try {
    const data = await api("/api/model/status");
    el.textContent = `${data.model.provider} · ${data.model.model} · ${data.model.available === true ? "已找到本地模型" : data.model.available === false ? "本地模型未连接，请启动 Ollama" : "已配置，运行时验证连接"}`;
    $("#run-model").disabled = modelRunning || data.model.available === false;
  } catch (error) { el.textContent = error.message; $("#run-model").disabled = true; }
}
function renderModel(result) {
  modelResult = result;
  $("#model-results").hidden = false;
  $("#model-run-title").textContent = `${result.model?.model || "模型实验"} · ${result.id || "排队中"}`;
  $("#model-summary").innerHTML = (result.summary || []).map(r => `<tr><td>${realMethodNames[r.method]}</td><td>${r.successes}/${r.n} · ${r.success_rate}%</td><td>${r.both_variants_correct}/${r.complete_pairs}</td><td>${tokenLabel(r.input_tokens)}</td><td>${tokenLabel(r.output_tokens)}</td><td>${r.queries} / ${r.model_calls}${r.requests_failed || r.invalid_responses ? ` · 异常 ${r.requests_failed + r.invalid_responses}` : ""}</td><td>${(r.elapsed_ms/1000).toFixed(1)}s</td></tr>`).join("");
  $("#model-rows").innerHTML = (result.rows || []).map(r => `<details class="model-row"><summary><span class="${r.success ? "success" : "failure"}">${r.success ? "✓" : "×"} ${escapeHTML(realTaskNames[r.task_id] || r.task_id)}</span><span>${realMethodNames[r.method]}</span><span>${r.choice ? "补丁 " + r.choice : escapeHTML(r.status)} · ${r.passed}/${r.total} 验收</span><span>${r.queries} 次重查</span></summary><p>重复 ${r.repeat+1} · ${tokenLabel(r.input_tokens)} 输入 / ${tokenLabel(r.output_tokens)} 输出 token · ${(r.elapsed_ms/1000).toFixed(2)}s</p><pre>${escapeHTML(JSON.stringify({visible_output:r.visible_output,trace:r.trace,retrievals:r.retrievals},null,2))}</pre></details>`).join("");
}
$("#refresh-model").addEventListener("click", checkModel);
$("#run-model").addEventListener("click", async () => {
  if (modelRunning) return;
  modelRunning = true;
  const controls = $$("#model .control-panel input, #model .control-panel select, #run-model, #refresh-model");
  controls.forEach(c => { c.disabled = true; });
  const family = $("#model-tasks").value;
  const families = family === "all" ? ["threshold","unicode","delimiter"] : [family];
  const params = {task_ids:families.flatMap(f => [`${f}-0`,`${f}-1`]),methods:["full","errors","structured","no_log"],max_queries:Number($("#model-queries").value),repeats:Number($("#model-repeats").value),seed:Number($("#model-seed").value)};
  if ($("#model-oracle").checked) params.methods.push("oracle");
  $("#model-progress").textContent = "正在开始真实调用，请保持服务窗口运行。结果逐题保存，网络失败不自动重试。";
  try {
    const {job_id} = await api("/api/model/run", params);
    let result;
    do {
      await new Promise(resolve => setTimeout(resolve, 1200));
      result = await api(`/api/model/jobs/${job_id}`);
      renderModel(result);
      $("#model-progress").textContent = `已完成 ${result.rows.length}/${result.total} 条 · ${result.state === "running" ? "真实模型推理中…" : result.state}`;
    } while (["running","queued"].includes(result.state));
    if (result.state !== "completed") toast(result.error || "实验已停止，请展开失败记录查看原因。");
  } catch (error) { toast(error.message); $("#model-progress").textContent = "页面未取得完整结果。后台可能仍在运行，请勿立即重复提交；记录保存在 runs 目录。"; }
  finally { modelRunning = false; controls.forEach(c => { c.disabled = false; }); }
});
$("#export-model").addEventListener("click", () => {
  if (!modelResult) return;
  const blob = new Blob([JSON.stringify(modelResult,null,2)], {type:"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = `agent-budget-model-${modelResult.id || "partial"}.json`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
checkModel();
