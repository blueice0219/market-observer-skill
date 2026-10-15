'use strict';
const $ = id => document.getElementById(id);
const state = { rows: [], meta: null, status: null, view: 'market', exchange: '', query: '', sort: 'code', order: 1, page: 1, size: 25, auto: true, busy: false, key: '', selected: null, error: '', watches: new Set() };
try { const saved = JSON.parse(localStorage.getItem('market-observer-watch') || '[]'); if (Array.isArray(saved)) state.watches = new Set(saved.filter(x => /^\d{6}$/.test(x))); } catch (_) {}
const exchangeNames = {sh:'沪',sz:'深',bj:'京'};
const titles = {market:'全市场行情',watch:'我的自选',rank:'市场排行榜',status:'数据与状态'};
const sources = {sina:'新浪财经',eastmoney:'东方财富',demo:'离线示例',file:'本地文件'};
const format = (value, digits=2) => value == null ? '—' : Number(value).toLocaleString('zh-CN',{minimumFractionDigits:digits,maximumFractionDigits:digits});
const compact = value => value == null ? '—' : Math.abs(value) >= 1e12 ? format(value/1e12)+' 万亿' : Math.abs(value) >= 1e8 ? format(value/1e8)+' 亿' : Math.abs(value) >= 1e4 ? format(value/1e4)+' 万' : format(value,0);
const tone = value => value == null || value === 0 ? 'neutral' : value > 0 ? 'up' : 'down';
const percent = value => value == null ? '—' : (value>0?'+':'')+format(value)+'%';
const time = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false,timeZone:'Asia/Shanghai'}) : '—';
function node(tag, text, cls) { const e = document.createElement(tag); if(text != null) e.textContent=text; if(cls) e.className=cls; return e; }
function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').hidden=true,2500); }
function toggleWatch(code) { state.watches.has(code)?state.watches.delete(code):state.watches.add(code); try { localStorage.setItem('market-observer-watch',JSON.stringify([...state.watches])); } catch (_) { toast('浏览器无法保存自选，本次会话内仍可使用'); } renderTable(); if(state.selected) renderDetail(); }
async function request(path) {
 const controller=new AbortController(); const timer=setTimeout(()=>controller.abort(),15000);
 try { const response=await fetch(path,{headers:state.key?{'X-API-Key':state.key}:{},signal:controller.signal,cache:'no-store'}); const body=await response.json();
  if(!response.ok) {const err=new Error(response.status===401?'服务需要密钥，请点击左下角「连接设置」。':body.error?.message||'请求失败'); err.status=response.status; throw err;} return body;
 } finally {clearTimeout(timer);}
}
async function refresh() {
 if(state.busy)return; state.busy=true; $('refresh').disabled=true; $('refresh').textContent='↻ 读取中…';
 try {
  const status=await request('/api/v1/status'); state.status=status;
  if(!status.meta) {state.rows=[];state.meta=null;throw new Error('尚无行情快照，采集器正在准备数据。请稍后刷新，或在「数据与状态」查看原因。');}
  let first=await request('/api/v1/quotes?limit=10000'); let rows=first.data;
  while(rows.length<first.total) { const next=await request('/api/v1/quotes?limit=10000&offset='+rows.length+'&expected_version='+encodeURIComponent(first.meta.version)); if(!next.data.length)throw new Error('快照分页不完整，请重试'); rows=rows.concat(next.data); }
  state.rows=rows; state.meta=first.meta; state.error='';
  $('last-refresh').textContent=' · 页面读取 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});
 } catch(error) { state.error=error.name==='AbortError'?'服务响应超时，请检查本机服务是否运行。':error.message==='Failed to fetch'?'无法连接本机服务，请运行桌面启动入口后重试。':error.message; }
 finally {state.busy=false;$('refresh').disabled=false;$('refresh').textContent='↻ 刷新行情';render();if(state.selected)renderDetail();}
}
function filtered() {
 let rows=state.rows.filter(r=>(!state.exchange||r.exchange===state.exchange)&&(!state.query||(r.name+r.code+r.symbol).toLowerCase().includes(state.query))&&(state.view!=='watch'||state.watches.has(r.code)));
 let field=state.sort, order=state.order;
 if(state.view==='rank') {const type=$('rank-type').value; field=type==='volume'?'volume':type==='amount'?'amount':'change_pct';order=type==='loss'?1:-1;rows=rows.filter(r=>r[field]!=null);}
 return rows.sort((a,b)=>{const av=a[field],bv=b[field];if(av==null)return bv==null?a.code.localeCompare(b.code):1;if(bv==null)return -1;const comparison=typeof av==='string'?av.localeCompare(bv):av-bv;return comparison*order||a.code.localeCompare(b.code);});
}
function renderTable() {
 const rows=filtered(); const pages=Math.max(1,Math.ceil(rows.length/state.size));state.page=Math.min(state.page,pages);
 const start=(state.page-1)*state.size; const fragment=document.createDocumentFragment();
 for(const row of rows.slice(start,start+state.size)) {
  const tr=node('tr');const starCell=node('td');const star=node('button',state.watches.has(row.code)?'★':'☆','star'+(state.watches.has(row.code)?' chosen':''));star.setAttribute('aria-label',(state.watches.has(row.code)?'移除自选 ':'添加自选 ')+row.name);star.onclick=()=>toggleWatch(row.code);starCell.append(star);tr.append(starCell);
  const stockCell=node('td');const stock=node('button',row.name,'stock-link');stock.onclick=()=>openDetail(row.code);const code=node('div',null,'stock-code');code.append(node('span',exchangeNames[row.exchange],'exchange-label'),document.createTextNode(row.code));stockCell.append(stock,code);tr.append(stockCell);
  tr.append(node('td',format(row.price),tone(row.change_pct)));const pct=node('td');pct.append(node('span',percent(row.change_pct),'change-pill '+tone(row.change_pct)));tr.append(pct,node('td',compact(row.volume)),node('td',compact(row.amount)));fragment.append(tr);
 }
 $('quote-rows').replaceChildren(fragment);$('empty').hidden=rows.length>0;
 $('empty').textContent=state.rows.length===0?'尚无可展示的行情，请查看上方提示。':state.view==='watch'&&state.watches.size===0?'还没有自选股票。点击股票左侧的 ☆，建立你的观察列表。':'未找到匹配的股票，请尝试其他名称或代码。';
 $('result-count').textContent=rows.length.toLocaleString()+' 只股票';$('page-info').textContent=rows.length?`${start+1}–${Math.min(start+state.size,rows.length)} / 共 ${rows.length.toLocaleString()} 只`:'0 只股票';$('page-number').textContent=state.page+' / '+pages;
 $('prev').disabled=state.page<=1;$('next').disabled=state.page>=pages;$('export').disabled=!rows.length;$('watch-count').textContent=state.watches.size;
 const rankType=$('rank-type').value; const effectiveSort=state.view==='rank'?(rankType==='amount'?'amount':rankType==='volume'?'volume':'change_pct'):state.sort; const effectiveOrder=state.view==='rank'?(rankType==='loss'?1:-1):state.order;
 document.querySelectorAll('[data-sort]').forEach(b=>{b.querySelector('span').textContent=effectiveSort===b.dataset.sort?(effectiveOrder===1?'↑':'↓'):'↕';b.disabled=state.view==='rank';});
}
function renderSummary() {
 const rows=state.rows;const known=rows.filter(r=>r.change_pct!=null);const up=known.filter(r=>r.change_pct>0).length;const down=known.filter(r=>r.change_pct<0).length;const flat=known.length-up-down;
 $('metric-total').textContent=state.meta?rows.length.toLocaleString():'—';$('metric-up').textContent=state.meta?up.toLocaleString():'—';$('metric-down').textContent=state.meta?down.toLocaleString():'—';
 $('up-share').textContent=known.length?'占有涨跌幅股票的 '+format(up/known.length*100,1)+'%':'暂无有效涨跌幅';$('down-share').textContent=known.length?'占有涨跌幅股票的 '+format(down/known.length*100,1)+'%':'暂无有效涨跌幅';
 const amounts=rows.filter(r=>r.amount!=null);$('metric-amount').textContent=amounts.length?compact(amounts.reduce((sum,r)=>sum+r.amount,0)):'—';$('metric-amount-note').textContent=amounts.length===rows.length?'已返回股票成交额之和':`汇总 ${amounts.length} 只有效成交额`;
 $('metric-source').textContent=state.meta?(sources[state.meta.source]||state.meta.source)+' · '+(state.meta.is_demo?'示例数据':'覆盖完整性未验证'):'等待行情快照';
 $('breadth-ratio').textContent=known.length?format(up/known.length*100,1)+'%':'—';
 for(const [key,value] of [['up',up],['flat',flat],['down',down]]){$('breadth-'+key).style.width=(known.length?value/known.length*100:0)+'%';$('breadth-'+key+'-count').textContent=state.meta?value:'—';}
 $('breadth-note').textContent=`全市场有涨跌幅 ${known.length.toLocaleString()} 只 · 缺失 ${rows.length-known.length} 只`;
 const bins=[{label:'≥ 5%',count:known.filter(r=>r.change_pct>=5).length,color:'#d96a65'},{label:'0 ~ 5%',count:known.filter(r=>r.change_pct>0&&r.change_pct<5).length,color:'#e8a6a1'},{label:'0%',count:flat,color:'#c5cdd3'},{label:'−5 ~ 0%',count:known.filter(r=>r.change_pct<0&&r.change_pct>-5).length,color:'#a1c9bb'},{label:'≤ −5%',count:known.filter(r=>r.change_pct<=-5).length,color:'#56a08b'}];
 const max=Math.max(1,...bins.map(b=>b.count));$('distribution').replaceChildren(...bins.map(b=>{const row=node('div',null,'dist-row'),track=node('div',null,'dist-track'),fill=node('div',null,'dist-fill');fill.style.width=b.count/max*100+'%';fill.style.background=b.color;track.append(fill);row.append(node('span',b.label),track,node('b',b.count.toLocaleString()));return row;}));
}
function ageSeconds(){return state.meta?Math.max(0,(Date.now()-new Date(state.meta.observed_at).getTime())/1000):null;}
function renderHealth() {
 const age=ageSeconds();const stale=state.meta&&(age>state.meta.stale_after_seconds);const warning=state.error||stale||state.meta?.is_demo||state.status?.last_error;
 $('live-pill').textContent=state.error?'连接异常':!state.meta?'等待数据':state.meta.is_demo?'示例数据':stale?'快照已过期':state.status?.last_error?'采集异常':'快照可用';$('live-pill').classList.toggle('warn',!!warning);
 let notice=state.error;if(state.error&&state.meta)notice+=' 当前保留上一份成功读取的快照。';if(!notice&&state.meta?.is_demo)notice='当前为离线示例数据，不代表真实市场行情。';if(!notice&&stale)notice='当前快照已过期，表格保留历史采集结果。请查看采集状态。';if(!notice&&state.status?.last_error)notice='最近一次采集失败，当前显示上一份有效快照。详情见「数据与状态」。';
 $('notice').hidden=!notice;$('notice').textContent=notice||'';
 $('source').textContent=state.meta?sources[state.meta.source]||state.meta.source:'—';$('collected').textContent=state.meta?time(state.meta.collected_at).split(' ').slice(-1)[0]:'—';$('age').textContent=age==null?'—':age<60?Math.floor(age)+' 秒':Math.floor(age/60)+' 分钟';$('service-state').textContent=state.error?'连接异常':state.status?.last_error?'采集异常':state.meta?'服务已连接':'等待首轮数据';
}
function renderStatus() {
 const status=state.status;const phase={weekend:'周末窗口',auction_window:'集合竞价窗口',continuous_window:'连续竞价窗口',closing_auction_window:'收盘竞价窗口',outside_session_window:'非连续交易窗口'};
 const details=[['连接地址',location.origin],['当前行情来源',state.meta?sources[state.meta.source]||state.meta.source:'尚无数据'],['最近成功采集',time(state.meta?.collected_at)],['最近采集尝试',time(status?.last_attempt)],['连续失败次数',status?.consecutive_failures??'—'],['快照标识',state.meta?.version||'—'],['交易时段估计',phase[status?.market_clock?.phase_estimate]||'—'],['覆盖与时间校验','未验证完整覆盖及交易所行情时间']];
 $('status-details').replaceChildren(...details.map(([label,value])=>{const row=node('div');row.append(node('dt',label),node('dd',String(value)));return row;}));$('last-error').textContent=status?.last_error||state.error||'最近一次采集没有报告错误。';
}
function render(){renderSummary();renderTable();renderHealth();renderStatus();}
function setView(view) {state.view=view;state.page=1;document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});$('title').firstChild.textContent=titles[view];$('breadcrumb').textContent=titles[view];$('subtitle').textContent={market:'一览沪深京市场动态，让每一次观察都有依据。',watch:'收藏值得持续关注的公司，自选保存在当前浏览器。',rank:'按当前行情快照排序，快速发现市场中的变化。',status:'了解数据从哪里来，以及最近一次采集是否顺利。'}[view];$('market-content').hidden=view==='status';$('status-content').hidden=view!=='status';$('rank-type').hidden=view!=='rank';renderTable();renderStatus();}
function openDetail(code){state.selected=code;renderDetail();$('detail-dialog').showModal();}
function renderDetail(){const row=state.rows.find(r=>r.code===state.selected);if(!row){$('detail-name').textContent='当前快照中暂无该股票';$('detail-symbol').textContent=state.selected;$('detail-price').replaceChildren();$('detail-fields').replaceChildren();$('detail-watch').hidden=true;return;}$('detail-watch').hidden=false;$('detail-name').textContent=row.name;$('detail-symbol').textContent=row.code+' · '+exchangeNames[row.exchange]+'市 · '+time(state.meta.collected_at);const price=$('detail-price');price.className='detail-price '+tone(row.change_pct);price.replaceChildren(document.createTextNode(format(row.price)),node('small',percent(row.change_pct)));const fields=[['今开',format(row.open)],['昨收',format(row.prev_close)],['最高',format(row.high)],['最低',format(row.low)],['涨跌额',format(row.change)],['换手率',row.turnover_pct==null?'—':format(row.turnover_pct)+'%'],['成交量（股）',compact(row.volume)],['成交额（元）',compact(row.amount)],['源时间原文',row.quote_time||'未提供'],['数据来源',sources[state.meta.source]||state.meta.source]];$('detail-fields').replaceChildren(...fields.map(([key,value])=>{const div=node('div');div.append(node('dt',key),node('dd',value));return div;}));$('detail-watch').textContent=state.watches.has(row.code)?'★ 移出我的自选':'☆ 添加到我的自选';}
function exportCsv(){const rows=filtered();if(!rows.length)return;const fields=[['代码','code'],['名称','name'],['最新价（元）','price'],['涨跌幅（%）','change_pct'],['成交量（股）','volume'],['成交额（元）','amount']];const cell=(value,key)=>{if(value==null)return '""';let text=String(value);if(key==='code'||(typeof value==='string'&&/^[=+\-@\t\r]/.test(text)))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};const text='\uFEFF'+fields.map(x=>cell(x[0])).join(',')+'\r\n'+rows.map(r=>fields.map(x=>cell(r[x[1]],x[1])).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const link=node('a');link.href=url;link.download='观市行情_'+new Date().toISOString().slice(0,10)+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出当前筛选的 '+rows.length+' 只股票');}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
document.querySelectorAll('[data-exchange]').forEach(b=>b.onclick=()=>{state.exchange=b.dataset.exchange;state.page=1;document.querySelectorAll('[data-exchange]').forEach(x=>x.classList.toggle('selected',x===b));renderTable();});
document.querySelectorAll('[data-sort]').forEach(b=>b.onclick=()=>{if(state.sort===b.dataset.sort)state.order*=-1;else{state.sort=b.dataset.sort;state.order=state.sort==='code'?1:-1;}state.page=1;renderTable();});
$('search').oninput=e=>{state.query=e.target.value.trim().toLowerCase();state.page=1;renderTable();};$('rank-type').onchange=()=>{state.page=1;renderTable();};
$('prev').onclick=()=>{state.page--;renderTable();};$('next').onclick=()=>{state.page++;renderTable();};$('refresh').onclick=refresh;$('auto').onclick=()=>{state.auto=!state.auto;$('auto').textContent='◷ 自动刷新 · '+(state.auto?'开':'关');};
$('export').onclick=exportCsv;$('settings').onclick=()=>$('settings-dialog').showModal();$('settings-top').onclick=()=>$('settings-dialog').showModal();$('save-key').onclick=()=>{state.key=$('api-key').value;$('settings-dialog').close();refresh();};
document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());$('detail-watch').onclick=()=>toggleWatch(state.selected);$('detail-dialog').onclose=()=>state.selected=null;
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)&&!document.querySelector('dialog[open]')){e.preventDefault();if(state.view==='status')setView('market');$('search').focus();}});
function tick(){$('clock').textContent=new Date().toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});renderHealth();}tick();setInterval(tick,1000);setInterval(()=>{if(state.auto&&!document.hidden)refresh();},30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden&&state.auto)refresh();});refresh();
