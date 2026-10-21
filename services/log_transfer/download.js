'use strict';
let files = [];
const list = document.getElementById('files');
const message = document.getElementById('message');
function size(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : (n / 1024).toFixed(1) + ' KB'; }
function render() {
  list.replaceChildren();
  const selected = document.getElementById('filter').value;
  const rows = files.filter(f => selected === 'all' || f.kind === selected || selected === 'log' && f.kind === 'racechrono');
  message.textContent = rows.length ? `${rows.length} 个文件 · 选择下载` : '这里还没有对应的记录文件';
  for (const f of rows) {
    const card = document.createElement('article'); card.className = 'card';
    const meta = document.createElement('div'); meta.className = 'meta';
    const tag = document.createElement('div'); tag.className = 'tag'; tag.textContent = f.kind === 'racechrono' ? 'RaceChrono CSV v3' : f.kind === 'log' ? '原始 LOG / JSONL' : 'GPS / ' + f.name.split('.').pop().toUpperCase();
    const name = document.createElement('div'); name.className = 'name'; name.textContent = f.name;
    const detail = document.createElement('div'); detail.className = 'details'; detail.textContent = (f.generated ? '按需生成 CSV · 不改动原始 LOG' : size(f.size)) + ' · ' + new Date(f.modified).toLocaleString('zh-CN');
    meta.append(tag, name, detail); card.append(meta);
    if (f.recording) { const busy = document.createElement('small'); busy.textContent = '行程记录中'; card.append(busy); }
    else { const link = document.createElement('a'); link.className = 'download'; link.textContent = '下载'; link.href = f.url; link.download = f.name; card.append(link); }
    list.append(card);
  }
}
async function load() {
  message.textContent = '正在刷新…';
  try {
    const response = await fetch('api/files', {cache: 'no-store'});
    if (!response.ok) throw new Error('共享已关闭或网络已断开');
    files = (await response.json()).files;
    render();
  } catch (e) { message.textContent = e.message + '，请连接仪表热点后重新扫描下载二维码。'; }
}
document.getElementById('refresh').onclick = load;
document.getElementById('filter').onchange = render;
load();
