"""Build two static viewer pages that fetch reports from results/ at runtime."""

import json

CSS = """
:root{--blue:#1e40af;--ink:#17243c;--muted:#526078;--bg:#f5f7fb;--line:#dce3ee;--green:#126442;--red:#a92738;--amber:#945a0b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI","Noto Sans CJK SC",sans-serif}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}a,button,select,summary{cursor:pointer}button,input,select{font:inherit}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:3px solid #3b82f6;outline-offset:3px}
.top{background:#12213d;color:white}.bar{max-width:1480px;margin:auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:72px}
.brand{font-weight:700;letter-spacing:.03em;display:flex;align-items:center;gap:12px}.mark{background:#3155b9;display:grid;place-items:center;width:34px;height:34px;border-radius:8px}
nav{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}nav a{color:#d7e2ff;padding:14px 16px;min-height:48px}nav a.active{color:white;background:#253858;border-radius:7px}
main{max-width:1480px;margin:36px auto 70px;padding:0 28px}.eyebrow{font-size:12px;color:var(--blue);font-weight:700;letter-spacing:.14em}h1{font-size:32px;line-height:1.25;letter-spacing:-.03em;margin:8px 0 12px}h2{font-size:20px;margin:0;overflow-wrap:anywhere}h3{font-size:16px;margin:0 0 12px}
p{margin:8px 0}.muted{color:var(--muted)}.lead{max-width:900px;color:var(--muted)}.heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}
.pill{display:inline-block;white-space:nowrap;background:#e8eefc;color:var(--blue);font-size:12px;padding:4px 10px;border-radius:5px;font-weight:650}.badge{font-size:12px;display:inline-block;padding:3px 8px;border-radius:4px;background:#edf1f7;color:var(--muted)}.pass{background:#e9f6ee;color:var(--green)}.fail{background:#fff0f1;color:var(--red)}.unknown{background:#fff3df;color:var(--amber)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:24px 0}.kpi,.panel{background:white;border:1px solid var(--line);border-radius:10px}.kpi{padding:18px 20px}.kpi-label{color:var(--muted);font-size:13px}.kpi-value{font-size:27px;font-weight:680;letter-spacing:-.04em;margin:4px 0}.kpi small{color:var(--muted)}
.panel{padding:22px;margin:20px 0;min-width:0}.panel-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.toolbar{display:flex;flex-wrap:wrap;align-items:end;gap:14px}.field{display:grid;gap:6px;min-width:145px;flex:1}.field.wide{flex:2;min-width:230px}label{color:var(--muted);font-size:13px;font-weight:600}input,select,button,.button{border:1px solid #bfcbdc;border-radius:6px;background:white;color:var(--ink);min-height:44px;padding:9px 12px;max-width:100%}input{width:100%}select{width:100%;text-overflow:ellipsis}.button,button{display:inline-flex;align-items:center;justify-content:center;gap:8px;font-weight:600}.primary{background:var(--blue);border-color:var(--blue);color:white}button:hover,.button:hover{filter:brightness(.96);text-decoration:none}button:disabled{opacity:.5;cursor:default}
.latency-round{border:1px solid var(--line);border-radius:8px;padding:16px;margin:14px 0}.latency-round h3{margin-bottom:4px}.latency-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:12px 0}.latency-grid.bands{grid-template-columns:repeat(3,minmax(0,1fr))}.latency-stat{background:#f7f9fc;border-radius:6px;padding:10px 12px}.latency-stat strong{display:block;font-size:18px}.latency-stat span{font-size:12px;color:var(--muted)}.latency-stat.fast{border-left:4px solid #16a34a}.latency-stat.medium{border-left:4px solid #f59e0b}.latency-stat.slow{border-left:4px solid #dc2626}.latency-chart{overflow-x:auto;border-top:1px solid var(--line);padding-top:12px}.latency-chart svg{display:block;width:100%;min-width:620px;height:auto}.chart-axis{stroke:#94a3b8;stroke-width:1}.chart-grid{stroke:#e3e8f0;stroke-width:1}.chart-point{fill-opacity:.78;stroke-width:1.4}.chart-point.fast{fill:#22c55e;stroke:#166534}.chart-point.medium{fill:#f59e0b;stroke:#92400e}.chart-point.slow{fill:#ef4444;stroke:#991b1b}.chart-point:hover,.chart-point:focus{fill-opacity:1;stroke-width:2.4}.chart-label{fill:var(--muted);font-size:11px}.chart-title{fill:var(--ink);font-size:12px;font-weight:600}.chart-legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin:4px 0 8px;font-size:12px;color:var(--muted)}.legend-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}.legend-dot.fast{background:#22c55e}.legend-dot.medium{background:#f59e0b}.legend-dot.slow{background:#ef4444}
#round-table{min-width:1100px}#round-table tbody tr[aria-selected="true"]{background:#edf3ff}#round-table td:last-child,#round-table th:last-child{position:sticky;right:0;background:white;min-width:150px}#round-table th:last-child{background:#f1f5fb;z-index:2}#round-panel .table-scroll{max-height:380px}.model-group>summary{padding:16px 20px;min-height:52px;background:white;border:1px solid var(--line);border-radius:8px;overflow-wrap:anywhere;font-weight:600;margin:12px 0}.model-group>.panel{margin-top:8px}#comparison-table{min-width:1700px}#comparison-table td:first-child{min-width:200px}#comparison-table td:last-child,#comparison-table th:last-child{position:sticky;right:0;background:white;box-shadow:-3px 0 6px #17243c0a;min-width:145px}#comparison-table th:last-child{background:#f1f5fb;z-index:2}#comparison-table .request-link{min-height:44px}.model-stats{display:flex;flex-wrap:wrap;gap:14px 34px;margin:16px 0 22px}.model-stats strong{font-size:23px;font-weight:650;display:block}.model-stats span{font-size:12px;color:var(--muted)}.table-scroll{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:7px}table{border-collapse:collapse;width:100%;min-width:890px;text-align:left;font-size:14px}th{background:#f1f5fb;color:#475873;font-size:12px;font-weight:650;position:sticky;top:0;z-index:1}td,th{padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:top}tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:#f8faff}.num{font-variant-numeric:tabular-nums;white-space:nowrap}.utterance{min-width:240px;max-width:380px}.utterance span{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.request-link{white-space:nowrap;display:inline-flex;align-items:center;min-height:30px;font-weight:600}.status{font-size:13px;color:var(--muted);margin-top:12px}.empty{text-align:center;padding:40px 16px;color:var(--muted)}.notice{padding:12px 16px;background:#fff4e2;border-left:3px solid #ba7b21;border-radius:4px;color:#764b09;margin:16px 0}.metrics{border-top:1px solid var(--line);padding:10px 0;margin:12px 0}.metrics summary{min-height:44px;display:list-item;padding:9px 0;color:var(--blue);font-weight:600}.metrics h3{margin-top:18px}.confusion{display:flex;flex-wrap:wrap;gap:10px 22px;padding:10px 0}.confusion span{font-size:13px}
.detail-layout{display:grid;grid-template-columns:minmax(230px,285px) minmax(0,1fr);gap:22px;align-items:start}.detail-side{position:sticky;top:20px}.detail-side .field{margin-bottom:14px}.detail-side .panel{margin-top:0}.detail-nav{display:flex;gap:8px}.detail-nav button{flex:1}.quote{font-size:19px;line-height:1.7;margin:14px 0 18px;overflow-wrap:anywhere}.facts{display:flex;gap:24px;flex-wrap:wrap;font-size:13px}.facts strong{display:block;font-size:16px}.reason{border-top:1px solid var(--line);padding-top:14px;margin-top:16px;color:var(--muted)}.code-head{display:flex;justify-content:space-between;align-items:center;gap:16px}.code-head p{font-size:12px;color:var(--muted);overflow-wrap:anywhere}pre{padding:20px;border-radius:7px;background:#11213b;color:#e2eaf8;font:13px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;tab-size:2;margin-bottom:0}.error{color:var(--red);overflow-wrap:anywhere}.links{display:flex;gap:16px;flex-wrap:wrap;font-size:13px}.footer{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin-top:28px}.round-line{font-size:13px;color:var(--muted);margin:12px 0 16px}.hash{font-family:ui-monospace,monospace;font-size:11px} [hidden]{display:none!important}
@media(max-width:800px){main{padding:0 16px;margin-top:24px}.bar{padding:0 16px}.heading{display:block}h1{font-size:27px}.kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.kpi{padding:14px}.kpi-value{font-size:24px}.panel{padding:16px}.panel-head{display:block}.detail-layout{grid-template-columns:minmax(0,1fr)}.detail-side{position:static}.detail-side .toolbar{display:grid;grid-template-columns:1fr 1fr}.detail-side .field{min-width:0}.brand span:last-child{display:none}nav a{padding:14px 12px}.model-stats{gap:12px 24px}.field.wide{min-width:180px}.links{margin-top:12px}.detail-nav{margin-top:12px}.latency-grid,.latency-grid.bands{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:no-preference){a,button,tbody tr{transition:background-color .16s,color .16s}}
"""

