'use strict';
const catalog = window.WORKFLOW_CATALOG || {};
const files = Object.keys(catalog);
const $ = id => document.getElementById(id);
const flows = {
  'Live Capture': [
    ['จับแพ็กเก็ต','services/live_capture.py','run','อ่านแพ็กเก็ตจากอะแดปเตอร์'],
    ['รวมเป็น flow','capture/flows.py','push','จับคู่แพ็กเก็ตขาไปและขากลับ'],
    ['เตรียมฟีเจอร์','capture/flows.py','flow_record','สรุปเวลา ไบต์ และโปรโตคอล'],
    ['ทำนาย','services/inference.py','predict','ให้คะแนนและจัดคลาส'],
    ['บันทึก','db/mysql_store.py','save_records','เก็บ flow, prediction และ alert'],
    ['แสดงภาพรวม','features/monitor.js','renderMetrics','นับผลตามช่วงเวลาที่เลือก']
  ],
  'Import PCAP': [
    ['เลือกไฟล์','traffic/importCapture.js','importCaptureFile','อัปโหลดจาก Traffic Explorer'],
    ['รับไฟล์','controllers/captures.py','upload_capture','อ่านไฟล์ที่ส่งมา'],
    ['อ่านแพ็กเก็ต','capture/pcap.py','capture_flows','รวมแพ็กเก็ตเป็น flow'],
    ['ประเมินและบันทึก','controllers/captures.py','save_upload','ทำนายเป็นชุดแล้วบันทึกผล'],
    ['โหลดรายการ','traffic/loadTraffic.js','refreshTraffic','ดึง flow และ alert กลับมา']
  ],
  'CENTRAL Test': [
    ['เลือกตัวอย่าง','TrafficReplay/server.py','evaluate_demo','ส่ง record และฟีเจอร์ไปที่ API'],
    ['รับคำขอ','routes/inference.py','save_central_test','ตรวจรูปแบบรายการ'],
    ['ทำนายและบันทึก','controllers/inference.py','save_central_test','เก็บผลเป็น central_test'],
    ['แปลงเป็นแถวบนเว็บ','traffic/mapFlow.js','dashboardFlow','กำหนดแหล่งเป็น CENTRAL Test']
  ],
  'Feedback และฝึกโมเดล': [
    ['รายงานจาก Alerts','alerts/selection.js','bulkAlertAction','ส่งผลที่คนตรวจว่าเป็น false positive'],
    ['บันทึก Feedback','db/feedback_queries.py','report','เก็บรายงานและอัปเดตสถานะ alert'],
    ['เตรียมงานเทรน','services/model_training.py','start_training_job','เลือกข้อมูลและค่าที่ใช้ฝึก'],
    ['ฝึกและลงทะเบียน','services/model_training.py','run_training_job','สร้างโมเดล candidate'],
    ['เลือกใช้งาน','services/model_management.py','activate','เปลี่ยนโมเดลที่ระบบใช้อยู่']
  ],

};
const fileNotes = {
  'loadTraffic.js':'ดึง flow และ alert จาก API แล้วไล่ cursor เมื่อเริ่มโหลด จากนั้นรวมรายการที่ได้รับไว้สำหรับแสดงและค้นหา',
  'filterFlows.js':'ตรวจช่วงเวลา แหล่งข้อมูล โปรโตคอล สถานะ และข้อความค้นหาของแต่ละ flow',
  'mysql_store.py':'เชื่อมต่อ MySQL และจัดการการบันทึก capture, flow, prediction และ alert ใน transaction',
  'central_contract.py':'กำหนดคอลัมน์และขั้นตอนแปลงข้อมูลให้ตรงกับที่โมเดล CENTRAL ใช้',
  'model_registry.py':'ค้นหาไฟล์โมเดลตามเวอร์ชันและจัดการตำแหน่งโมเดลสำรอง',
  'schema.sql':'คำสั่งสร้างตาราง MySQL รวมถึงคีย์ที่เชื่อม flow, prediction, alert และ feedback',
  'windows_firewall.ps1':'สคริปต์ที่ backend เรียกสำหรับจัดการกฎ Windows Firewall ของ Flowwatch'
};
const functionNotes = {
  'services/inference.py:Predictor.predict':'ตรวจข้อมูลเข้า แปลงเป็นฟีเจอร์ตามรุ่นโมเดล ให้คะแนน attack และเลือกคลาสสำหรับ flow ที่ถูก flag',
  'db/mysql_store.py:MySQLStore.save_records':'ใช้ flow เดิมเมื่อพบ PCAP และเฟรมเดิม บันทึกผลทำนาย แล้วสร้าง alert เมื่อโมเดล flag',
  'capture/flows.py:FlowCollector.push':'อ่านหัว IP และโปรโตคอล ใช้คู่ปลายทางเพื่อหา flow เดิม แล้วเพิ่มจำนวนแพ็กเก็ตและไบต์',
  'traffic/loadTraffic.js:fetchAllTrafficPages':'ตาม next_before_id ไปทีละหน้าและรวมแถวจน API ไม่มีหน้าถัดไป',
  'traffic/mapFlow.js:dashboardFlow':'แปลงแถวจาก API ให้เป็นโครงข้อมูลที่ตาราง กราฟ และแผงรายละเอียดใช้ร่วมกัน'
};
const suffixName = name => name.split('.').at(-1);
const leaf = path => path.split('/').at(-1);
function el(tag, content, className) {
  const node = document.createElement(tag);
  if (content != null) node.textContent = content;
  if (className) node.className = className;
  return node;
}
function button(label, action) {
  const node = el('button',label);
  node.type = 'button';
  node.addEventListener('click',action);
  return node;
}
function resolveFile(hint) {
  return files.find(file=>file===hint) || files.find(file=>file.endsWith('/'+hint));
}
function navigate(file, index) {
  const hash = '#'+encodeURIComponent(file)+(index==null?'':':'+index);
  if (location.hash === hash) showLocation(true);
  else location.hash = hash;
}
function renderScenarios() {
  for (const name of Object.keys(flows)) {
    const control = button(name,()=>activate(name));
    $('scenarios').append(control);
  }
  function activate(name) {
    for (const control of $('scenarios').children)
      control.setAttribute('aria-pressed',String(control.textContent===name));
    $('steps').replaceChildren();
    for (const [label,hint,fn,detail] of flows[name]) {
      const item = el('li');
      const file = resolveFile(hint);
      const control = button(label,()=>{
        if (file) {
          const index = catalog[file].functions.findIndex(item=>suffixName(item.name)===fn);
          navigate(file,index<0?null:index);
        } else navigate(hint);
      });
      control.append(el('small',detail));
      item.append(control);
      $('steps').append(item);
    }
  }
  activate(Object.keys(flows)[0]);
}
function renderTree(selected, query) {
  const tree = $('tree');
  tree.replaceChildren();
  const folders = new Map();
  const search = query.trim().toLowerCase();
  for (const file of files) {
    const entry = catalog[file];
    const matching = entry.functions.map((fn,index)=>[fn,index])
      .filter(([fn])=>search && fn.name.toLowerCase().includes(search));
    if (search && !file.toLowerCase().includes(search) && !matching.length) continue;
    if (search) {
      const result = el('div',null,'search-result');
      result.append(button(leaf(file),()=>navigate(file)),el('small',file.replace(/^webapp\//,'')));
      for (const [fn,index] of matching) result.append(button('↳ '+fn.name,()=>navigate(file,index)));
      tree.append(result);
      continue;
    }
    const parts = file.replace(/^webapp\//,'').split('/');
    let container = tree;
    for (let i=0;i<parts.length-1;i++) {
      const folder = 'webapp/'+parts.slice(0,i+1).join('/')+'/';
      if (!folders.has(folder)) {
        const group = el('details');
        group.open = Boolean(search || selected.startsWith(folder) || i===0);
        const label = el('summary',parts[i]+'/');
        label.title = catalog[file].role;
        group.append(label,button('เกี่ยวกับโฟลเดอร์',()=>navigate(folder)));
        container.append(group);
        folders.set(folder,group);
      }
      container = folders.get(folder);
    }
    const control = button(leaf(file),()=>navigate(file));
    control.title = file;
    if (file===selected) control.setAttribute('aria-current','true');
    container.append(control);
    for (const [fn,index] of matching) container.append(button('↳ '+fn.name,()=>navigate(file,index)));
  }
  if (!tree.children.length) tree.append(el('p','ไม่พบไฟล์หรือฟังก์ชัน'));
}
function normalized(path) {
  const parts = [];
  for (const part of path.split('/')) {
    if (part==='..') parts.pop();
    else if (part && part!=='.') parts.push(part);
  }
  return parts.join('/');
}
function importPath(file, specifier, name) {
  const folder = file.split('/').slice(0,-1);
  let base;
  if (file.endsWith('.py') || file.endsWith('.ipynb')) {
    const dots = specifier.match(/^\.+/)?.[0].length || 0;
    const module = specifier.slice(dots).replaceAll('.','/');
    base = dots ? normalized([...folder.slice(0,folder.length-dots+1),module].join('/'))
      : normalized([folder.join('/'),module].join('/'));
    for (const candidate of [base+'/'+name+'.py',base+'.py',base+'/__init__.py',module+'.py'])
      if (catalog[candidate]) return candidate;
  } else if (specifier.startsWith('.')) {
    base = normalized([...folder,specifier].join('/'));
    for (const extension of ['','.js','.jsx','/index.js'])
      if (catalog[base+extension]) return base+extension;
  }
  return null;
}
const importsByFile = new Map(files.map(file=>[file,[...new Set(catalog[file].imports
  .map(([spec,name])=>importPath(file,spec,name)).filter(Boolean))]]));
function fileLinks(title, paths, host) {
  if (!paths.length) return;
  host.append(el('h3',title));
  const row = el('div',null,'links');
  for (const path of paths) {
    const control = button(leaf(path),()=>navigate(path));
    control.title = path;
    row.append(control);
  }
  host.append(row);
}
function codeBlock(source) {
  const pre = el('pre');
  pre.append(el('code',source));
  return pre;
}
function renderFile(file, selectedIndex) {
  const host = $('reader');
  const entry = catalog[file];
  host.replaceChildren(el('small',file),el('h2',leaf(file)),el('p',fileNotes[leaf(file)] || entry.description || entry.role));
  if (entry.note) host.append(el('p',entry.note,'muted'));
  const dependencies = el('details',null,'secondary');
  dependencies.append(el('summary','ไฟล์ที่เชื่อมโยง'));
  fileLinks('ไฟล์ที่ใช้',importsByFile.get(file),dependencies);
  fileLinks('ไฟล์ที่เรียกใช้ไฟล์นี้',files.filter(other=>importsByFile.get(other).includes(file)),dependencies);
  const importNames = [...new Set(entry.imports.map(([spec])=>spec).filter(Boolean))];
  if (importNames.length) dependencies.append(el('p',importNames.join(', ')));
  if (dependencies.children.length>1) host.append(dependencies);
  host.append(el('h3','ฟังก์ชันและเมธอด ('+entry.functions.length+')'));
  if (!entry.functions.length) host.append(el('p','ไฟล์นี้ไม่มีฟังก์ชันที่แยกแสดงได้','muted'));
  const lines = (entry.source || '').split('\n');
  entry.functions.forEach((fn,index)=>{
    const section = el('details',null,'function');
    section.id = 'function-'+index;
    section.open = selectedIndex===index;
    const summary = el('summary');
    summary.append(el('code',fn.name),el('small','บรรทัด '+fn.line));
    section.append(summary);
    section.addEventListener('toggle',()=>{
      if (!section.open || section.children.length>1) return;
      const note = Object.entries(functionNotes).find(([key])=>key.endsWith(':'+fn.name) && file.endsWith(key.split(':')[0]))?.[1];
      if (note || fn.description) section.append(el('p',note || fn.description));
      if (fn.steps.length) {
        const walkthrough = el('details',null,'secondary');
        walkthrough.open = !(note || fn.description);
        walkthrough.append(el('summary','ทำงานทีละขั้น'));
        const list = el('ol');
        for (const [label,statement] of fn.steps) {
          const item=el('li',label+' ');
          item.append(el('code',statement));
          list.append(item);
        }
        walkthrough.append(list);
        section.append(walkthrough);
      }
      if (fn.calls.length) {
        const calls = el('details',null,'secondary');
        calls.append(el('summary','ฟังก์ชันที่เรียกใช้'));
        const row = el('div',null,'links');
        const candidates = [file,...importsByFile.get(file)];
        for (const call of fn.calls) {
          const name = suffixName(call);
          const matches = candidates.flatMap(path=>catalog[path].functions
            .map((func,index)=>({func,index,path})).filter(({func})=>suffixName(func.name)===name));
          if (matches.length===1 && (!call.includes('.') || /^(self|this)\./.test(call))) {
            const {path,index} = matches[0];
            row.append(button(call,()=>navigate(path,index)));
          } else row.append(el('code',call));
        }
        calls.append(row);
        section.append(calls);
      }
      section.append(el('h4','ซอร์สโค้ด'),codeBlock(fn.code ?? lines.slice(fn.line-1,fn.end).join('\n')));
    });
    host.append(section);
  });
  if (entry.source) {
    const source = el('details');
    source.append(el('summary','ดูซอร์สทั้งไฟล์'));
    source.addEventListener('toggle',()=>{
      if (source.open && source.children.length===1) source.append(codeBlock(entry.source));
    });
    host.append(source);
  }
}
function showLocation(focus=false) {
  const [encoded,index] = location.hash.slice(1).split(':');
  let file;
  try { file = decodeURIComponent(encoded || ''); } catch { file = ''; }
  renderTree(file,$('search').value);
  if (catalog[file]) renderFile(file,index==null?null:Number(index));
  else {
    const host = $('reader');
    const descendants = file.endsWith('/')?files.filter(path=>path.startsWith(file)):[];
    host.replaceChildren(el('h2',descendants.length?file:'เลือกจุดเริ่มอ่านโค้ด'));
    if (descendants.length) {
      const roles = [...new Set(descendants.map(path=>catalog[path].role))];
      for (const role of roles) host.append(el('p',role));
      fileLinks('ไฟล์ในโฟลเดอร์ ('+descendants.length+')',descendants,host);
    } else host.append(el('p','กดขั้นในแผนภาพด้านบน หรือค้นหาจากชื่อไฟล์และชื่อฟังก์ชันด้านซ้าย'));
    if (!files.length) host.append(el('p','ยังไม่มีสารบัญ ให้รัน build_catalog.py ในโฟลเดอร์ WorkflowGuide'));
  }
  if (focus) {
    const target = index==null?$('reader'):$('function-'+index)?.querySelector('summary') || $('reader');
    target.focus({preventScroll:true});
    target.scrollIntoView({block:'nearest'});
  }
}
$('counts').textContent = files.length+' ไฟล์ / '+files.reduce((sum,file)=>sum+catalog[file].functions.length,0)+' ฟังก์ชัน';
renderScenarios();
showLocation();
window.addEventListener('hashchange',()=>showLocation(true));
$('search').addEventListener('input',()=>renderTree('', $('search').value));
