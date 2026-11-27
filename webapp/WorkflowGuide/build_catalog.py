import ast
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEXT = {".py", ".js", ".jsx", ".html", ".css", ".sql", ".ps1", ".md", ".toml", ".yaml", ".yml", ".ipynb"}
STEP = {
    ast.Assign: "กำหนดค่าให้ตัวแปร", ast.AnnAssign: "กำหนดค่าพร้อมระบุชนิด",
    ast.If: "ตรวจเงื่อนไข", ast.For: "ทำซ้ำทีละรายการ",
    ast.AsyncFor: "อ่านข้อมูลทีละชุดแบบรอได้", ast.While: "ทำซ้ำตราบที่เงื่อนไขเป็นจริง",
    ast.Try: "จัดการกรณีที่คำสั่งล้มเหลว", ast.With: "เปิดทรัพยากรและจัดการเมื่อจบงาน",
    ast.Return: "ส่งผลกลับให้ตัวเรียก", ast.Expr: "เรียกใช้คำสั่ง",
    ast.Raise: "แจ้งข้อผิดพลาด", ast.AugAssign: "ปรับค่าที่มีอยู่",
    ast.FunctionDef: "ประกาศฟังก์ชันย่อย", ast.AsyncFunctionDef: "ประกาศฟังก์ชันย่อย",
}

def python_index(source):
    tree = ast.parse(source)
    lines = source.splitlines()
    items = []
    def visit(node, parents=()):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            parents = (*parents, node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            calls = []
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    calls.append(ast.unparse(child.func))
            steps = []
            for statement in node.body:
                if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
                    continue
                steps.append([STEP.get(type(statement), "ประมวลผลคำสั่ง"), lines[statement.lineno-1].strip()])
            items.append(dict(name=".".join(parents), line=start, end=node.end_lineno,
                description=ast.get_docstring(node) or "", calls=list(dict.fromkeys(calls)), steps=steps))
        for child in ast.iter_child_nodes(node):
            visit(child, parents)
    visit(tree)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.extend(("." * node.level + (node.module or ""), alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            imports.extend((alias.name, "") for alias in node.names)
    return items, imports, ast.get_docstring(tree) or ""

def notebook_source(path):
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    blocks = []
    for index, cell in enumerate(cells, 1):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        # Notebook magics are commands, not Python syntax. Keep their lines visible as comments.
        source = re.sub(r"(?m)^(\s*)([%!].*)$", r"\1# \2", source)
        blocks.append(f"# Code cell {index}\n{source}")
    return "\n\n".join(blocks)

def role(path):
    groups = [
        ("webapp/Dashboard/frontend/", "หน้าเว็บ Dashboard และการเรียก API"),
        ("webapp/Dashboard/backend/src/routes/", "กำหนด URL และรับคำขอ HTTP"),
        ("webapp/Dashboard/backend/src/controllers/", "จัดลำดับงานเมื่อ API ได้รับคำขอ"),
        ("webapp/Dashboard/backend/src/services/capture/", "อ่านแพ็กเก็ตและประกอบเป็น flow"),
        ("webapp/Dashboard/backend/src/services/", "งานเบื้องหลัง เช่น การทำนาย จับทราฟฟิก หรือเทรน"),
        ("webapp/Dashboard/backend/src/db/", "เก็บและอ่านข้อมูลจากฐานข้อมูล"),
        ("webapp/Dashboard/backend/src/models/", "กำหนดรูปแบบข้อมูลและฟีเจอร์"),
        ("webapp/Dashboard/backend/model_backup/", "ไฟล์โมเดลและข้อมูลเวอร์ชัน"),
        ("webapp/Dashboard/backend/captures/", "ไฟล์ข้อมูลสำหรับวิเคราะห์ทราฟฟิก"),
        ("webapp/TrafficReplay/", "ส่งตัวอย่างทดสอบและแสดงผลเดโม"),
        ("webapp/Dashboard/", "เปิดระบบ ตั้งค่า หรือดูแล Dashboard"),
    ]
    return next((label for prefix, label in groups if path.startswith(prefix)), "ไฟล์ประกอบของโปรเจกต์")

def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT)
    paths = sorted(set(tracked.decode().split("\0")) - {""})
    files = {}
    js = {}
    for key in paths:
        path = ROOT / key
        if not key.startswith(("webapp/Dashboard/", "webapp/TrafficReplay/")):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if any(part.startswith(".env") and part != ".env.example" for part in path.parts):
            continue
        ext = path.suffix.lower()
        entry = dict(role=role(key), kind=ext, functions=[], imports=[], note="")
        files[key] = entry
        if ext not in TEXT or path.stat().st_size > 1_000_000:
            entry["note"] = "แสดงชื่อและตำแหน่งของไฟล์ประกอบ"
            continue
        try:
            source = notebook_source(path) if ext == ".ipynb" else path.read_text(encoding="utf-8-sig")
            entry["source"] = source
            if ext in {".py", ".ipynb"}:
                entry["functions"], entry["imports"], entry["description"] = python_index(source)
            elif ext in {".js", ".jsx", ".html"}:
                js[key] = source
            elif ext == ".ps1":
                matches = list(re.finditer(r"(?im)^\s*function\s+([\w-]+)", source))
                for index, match in enumerate(matches):
                    end = matches[index+1].start() if index+1 < len(matches) else len(source)
                    block = source[match.start():end].rstrip()
                    entry["functions"].append(dict(name=match[1], line=source[:match.start()].count("\n")+1, code=block,
                                                  description="คำสั่ง PowerShell ที่ประกาศในสคริปต์นี้", calls=[], steps=[]))
        except (SyntaxError, ValueError, OSError) as error:
            entry["note"] = f"แสดงซอร์สที่อ่านได้ แต่แยกรายการฟังก์ชันไม่ได้ ({type(error).__name__})"
    result = subprocess.run(["node", str(HERE/"index-js.cjs")], input=json.dumps(js), capture_output=True, encoding="utf-8", check=True)
    for key, details in json.loads(result.stdout).items():
        files[key].update(details)
    (HERE/"catalog.js").write_text("window.WORKFLOW_CATALOG = " + json.dumps(files, ensure_ascii=True) + ";\n", encoding="utf-8")
    print(f"{len(files)} files, {sum(len(entry['functions']) for entry in files.values())} functions")

if __name__ == "__main__":
    main()