COMMON_JS = r"""
const $ = id => document.getElementById(id);
function el(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
const fmt = n => Number(n).toLocaleString('zh-CN');
const pct = n => (100*n).toFixed(2)+'%';
const exactTokens = value => value===null||value===undefined?'未知':fmt(value);
function cumulativeTokens(row){return row.missing_usage_count ? (row.known_input_tokens ? '≥ '+fmt(row.known_input_tokens) : '未知')+' · '+row.missing_usage_count+' 次 usage 缺失' : fmt(row.known_input_tokens);}
function option(select,value,text){const o=el('option',text);o.value=value;select.append(o);}
function badge(text,cls){return el('span',text,'badge '+cls);}
function status(row){return row.error?'failed':row.correct?'correct':'wrong';}
function addStat(parent,value,label){const n=el('div');n.append(el('strong',value),el('span',label));parent.append(n);}
function metaFooter(meta){$('meta').textContent='数据集 SHA-256 '+meta.dataset_sha256+'  ·  提示词 SHA-256 '+meta.prompt_sha256;}
function notice(meta){const notes=[];if(meta.flagged_runs?.length)notes.push('当前统计包含目录中的全部测试，其中 '+meta.flagged_runs.length+' 份历史报告带有评测输入错误标记；原始标记及调用记录保留在明细中。');if(!meta.aggregate&&meta.human_utterances_per_round<meta.full_dataset_human_utterances)notes.push('冒烟测试：每轮仅评测前 '+meta.human_utterances_per_round+' 条人类发言，不代表完整数据集的准确率。');if(!meta.aggregate&&meta.status!=='complete')notes.push('本次测试尚未完整结束，当前统计仅包括已尝试的发言（失败已计错）。');if(notes.length){$('notice').hidden=false;$('notice').textContent=notes.join(' ');}}
"""

SUMMARY_BODY = """
<div class="heading"><div><div class="eyebrow">ROBOT ADDRESSING / BENCHMARK</div><h1>意图识别测试汇总</h1><p class="lead">同一模型与数据集下，每句话只显示一行。轮次是累计测试次数，准确率是正确次数除以测试次数。</p></div></div>
<div id="notice" class="notice" hidden></div><div class="kpis" id="overview"></div>
<section class="panel" aria-label="结果筛选"><div class="toolbar"><div class="field"><label for="model">模型</label><select id="model"><option value="">全部模型</option></select></div><div class="field"><label for="dataset">数据集</label><select id="dataset"><option value="">全部数据集</option></select></div><div class="field"><label for="outcome">识别结果</label><select id="outcome"><option value="">全部结果</option><option value="correct">全部正确</option><option value="wrong">有错误</option><option value="failed">有调用失败</option></select></div><div class="field wide"><label for="search">搜索对话 ID 或发言</label><input id="search" type="search" placeholder="例如 u001：查看这句话的累计准确率"></div></div><p class="status" id="count" role="status" aria-live="polite"></p></section>
<div id="models"></div><p id="empty" class="empty" hidden>没有符合条件的测试结果，请调整筛选条件。</p><p class="footer">“对话 ID”使用逐句编号 u001–u200；完整会话 ID 为 <span id="conversation"></span>。每句话只显示一行；“轮次”是这句话的测试总次数，准确率为正确次数 / 测试次数。两次命令各运行 3 轮，此列显示 6 次。输入、输出、总 token 是所有测试的累计量；含重试的输入另列。点击对话 ID 查看各次测试的详情。</p><p id="meta" class="footer hash"></p>
"""

RUNS_BODY = """
<div class="heading"><div><div class="eyebrow">ROBOT ADDRESSING / RUN COMPARISON</div><h1>单次运行结果对比</h1><p class="lead">每次命令运行独立展示，不跨批次合并。用于比较不同时间、模型配置、数据集或请求参数下的评测效果。</p></div></div>
<div id="notice" class="notice" hidden></div><div class="kpis" id="overview"></div>
<section class="panel" aria-label="运行结果筛选"><div class="toolbar"><div class="field"><label for="run">运行批次</label><select id="run"><option value="">全部运行</option></select></div><div class="field"><label for="model">模型</label><select id="model"><option value="">全部模型</option></select></div><div class="field"><label for="dataset">数据集</label><select id="dataset"><option value="">全部数据集</option></select></div><div class="field"><label for="outcome">识别结果</label><select id="outcome"><option value="">全部结果</option><option value="correct">全部正确</option><option value="wrong">有错误</option><option value="failed">有调用失败</option></select></div><div class="field wide"><label for="search">搜索对话 ID 或发言</label><input id="search" type="search" placeholder="例如 u001"></div></div><p class="status" id="count" role="status" aria-live="polite"></p></section>
<section class="panel"><div class="panel-head"><div><h2>运行效果总览</h2><p class="muted">每行对应一次运行中的一个模型配置，可直接比较分类指标和延迟指标。</p></div></div><div id="run-comparison"></div></section>
<div id="models"></div><p id="empty" class="empty" hidden>没有符合条件的单次运行结果，请调整筛选条件。</p><p class="footer">每个模型卡片对应一次命令运行中的一个模型配置。轮次仅在该次运行内部累计，不与其他批次合并。点击对话 ID 可查看对应调用详情。</p><span id="conversation" hidden></span><p id="meta" class="footer hash"></p>
"""

