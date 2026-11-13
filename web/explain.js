"use strict";
// Teaching copy stays in the UI. It is never added to real-model prompts or gold data.
const caseExplanations = {
  unicode: {
    name:"商品编号：全角 ＡＢＣ 查不到半角 ABC",
    short:"用商品搜索举例：输入法打出的全角字母，需要变成数据库使用的统一写法。",
    heading:"都是字母，计算机为什么认为它们不同？",
    story:"假设商品库里有编号 ABC，用户却输入了全角 ＡＢＣ。我们希望两种输入最后都变成 abc，这样才能查到同一条记录。这里的“匹配”就是比较处理后的字符串是否完全相等。这个 demo 只运行文字处理函数，用商品搜索帮助你理解用途。",
    examples:[
      ["半角 ABC", "转成小写后是 abc", "这是这个案例希望得到的统一写法。"],
      ["全角 ＡＢＣ", "只转小写会得到 ａｂｃ", "字母变小写了，但仍是全角，和 abc 不相等。"],
      ["CAFÉ", "应该得到 café", "保留重音符号；直接删除非英文字符会把有意义的字母也丢掉。"]
    ],
    clue:"normalization=NFKC 表示采用一种 Unicode 统一写法：本例要把全角字母转成半角，也把 ① 转成 1。preserve accents 表示保留 é 这样的重音字母。",
    observe:"只留错误时，规则默认采用“清理空格＋转小写”，全角问题仍然存在。保留运行条件后，它才会选择包含 NFKC 的候选修复。看下方实际输出是否变成 abc，并检查 5 项验收是否全部通过。"
  },
  threshold: {
    name:"阈值设置：主动输入的 0 被改成 10",
    short:"用告警阈值设置举例：用户填了 0，和用户根本没填，应当分别处理。",
    heading:"填了 0，为什么系统却读到了默认值？",
    story:"假设一个设置页面允许用户填写阈值，默认值是 10。这个案例约定：主动填写 0 就保存 0；没有填写时用 None 表示，再采用默认值。原函数用 value or 10，把 0 也当成“没填”。这里测试的是读取设置的函数，负数也按本案例约定保留。",
    examples:[
      ["用户填 0", "应当读到 0", "0 是有效设置；原函数却返回 10。"],
      ["用户没填：None", "应当读到 10", "只有这一种情况才使用默认值。"],
      ["用户填 -2", "应当读到 -2", "不能顺手把负数改成 0；本案例允许负数。"]
    ],
    clue:"missing means None 表示只有 None 才算缺失；threshold=0 is explicit user input 表示 0 是用户有意填写的值。",
    observe:"比较只留错误和保留配置的结果。重点找输入为 0 的验收行：实际输出究竟是 10 还是 0？再检查未填写和负数是否也处理正确。"
  },
  csv: {
    name:"联系人导入：名字里的逗号被误当成分栏",
    short:"用联系人表格导入举例：姓名里可以有逗号，但不应该因此多出一列。",
    heading:"一行两列的数据，为什么被拆成了三列？",
    story:'CSV 是用分隔符保存表格的文本格式。假设一行是 "Lee, Ada",support，第一列是姓名 Lee, Ada，第二列是部门 support。姓名外面的引号说明：里面的逗号属于姓名，不用于分列。原函数遇到每个逗号都拆开，因此拆错了。',
    examples:[
      ['"Lee, Ada",support', '["Lee, Ada", "support"]', "正确结果只有姓名和部门两列。"],
      ['"say ""hi""",ok', '[\'say "hi"\', "ok"]', "CSV 中连续两个双引号表示字段内部的一个双引号。"],
      ["a,b,c", '["a", "b", "c"]', "普通数据也要保持正确，不能只修好含引号的一行。"]
    ],
    clue:"quoting=RFC4180 表示按这一 CSV 引号约定解析；preserve field contents 表示保留字段本来的内容，不能先把所有引号粗暴删除。",
    observe:"看姓名里的逗号是否还在同一个字段里，并核对双引号转义。比较模式是否让规则选择了真正理解 CSV 格式的候选解析器。"
  }
};

function renderCaseExplanation(id) {
  const c = caseExplanations[id];
  if (!c) return;
  document.querySelector("#case-task").textContent = c.short;
  const esc = s => String(s).replace(/[&<>"']/g, x => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[x]));
  const example = text => esc(text).replace(/[Ａ-Ｚａ-ｚ]+/g, token => `<span class="example-token">${token}</span>`);
  document.querySelector("#case-story").innerHTML = `<div class="eyebrow">先理解这道题</div><h3>${esc(c.heading)}</h3><p>${esc(c.story)}</p><div class="example-table-wrap"><table><thead><tr><th>输入 / 情况</th><th>处理结果</th><th>为什么要这样处理</th></tr></thead><tbody>${c.examples.map(row => `<tr>${row.map(cell => `<td>${example(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div><p><b>日志里要找什么：</b>${esc(c.clue)}</p><p class="reading-focus"><b>运行后看哪里：</b>${esc(c.observe)}</p>`;
}

function updateProbeExplanation() {
  const n = Number(document.querySelector("#probe-size").value);
  const budget = Number(document.querySelector("#eval-budget").value);
  document.querySelector("#probe-budget-example").textContent = `按当前设置，6 个候选各看 ${n} 条工单，初筛需要 6 × ${n} = ${6*n} 单位；总预算上限为每种策略 ${budget} 单位。随机整体验证不做这一步初筛。候选训练耗时另列，不算在这个评价预算里。`;
}

const modelScenes = {
  threshold:"例子：两个部署都要读取阈值，但第一个把 0 当作用户填写的有效值，第二个把 0 当作“使用默认值”的标记。代码与候选相同，只有日志里的约定不同，正确补丁也应随之改变。",
  unicode:"例子：一个部署要求 NFC，保留全角字母等兼容字符的样式；另一个要求 NFKC，把全角等写法统一。不能仅凭“通常怎样处理文字”选择补丁，必须读本次部署约定。",
  delimiter:"例子：一个导入文件用逗号分列，另一个用分号分列；两者都支持引号。两题的代码与选项相同，正确的解析方式由日志里的文件格式决定。",
  all:"共三对任务：读取阈值时如何对待 0、文字采用哪种统一写法、导入文件用逗号还是分号。同一对的题干和候选完全相同，只改变日志中的约定。"
};

function updateModelExplanation() {
  const family = document.querySelector("#model-tasks").value;
  const tasks = family === "all" ? 6 : 2;
  const repeats = Number(document.querySelector("#model-repeats").value);
  const queries = Number(document.querySelector("#model-queries").value);
  const methods = document.querySelector("#model-oracle").checked ? 5 : 4;
  const trials = tasks * repeats * methods;
  const calls = tasks * repeats * ((methods-1)*(queries+1)+1);
  document.querySelector("#model-task-story").textContent = modelScenes[family];
  document.querySelector("#model-plan").textContent = `当前计划：${tasks} 道题 × ${methods} 种输入 × ${repeats} 轮 = ${trials} 条实验。最多 ${calls} 次模型调用（无日志组始终不能重查）。${trials > 80 ? "超过每批 80 条的上限，请减少重复或输入条件。" : "改变设置后，已有结果仍属于上一轮，需重新运行。"}`;
}

for (const id of ["probe-size", "eval-budget"]) document.querySelector("#"+id).addEventListener("input", updateProbeExplanation);
for (const id of ["model-tasks", "model-repeats", "model-queries", "model-oracle"]) document.querySelector("#"+id).addEventListener("change", updateModelExplanation);
updateProbeExplanation();
updateModelExplanation();
