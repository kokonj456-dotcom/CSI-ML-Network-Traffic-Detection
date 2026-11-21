#!/usr/bin/env python3
"""Build script for the Standalone Interactive React Dashboard.

Embeds results from experiments/scaling_and_domain_shift/results/benchmark_results.json
into experiments/scaling_and_domain_shift/dashboard/index.html.
Uses React 18 + Babel + Tailwind CSS + Lucide Icons via CDN.
"""

import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RESULTS_FILE = EXP_DIR / "results" / "benchmark_results.json"
DASHBOARD_FILE = EXP_DIR / "dashboard" / "index.html"

with open(RESULTS_FILE, "r", encoding="utf8") as f:
    benchmark_data = json.load(f)

json_str = json.dumps(benchmark_data, ensure_ascii=False)

html_template = """<!DOCTYPE html>
<html lang="th" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cross-Dataset Generalization & Data Scaling Benchmark</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f0f9ff',
              500: '#0284c7',
              600: '#0369a1',
              900: '#0c4a6e',
            },
            dark: {
              bg: '#0b0f19',
              card: '#111827',
              border: '#1f2937',
              hover: '#1e293b'
            }
          }
        }
      }
    }
  </script>
  <!-- React 18 & ReactDOM -->
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <!-- Babel Standalone for JSX -->
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    body {
      font-family: 'Inter', sans-serif;
      background-color: #0b0f19;
      color: #f3f4f6;
    }
    code, pre, .font-mono {
      font-family: 'JetBrains+Mono', monospace;
    }
    .custom-scrollbar::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
      background: #111827;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
      background: #374151;
      border-radius: 3px;
    }
  </style>
</head>
<body class="min-h-screen bg-[#0b0f19] text-slate-100 antialiased custom-scrollbar">
  <div id="root"></div>

  <!-- Raw Benchmark JSON -->
  <script id="raw-benchmark-data" type="application/json">
__BENCHMARK_DATA_PLACEHOLDER__
  </script>

  <!-- React Application -->
  <script type="text/babel">
    const { useState, useMemo } = React;

    const RAW_DATA = JSON.parse(document.getElementById('raw-benchmark-data').textContent);

    function App() {
      const [evalMode, setEvalMode] = useState('binary'); // 'binary' or 'multiclass'
      const [matrixMetric, setMatrixMetric] = useState('f1'); // 'f1', 'fpr', 'accuracy'
      const [sortCol, setSortCol] = useState('overall_f1');
      const [sortAsc, setSortAsc] = useState(false);

      const modelsList = useMemo(() => {
        return Object.values(RAW_DATA.models);
      }, []);

      const testSets = RAW_DATA.metadata.test_sets;

      // Color mapping for Heatmap
      const getCellColor = (val, metric) => {
        if (metric === 'fpr') {
          if (val <= 3) return 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60';
          if (val <= 10) return 'bg-emerald-900/40 text-emerald-200 border-emerald-700/40';
          if (val <= 30) return 'bg-amber-950/50 text-amber-300 border-amber-800/40';
          if (val <= 70) return 'bg-orange-950/70 text-orange-300 border-orange-800/50';
          return 'bg-rose-950/90 text-rose-300 font-bold border-rose-800/80';
        }
        // F1 or Accuracy (Higher is better)
        if (val >= 90) return 'bg-emerald-950/80 text-emerald-300 font-semibold border-emerald-800/60';
        if (val >= 75) return 'bg-emerald-900/50 text-emerald-200 border-emerald-700/40';
        if (val >= 50) return 'bg-amber-950/50 text-amber-300 border-amber-800/40';
        if (val >= 25) return 'bg-orange-950/70 text-orange-300 border-orange-800/50';
        return 'bg-rose-950/90 text-rose-300 font-bold border-rose-800/80';
      };

      // Leaderboard Table data
      const leaderboardData = useMemo(() => {
        const key = evalMode === 'binary' ? 'eval_binary' : 'eval_multiclass';
        const f1Key = evalMode === 'binary' ? 'f1_binary' : 'f1_macro';

        return modelsList.map(m => {
          const fullEval = m[key]['CENTRAL Full'];
          const subDatasets = ['NSL-KDD', 'UNSW-NB15', 'CIC-IDS2017', 'BoT-IoT'];
          const avgCross = (subDatasets.reduce((acc, k) => acc + m[key][k][f1Key], 0) / subDatasets.length).toFixed(2);
          
          let inDomain = fullEval[f1Key];
          if (m.group === 'Specialist') {
            inDomain = m[key][m.in_domain_name][f1Key];
          }
          const gap = (inDomain - avgCross).toFixed(2);

          return {
            ...m,
            overall_f1: fullEval[f1Key],
            overall_acc: fullEval.accuracy,
            overall_fpr: fullEval.fpr,
            latency: fullEval.latency_ms_per_1k || 0.8,
            in_domain_val: inDomain,
            cross_domain_avg: avgCross,
            gen_gap: gap,
          };
        }).sort((a, b) => {
          let vA = a[sortCol];
          let vB = b[sortCol];
          if (typeof vA === 'string') {
            return sortAsc ? vA.localeCompare(vB) : vB.localeCompare(vA);
          }
          return sortAsc ? vA - vB : vB - vA;
        });
      }, [evalMode, sortCol, sortAsc]);

      return (
        <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
          
          {/* Header */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-950 text-sky-400 border border-sky-800">
                    Empirical Proof Suite
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                    1.89M Big Data Scaled
                  </span>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-950 text-purple-400 border border-purple-800">
                    Standalone React Dashboard
                  </span>
                </div>
                <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-white">
                  Cross-Dataset Generalization &amp; Data Scaling Benchmark
                </h1>
                <p className="text-slate-400 text-sm mt-1 max-w-3xl">
                  การทดลองพิสูจน์ปัญหา <span className="text-rose-400 font-semibold">Domain Shift</span> ในโมเดลที่เทรนเพียง Dataset เดียว เทียบกับความทนทานของ <span className="text-emerald-400 font-semibold">CENTRAL &amp; CENTRAL-UNCUT</span> และการพิสูจน์สมมติฐาน <span className="text-sky-400 font-semibold">Data Scaling Law (~1.89M Rows)</span>
                </p>
              </div>

              {/* Mode Toggle Controls */}
              <div className="flex flex-col sm:flex-row items-center gap-2 bg-slate-950/80 p-1.5 rounded-xl border border-slate-800">
                <button
                  onClick={() => setEvalMode('binary')}
                  className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                    evalMode === 'binary'
                      ? 'bg-sky-600 text-white shadow-lg shadow-sky-600/30'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Binary (Normal vs Attack)
                </button>
                <button
                  onClick={() => setEvalMode('multiclass')}
                  className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                    evalMode === 'multiclass'
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  6-Class (MITRE ATT&CK)
                </button>
              </div>
            </div>
          </div>

          {/* Key Findings Hero Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-slate-900/80 border border-rose-900/30 rounded-xl p-5 shadow-lg relative overflow-hidden">
              <div className="text-xs uppercase tracking-wider font-semibold text-rose-400 mb-1">
                Domain Shift Failure (Specialists)
              </div>
              <div className="text-2xl font-bold text-white mb-1">
                99.2% <span className="text-rose-500 text-sm font-normal">→ 0.0%</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                CIC Specialist ทำ F1 ได้ 99.2% ในบ้านตัวเอง แต่เมื่อตรวจจับ UNSW/BoT ดรอปเหลือ 0.0% ทันที (จำเพาะต่อแล็บปิด)
              </p>
            </div>

            <div className="bg-slate-900/80 border border-emerald-900/30 rounded-xl p-5 shadow-lg relative overflow-hidden">
              <div className="text-xs uppercase tracking-wider font-semibold text-emerald-400 mb-1">
                Data Scaling Law Champion
              </div>
              <div className="text-2xl font-bold text-white mb-1">
                83.20% <span className="text-emerald-400 text-sm font-normal">Multi F1 (+14.8%)</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                CENTRAL-MAX (19 ฟีเจอร์, 1.89M แถว) กระโดดจาก 68.4% เป็น 83.2% พิสูจน์ว่า Data กว้างชนะ Feature เยอะ
              </p>
            </div>

            <div className="bg-slate-900/80 border border-sky-900/30 rounded-xl p-5 shadow-lg relative overflow-hidden">
              <div className="text-xs uppercase tracking-wider font-semibold text-sky-400 mb-1">
                UNCUT 80-Features Feasibility
              </div>
              <div className="text-2xl font-bold text-white mb-1">
                90.92% <span className="text-sky-400 text-sm font-normal">Binary F1</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                CENTRAL-UNCUT (Native NaN) สามารถเทรนตรงบน 80 ฟีเจอร์ได้โดยไม่ต้องตัดฟีเจอร์ และได้ผลลัพธ์สูงกว่า Imputed
              </p>
            </div>

            <div className="bg-slate-900/80 border border-amber-900/30 rounded-xl p-5 shadow-lg relative overflow-hidden">
              <div className="text-xs uppercase tracking-wider font-semibold text-amber-400 mb-1">
                FPR Explosion Risk
              </div>
              <div className="text-2xl font-bold text-white mb-1">
                90% - 100% <span className="text-amber-500 text-sm font-normal">Out-of-Domain FPR</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                โมเดลที่เทรนเพียงชุดเดียว เมื่อเจอทราฟฟิกข้ามเครือข่ายจะแจ้งเตือนผิดพลาด (False Positive) แทบทุกโฟลว์ปกติ
              </p>
            </div>
          </div>

          {/* Section 1: Cross-Dataset Transfer Matrix Heatmap */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <span>Cross-Dataset Transfer Matrix (Domain Shift Heatmap)</span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  ตารางทดสอบไขว้: แถวนอนคือโมเดลที่ถูกเทรน (Training Set) | คอลัมน์แนวตั้งคือชุดข้อมูลที่ใช้ทดสอบ (Test Set)
                </p>
              </div>

              {/* Metric Selector for Heatmap */}
              <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
                <span className="text-slate-400 px-2 font-medium">Metric:</span>
                <button
                  onClick={() => setMatrixMetric('f1')}
                  className={`px-2.5 py-1 rounded font-semibold ${
                    matrixMetric === 'f1' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  F1-Score
                </button>
                <button
                  onClick={() => setMatrixMetric('fpr')}
                  className={`px-2.5 py-1 rounded font-semibold ${
                    matrixMetric === 'fpr' ? 'bg-rose-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  False Positive Rate (FPR)
                </button>
                <button
                  onClick={() => setMatrixMetric('accuracy')}
                  className={`px-2.5 py-1 rounded font-semibold ${
                    matrixMetric === 'accuracy' ? 'bg-emerald-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Accuracy
                </button>
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="py-3 px-4 font-semibold w-1/4">Trained Model</th>
                    <th className="py-3 px-3 font-semibold text-center">NSL-KDD Test<br/><span className="font-normal text-[10px] text-slate-500">(22,544 rows)</span></th>
                    <th className="py-3 px-3 font-semibold text-center">UNSW-NB15 Test<br/><span className="font-normal text-[10px] text-slate-500">(82,332 rows)</span></th>
                    <th className="py-3 px-3 font-semibold text-center">CIC-IDS2017 Test<br/><span className="font-normal text-[10px] text-slate-500">(18,219 rows)</span></th>
                    <th className="py-3 px-3 font-semibold text-center">BoT-IoT Test<br/><span className="font-normal text-[10px] text-slate-500">(20,000 rows)</span></th>
                    <th className="py-3 px-3 font-semibold text-center bg-slate-950/60 text-sky-300">CENTRAL Held-Out<br/><span className="font-normal text-[10px] text-slate-400">(143,095 rows)</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {modelsList.map((m, idx) => {
                    const key = evalMode === 'binary' ? 'eval_binary' : 'eval_multiclass';
                    const metricKey = matrixMetric === 'f1' 
                      ? (evalMode === 'binary' ? 'f1_binary' : 'f1_macro')
                      : matrixMetric;

                    return (
                      <tr key={m.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-sans font-medium text-slate-200">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-slate-500 font-mono">M{idx+1}</span>
                            <div>
                              <div className="font-semibold text-xs text-white">{m.name}</div>
                              <div className="text-[10px] text-slate-400 font-normal">
                                {m.features_count} Features | {m.train_rows.toLocaleString()} train rows
                              </div>
                            </div>
                          </div>
                        </td>

                        {testSets.map(tname => {
                          const val = m[key][tname][metricKey];
                          const isSpecialistInDomain = m.group === 'Specialist' && m.in_domain_name === tname;
                          const cellClass = getCellColor(val, matrixMetric);

                          return (
                            <td key={tname} className="py-2.5 px-3 text-center">
                              <div className={`inline-block px-3 py-1.5 rounded-lg border text-xs shadow-sm ${cellClass} ${
                                isSpecialistInDomain ? 'ring-2 ring-sky-400 font-extrabold' : ''
                              }`}>
                                {val.toFixed(2)}%
                                {isSpecialistInDomain && (
                                  <div className="text-[8px] font-sans uppercase tracking-tighter text-sky-300 -mt-0.5">
                                    In-Domain
                                  </div>
                                )}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Heatmap Legend */}
            <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-slate-800/60 gap-4">
              <div className="flex items-center gap-4">
                <span className="font-semibold text-slate-300">Legend:</span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-emerald-950 border border-emerald-800 inline-block"></span>
                  <span>Excellent (&gt;90%)</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-amber-950 border border-amber-800 inline-block"></span>
                  <span>Moderate (50-75%)</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded bg-rose-950 border border-rose-800 inline-block"></span>
                  <span>Severe Failure (&lt;25% / High FPR)</span>
                </span>
              </div>
              <div>
                <span className="ring-1 ring-sky-400 px-1.5 py-0.5 rounded text-[10px] text-sky-300">Blue Outline</span> = In-Domain Test
              </div>
            </div>
          </div>

          {/* Section 2: Visual Comparison (Generalization Gap & Scaling Law) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Generalization Gap Chart */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <div>
                <h3 className="text-base font-bold text-white">Generalization Gap (In-Domain vs Cross-Domain)</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  เปรียบเทียบคะแนนตอนทดสอบในบ้านตัวเอง (In-Domain) กับค่าเฉลี่ยเมื่อเจอเน็ตเวิร์กอื่น (Out-of-Domain)
                </p>
              </div>

              <div className="space-y-3 font-mono text-xs pt-2">
                {leaderboardData.map(m => {
                  const inVal = parseFloat(m.in_domain_val);
                  const crossVal = parseFloat(m.cross_domain_avg);
                  const drop = inVal - crossVal;

                  return (
                    <div key={m.id} className="space-y-1 bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/60">
                      <div className="flex justify-between text-xs font-sans">
                        <span className="font-semibold text-slate-200">{m.name}</span>
                        <span className={`font-mono text-xs ${
                          drop > 40 ? 'text-rose-400 font-bold' : (drop < 5 ? 'text-emerald-400 font-bold' : 'text-amber-400')
                        }`}>
                          {drop > 0 ? `Gap: -${drop.toFixed(1)}%` : `Consistent (+${Math.abs(drop).toFixed(1)}%)`}
                        </span>
                      </div>

                      {/* Progress Bars */}
                      <div className="space-y-1 text-[10px] text-slate-400">
                        <div className="flex items-center gap-2">
                          <span className="w-16">In-Domain:</span>
                          <div className="flex-1 bg-slate-800 h-2 rounded-full overflow-hidden">
                            <div className="bg-sky-500 h-full rounded-full" style={{ width: `${Math.max(0, inVal)}%` }}></div>
                          </div>
                          <span className="w-10 text-right">{inVal.toFixed(1)}%</span>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="w-16">Cross-Avg:</span>
                          <div className="flex-1 bg-slate-800 h-2 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${
                              crossVal > 80 ? 'bg-emerald-500' : (crossVal > 50 ? 'bg-amber-500' : 'bg-rose-500')
                            }`} style={{ width: `${Math.max(0, crossVal)}%` }}></div>
                          </div>
                          <span className="w-10 text-right">{crossVal.toFixed(1)}%</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Data Scaling Law Analysis */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
              <div>
                <h3 className="text-base font-bold text-white">The Data Scaling Law (467k vs 1.89M vs 5.04M Rows)</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  พิสูจน์สมมติฐาน Scaling Law: เมื่อเพิ่มข้อมูลจาก 467k -&gt; 1.89M -&gt; 5.04M แถว (Optuna Tuned) ประสิทธิภาพพุ่งสูงขึ้นอย่างก้าวกระโดด
                </p>
              </div>

              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-4 text-xs">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                    <div className="text-slate-400 text-[10px] uppercase font-semibold">M5: CENTRAL 19</div>
                    <div className="text-base font-bold text-white mt-1">467,860 แถว</div>
                    <div className="text-slate-500 text-[10px]">Multi F1: 68.42%</div>
                  </div>
                  <div className="bg-sky-950/40 p-2.5 rounded-lg border border-sky-800/60">
                    <div className="text-sky-400 text-[10px] uppercase font-semibold">M8: CENTRAL-MAX</div>
                    <div className="text-base font-bold text-sky-300 mt-1">1,890,288 แถว</div>
                    <div className="text-sky-400 text-[10px] font-semibold">Multi F1: 83.20%</div>
                  </div>
                  <div className="bg-emerald-950/60 p-2.5 rounded-lg border border-emerald-600 shadow-lg shadow-emerald-950/50 ring-1 ring-emerald-500/50">
                    <div className="text-emerald-300 text-[10px] uppercase font-bold">M9: CENTRAL-FINAL</div>
                    <div className="text-base font-bold text-emerald-200 mt-1">5,036,579 แถว</div>
                    <div className="text-emerald-300 text-[10px] font-bold">Multi F1: 84.91% (+16.5%)</div>
                  </div>
                </div>

                <div className="space-y-2 pt-2 border-t border-slate-800 text-xs text-slate-300 leading-relaxed font-sans">
                  <div className="font-semibold text-white">ข้อค้นพบสำคัญ (Key Scientific Takeaways):</div>
                  <ul className="list-disc pl-4 space-y-1.5 text-slate-400 text-[11px]">
                    <li><strong className="text-white">พิสูจน์ Scaling Law:</strong> เมื่อเพิ่มข้อมูลจาก 467k เป็น 5.04M แถว (6 Datasets) โมเดล 19 ฟีเจอร์ทำ Multiclass F1 พุ่งสูงถึง <strong className="text-emerald-400">84.91%</strong> (Optuna Val Macro F1: <strong>90.20%</strong>) ชนะโมเดล 80 ฟีเจอร์ UNCUT (73.46%) อย่างขาดลอย</li>
                    <li><strong className="text-white">ชนะ Specialist ทุกชุดข้อมูล:</strong> Binary F1 ข้ามโดเมนเฉลี่ยสูงถึง <strong className="text-sky-400">95.79%</strong> (NSL 96.63%, UNSW 91.57%, CIC 94.99%, BoT 99.98%) และลด FPR เหลือเพียง 1-2% ในเน็ตเวิร์กองค์กร</li>
                    <li><strong className="text-white">Production Ready & Speed:</strong> โมเดล Stage 1 + Stage 2 ใช้เวลา Predict เพียง <strong>~1.1 ms ต่อ 1,000 โฟลว์</strong> พร้อม Deploy เข้า Live Pipeline และ Web Dashboard ได้ทันที</li>
                  </ul>
                </div>
              </div>
            </div>

          </div>

          {/* Section 3: Master Leaderboard Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-lg font-bold text-white">Full Benchmark Leaderboard</h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  คลิกที่หัวตารางเพื่อเรียงลำดับตามตัวชี้วัดที่ต้องการ (คะแนนอิงตาม {evalMode === 'binary' ? 'Binary Detection' : '6-Class Multiclass'})
                </p>
              </div>
            </div>

            <div className="overflow-x-auto custom-scrollbar">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-semibold cursor-pointer select-none">
                    <th className="py-3 px-3">Model Name</th>
                    <th className="py-3 px-3">Category</th>
                    <th className="py-3 px-3 text-right" onClick={() => { setSortCol('features_count'); setSortAsc(!sortAsc); }} >Features</th>
                    <th className="py-3 px-3 text-right" onClick={() => { setSortCol('train_rows'); setSortAsc(!sortAsc); }} >Train Rows</th>
                    <th className="py-3 px-3 text-right text-sky-400" onClick={() => { setSortCol('in_domain_val'); setSortAsc(!sortAsc); }} >In-Domain F1</th>
                    <th className="py-3 px-3 text-right text-amber-400" onClick={() => { setSortCol('cross_domain_avg'); setSortAsc(!sortAsc); }} >Cross-Domain Avg</th>
                    <th className="py-3 px-3 text-right" onClick={() => { setSortCol('gen_gap'); setSortAsc(!sortAsc); }} >Generalization Gap</th>
                    <th className="py-3 px-3 text-right text-emerald-400 font-bold" onClick={() => { setSortCol('overall_f1'); setSortAsc(!sortAsc); }} >Overall Held-Out F1</th>
                    <th className="py-3 px-3 text-right text-rose-400" onClick={() => { setSortCol('overall_fpr'); setSortAsc(!sortAsc); }} >Overall FPR</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {leaderboardData.map((m, rank) => {
                    return (
                      <tr key={m.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-3 font-sans font-semibold text-white flex items-center gap-2">
                          <span className="w-5 text-slate-500 font-mono text-[10px]">#{rank+1}</span>
                          <span>{m.name}</span>
                        </td>
                        <td className="py-3 px-3 font-sans">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            m.group === 'Specialist' ? 'bg-slate-800 text-slate-300' :
                            (m.group === 'Harmonized' ? 'bg-sky-950 text-sky-300 border border-sky-800/40' : 'bg-emerald-950 text-emerald-300 border border-emerald-800/40')
                          }`}>
                            {m.group}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-right text-slate-300">{m.features_count}</td>
                        <td className="py-3 px-3 text-right text-slate-300">{m.train_rows.toLocaleString()}</td>
                        <td className="py-3 px-3 text-right text-sky-300 font-semibold">{m.in_domain_val}%</td>
                        <td className="py-3 px-3 text-right text-amber-300 font-semibold">{m.cross_domain_avg}%</td>
                        <td className={`py-3 px-3 text-right font-bold ${
                          m.gen_gap > 30 ? 'text-rose-400' : (m.gen_gap < 5 ? 'text-emerald-400' : 'text-amber-400')
                        }`}>
                          {m.gen_gap > 0 ? `-${m.gen_gap}%` : `+${Math.abs(m.gen_gap)}%`}
                        </td>
                        <td className="py-3 px-3 text-right text-emerald-400 font-extrabold text-sm bg-emerald-950/20">{m.overall_f1}%</td>
                        <td className="py-3 px-3 text-right text-rose-400">{m.overall_fpr}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 4: Academic Defense & Presentation Guidance */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
            <h3 className="text-base font-bold text-white">แนวทางการตอบอาจารย์และข้อสรุปเชิงวิชาการ (Academic Defense)</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-slate-300 leading-relaxed">
              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="font-semibold text-rose-400">1. ประเด็น: ทำไมไม่เทรน Dataset เดี่ยวด้วย Features เต็ม?</div>
                <p className="text-slate-400 text-[11px]">
                  <strong>ตอบอาจารย์ด้วยหลักฐาน:</strong> เราได้ทำการทดลองเปรียบเทียบโมเดลเฉพาะทางทั้ง 4 ตัว (M1 - M4) และพบว่าแม้โมเดลเหล่านั้นจะได้ F1 ถึง 99.2% ในบ้านตัวเอง แต่เมื่อนำไปทดสอบกับเน็ตเวิร์กอื่น ประสิทธิภาพดรอปลงเหลือ 0% หรือเกิด False Positive พุ่งสูงถึง 90-100% เนื่องจากเกิดภาวะ <em>Domain Shift</em> (Overfitting กับเครื่องมือดักจับแพ็กเก็ตของแล็บนั้นๆ)
                </p>
              </div>

              <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="font-semibold text-emerald-400">2. ประเด็น: ทำไมโมเดล 19 ฟีเจอร์ที่ Data เยอะ ถึงดีกว่า?</div>
                <p className="text-slate-400 text-[11px]">
                  <strong>ตอบอาจารย์ด้วยหลักฐาน:</strong> การเพิ่มข้อมูลเป็น 1.89M แถวใน M8 ทำให้คะแนน Multiclass F1 พุ่งจาก 68.4% เป็น 83.2% ชนะโมเดล 80 ฟีเจอร์ของ CENTRAL-UNCUT อย่างชัดเจน เพราะ 19 ฟีเจอร์คือพฤติกรรมฟิสิกส์พื้นฐานที่ไม่ขึ้นกับแล็บ ทำให้โมเดลเรียนรู้แก่นของการโจมตีที่แท้จริง ไม่หลงไปจำพารามิเตอร์แปลกปลอม
                </p>
              </div>
            </div>
          </div>

        </div>
      );
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  </script>
</body>
</html>
"""