SUMMARY_JS = r"""
const meta=DATA.metadata;notice(meta);metaFooter(meta);$('conversation').textContent=meta.conversation_id;
const modelIDs=[...new Set(DATA.models.map(model=>model.model))];
const datasets=[...new Map(DATA.models.map(model=>[model.dataset_sha256||meta.dataset_sha256,model])).entries()];
const runIDs=[...new Set(DATA.models.map(model=>model.run_id).filter(Boolean))];
for(const [value,label,sub] of [[meta.run_comparison?runIDs.length:modelIDs.length,meta.run_comparison?'运行批次数量':'模型数量',meta.run_comparison?'每次命令独立比较':'同一模型合并历史测试'],[datasets.length,'数据集数量','按 SHA-256 区分数据集'],[DATA.models.reduce((sum,model)=>sum+model.rounds.length,0),'累计测试轮数','包含全部保存的测试结果'],[DATA.models.reduce((sum,model)=>sum+model.rows.length,0),'目标话语数',meta.completed_evaluations+' 次测试记录']]){
 const k=el('div',undefined,'kpi');k.append(el('div',label,'kpi-label'),el('div',fmt(value),'kpi-value'),el('small',sub));$('overview').append(k);
}
function refillIntent(id,values,label){const select=$(id);if(!select)return;const selected=select.value;select.replaceChildren();option(select,'',id==='run'?'全部运行':id==='model'?'全部模型':'全部数据集');for(const value of values)option(select,value,label(value));if(values.includes(selected))select.value=selected;}
function syncIntentFilters(){const selected={run:$('run')?.value||'',model:$('model').value,dataset:$('dataset').value};for(const key of ['run','model','dataset']){const values=[...new Set(DATA.models.filter(item=>{const digest=item.dataset_sha256||meta.dataset_sha256;return (key==='run'||!selected.run||item.run_id===selected.run)&&(key==='model'||!selected.model||item.model===selected.model)&&(key==='dataset'||!selected.dataset||digest===selected.dataset);}).map(item=>key==='run'?item.run_id:key==='model'?item.model:(item.dataset_sha256||meta.dataset_sha256)).filter(Boolean))];refillIntent(key,values,value=>{if(key==='run'){const item=DATA.models.find(model=>model.run_id===value);return value+' · '+(item?.run_started_at||'');}if(key==='model')return value;const item=DATA.models.find(model=>(model.dataset_sha256||meta.dataset_sha256)===value);return (item?.conversation_id||meta.conversation_id)+' · '+value.slice(0,12);});}}
syncIntentFilters();

function groupedMetrics(groups){
 const wrap=el('div',undefined,'table-scroll');wrap.tabIndex=0;
 const table=el('table'),head=el('thead'),tr=el('tr');
 for(const label of ['分组','样本数','准确率','Precision','Recall','F1','误接话率']){const th=el('th',label);th.scope='col';tr.append(th);}
 head.append(tr);table.append(head);const body=el('tbody');
 for(const [name,stat] of Object.entries(groups||{})){
  const row=el('tr');for(const value of [name,fmt(stat.total),pct(stat.accuracy),pct(stat.precision),pct(stat.recall),pct(stat.f1),pct(stat.false_activation_rate)])row.append(el('td',value));body.append(row);
 }
 table.append(body);wrap.append(table);return wrap;
}
const svgNS='http://www.w3.org/2000/svg';
function svgEl(tag,attrs={},text){const node=document.createElementNS(svgNS,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(text!==undefined)node.textContent=text;return node;}
function seconds(value){return value===null||value===undefined?'未知':Number(value).toFixed(3)+' s';}
function ratio(value){return value===null||value===undefined?'未知':pct(value);}
function latencyChart(latency,roundNumber){
 const wrap=el('div',undefined,'latency-chart');
 if(!latency){wrap.append(el('p','当前报告接口未提供耗时统计。请停止并重新启动 python evaluate.py serve，然后刷新页面。','notice'));return wrap;}
 const points=latency.input_token_points||[];
 if(!points.length){wrap.append(el('p','没有同时包含输入 token 与耗时的记录，无法绘制图表。','muted'));return wrap;}
 const width=760,height=300,left=62,right=22,top=28,bottom=58,plotW=width-left-right,plotH=height-top-bottom;
 const minToken=Math.min(...points.map(item=>item.input_tokens)),maxToken=Math.max(...points.map(item=>item.input_tokens));
 const minX=Math.floor(minToken/1000)*1000,maxX=Math.max(Math.ceil((maxToken+1)/1000)*1000,minX+1000),maxY=Math.max(5,Math.ceil(Math.max(...points.map(item=>item.latency_seconds))));
 const x=value=>left+(value-minX)/(maxX-minX)*plotW,y=value=>top+plotH-value/maxY*plotH;
 const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':`第 ${roundNumber} 轮输入 token 与真实耗时散点图`});
 svg.append(svgEl('text',{x:left,y:15,class:'chart-title'},'单次请求真实耗时（秒）'));
 const yStep=Math.max(1,Math.ceil(maxY/10));
 for(let value=0;value<=maxY;value+=yStep){const py=y(value);svg.append(svgEl('line',{x1:left,y1:py,x2:width-right,y2:py,class:'chart-grid'}),svgEl('text',{x:left-8,y:py+4,'text-anchor':'end',class:'chart-label'},String(value)));}
 svg.append(svgEl('line',{x1:left,y1:top,x2:left,y2:top+plotH,class:'chart-axis'}),svgEl('line',{x1:left,y1:top+plotH,x2:width-right,y2:top+plotH,class:'chart-axis'}));
 const boundaries=[];for(let value=minX;value<=maxX;value+=1000)boundaries.push(value);
 const labelStep=Math.max(1,Math.ceil(boundaries.length/8));
 for(const [index,value] of boundaries.entries()){
  const px=x(value);svg.append(svgEl('line',{x1:px,y1:top,x2:px,y2:top+plotH,class:'chart-grid'}));
  if(index%labelStep===0||index===boundaries.length-1)svg.append(svgEl('text',{x:px,y:top+plotH+20,'text-anchor':'middle',class:'chart-label'},fmt(value)));
 }
 for(const item of points){const speed=item.latency_seconds<1?'fast':item.latency_seconds<2?'medium':'slow',circle=svgEl('circle',{cx:x(item.input_tokens),cy:y(item.latency_seconds),r:3,class:'chart-point '+speed,tabindex:0});circle.append(svgEl('title',{},`${item.id||'请求'}\n输入 ${fmt(item.input_tokens)} tokens\n真实耗时 ${seconds(item.latency_seconds)}`));svg.append(circle);}
 svg.append(svgEl('text',{x:left+plotW/2,y:height-8,'text-anchor':'middle',class:'chart-title'},'实际输入 token（每 1,000 tokens 一条分界线）'));
 const legend=el('div',undefined,'chart-legend');for(const [cls,label] of [['fast','< 1秒'],['medium','1秒 ≤ 耗时 < 2秒'],['slow','≥ 2秒']]){const item=el('span');item.append(el('i',undefined,'legend-dot '+cls),document.createTextNode(label));legend.append(item);}wrap.append(legend,svg);return wrap;
}
function latencyOverview(model){
 const latency=model.statistics.latency||{},section=el('section',undefined,'metrics latency-round');
 section.append(el('h3','总体耗时统计'),el('p','全部轮次 · 有效耗时 '+fmt(latency.count||0)+' 条'+(latency.missing_count?' · 缺失耗时 '+fmt(latency.missing_count)+' 条':''),'muted'));
 const grid=el('div',undefined,'latency-grid');
 for(const [label,value] of [['平均耗时',latency.average_seconds],['P50',latency.p50_seconds],['P95',latency.p95_seconds],['P99',latency.p99_seconds],['MAX',latency.max_seconds]]){const card=el('div',undefined,'latency-stat');card.append(el('strong',seconds(value)),el('span',label));grid.append(card);}
 const bands=latency.latency_bands||{},bandGrid=el('div',undefined,'latency-grid bands');
 for(const [key,label,cls] of [['under_1_second','0–1秒占比','fast'],['from_1_to_2_seconds','1–2秒占比','medium'],['at_least_2_seconds','2秒以上占比','slow']]){const value=bands[key],card=el('div',undefined,'latency-stat '+cls);card.append(el('strong',ratio(value?.ratio)),el('span',label+' · '+fmt(value?.count||0)+' 次'));bandGrid.append(card);}
 section.append(grid,bandGrid);return section;
}
function latencyDetails(model){
 const details=el('details',undefined,'metrics'),summary=el('summary','各轮耗时统计与 Token-耗时图表');details.append(summary);
 details.append(el('p','P95/P99 使用 nearest-rank（最近秩）方法。散点图中的每个点代表一次真实请求，X 为实际 input tokens，Y 为真实耗时；每 1,000 tokens 显示一条分界线。缺失 input token 的调用不进入图表。','muted'));
 for(const round of model.rounds){
  const latency=round.statistics.latency||{},section=el('section',undefined,'latency-round');
  section.append(el('h3','第 '+round.round+' 轮'),el('p','有效耗时 '+fmt(latency.count||0)+' 条 · 图表样本 '+fmt(latency.charted_count||0)+' 条'+(latency.missing_count?' · 缺失耗时 '+fmt(latency.missing_count)+' 条':''),'muted'));
  const grid=el('div',undefined,'latency-grid');
  for(const [label,value] of [['平均耗时',latency.average_seconds],['P50',latency.p50_seconds],['P95',latency.p95_seconds],['P99',latency.p99_seconds],['最大耗时',latency.max_seconds]]){const card=el('div',undefined,'latency-stat');card.append(el('strong',seconds(value)),el('span',label));grid.append(card);}
  const bands=latency.latency_bands||{},bandGrid=el('div',undefined,'latency-grid bands');
  for(const [key,label,cls] of [['under_1_second','0–1秒占比','fast'],['from_1_to_2_seconds','1–2秒占比','medium'],['at_least_2_seconds','2秒以上占比','slow']]){const value=bands[key],card=el('div',undefined,'latency-stat '+cls);card.append(el('strong',ratio(value?.ratio)),el('span',label+' · '+fmt(value?.count||0)+' 次'));bandGrid.append(card);}
  section.append(grid,bandGrid,latencyChart(latency,round.round));details.append(section);
 }
 return details;
}
function renderRunComparison(){
 const target=$('run-comparison');if(!target)return;target.replaceChildren();
 const selected=DATA.models.filter(model=>{const digest=model.dataset_sha256||meta.dataset_sha256;return !($('run').value&&$('run').value!==model.run_id)&&!($('model').value&&$('model').value!==model.model)&&!($('dataset').value&&$('dataset').value!==digest);});
 if(!selected.length){target.append(el('p','没有符合当前运行、模型和数据集筛选条件的批次。','empty'));return;}
 const wrap=el('div',undefined,'table-scroll');wrap.tabIndex=0;const table=el('table'),thead=el('thead'),head=el('tr');
 for(const label of ['运行批次','模型','数据集','轮次','测试数','Accuracy','Precision','Recall','F1','平均耗时','P50','P95','P99','最大耗时','<1秒','1–2秒','≥2秒']){const th=el('th',label);th.scope='col';head.append(th);}thead.append(head);table.append(thead);const body=el('tbody');
 for(const model of selected){const stat=model.statistics,latency=stat.latency||{},bands=latency.latency_bands||{},row=el('tr');for(const value of [model.run_id,model.model,(model.conversation_id||'')+' · '+(model.dataset_sha256||'').slice(0,8),fmt(model.rounds.length),fmt(stat.total),pct(stat.accuracy),pct(stat.precision),pct(stat.recall),pct(stat.f1),seconds(latency.average_seconds),seconds(latency.p50_seconds),seconds(latency.p95_seconds),seconds(latency.p99_seconds),seconds(latency.max_seconds),ratio(bands.under_1_second?.ratio),ratio(bands.from_1_to_2_seconds?.ratio),ratio(bands.at_least_2_seconds?.ratio)])row.append(el('td',value));body.append(row);}
 table.append(body);wrap.append(table);target.append(wrap);
}
function render(){
 renderRunComparison();const root=$('models');root.replaceChildren();let shown=0;
 for(const model of DATA.models){
  const digest=model.dataset_sha256||meta.dataset_sha256;
  if(($('run')?.value&&$('run').value!==model.run_id)||($('model').value&&$('model').value!==model.model)||($('dataset').value&&$('dataset').value!==digest))continue;
  const query=$('search').value.trim().toLowerCase();
  const rows=model.rows.filter(row=>(!$('outcome').value||($('outcome').value==='correct'?row.correct_count===row.rounds:$('outcome').value==='failed'?row.failed_count>0:row.correct_count<row.rounds))&&(!query||(row.id+' '+row.text).toLowerCase().includes(query)));
  if(!rows.length)continue;shown+=rows.length;
  const panel=el('section',undefined,'panel model-results');panel.dataset.group=model.profile;
  const head=el('div',undefined,'panel-head'),identity=el('div');
  identity.append(el('h2','模型名称：'+model.model),el('p',(model.run_id?'运行批次：'+model.run_id+' · '+(model.run_started_at||'')+'\n':'')+'数据集：'+(model.conversation_id||meta.conversation_id)+' · '+digest.slice(0,12),'muted'));
  head.append(identity,badge(model.rounds.length+' 次测试 · '+(model.run_status||((model.source_run_ids?.length||1)+' 次命令运行')),''));panel.append(head);
  const stats=el('div',undefined,'model-stats');
  addStat(stats,pct(model.statistics.accuracy),'总体准确率 · '+model.statistics.correct+'/'+model.statistics.total);
  addStat(stats,pct(model.statistics.precision),'Precision');addStat(stats,pct(model.statistics.recall),'Recall');addStat(stats,pct(model.statistics.f1),'F1');
  addStat(stats,cumulativeTokens(model.statistics),'累计输入 token');addStat(stats,fmt(model.statistics.missing_or_failed),'调用失败 / 漏答');panel.append(stats,latencyOverview(model));
  const extra=el('details',undefined,'metrics');extra.append(el('summary','各轮统计、混淆计数与分组指标'));
  const roundStats=el('div',undefined,'round-line');
  for(const round of model.rounds){
   const line=el('p','第 '+round.round+' 轮：'+pct(round.statistics.accuracy)+'（'+round.statistics.correct+'/'+round.statistics.total+'）');
   line.title=(round.source_run_id||'')+' · 原第 '+(round.source_round||round.round)+' 轮 · '+(round.source_status||meta.status);roundStats.append(line);
  }
  const counts=el('div',undefined,'confusion');for(const [key,label] of [['tp','TP 正类判对'],['tn','TN 负类判对'],['fp','FP 误接话'],['fn','FN 漏识别'],['missing_positive','正例失败/漏答'],['missing_negative','负例失败/漏答']])counts.append(el('span',label+'：'+model.statistics.confusion[key]));
  extra.append(roundStats,counts,el('h3','按说话者统计'),groupedMetrics(model.by_speaker),el('h3','按场景类型统计'),groupedMetrics(model.by_tag));panel.append(extra);
  panel.append(latencyDetails(model));
  const wrap=el('div',undefined,'table-scroll');wrap.tabIndex=0;wrap.setAttribute('aria-label',model.model+' 与数据集 '+digest.slice(0,12)+' 的全部测试结果');
  const table=el('table',undefined,'results-table'),headRow=el('tr'),thead=el('thead'),body=el('tbody');
  for(const label of ['对话 ID','轮次','目标话语','输入 token','输出 token','总 token','累计输入（含重试）','意图识别准确率']){const th=el('th',label);th.scope='col';headRow.append(th);}
  thead.append(headRow);table.append(thead);
  for(const row of rows){
   const tr=el('tr');tr.dataset.id=row.id;tr.dataset.testCount=String(row.rounds);
   const id=el('td',undefined,'num'),link=el('a',row.id,'request-link');const url=new URL(row.request_link,location.href);url.searchParams.set('utterance',row.id);link.href=url.href;link.title='查看这句话的全部测试详情';link.setAttribute('aria-label',row.id+' 全部测试详情');id.append(link);
   const round=el('td',fmt(row.rounds)+' 次','num');round.title='这句话累计测试 '+row.rounds+' 次';
   const text=el('td',undefined,'utterance');text.append(el('span',row.text));
   const result=el('td');result.append(badge(pct(row.accuracy)+' · '+row.correct_count+'/'+row.rounds,row.correct_count===row.rounds?'pass':row.correct_count===0?'fail':'unknown'));
   tr.append(id,round,text,el('td',exactTokens(row.input_tokens),'num'),el('td',exactTokens(row.output_tokens),'num'),el('td',exactTokens(row.total_tokens),'num'),el('td',cumulativeTokens(row),'num'),result);body.append(tr);
  }
  table.append(body);wrap.append(table);panel.append(wrap);root.append(panel);
 }
 $('count').textContent='显示 '+fmt(shown)+' / '+fmt(DATA.models.reduce((sum,model)=>sum+model.rows.length,0))+' 条目标话语；每句话一行，准确率为正确次数 / 测试次数。';$('empty').hidden=shown!==0;
}
for(const name of ['run','model','dataset'])if($(name))$(name).addEventListener('change',()=>{syncIntentFilters();render();});$('outcome').addEventListener('change',render);$('search').addEventListener('input',render);render();
"""

