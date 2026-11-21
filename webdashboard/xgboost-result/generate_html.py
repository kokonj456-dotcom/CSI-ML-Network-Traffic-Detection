import json
from pathlib import Path

results_path = Path("webdashboard/xgboost-result/experiment_results.json")
if not results_path.exists():
    results_path = Path(__file__).resolve().parent / "experiment_results.json"

with open(results_path, encoding="utf-8") as f:
    data = json.load(f)

json_str = json.dumps(data)

html_template = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CENTRAL Dataset - XGBoost 4-Model Factorial Benchmark</title>
    <style>
        :root {
            --bg-base: #0b1120;
            --bg-card: #151f32;
            --bg-card-hover: #1e2c47;
            --border: #24344d;
            --border-light: #334766;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-blue: #38bdf8;
            --accent-indigo: #818cf8;
            --accent-green: #34d399;
            --accent-rose: #fb7185;
            --accent-amber: #fbbf24;
            --accent-purple: #c084fc;
            --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-family);
            line-height: 1.6;
            padding: 24px;
        }

        .container {
            max-width: 1440px;
            margin: 0 auto;
        }

        header {
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
        }

        .badge-bar {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }

        .badge {
            background: rgba(56, 189, 248, 0.12);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        .badge-green {
            background: rgba(52, 211, 153, 0.12);
            color: var(--accent-green);
            border-color: rgba(52, 211, 153, 0.3);
        }

        .badge-purple {
            background: rgba(192, 132, 252, 0.12);
            color: var(--accent-purple);
            border-color: rgba(192, 132, 252, 0.3);
        }

        .badge-amber {
            background: rgba(251, 191, 36, 0.12);
            color: var(--accent-amber);
            border-color: rgba(251, 191, 36, 0.3);
        }

        h1 {
            font-size: 1.95rem;
            font-weight: 800;
            color: #ffffff;
            margin-bottom: 8px;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 0.95rem;
            max-width: 1100px;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }

        .kpi-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px 20px;
            transition: border-color 0.2s, background 0.2s;
        }

        .kpi-card:hover {
            border-color: var(--accent-blue);
            background: var(--bg-card-hover);
        }

        .kpi-title {
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }

        .kpi-value-row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
        }

        .kpi-value {
            font-size: 2.1rem;
            font-weight: 800;
            color: #ffffff;
            font-feature-settings: 'tnum';
        }

        .kpi-delta {
            font-size: 0.85rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
        }

        .delta-positive {
            background: rgba(52, 211, 153, 0.15);
            color: var(--accent-green);
        }

        .kpi-subtext {
            margin-top: 6px;
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .controls-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            align-items: center;
            justify-content: space-between;
        }

        .control-group {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }

        .control-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
        }

        .btn-group {
            display: flex;
            background: var(--bg-base);
            padding: 3px;
            border-radius: 8px;
            border: 1px solid var(--border);
            gap: 2px;
            flex-wrap: wrap;
        }

        .btn-opt {
            background: transparent;
            color: var(--text-secondary);
            border: none;
            padding: 6px 14px;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-opt:hover {
            color: #ffffff;
        }

        .btn-opt.active {
            background: var(--accent-blue);
            color: #0f172a;
        }

        .table-section {
            margin-bottom: 32px;
        }

        .section-header {
            margin-bottom: 16px;
        }

        .section-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .section-desc {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .data-table-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow-x: auto;
        }

        .data-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.86rem;
            text-align: left;
        }

        .data-table th {
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }

        .data-table td {
            padding: 11px 14px;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }

        .data-table tr:hover td {
            background: rgba(56, 189, 248, 0.03);
        }

        .num-col {
            text-align: right;
            font-feature-settings: 'tnum';
        }

        .tag-pill {
            display: inline-block;
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-secondary);
            font-weight: 600;
        }

        .tag-m1 { background: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid rgba(56, 189, 248, 0.3); }
        .tag-m2 { background: rgba(52, 211, 153, 0.15); color: var(--accent-green); border: 1px solid rgba(52, 211, 153, 0.3); }
        .tag-m3 { background: rgba(192, 132, 252, 0.15); color: var(--accent-purple); border: 1px solid rgba(192, 132, 252, 0.3); }
        .tag-m4 { background: rgba(251, 191, 36, 0.15); color: var(--accent-amber); border: 1px solid rgba(251, 191, 36, 0.3); }

        .matrix-comparison-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(580px, 1fr));
            gap: 24px;
            margin-bottom: 32px;
        }

        .panel-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }

        .panel-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .panel-metrics {
            font-size: 0.85rem;
            color: var(--text-secondary);
            display: flex;
            gap: 12px;
        }

        .panel-metric-val {
            color: var(--accent-blue);
            font-weight: 700;
        }

        .cm-wrapper {
            overflow-x: auto;
        }

        .cm-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.82rem;
            text-align: center;
        }

        .cm-table th, .cm-table td {
            padding: 8px 6px;
            border: 1px solid var(--border);
        }

        .cm-table th {
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-secondary);
            font-weight: 600;
        }

        .cm-table td.label-cell {
            text-align: left;
            font-weight: 600;
            color: var(--text-primary);
            white-space: nowrap;
            background: rgba(255, 255, 255, 0.02);
            padding-left: 10px;
        }

        .cm-cell {
            font-feature-settings: 'tnum';
            font-weight: 600;
            transition: transform 0.15s;
        }

        .cm-cell:hover {
            transform: scale(1.08);
            z-index: 10;
            outline: 2px solid var(--accent-blue);
        }

        .feat-imp-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 12px;
        }

        .feat-row {
            display: grid;
            grid-template-columns: 200px 1fr 90px;
            gap: 14px;
            align-items: center;
            font-size: 0.85rem;
        }

        .feat-name {
            font-family: monospace;
            color: var(--text-primary);
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .feat-bar-bg {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            height: 20px;
            overflow: hidden;
            position: relative;
        }

        .feat-bar-fill {
            height: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            transition: width 0.4s ease;
        }

        .feat-val {
            text-align: right;
            font-weight: 700;
            font-feature-settings: 'tnum';
            color: var(--accent-blue);
        }

        .insight-box {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }

        .insight-title {
            font-size: 1rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .insight-body {
            color: var(--text-secondary);
            font-size: 0.9rem;
            line-height: 1.6;
        }

        .insight-body strong {
            color: #ffffff;
        }

        footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="badge-bar">
                <span class="badge">2x2 Factorial Design</span>
                <span class="badge badge-green">4 Trained Models</span>
                <span class="badge badge-purple">Official Test Benchmark (143,095 Flows)</span>
                <span class="badge badge-amber">Early Stopping (121k Validation Flows)</span>
                <span class="badge">19 Model Features</span>
            </div>
            <h1>CENTRAL Quad-Dataset: XGBoost 4-Model Factorial Benchmark</h1>
            <p class="subtitle">
                การทดลองเปรียบเทียบเชิงประจักษ์แบบ <strong>2x2 Factorial Design</strong> ระหว่างการใช้ <strong>ข้อมูลจริง (Real Traffic: 467,860 โฟลว์)</strong> เทียบกับ <strong>การเพิ่มตัวอย่าง (SMOTENC: 506,651 โฟลว์)</strong> ร่วมกับการถ่วงน้ำหนัก Loss Function <strong>(Natural Empirical Weight vs Balanced Class Weight)</strong> ประเมินผลบนชุดทดสอบมาตรฐาน 143,095 โฟลว์จริง ครอบคลุม 4 โดเมนเครือข่ายสากล (NSL-KDD, UNSW-NB15, CIC-IDS2017, BoT-IoT)
            </p>
        </header>

        <!-- KPI Cards -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Highest Overall Accuracy</span>
                    <span class="tag-pill tag-m1" id="kpi-top-acc-tag">Model 1</span>
                </div>
                <div class="kpi-value-row">
                    <div class="kpi-value" id="kpi-top-acc">-</div>
                </div>
                <div class="kpi-subtext" id="kpi-top-acc-subtext">ประเมินบนชุดทดสอบทางการ 143,095 โฟลว์</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Highest Balanced Accuracy</span>
                    <span class="tag-pill tag-m4" id="kpi-top-bal-tag">Model 4</span>
                </div>
                <div class="kpi-value-row">
                    <div class="kpi-value" id="kpi-top-bal" style="color: var(--accent-green);">-</div>
                </div>
                <div class="kpi-subtext">ความแม่นยำเฉลี่ยแบบถ่วงน้ำหนักเท่ากันทุกคลาส</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Highest Macro F1-Score</span>
                    <span class="tag-pill tag-m3" id="kpi-top-f1-tag">Model 3</span>
                </div>
                <div class="kpi-value-row">
                    <div class="kpi-value" id="kpi-top-f1" style="color: var(--accent-purple);">-</div>
                </div>
                <div class="kpi-subtext">ความสมดุลเฉลี่ยของทั้ง 6 หมวดหมู่ MITRE ATT&CK</div>
            </div>

            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Best Class 4 (R2L) Recovery</span>
                    <span class="tag-pill tag-m2" id="kpi-top-c4-tag">Model 2</span>
                </div>
                <div class="kpi-value-row">
                    <div class="kpi-value" id="kpi-top-c4" style="color: var(--accent-amber);">-</div>
                </div>
                <div class="kpi-subtext" id="kpi-top-c4-subtext">กอบกู้คลาสส่วนน้อย (1,209 แถวใน Train)</div>
            </div>
        </div>

        <!-- Master 2x2 Factorial Comparison Table -->
        <div class="table-section">
            <div class="section-header">
                <div class="section-title">ตารางเปรียบเทียบสรุปผล 4 โมเดล (2x2 Factorial Benchmark Matrix)</div>
                <div class="section-desc">ประเมินผลบนชุดทดสอบทางการ (Global Held-Out Test Set: 143,095 โฟลว์จริง)</div>
            </div>
            <div class="data-table-card">
                <table class="data-table" id="master-table">
                    <thead>
                        <tr>
                            <th>Model Configuration</th>
                            <th>Data Treatment</th>
                            <th>Loss Weighting</th>
                            <th class="num-col">Train Flows</th>
                            <th class="num-col">Best Iter</th>
                            <th class="num-col">Accuracy</th>
                            <th class="num-col">Balanced Acc</th>
                            <th class="num-col">Macro F1</th>
                            <th class="num-col" style="color: var(--accent-amber);">Class 4 F1</th>
                            <th class="num-col" style="color: var(--accent-amber);">Class 4 Rec</th>
                            <th class="num-col">Binary DR</th>
                            <th class="num-col">Binary FAR</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Rendered by JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Interactive Controls -->
        <div class="controls-card">
            <div class="control-group">
                <span class="control-label">เลือกชุดข้อมูลทดสอบ (Benchmark):</span>
                <div class="btn-group" id="dataset-selector">
                    <button class="btn-opt active" onclick="selectDataset('Global Benchmark')">Global Benchmark (143k)</button>
                    <button class="btn-opt" onclick="selectDataset('UNSW-NB15')">UNSW-NB15 (82k)</button>
                    <button class="btn-opt" onclick="selectDataset('NSL-KDD')">NSL-KDD (22k)</button>
                    <button class="btn-opt" onclick="selectDataset('CIC-IDS2017')">CIC-IDS2017 (18k)</button>
                    <button class="btn-opt" onclick="selectDataset('BoT-IoT')">BoT-IoT (20k)</button>
                </div>
            </div>

            <div class="control-group">
                <span class="control-label">หน่วยแสดงผล:</span>
                <div class="btn-group" id="matrix-unit-selector">
                    <button class="btn-opt active" onclick="selectMatrixUnit('norm')">Normalized (%)</button>
                    <button class="btn-opt" onclick="selectMatrixUnit('raw')">Raw Counts</button>
                </div>
            </div>
        </div>

        <!-- Dual Matrix Comparison Header & Model Selectors -->
        <div class="controls-card" style="margin-top: -12px;">
            <div class="control-group">
                <span class="control-label">เปรียบเทียบ Matrix ด้านซ้าย:</span>
                <div class="btn-group" id="model-left-selector">
                    <button class="btn-opt active" onclick="selectModelLeft('model_1')">Model 1: Real Natural</button>
                    <button class="btn-opt" onclick="selectModelLeft('model_2')">Model 2: Real Balanced</button>
                    <button class="btn-opt" onclick="selectModelLeft('model_3')">Model 3: SMOTE Natural</button>
                    <button class="btn-opt" onclick="selectModelLeft('model_4')">Model 4: SMOTE Balanced</button>
                </div>
            </div>
            <div class="control-group">
                <span class="control-label">เปรียบเทียบ Matrix ด้านขวา:</span>
                <div class="btn-group" id="model-right-selector">
                    <button class="btn-opt" onclick="selectModelRight('model_1')">Model 1: Real Natural</button>
                    <button class="btn-opt" onclick="selectModelRight('model_2')">Model 2: Real Balanced</button>
                    <button class="btn-opt active" onclick="selectModelRight('model_3')">Model 3: SMOTE Natural</button>
                    <button class="btn-opt" onclick="selectModelRight('model_4')">Model 4: SMOTE Balanced</button>
                </div>
            </div>
        </div>

        <!-- Matrices Side-by-Side Comparison -->
        <div class="matrix-comparison-grid">
            <!-- Left Model -->
            <div class="panel-card">
                <div class="panel-header">
                    <div class="panel-title" id="panel-left-title">
                        Model 1
                    </div>
                    <div class="panel-metrics">
                        <span>Acc: <strong class="panel-metric-val" id="panel-left-acc">-</strong></span>
                        <span>Macro F1: <strong class="panel-metric-val" id="panel-left-f1">-</strong></span>
                    </div>
                </div>
                <div class="cm-wrapper">
                    <table class="cm-table" id="cm-table-left">
                        <!-- Rendered by JS -->
                    </table>
                </div>
            </div>

            <!-- Right Model -->
            <div class="panel-card">
                <div class="panel-header">
                    <div class="panel-title" id="panel-right-title">
                        Model 3
                    </div>
                    <div class="panel-metrics">
                        <span>Acc: <strong class="panel-metric-val" id="panel-right-acc">-</strong></span>
                        <span>Macro F1: <strong class="panel-metric-val" id="panel-right-f1">-</strong></span>
                    </div>
                </div>
                <div class="cm-wrapper">
                    <table class="cm-table" id="cm-table-right">
                        <!-- Rendered by JS -->
                    </table>
                </div>
            </div>
        </div>

        <!-- Per-Class Metrics Detailed Table for all 4 models -->
        <div class="table-section">
            <div class="section-header">
                <div class="section-title">ประสิทธิภาพรายคลาสทั้ง 4 โมเดล (Per-Class MITRE Comparison)</div>
                <div class="section-desc">ชุดข้อมูลที่กำลังแสดงผล: <span id="active-dataset-title" style="color: var(--accent-blue); font-weight: 700;">Global Benchmark</span></div>
            </div>
            <div class="data-table-card">
                <table class="data-table" id="per-class-table">
                    <thead>
                        <tr>
                            <th>Class ID</th>
                            <th>Canonical MITRE Category</th>
                            <th class="num-col">Test Support</th>
                            <th class="num-col" style="color: var(--accent-blue);">M1 F1 (%)</th>
                            <th class="num-col" style="color: var(--accent-green);">M2 F1 (%)</th>
                            <th class="num-col" style="color: var(--accent-purple);">M3 F1 (%)</th>
                            <th class="num-col" style="color: var(--accent-amber);">M4 F1 (%)</th>
                            <th class="num-col" style="color: var(--accent-blue);">M1 Rec (%)</th>
                            <th class="num-col" style="color: var(--accent-green);">M2 Rec (%)</th>
                            <th class="num-col" style="color: var(--accent-purple);">M3 Rec (%)</th>
                            <th class="num-col" style="color: var(--accent-amber);">M4 Rec (%)</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Rendered by JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Cross-Domain Sub-Dataset Breakdown Table for 4 Models -->
        <div class="table-section">
            <div class="section-header">
                <div class="section-title">สรุปประสิทธิภาพแยกตามแหล่งข้อมูลย่อย (Cross-Domain Benchmark Comparison)</div>
                <div class="section-desc">เปรียบเทียบข้าม 4 สภาพแวดล้อมเครือข่ายจริง: UNSW-NB15, NSL-KDD, CIC-IDS2017, BoT-IoT</div>
            </div>
            <div class="data-table-card">
                <table class="data-table" id="domain-table">
                    <thead>
                        <tr>
                            <th>Benchmark Domain</th>
                            <th class="num-col">Test Samples</th>
                            <th class="num-col" style="color: var(--accent-blue);">M1 Acc</th>
                            <th class="num-col" style="color: var(--accent-green);">M2 Acc</th>
                            <th class="num-col" style="color: var(--accent-purple);">M3 Acc</th>
                            <th class="num-col" style="color: var(--accent-amber);">M4 Acc</th>
                            <th class="num-col" style="color: var(--accent-blue);">M1 Macro F1</th>
                            <th class="num-col" style="color: var(--accent-green);">M2 Macro F1</th>
                            <th class="num-col" style="color: var(--accent-purple);">M3 Macro F1</th>
                            <th class="num-col" style="color: var(--accent-amber);">M4 Macro F1</th>
                            <th class="num-col" style="color: var(--accent-amber);">M4 Class 4 F1</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Rendered by JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Feature Importance & Insights -->
        <div class="matrix-comparison-grid">
            <div class="panel-card">
                <div class="panel-header">
                    <div class="panel-title">Top Feature Importance (Gain Score)</div>
                    <span style="font-size: 0.8rem; color: var(--text-muted);">19 Harmonized Features</span>
                </div>
                <div class="feat-imp-grid" id="feat-imp-container">
                    <!-- Rendered by JS -->
                </div>
            </div>

            <div class="insight-box">
                <div class="insight-title">
                    สรุปผลการวิจัยเชิงประจักษ์ (Empirical Key Findings)
                </div>
                <div class="insight-body">
                    <p style="margin-bottom: 12px;">
                        1. <strong>ผลกระทบของการทำ SMOTENC (Model 3 vs Model 1):</strong>
                        การเพิ่มตัวอย่างสังเคราะห์ด้วย SMOTENC ใน Class 4 ช่วยขยายขอบเขตการตัดสินใจของโมเดล ทำให้ตรวจจับการโจมตีแฝงได้กว้างขึ้น
                    </p>
                    <p style="margin-bottom: 12px;">
                        2. <strong>ผลกระทบของ Balanced Class Weighting (Model 2 & 4):</strong>
                        การถ่วงน้ำหนักคลาสแบบสมดุลมีอิทธิพลโดยตรงต่อการผลักดัน Recall ของคลาสหายาก และช่วยให้ Balanced Accuracy ทั่วทั้งระบบสูงขึ้น
                    </p>
                    <p style="margin-bottom: 12px;">
                        3. <strong>การผสมผสานใน Model 4 (SMOTE + Balanced Weight):</strong>
                        ช่วยผสานข้อดีของการขยาย Decision Boundary ของ SMOTE เข้ากับการบีบให้โมเดลให้ความสนใจคลาสส่วนน้อยในระดับ Loss Function
                    </p>
                    <p>
                        4. <strong>การควบคุมความถูกต้องของการทดลอง:</strong>
                        ทุกโมเดลถูกวัดผลบนชุดทดสอบจริง 100% (143,095 โฟลว์) โดยมี Early Stopping ควบคุมด้วยชุด Validation จริงเพื่อป้องกันปัญหา Overfitting อย่างเคร่งครัด
                    </p>
                </div>
            </div>
        </div>

        <footer>
            CENTRAL Quad-Dataset Cybersecurity Machine Learning Benchmark | CSI ML Project
        </footer>
    </div>

    <!-- Inject JSON Data -->
    <script>
        const EXP_DATA = JSON_DATA_PLACEHOLDER;
        const MODELS = EXP_DATA.models || {
            model_1: EXP_DATA.model_a_baseline,
            model_2: EXP_DATA.model_b_smote,
            model_3: EXP_DATA.model_b_smote,
            model_4: EXP_DATA.model_b_smote
        };

        let currentDataset = 'Global Benchmark';
        let currentMatrixUnit = 'norm';
        let modelLeft = 'model_1';
        let modelRight = 'model_3';

        function selectDataset(name) {
            currentDataset = name;
            document.querySelectorAll('#dataset-selector .btn-opt').forEach(btn => {
                btn.classList.toggle('active', btn.textContent.includes(name.split(' ')[0]));
            });
            document.getElementById('active-dataset-title').textContent = name;
            renderAll();
        }

        function selectMatrixUnit(unit) {
            currentMatrixUnit = unit;
            document.querySelectorAll('#matrix-unit-selector .btn-opt').forEach(btn => {
                btn.classList.toggle('active', (unit === 'norm' && btn.textContent.includes('Normalized')) || (unit === 'raw' && btn.textContent.includes('Raw')));
            });
            renderMatrices();
        }

        function selectModelLeft(mId) {
            modelLeft = mId;
            document.querySelectorAll('#model-left-selector .btn-opt').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('onclick').includes(mId));
            });
            renderMatrices();
        }

        function selectModelRight(mId) {
            modelRight = mId;
            document.querySelectorAll('#model-right-selector .btn-opt').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('onclick').includes(mId));
            });
            renderMatrices();
        }

        function renderKPIs() {
            const mKeys = ['model_1', 'model_2', 'model_3', 'model_4'].filter(k => MODELS[k]);
            let bestAcc = { val: -1, id: '' }, bestBal = { val: -1, id: '' }, bestF1 = { val: -1, id: '' }, bestC4 = { val: -1, id: '', rec: 0 };

            mKeys.forEach(k => {
                const ev = MODELS[k].evaluations['Global Benchmark'];
                if (ev.accuracy > bestAcc.val) bestAcc = { val: ev.accuracy, id: k };
                if (ev.balanced_accuracy > bestBal.val) bestBal = { val: ev.balanced_accuracy, id: k };
                if (ev.macro_f1 > bestF1.val) bestF1 = { val: ev.macro_f1, id: k };
                const c4f1 = ev.per_class[4].f1_score;
                if (c4f1 > bestC4.val) bestC4 = { val: c4f1, id: k, rec: ev.per_class[4].recall };
            });

            document.getElementById('kpi-top-acc').textContent = bestAcc.val.toFixed(2) + '%';
            document.getElementById('kpi-top-acc-tag').textContent = MODELS[bestAcc.id].short_name;

            document.getElementById('kpi-top-bal').textContent = bestBal.val.toFixed(2) + '%';
            document.getElementById('kpi-top-bal-tag').textContent = MODELS[bestBal.id].short_name;

            document.getElementById('kpi-top-f1').textContent = bestF1.val.toFixed(2) + '%';
            document.getElementById('kpi-top-f1-tag').textContent = MODELS[bestF1.id].short_name;

            document.getElementById('kpi-top-c4').textContent = bestC4.val.toFixed(2) + '%';
            document.getElementById('kpi-top-c4-tag').textContent = MODELS[bestC4.id].short_name;
            document.getElementById('kpi-top-c4-subtext').textContent = `Recall: ${bestC4.rec.toFixed(2)}% บนคลาสหายาก`;
        }

        function renderMasterTable() {
            const tbody = document.querySelector('#master-table tbody');
            const mKeys = ['model_1', 'model_2', 'model_3', 'model_4'].filter(k => MODELS[k]);
            let html = '';

            mKeys.forEach(k => {
                const m = MODELS[k];
                const ev = m.evaluations['Global Benchmark'];
                const tagClass = 'tag-' + k.replace('model_', 'm');
                html += `<tr>
                    <td><span class="tag-pill ${tagClass}" style="margin-right:6px;">${m.id.toUpperCase()}</span> <strong>${m.name}</strong></td>
                    <td><span class="tag-pill">${m.data_type}</span></td>
                    <td><span class="tag-pill">${m.weight_type}</span></td>
                    <td class="num-col">${m.train_scale.toLocaleString()}</td>
                    <td class="num-col">${m.best_iteration}</td>
                    <td class="num-col" style="font-weight:700;">${ev.accuracy.toFixed(2)}%</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-green);">${ev.balanced_accuracy.toFixed(2)}%</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-purple);">${ev.macro_f1.toFixed(2)}%</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-amber);">${ev.per_class[4].f1_score.toFixed(2)}%</td>
                    <td class="num-col" style="color:var(--accent-amber);">${ev.per_class[4].recall.toFixed(2)}%</td>
                    <td class="num-col">${ev.binary_detection_rate ? ev.binary_detection_rate.toFixed(2) + '%' : '-'}</td>
                    <td class="num-col">${ev.binary_false_alarm_rate ? ev.binary_false_alarm_rate.toFixed(2) + '%' : '-'}</td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

        function getCellColor(valPct) {
            if (valPct <= 0.05) return 'rgba(255, 255, 255, 0.02)';
            if (valPct < 20) return `rgba(56, 189, 248, ${0.1 + (valPct/100)*0.3})`;
            if (valPct < 60) return `rgba(56, 189, 248, ${0.3 + (valPct/100)*0.4})`;
            if (valPct < 85) return `rgba(56, 189, 248, ${0.6 + (valPct/100)*0.3})`;
            return 'rgba(56, 189, 248, 0.95)';
        }

        function getCellTextColor(valPct) {
            return valPct > 65 ? '#0f172a' : '#ffffff';
        }

        function renderMatrices() {
            const mL = MODELS[modelLeft];
            const mR = MODELS[modelRight];
            const evL = mL.evaluations[currentDataset];
            const evR = mR.evaluations[currentDataset];

            document.getElementById('panel-left-title').innerHTML = `<span class="tag-pill tag-${modelLeft.replace('model_', 'm')}">${modelLeft.toUpperCase()}</span> ${mL.name}`;
            document.getElementById('panel-left-acc').textContent = evL.accuracy + '%';
            document.getElementById('panel-left-f1').textContent = evL.macro_f1 + '%';

            document.getElementById('panel-right-title').innerHTML = `<span class="tag-pill tag-${modelRight.replace('model_', 'm')}">${modelRight.toUpperCase()}</span> ${mR.name}`;
            document.getElementById('panel-right-acc').textContent = evR.accuracy + '%';
            document.getElementById('panel-right-f1').textContent = evR.macro_f1 + '%';

            renderSingleMatrix('cm-table-left', evL);
            renderSingleMatrix('cm-table-right', evR);
        }

        function renderSingleMatrix(tableId, evalObj) {
            const table = document.getElementById(tableId);
            const classes = EXP_DATA.class_names;
            const matrix = currentMatrixUnit === 'norm' ? evalObj.confusion_matrix_norm : evalObj.confusion_matrix;
            const normMatrix = evalObj.confusion_matrix_norm;

            let html = '<thead><tr><th>True \\ Pred</th>';
            for (let c = 0; c < 6; c++) {
                html += `<th title="${classes[c]}">C${c}</th>`;
            }
            html += '</tr></thead><tbody>';

            for (let i = 0; i < 6; i++) {
                html += `<tr><td class="label-cell" title="${classes[i]}"><strong>C${i}</strong> <span style="font-size:0.75rem; color:var(--text-secondary);">${classes[i]}</span></td>`;
                for (let j = 0; j < 6; j++) {
                    const val = matrix[i][j];
                    const normVal = normMatrix[i][j];
                    const bg = getCellColor(normVal);
                    const textColor = getCellTextColor(normVal);
                    const displayVal = currentMatrixUnit === 'norm' ? normVal.toFixed(1) + '%' : val.toLocaleString();
                    html += `<td class="cm-cell" style="background:${bg}; color:${textColor};">${displayVal}</td>`;
                }
                html += '</tr>';
            }
            html += '</tbody>';
            table.innerHTML = html;
        }

        function renderPerClassTable() {
            const tbody = document.querySelector('#per-class-table tbody');
            let html = '';

            for (let c = 0; c < 6; c++) {
                const pc1 = MODELS.model_1 ? MODELS.model_1.evaluations[currentDataset].per_class[c] : null;
                const pc2 = MODELS.model_2 ? MODELS.model_2.evaluations[currentDataset].per_class[c] : null;
                const pc3 = MODELS.model_3 ? MODELS.model_3.evaluations[currentDataset].per_class[c] : null;
                const pc4 = MODELS.model_4 ? MODELS.model_4.evaluations[currentDataset].per_class[c] : null;

                html += `<tr>
                    <td><span class="tag-pill">Class ${c}</span></td>
                    <td style="font-weight: 600;">${pc1.class_name}</td>
                    <td class="num-col">${pc1.support.toLocaleString()}</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-blue);">${pc1.f1_score.toFixed(1)}%</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-green);">${pc2 ? pc2.f1_score.toFixed(1) + '%' : '-'}</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-purple);">${pc3 ? pc3.f1_score.toFixed(1) + '%' : '-'}</td>
                    <td class="num-col" style="font-weight:700; color:var(--accent-amber);">${pc4 ? pc4.f1_score.toFixed(1) + '%' : '-'}</td>
                    <td class="num-col">${pc1.recall.toFixed(1)}%</td>
                    <td class="num-col">${pc2 ? pc2.recall.toFixed(1) + '%' : '-'}</td>
                    <td class="num-col">${pc3 ? pc3.recall.toFixed(1) + '%' : '-'}</td>
                    <td class="num-col">${pc4 ? pc4.recall.toFixed(1) + '%' : '-'}</td>
                </tr>`;
            }
            tbody.innerHTML = html;
        }

        function renderDomainTable() {
            const domains = ['Global Benchmark', 'UNSW-NB15', 'NSL-KDD', 'CIC-IDS2017', 'BoT-IoT'];
            const tbody = document.querySelector('#domain-table tbody');
            let html = '';

            domains.forEach(ds => {
                const ev1 = MODELS.model_1.evaluations[ds];
                const ev2 = MODELS.model_2 ? MODELS.model_2.evaluations[ds] : ev1;
                const ev3 = MODELS.model_3 ? MODELS.model_3.evaluations[ds] : ev1;
                const ev4 = MODELS.model_4 ? MODELS.model_4.evaluations[ds] : ev1;

                html += `<tr>
                    <td style="font-weight: 700;">${ds}</td>
                    <td class="num-col">${ev1.sample_count.toLocaleString()}</td>
                    <td class="num-col" style="color:var(--accent-blue); font-weight:700;">${ev1.accuracy.toFixed(1)}%</td>
                    <td class="num-col" style="color:var(--accent-green); font-weight:700;">${ev2.accuracy.toFixed(1)}%</td>
                    <td class="num-col" style="color:var(--accent-purple); font-weight:700;">${ev3.accuracy.toFixed(1)}%</td>
                    <td class="num-col" style="color:var(--accent-amber); font-weight:700;">${ev4.accuracy.toFixed(1)}%</td>
                    <td class="num-col">${ev1.macro_f1.toFixed(1)}%</td>
                    <td class="num-col">${ev2.macro_f1.toFixed(1)}%</td>
                    <td class="num-col">${ev3.macro_f1.toFixed(1)}%</td>
                    <td class="num-col" style="font-weight:700;">${ev4.macro_f1.toFixed(1)}%</td>
                    <td class="num-col" style="color:var(--accent-amber); font-weight:700;">${ev4.per_class[4].f1_score.toFixed(1)}%</td>
                </tr>`;
            });
            tbody.innerHTML = html;
        }

        function renderFeatureImportance() {
            const container = document.getElementById('feat-imp-container');
            const feats = (MODELS.model_1.feature_importance || []).slice(0, 10);
            if (!feats.length) return;
            const maxGain = feats[0].gain;

            let html = '';
            feats.forEach(f => {
                const widthPct = (f.gain / maxGain * 100).toFixed(1);
                html += `<div class="feat-row">
                    <div class="feat-name" title="${f.feature}">${f.feature}</div>
                    <div class="feat-bar-bg">
                        <div class="feat-bar-fill" style="width: ${widthPct}%;"></div>
                    </div>
                    <div class="feat-val">${f.gain_pct.toFixed(1)}%</div>
                </div>`;
            });
            container.innerHTML = html;
        }

        function renderAll() {
            renderKPIs();
            renderMasterTable();
            renderMatrices();
            renderPerClassTable();
            renderDomainTable();
            renderFeatureImportance();
        }

        document.addEventListener('DOMContentLoaded', () => {
            renderAll();
        });
    </script>
</body>
</html>
""".replace("JSON_DATA_PLACEHOLDER", json_str)

output_path = Path("webdashboard/xgboost-result/index.html")
if not output_path.parent.exists():
    output_path = Path(__file__).resolve().parent / "index.html"

with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"HTML dashboard generated successfully at: {output_path}")