html_rendered = html_template.replace("__BENCHMARK_DATA_PLACEHOLDER__", json_str)

with open(DASHBOARD_FILE, "w", encoding="utf8") as f:
    f.write(html_rendered)

print(f"Standalone React Dashboard built successfully at {DASHBOARD_FILE} ({DASHBOARD_FILE.stat().st_size / 1024:.1f} KB)")

# Precompile JSX to pure JavaScript using Node + Babel to eliminate runtime Babel dependency
import shutil
import subprocess

try:
    node_precompile_script = """
global.window = global;
global.document = { getElementsByTagName: () => [] };
global.navigator = { userAgent: 'node' };

const fs = require('fs');
const https = require('https');
const dashboardPath = 'experiments/scaling_and_domain_shift/dashboard/index.html';
const html = fs.readFileSync(dashboardPath, 'utf8');

const scriptMatch = html.match(/<script type="text\\/babel">([\\s\\S]*?)<\\/script>/);
if (scriptMatch) {
  const jsxCode = scriptMatch[1];
  const babelPath = '/tmp/babel.min.js';
  
  function doTransform(Babel) {
    const transformed = Babel.transform(jsxCode, {
      presets: [['react', { runtime: 'classic' }]]
    }).code;
    
    let newHtml = html.replace(
      `<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>`,
      `<!-- Precompiled React - No Babel runtime required -->`
    );
    newHtml = newHtml.replace(
      /<script type="text\\/babel">[\\s\\S]*?<\\/script>/,
      `<script>\\n${transformed}\\n</script>`
    );
    fs.writeFileSync(dashboardPath, newHtml, 'utf8');
    const webdashPath = 'webdashboard/scaling_and_domain_shift.html';
    fs.writeFileSync(webdashPath, newHtml, 'utf8');
    console.log('Successfully precompiled JSX to native JS for instant browser rendering!');
  }

  if (fs.existsSync(babelPath)) {
    const Babel = require(babelPath);
    doTransform(Babel);
  } else {
    https.get('https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.10/babel.min.js', (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        fs.writeFileSync(babelPath, data);
        const Babel = require(babelPath);
        doTransform(Babel);
      });
    }).on('error', (err) => console.log('Node Babel precompile fetch error, keeping Babel runtime:', err.message));
  }
}
"""
    res = subprocess.run(["node", "-e", node_precompile_script], capture_output=True, text=True, timeout=15)
    if res.returncode == 0:
        print(res.stdout.strip())
    else:
        print(f"Node precompilation skipped: {res.stderr.strip()[:200]}")
except Exception as e:
    print(f"Notice: Precompilation fallback (using runtime Babel): {e}")

# Ensure webdashboard copy exists
PROJECT_ROOT = EXP_DIR.parent.parent
webdash_dest = PROJECT_ROOT / "webdashboard" / "scaling_and_domain_shift.html"
if DASHBOARD_FILE.exists():
    shutil.copy(DASHBOARD_FILE, webdash_dest)
    print(f"Copied dashboard to {webdash_dest}")