DETAILS_BODY = """
<div class="heading"><div><div class="eyebrow">ROBOT ADDRESSING / REQUEST TRACE</div><h1>每次测试的明细</h1><p class="lead">核对目标话语、参考标签、模型返回和实际提交的完整 request。新测试每条只调用一次，历史批次的重试记录保留。</p></div></div>
<div id="notice" class="notice" hidden></div><p id="empty" class="empty" hidden>当前没有已完成的测试调用。</p>
<div class="detail-layout" id="layout"><aside class="detail-side"><section class="panel"><h3>定位一次测试</h3><div class="toolbar"><div class="field"><label for="model">模型与数据集</label><select id="model"></select></div><div class="field"><label for="round">测试轮次</label><select id="round"></select></div><div class="field"><label for="utterance">对话 ID</label><select id="utterance"></select></div></div><div class="detail-nav"><button id="previous">上一条</button><button id="next">下一条</button></div><p class="status" id="position" role="status" aria-live="polite"></p><a id="back" class="request-link" href="summary.html">← 返回汇总</a></section><section class="panel"><h3>调用与计分</h3><p class="muted" id="context"></p><p class="status">历史发言携带数据集已有标签；当前句的答案与未来发言不进入 request。</p></section></aside>
<div><section class="panel" id="utterance-history-panel" hidden><h2 id="utterance-history-title">这句话的历次测试结果</h2><div class="table-scroll" tabindex="0"><table><thead><tr><th>测试序号</th><th>来源批次 / 原轮次</th><th>预测</th><th>是否正确</th><th>输入 token</th><th>输出 token</th><th>调用详情</th></tr></thead><tbody id="utterance-history"></tbody></table></div></section><section class="panel" id="round-panel"><div class="panel-head"><div><h2>本轮逐句测试结果</h2><p class="muted" id="round-context"></p></div></div><div class="toolbar"><div class="field"><label for="detail-outcome">识别结果</label><select id="detail-outcome"><option value="">全部结果</option><option value="correct">正确</option><option value="wrong">分类错误</option><option value="failed">调用失败</option></select></div><div class="field wide"><label for="detail-search">搜索对话 ID 或发言</label><input id="detail-search" type="search" placeholder="例如 u146、行李、会议区"></div></div><p class="status" id="round-count" role="status" aria-live="polite"></p><div class="table-scroll" tabindex="0" aria-label="本轮逐句结果，可横向滚动"><table class="results-table" id="round-table"><thead><tr><th>对话 ID</th><th>目标话语</th><th>参考标签</th><th>模型预测</th><th>输入 token</th><th>输出 token</th><th>总 token</th><th>识别结果</th><th>本次调用详情</th></tr></thead><tbody id="round-results"></tbody></table></div></section>
<article class="panel" id="call-details"><div class="panel-head"><h2 id="title"></h2><span id="outcome"></span></div><p class="quote" id="text"></p><div class="facts" id="facts"></div><p class="reason" id="reason"></p><p class="error" id="error" hidden></p><p id="correction" class="notice" hidden></p><p id="source-warning" class="notice" hidden></p></article>
<section class="panel" id="batch-panel" hidden><h3>本次调用的全部分类结果</h3><p class="status">逐项核对本次调用的分类输出，只对当前目标句计分。</p><div class="table-scroll"><table id="batch-table"><thead><tr><th>索引</th><th>对话 ID</th><th>发言</th><th>模型结果</th><th>参考标签</th><th>计分对象</th></tr></thead><tbody id="batch"></tbody></table></div></section>
<section class="panel"><div class="toolbar"><div class="field"><label for="attempt">HTTP 调用记录</label><select id="attempt"></select></div></div><div class="code-head"><div><h3 style="margin-top:20px">提交给模型的完整 request</h3><p id="endpoint"></p></div><button id="copy" type="button">复制 request</button></div><pre id="request" tabindex="0" aria-label="完整 request 参数"></pre><p class="status" id="copy-status" role="status"></p></section>
<section class="panel"><h3>模型原始返回</h3><pre id="response" tabindex="0" aria-label="完整模型返回"></pre></section><section class="panel"><h3>实际 token 用量与调用状态</h3><pre id="usage" tabindex="0" aria-label="接口 usage 与耗时"></pre></section></div></div><p id="meta" class="footer hash"></p>
"""

