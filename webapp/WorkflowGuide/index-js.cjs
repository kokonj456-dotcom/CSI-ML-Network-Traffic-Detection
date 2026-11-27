const fs = require('node:fs');
const {createRequire} = require('node:module');
const path = require('node:path');
const parser = createRequire(path.join(__dirname, '../Dashboard/frontend/package.json'))('@babel/parser');
const sources = JSON.parse(fs.readFileSync(0, 'utf8'));
const types = new Set(['FunctionDeclaration','FunctionExpression','ArrowFunctionExpression','ObjectMethod','ClassMethod','ClassPrivateMethod']);
const descriptions = {
  ReturnStatement:'ส่งผลกลับ', IfStatement:'ตรวจเงื่อนไข', VariableDeclaration:'เตรียมค่าที่ใช้',
  ExpressionStatement:'เรียกคำสั่ง', TryStatement:'จัดการข้อผิดพลาด', ForOfStatement:'ทำงานทีละรายการ',
  SwitchStatement:'เลือกงานตามค่า', ForStatement:'ทำซ้ำ', ThrowStatement:'แจ้งข้อผิดพลาด'
};
function nameOf(node) {
  if (!node) return '';
  if (node.type === 'Identifier' || node.type === 'PrivateName') return node.name || '#' + nameOf(node.id);
  if (node.type === 'MemberExpression' || node.type === 'OptionalMemberExpression')
    return [nameOf(node.object),nameOf(node.property)].filter(Boolean).join('.');
  if (node.type === 'ThisExpression') return 'this';
  return String(node.value ?? '');
}
const output = {};
for (const [file, source] of Object.entries(sources)) {
  const functions = [], imports = [], errors = [];
  const blocks = file.endsWith('.html')
    ? [...source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].filter(m => !m[0].slice(0,m[0].indexOf(">")).includes("application/json")).map(m => [m[1], source.slice(0,m.index+m[0].indexOf('>')+1).split('\n').length-1])
    : [[source,0]];
  for (const [code, offset] of blocks) {
    function walk(node,parent,current,owner) {
      if (!node || typeof node.type !== 'string') return;
      if (node.type === 'ClassDeclaration') owner = nameOf(node.id);
      if (node.type === 'ImportDeclaration') imports.push([node.source.value,'']);
      if (types.has(node.type)) {
        const name = nameOf(node.id || node.key || parent?.id || parent?.key);
        const label = name || nameOf(parent?.callee) || 'callback';
        const statements = node.body.type==='BlockStatement' ? node.body.body : [node.body];
        const declaration = parent?.type === 'VariableDeclarator' && parent.init === node ? parent : node;
        current = {name: [owner,label].filter(Boolean).join('.'), line: declaration.loc.start.line+offset,
          end: node.loc.end.line+offset, code:code.slice(declaration.start,node.end),
          description: '', calls: [], steps: statements.map(s=>[descriptions[s.type] || 'ประมวลผลนิพจน์',code.slice(s.start,s.end).split('\n')[0]])};
        functions.push(current);
      }
      if (current && (node.type === 'CallExpression' || node.type === 'OptionalCallExpression')) {
        const target = nameOf(node.callee);
        if (target && !current.calls.includes(target)) current.calls.push(target);
      }
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) for (const child of value) walk(child,node,current,owner);
        else if (value && typeof value==='object') walk(value,node,current,owner);
      }
    }
    try { walk(parser.parse(code,{sourceType:'unambiguous',plugins:['jsx']}).program); }
    catch { errors.push('มีสคริปต์ที่แยกฟังก์ชันอัตโนมัติไม่ได้'); }
  }
  output[file] = {functions, imports, note:errors.join(' ')};
}
process.stdout.write(JSON.stringify(output));