DETAILS_JS = r"""
const meta=DATA.metadata,rows=DATA.results;notice(meta);metaFooter(meta);let current=null;const models=[...new Set(rows.map(r=>r.profile))];for(const profile of models){const row=rows.find(r=>r.profile===profile);option($('model'),profile,row.model+' · '+row.conversation_id+' · '+(row.dataset_sha256||meta.dataset_sha256).slice(0,12));}
function setRounds(preferred){const numbers=[...new Set(rows.filter(r=>r.profile===$('model').value).map(r=>r.round))].sort((a,b)=>a-b);$('round').replaceChildren();for(const n of numbers)option($('round'),String(n),'第 '+n+' 轮');if(numbers.some(n=>String(n)===String(preferred)))$('round').value=String(preferred);}
function candidates(){return rows.filter(r=>r.profile===$('model').value&&String(r.round)===$('round').value);}
function renderRoundResults(){
 const list=candidates(),query=$('detail-search').value.trim().toLowerCase();
 const filtered=list.filter(row=>(!$('detail-outcome').value||status(row)===$('detail-outcome').value)&&(!query||(row.id+' '+row.text).toLowerCase().includes(query)));
 const body=$('round-results');body.replaceChildren();
 $('round-context').textContent=(list[0]?.model||'')+' · 累计第 '+$('round').value+' 轮'+(list[0]?.source_run_id?' · 原批次 '+list[0].source_run_id+' 的第 '+list[0].source_round+' 轮':'');
 $('round-count').textContent='显示 '+filtered.length+' / '+list.length+' 条；点击调用详情查看这一句的完整 request、响应和 usage。';
 for(const row of filtered){
  const tr=el('tr');tr.dataset.id=row.id;tr.dataset.anchor=row.request_anchor;
  if(current?.request_anchor===row.request_anchor)tr.setAttribute('aria-selected','true');
  const text=el('td',undefined,'utterance');text.append(el('span',row.text));
  tr.append(el('td',row.id,'num'),text,el('td',row.expected),el('td',row.intent||'无有效分类'));
  for(const key of ['input_tokens','output_tokens','total_tokens'])tr.append(el('td',exactTokens(row[key]),'num'));
  const outcome=el('td');outcome.append(badge(row.error?'调用失败':row.correct?'正确':'分类错误',row.correct?'pass':row.error?'unknown':'fail'));
  const cell=el('td'),button=el('button',row.legacy_import?'查看历史输出':'查看 request');
  button.type='button';button.setAttribute('aria-label',row.id+' 第 '+row.round+' 轮调用详情');
  button.addEventListener('click',()=>{$('utterance').value=row.request_anchor;select(row.request_anchor);$('call-details').scrollIntoView({behavior:'instant',block:'start'});});
  cell.append(button);tr.append(outcome,cell);body.append(tr);
 }
}
function renderUtteranceHistory(){
 if(!new URLSearchParams(location.search).has('utterance'))return;
 const history=rows.filter(row=>row.profile===current.profile&&row.id===current.id),body=$('utterance-history');body.replaceChildren();$('utterance-history-panel').hidden=false;
 $('utterance-history-title').textContent=current.id+' · 共测试 '+history.length+' 次，正确 '+history.filter(row=>row.correct).length+' 次';
 for(const row of history){const tr=el('tr');for(const value of ['第 '+row.round+' 次',(row.source_run_id||'本次运行')+' / 原第 '+(row.source_round||row.round)+' 轮',row.intent||'无有效分类',row.correct?'正确':row.error?'调用失败':'分类错误',exactTokens(row.input_tokens),exactTokens(row.output_tokens)])tr.append(el('td',value));const cell=el('td'),button=el('button','查看详情');button.type='button';button.setAttribute('aria-label',current.id+' 第 '+row.round+' 次详情');button.addEventListener('click',()=>{$('model').value=row.profile;setRounds(row.round);chooseList(row.request_anchor);$('call-details').scrollIntoView({behavior:'instant'});});cell.append(button);tr.append(cell);body.append(tr);}
}
function chooseList(preferred){$('utterance').replaceChildren();const list=candidates();for(const r of list)option($('utterance'),r.request_anchor,r.id+' · '+r.text.slice(0,25));if(preferred&&list.some(r=>r.request_anchor===preferred))$('utterance').value=preferred;if(list.length)select($('utterance').value);}
function select(anchor){const row=rows.find(r=>r.request_anchor===anchor);if(!row)return;current=row;if(location.hash!=='#'+anchor)location.hash=anchor;$('title').textContent=row.id+' · 第 '+row.round+' 轮';$('text').textContent=row.text;$('outcome').replaceChildren(badge(row.error?'调用失败':row.correct?'识别正确':'分类错误',row.correct?'pass':row.error?'unknown':'fail'));$('context').textContent=row.model+'\n'+row.conversation_id+' · '+meta.label_key+(row.source_run_id?'\n来源：'+row.source_run_id+' · 原第 '+row.source_round+' 轮':'');
 $('reason').textContent='标注理由：'+row.reason;$('error').hidden=!row.error;$('error').textContent=row.error||'';$('source-warning').hidden=row.source_evaluation_valid!==false;$('source-warning').textContent=row.source_evaluation_valid===false?'此批次曾标记评测输入错误，当前汇总包含此记录。原始说明：'+(row.source_invalidated_reason||''):'';$('correction').hidden=!row.parser_correction;$('correction').textContent=row.parser_correction||'';$('attempt').replaceChildren();row.attempts.forEach((a,i)=>option($('attempt'),String(i),a.attempt===null?'历史输出（HTTP 尝试次数未记录）':'第 '+a.attempt+' 次调用'+(a.error?' · 失败':'')));$('attempt').value=String(row.attempts.length-1);showAttempt();const list=candidates(),index=list.indexOf(row);$('previous').disabled=index<=0;$('next').disabled=index>=list.length-1;$('position').textContent='当前模型本轮 '+(index+1)+' / '+list.length+' 条';renderRoundResults();renderUtteranceHistory();}
function showAttempt(){if(!current)return;const attempt=current.attempts[Number($('attempt').value)],legacy=attempt.request_capture_status==='not_recorded';$('request').textContent=legacy?'旧报告未记录完整 request，无法还原当时实际提交的参数。':JSON.stringify(attempt.request?.body??null,null,2);$('endpoint').textContent=attempt.request?attempt.request.method+' '+attempt.request.url:legacy?'历史报告：request 未记录':'本次调用未提交 HTTP request';$('response').textContent=JSON.stringify(legacy?{legacy_raw_output:attempt.legacy_raw_output,note:'旧报告仅保留输出文本，没有完整 SDK response'}:attempt.response,null,2);$('usage').textContent=JSON.stringify({usage:attempt.usage,latency_seconds:attempt.latency_seconds,error:attempt.error},null,2);$('copy').disabled=legacy||!attempt.request;$('copy-status').textContent='';
 const facts=$('facts');facts.replaceChildren();for(const [label,value] of [['参考标签',current.expected],['目标句预测',current.intent||'无有效分类'],['本次输入 token',exactTokens(attempt.usage?.prompt_tokens)],['本次输出 token',exactTokens(attempt.usage?.completion_tokens)],['本次总 token',exactTokens(attempt.usage?.total_tokens)],['累计输入（含重试）',cumulativeTokens(current)],['累计输出（已知）',exactTokens(current.known_output_tokens)],['累计总 token（已知）',exactTokens(current.known_total_tokens)],['整句测试耗时',current.latency_seconds.toFixed(3)+' s']]){const fact=el('div');fact.append(el('span',label,'muted'),el('strong',value));facts.append(fact);}
 const batch=$('batch');batch.replaceChildren();const classifications=attempt.classifications||[];const items=current.batch_results||[];$('batch-panel').hidden=!classifications.length;for(const prediction of classifications){const item=items.find(item=>item.utterance_index===prediction.utterance_index);const target=item?.id===current.id;const tr=el('tr');for(const value of [prediction.utterance_index,item?.id||'未记录',item?.text||'未记录',prediction.intent,item?.expected||'未记录',target?'当前目标句 · 计入统计':'历史上下文 · 不重复计分'])tr.append(el('td',value));if(target)tr.className='pass';batch.append(tr);}}

function fromHash(){const row=rows.find(r=>r.request_anchor===decodeURIComponent(location.hash.slice(1)));if(row){$('model').value=row.profile;setRounds(row.round);chooseList(row.request_anchor);}else if(!current&&rows.length){$('model').value=rows[0].profile;setRounds(rows[0].round);chooseList(rows[0].request_anchor);}}
$('detail-outcome').addEventListener('change',renderRoundResults);$('detail-search').addEventListener('input',renderRoundResults);
$('model').addEventListener('change',()=>{setRounds($('round').value);chooseList();});$('round').addEventListener('change',()=>chooseList());$('utterance').addEventListener('change',()=>select($('utterance').value));$('attempt').addEventListener('change',showAttempt);for(const [id,delta] of [['previous',-1],['next',1]])$(id).addEventListener('click',()=>{const list=candidates(),index=list.indexOf(current)+delta;if(list[index])select(list[index].request_anchor);});$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('request').textContent);$('copy-status').textContent='request 已复制';}catch{$('copy-status').textContent='浏览器未允许自动复制，可直接选中上方 request 文本复制。';}});window.addEventListener('hashchange',fromHash);if(rows.length)fromHash();else{$('layout').hidden=true;$('empty').hidden=false;}
"""

RESULT_SUMMARY_BODY = """
<div class="heading"><div><div class="eyebrow">RESULT EVALUATION / BENCHMARK</div><h1>结果判断汇总</h1><p class="lead">原生工具调用、JSON 参数和文本关键词全部使用本地确定性规则校验，不调用裁判模型。</p></div></div>
<div class="kpis" id="overview"></div><section class="panel"><div class="toolbar"><div class="field"><label for="model">模型</label><select id="model"><option value="">全部模型</option></select></div><div class="field"><label for="dataset">数据集</label><select id="dataset"><option value="">全部数据集</option></select></div><div class="field wide"><label for="search">搜索请求</label><input id="search" type="search"></div></div><p id="count" class="status"></p></section><div id="models"></div><p id="empty" class="empty" hidden>暂无结果判断记录。</p><p id="meta" class="footer hash"></p>
"""

RESULT_RUNS_BODY = RESULT_SUMMARY_BODY.replace("结果判断汇总", "结果判断 · 单次运行对比").replace(
    "原生工具调用、JSON 参数和文本关键词全部使用本地确定性规则校验，不调用裁判模型。",
    "每次命令运行独立展示，不跨批次合并，用于比较模型、Prompt、参数及本地校验版本的效果。").replace(
    '<div class="toolbar"><div class="field"><label for="model">',
    '<div class="toolbar"><div class="field"><label for="run">运行批次</label><select id="run"><option value="">全部运行</option></select></div><div class="field"><label for="model">')

RESULT_SUMMARY_JS = r"""
const meta=DATA.metadata,models=DATA.models||[];
const modelIDs=[...new Set(models.map(item=>item.model))],datasets=[...new Set(models.map(item=>item.dataset_sha256))],runIDs=[...new Set(models.map(item=>item.run_id).filter(Boolean))];
function refill(id,values,label){const select=$(id);if(!select)return;const selected=select.value;select.replaceChildren();option(select,'',id==='run'?'全部运行':id==='model'?'全部模型':'全部数据集');for(const value of values)option(select,value,label(value));if(values.includes(selected))select.value=selected;}
function syncResultFilters(){const selected={run:$('run')?.value||'',model:$('model').value,dataset:$('dataset').value};for(const key of ['run','model','dataset']){const values=[...new Set(models.filter(item=>(key==='run'||!selected.run||item.run_id===selected.run)&&(key==='model'||!selected.model||item.model===selected.model)&&(key==='dataset'||!selected.dataset||item.dataset_sha256===selected.dataset)).map(item=>key==='run'?item.run_id:key==='model'?item.model:item.dataset_sha256).filter(Boolean))];refill(key,values,value=>{if(key==='run')return value;if(key==='model')return value;const item=models.find(model=>model.dataset_sha256===value);return (item?.conversation_id||'数据集')+' · '+value.slice(0,12);});}}
syncResultFilters();
for(const [value,label,sub] of [[meta.source_runs?.length||0,'运行批次','保存的结果判断命令'],[models.length,'结果组','按模型、数据集和校验版本分组'],[meta.completed_evaluations||0,'判断次数','工具 schema + 参数比较 + 文本关键词'],[models.reduce((sum,m)=>sum+m.statistics.passed,0),'通过次数','符合本地确定性规则'],[models.reduce((sum,m)=>sum+(m.statistics.total_tokens||0),0),'结果生成总 token','正式回复请求累计消耗']]){const card=el('div',undefined,'kpi');card.append(el('div',label,'kpi-label'),el('div',fmt(value),'kpi-value'),el('small',sub));$('overview').append(card);}
function resultStats(parent,stat){for(const [value,label] of [[pct(stat.pass_rate),'总体通过率 · '+stat.passed+'/'+stat.total],[fmt(stat.candidate_failures),'模型调用失败次数'],[fmt(stat.validation_failures||0),'本地校验失败次数'],[fmt(stat.input_tokens||0),'结果生成输入 token'],[fmt(stat.output_tokens||0),'结果生成输出 token'],[fmt(stat.total_tokens||0),'结果生成总 token'],[fmt(stat.result_usage_count||0)+' / '+fmt(stat.result_call_count||0),'已记录 usage 的结果调用'+(stat.missing_usage_count?' · 缺失 '+fmt(stat.missing_usage_count)+' 次':'')]])addStat(parent,value,label);}
function resultSvg(tag,attrs={},content){const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,String(value));if(content!==undefined)node.textContent=content;return node;}
function resultLatencyChart(latency,roundNumber){const wrap=el('div',undefined,'latency-chart'),points=latency?.input_token_points||[];if(!points.length){wrap.append(el('p','没有同时包含回复生成输入 token 与耗时的记录，无法绘制图表。','muted'));return wrap;}const width=760,height=300,left=62,right=22,top=28,bottom=58,plotW=width-left-right,plotH=height-top-bottom,minToken=Math.min(...points.map(p=>p.input_tokens)),maxToken=Math.max(...points.map(p=>p.input_tokens)),minX=Math.floor(minToken/1000)*1000,maxX=Math.max(Math.ceil((maxToken+1)/1000)*1000,minX+1000),maxY=Math.max(5,Math.ceil(Math.max(...points.map(p=>p.latency_seconds)))),x=value=>left+(value-minX)/(maxX-minX)*plotW,y=value=>top+plotH-value/maxY*plotH,svg=resultSvg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':`第 ${roundNumber} 轮回复生成输入 token 与真实耗时散点图`});svg.append(resultSvg('text',{x:left,y:15,class:'chart-title'},'回复生成单次请求真实耗时（秒）'));const yStep=Math.max(1,Math.ceil(maxY/10));for(let value=0;value<=maxY;value+=yStep){const py=y(value);svg.append(resultSvg('line',{x1:left,y1:py,x2:width-right,y2:py,class:'chart-grid'}),resultSvg('text',{x:left-8,y:py+4,'text-anchor':'end',class:'chart-label'},String(value)));}svg.append(resultSvg('line',{x1:left,y1:top,x2:left,y2:top+plotH,class:'chart-axis'}),resultSvg('line',{x1:left,y1:top+plotH,x2:width-right,y2:top+plotH,class:'chart-axis'}));const boundaries=[];for(let value=minX;value<=maxX;value+=1000)boundaries.push(value);const labelStep=Math.max(1,Math.ceil(boundaries.length/8));for(const [index,value] of boundaries.entries()){const px=x(value);svg.append(resultSvg('line',{x1:px,y1:top,x2:px,y2:top+plotH,class:'chart-grid'}));if(index%labelStep===0||index===boundaries.length-1)svg.append(resultSvg('text',{x:px,y:top+plotH+20,'text-anchor':'middle',class:'chart-label'},fmt(value)));}for(const point of points){const speed=point.latency_seconds<1?'fast':point.latency_seconds<2?'medium':'slow',circle=resultSvg('circle',{cx:x(point.input_tokens),cy:y(point.latency_seconds),r:3,class:'chart-point '+speed,tabindex:0});circle.append(resultSvg('title',{},`${point.id||'请求'}\n输入 ${fmt(point.input_tokens)} tokens\n真实耗时 ${point.latency_seconds.toFixed(3)} s`));svg.append(circle);}svg.append(resultSvg('text',{x:left+plotW/2,y:height-8,'text-anchor':'middle',class:'chart-title'},'回复生成输入 token（每 1,000 tokens 一条分界线）'));const legend=el('div',undefined,'chart-legend');for(const [cls,label] of [['fast','< 1秒'],['medium','1秒 ≤ 耗时 < 2秒'],['slow','≥ 2秒']]){const item=el('span');item.append(el('i',undefined,'legend-dot '+cls),document.createTextNode(label));legend.append(item);}wrap.append(legend,svg);return wrap;}
function resultLatencyCards(latency){const fragment=document.createDocumentFragment(),grid=el('div',undefined,'latency-grid');for(const [label,value] of [['平均耗时',latency.average_seconds],['P50',latency.p50_seconds],['P95',latency.p95_seconds],['P99',latency.p99_seconds],['MAX',latency.max_seconds]]){const card=el('div',undefined,'latency-stat');card.append(el('strong',value===null||value===undefined?'未知':value.toFixed(3)+' s'),el('span',label));grid.append(card);}const bands=latency.latency_bands||{},bandGrid=el('div',undefined,'latency-grid bands');for(const [key,label,cls] of [['under_1_second','0–1秒占比','fast'],['from_1_to_2_seconds','1–2秒占比','medium'],['at_least_2_seconds','2秒以上占比','slow']]){const value=bands[key],card=el('div',undefined,'latency-stat '+cls);card.append(el('strong',value?.ratio===null||value?.ratio===undefined?'未知':pct(value.ratio)),el('span',label+' · '+fmt(value?.count||0)+' 次'));bandGrid.append(card);}fragment.append(grid,bandGrid);return fragment;}
function resultLatencyOverview(model){const latency=model.statistics.latency||{},section=el('section',undefined,'metrics latency-round');section.append(el('h3','总体耗时统计'),el('p','全部轮次 · 有效耗时 '+fmt(latency.count||0)+' 条'+(latency.missing_count?' · 缺失耗时 '+fmt(latency.missing_count)+' 条':''),'muted'),resultLatencyCards(latency));return section;}
function resultLatency(model){const details=el('details',undefined,'metrics');details.append(el('summary','各轮耗时统计与 Token-耗时图表'),el('p','每个点代表一次真实的回复生成请求，不包含意图识别耗时。Y 轴使用整数秒刻度。','muted'));for(const round of model.rounds){const latency=round.statistics.latency||{},section=el('section',undefined,'latency-round');section.append(el('h3','第 '+round.round+' 轮'),el('p','有效耗时 '+fmt(latency.count||0)+' 条 · 图表样本 '+fmt(latency.charted_count||0)+' 条','muted'),resultLatencyCards(latency),resultLatencyChart(latency,round.round));details.append(section);}return details;}
function tagTable(groups){const wrap=el('div',undefined,'table-scroll'),table=el('table'),head=el('tr'),thead=el('thead');for(const label of ['功能','测试数','通过数','成功率'])head.append(el('th',label));thead.append(head);table.append(thead);const body=el('tbody');for(const [name,s] of Object.entries(groups||{})){const row=el('tr');for(const value of [name,fmt(s.total),fmt(s.passed),pct(s.pass_rate)])row.append(el('td',value));body.append(row);}table.append(body);wrap.append(table);return wrap;}
function render(){const root=$('models');root.replaceChildren();let shown=0;const query=$('search').value.trim().toLowerCase();for(const model of models){if(($('run')?.value&&$('run').value!==model.run_id)||($('model').value&&$('model').value!==model.model)||($('dataset').value&&$('dataset').value!==model.dataset_sha256))continue;const rows=model.rows.filter(row=>!query||(row.id+' '+row.user_request+' '+row.expected_text).toLowerCase().includes(query));if(!rows.length)continue;shown+=rows.length;const panel=el('section',undefined,'panel'),head=el('div',undefined,'panel-head'),identity=el('div'),validator=model.validator?.type==='deterministic_local'?'本地确定性规则':('历史AI裁判 · '+(model.judge?.model||'未知'));identity.append(el('h2','模型名称：'+model.model),el('p',(model.run_id?'运行批次：'+model.run_id+'\n':'')+'数据集：'+model.conversation_id+' · '+model.dataset_sha256.slice(0,12)+'\n校验：'+validator,'muted'));head.append(identity,badge(model.rounds.length+' 轮',''));panel.append(head);const stats=el('div',undefined,'model-stats');resultStats(stats,model.statistics);panel.append(stats,resultLatencyOverview(model));const extra=el('details',undefined,'metrics');extra.append(el('summary','各轮统计与功能成功率'));for(const round of model.rounds)extra.append(el('p','第 '+round.round+' 轮：'+pct(round.statistics.pass_rate)+'（'+round.statistics.passed+'/'+round.statistics.total+'）','round-line'));extra.append(el('h3','不同功能的成功率'),tagTable(model.by_function));panel.append(extra,resultLatency(model));const wrap=el('div',undefined,'table-scroll'),table=el('table'),hr=el('tr'),thead=el('thead');for(const label of ['结果ID','测试次数','当前请求','类型','标准结果','通过率','详情'])hr.append(el('th',label));thead.append(hr);table.append(thead);const body=el('tbody');for(const row of rows){const tr=el('tr'),cell=el('td'),link=el('a','查看','request-link'),url=new URL(row.request_link,location.href);url.searchParams.set('result_id',row.id);link.href=url.href;cell.append(link);for(const value of [row.id,fmt(row.tests),row.user_request,row.result_type,row.expected_text,pct(row.pass_rate)])tr.append(el('td',value));tr.append(cell);body.append(tr);}table.append(body);wrap.append(table);panel.append(wrap);root.append(panel);} $('count').textContent='显示 '+shown+' 条结果样本';$('empty').hidden=shown!==0;}
for(const name of ['run','model','dataset'])if($(name))$(name).addEventListener('change',()=>{syncResultFilters();render();});$('search').addEventListener('input',render);render();
"""

RESULT_DETAILS_BODY = """
<div class="heading"><div><div class="eyebrow">RESULT EVALUATION / TRACE</div><h1>结果判断明细</h1><p class="lead">查看当前请求、数据集真值、模型返回和本地确定性校验结论。</p></div></div><p id="empty" class="empty" hidden>暂无结果判断记录。</p>
<div id="result-layout"><section class="panel"><div class="toolbar"><div class="field"><label for="record">结果记录</label><select id="record"></select></div></div></section><article class="panel"><div class="panel-head"><h2 id="result-title"></h2><span id="result-outcome"></span></div><h3>当前用户请求</h3><pre id="result-request"></pre><h3>数据集标准答案</h3><pre id="result-expected"></pre><h3>模型实际返回</h3><pre id="result-actual"></pre><h3>本地校验结论</h3><pre id="result-judgment"></pre></article><section class="panel" id="embedding-panel" hidden><h3>FastEmbed 中文语义评分</h3><p class="status">仅显示实际触发向量语义兜底的文本字段；结构化字段仍按确定性规则校验。</p><div class="table-scroll"><table><thead><tr><th>字段路径</th><th>标准文本</th><th>实际文本</th><th>相似度</th><th>阈值</th><th>结论</th></tr></thead><tbody id="embedding-scores"></tbody></table></div></section><section class="panel"><h3>待测模型完整调用</h3><pre id="candidate-call"></pre></section></div><p id="meta" class="footer hash"></p>
"""

RESULT_DETAILS_JS = r"""
const meta=DATA.metadata,rows=DATA.results||[];$('meta').textContent='结果记录 '+rows.length+' 条';
function show(anchor){const row=rows.find(item=>item.request_anchor===anchor);if(!row)return;location.hash=anchor;$('result-title').textContent=row.id+' · 第 '+row.round+' 轮 · '+row.model;$('result-outcome').replaceChildren(badge(row.passed?'通过':row.error?'模型调用失败':'不通过',row.passed?'pass':row.error?'unknown':'fail'));$('result-request').textContent=row.user_request;$('result-expected').textContent=row.expected_text;const raw=row.candidate_call?.raw_content??row.candidate_call?.response?.choices?.[0]?.message?.content;$('result-actual').textContent=row.actual_text??raw??'模型没有返回文本或函数调用';$('result-judgment').textContent=JSON.stringify(row.judgment,null,2);$('candidate-call').textContent=JSON.stringify(row.candidate_call,null,2);const scores=row.judgment?.embedding_scores||[],body=$('embedding-scores');body.replaceChildren();$('embedding-panel').hidden=!scores.length;for(const score of scores){const tr=el('tr');for(const value of [score.path,score.expected,score.actual,Number(score.similarity).toFixed(4),Number(score.threshold).toFixed(2)])tr.append(el('td',value));const outcome=el('td');outcome.append(badge(score.passed?'通过':'不通过',score.passed?'pass':'fail'));tr.append(outcome);body.append(tr);}}
for(const row of rows)option($('record'),row.request_anchor,row.source_run_id+' · 第'+row.round+'轮 · '+row.id+' · '+row.user_request.slice(0,30));$('record').addEventListener('change',()=>show($('record').value));if(rows.length){const wanted=decodeURIComponent(location.hash.slice(1)),first=rows.some(row=>row.request_anchor===wanted)?wanted:rows[0].request_anchor;$('record').value=first;show(first);}else{$('result-layout').hidden=true;$('empty').hidden=false;}
"""


def page(title, active, body, script, data_file):
    navigation = "".join(f'<a href="{name}.html" class="{"active" if name == active else ""}"'
                         + (' aria-current="page"' if name == active else '') + f'>{label}</a>'
                         for name, label in (("summary", "意图汇总"), ("runs", "意图单次"), ("details", "意图明细"),
                                             ("result_summary", "结果汇总"), ("result_runs", "结果单次"),
                                             ("result_details", "结果明细")))
    # Report JSON is fetched as data and rendered only with textContent. Neither
    # model output nor requests are embedded in the static viewer's source.
    loader = r"""
async function renderReport(){
 const state=document.getElementById('load-state');
 try{
  if(location.protocol==='file:')throw new Error('请通过本地 HTTP 服务打开：在 robot_addressing_v1 目录执行 python3 evaluate.py serve，然后访问 http://127.0.0.1:8786/templates/summary.html');
  const query=new URLSearchParams(location.search);
  const folder=query.get('results')||'results';
  const base=new URL('../'+folder.replace(/^\/+|\/$/g,'')+'/',location.href);
  const run=query.get('run');
  const reportURL=new URL(run?encodeURIComponent(run)+'/'+REPORT_FILE:REPORT_FILE,base);
  for(const key of ['label_key','complete_only'])if(query.has(key))reportURL.searchParams.set(key,query.get(key));
  const response=await fetch(reportURL,{cache:'no-store'});
  if(!response.ok)throw new Error('无法读取报告（HTTP '+response.status+'）。请先执行 python3 evaluate.py report 或运行一次测试。');
  const DATA=await response.json();
  for(const name of ['summary','runs','details']){const link=document.querySelector('a[href="results/'+name+'.json"]');if(link)link.href=new URL(run?encodeURIComponent(run)+'/'+name+'.json':name+'.json',base).href;}
  for(const link of document.querySelectorAll('nav a')){const url=new URL(link.href);for(const key of ['results','label_key','complete_only'])if(query.has(key))url.searchParams.set(key,query.get(key));link.href=url.href;}
  if(query.has('results')||query.has('label_key')||query.has('complete_only')||run)for(const model of DATA.models||[]){for(const row of model.rows){const url=new URL(row.request_link,location.href);for(const key of ['results','label_key','complete_only'])if(query.has(key))url.searchParams.set(key,query.get(key));if(run)url.searchParams.set('run',run);row.request_link=url.href;}if(model.source_run_id)model.source_summary_link=new URL(encodeURIComponent(model.source_run_id)+'/summary.json',base).href;}
  state.hidden=true;
"""
    loader += script + r"""
 }catch(error){
  state.hidden=false;state.className='notice';state.textContent=error.message;
  const layout=document.getElementById('layout');if(layout)layout.hidden=true;
 }
}
renderReport();
"""
    loader = 'const REPORT_FILE='+json.dumps(data_file)+';'+COMMON_JS+loader
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} · Robot Evaluation</title><link rel="icon" type="image/svg+xml" sizes="any" href="favicon.svg"><style>{CSS}</style></head><body>'
            f'<header class="top"><div class="bar"><div class="brand"><span class="mark" aria-hidden="true">R</span><span>Robot Evaluation</span></div><nav aria-label="报告导航">{navigation}</nav></div></header>'
            f'<main><p id="load-state" class="status" role="status">正在读取测试报告…</p>{body}</main>'
            f'<script>{loader}</script></body></html>')


def write_pages(directory):
    (directory / "summary.html").write_text(page("全部测试统计汇总", "summary", SUMMARY_BODY, SUMMARY_JS, "summary.json"), encoding="utf-8")
    (directory / "runs.html").write_text(page("单次运行结果对比", "runs", RUNS_BODY, SUMMARY_JS, "runs.json"), encoding="utf-8")
    (directory / "details.html").write_text(page("每次测试的明细", "details", DETAILS_BODY, DETAILS_JS, "details.json"), encoding="utf-8")
    (directory / "result_summary.html").write_text(page("结果判断汇总", "result_summary", RESULT_SUMMARY_BODY, RESULT_SUMMARY_JS, "result-summary.json"), encoding="utf-8")
    (directory / "result_runs.html").write_text(page("结果判断单次运行对比", "result_runs", RESULT_RUNS_BODY, RESULT_SUMMARY_JS, "result-runs.json"), encoding="utf-8")
    (directory / "result_details.html").write_text(page("结果判断明细", "result_details", RESULT_DETAILS_BODY, RESULT_DETAILS_JS, "result-details.json"), encoding="utf-8")
