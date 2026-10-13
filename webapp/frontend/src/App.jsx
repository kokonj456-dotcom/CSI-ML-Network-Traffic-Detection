import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  RadialLinearScale,
  ArcElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar, Doughnut, Radar } from 'react-chartjs-2';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Trash2,
  CheckCircle2,
  SlidersHorizontal,
  Flame,
  Search,
  RefreshCw,
  Cpu,
  Layers,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  ShieldAlert,
  Sliders,
  Sparkles
} from 'lucide-react';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  RadialLinearScale,
  ArcElement,
  Title,
  Tooltip,
  Legend
);

export default function App() {
  const [activeTab, setActiveTab] = useState('models'); // eda, cleansing, features, models
  const [dataset, setDataset] = useState('common'); // common, nsl-kdd, unsw-nb15
  const [split, setSplit] = useState('all');

  // EDA State
  const [edaData, setEdaData] = useState(null);
  const [edaLoading, setEdaLoading] = useState(false);

  // Cleansing State
  const [cleansingData, setCleansingData] = useState(null);
  const [cleansingLoading, setCleansingLoading] = useState(false);

  // Features State
  const [featureData, setFeatureData] = useState(null);
  const [featureLoading, setFeatureLoading] = useState(false);

  // Models State
  const [modelRuns, setModelRuns] = useState([]);
  const [modelLoading, setModelLoading] = useState(false);

  // Leaderboard Filtering & Sorting State
  const [leaderboardFamily, setLeaderboardFamily] = useState('all');
  const [leaderboardMode, setLeaderboardMode] = useState('all'); // all, binary, multiclass
  const [leaderboardSortKey, setLeaderboardSortKey] = useState('accuracy'); // accuracy, f1, precision, recall, fpr, run_id
  const [leaderboardSortDir, setLeaderboardSortDir] = useState('desc'); // desc, asc
  const [leaderboardSearch, setLeaderboardSearch] = useState('');
  const [leaderboardPage, setLeaderboardPage] = useState(1);
  const LEADERBOARD_PAGE_SIZE = 10;

  // 2-Tier Comparator State
  const [familyA, setFamilyA] = useState('XGBoost');
  const [selectedRunIdA, setSelectedRunIdA] = useState('');
  const [familyB, setFamilyB] = useState('Autoencoder');
  const [selectedRunIdB, setSelectedRunIdB] = useState('');
  const [evalSplit, setEvalSplit] = useState('kddtest'); // kddtest, kddtest21
  const [comparatorModeFilter, setComparatorModeFilter] = useState('all'); // all, binary, multiclass

  // Live Model Training State
  const [trainingConfig, setTrainingConfig] = useState(null);
  const [trainingHistory, setTrainingHistory] = useState([]);
  const [trainFamily, setTrainFamily] = useState('XGBoost');
  const [trainDataset, setTrainDataset] = useState('common');
  const [trainTargetType, setTrainTargetType] = useState('binary'); // binary, multiclass
  const [trainHyperparams, setTrainHyperparams] = useState({
    n_estimators: 100,
    max_depth: 6,
    learning_rate: 0.1,
    subsample: 0.9,
    random_state: 42
  });
  const [isTraining, setIsTraining] = useState(false);
  const [trainingJobId, setTrainingJobId] = useState(null);
  const [trainingProgress, setTrainingProgress] = useState(null);
  const [trainResult, setTrainResult] = useState(null);
  const [trainError, setTrainError] = useState(null);

  const fetchTrainingConfig = () => {
    fetch('/api/training/config')
      .then(res => res.json())
      .then(data => setTrainingConfig(data))
      .catch(console.error);
  };

  const fetchTrainingHistory = () => {
    fetch('/api/training/history')
      .then(res => res.json())
      .then(data => setTrainingHistory(data.history || []))
      .catch(console.error);
  };

  useEffect(() => {
    fetchTrainingConfig();
    fetchTrainingHistory();
  }, []);

  const getActiveParamDefs = () => {
    if (!trainingConfig?.models) return [];
    const found = trainingConfig.models.find(m => m.family.toLowerCase() === trainFamily.toLowerCase());
    return found ? found.parameters : [];
  };

  const handleSelectFamily = (fam) => {
    setTrainFamily(fam);
    if (trainingConfig?.models) {
      const found = trainingConfig.models.find(m => m.family.toLowerCase() === fam.toLowerCase());
      if (found) {
        const defaults = {};
        found.parameters.forEach(p => {
          defaults[p.key] = p.default;
        });
        setTrainHyperparams(defaults);
      }
    }
  };

  const handleParamChange = (key, val) => {
    setTrainHyperparams(prev => ({ ...prev, [key]: val }));
  };

  const resetToDefaults = () => {
    handleSelectFamily(trainFamily);
  };

  const refreshModels = () => {
    setModelLoading(true);
    fetch(`/api/models`)
      .then(res => res.json())
      .then(data => {
        const runs = data.runs || [];
        setModelRuns(runs);
        setModelLoading(false);
      })
      .catch(err => {
        console.error(err);
        setModelLoading(false);
      });
  };

  const handleDeleteModel = (modelId, runName) => {
    if (!window.confirm(`Are you sure you want to delete model run "${runName}"? This action cannot be undone.`)) {
      return;
    }
    fetch(`/api/models?model_id=${encodeURIComponent(modelId)}`, {
      method: 'DELETE'
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          refreshModels();
        } else {
          alert(`Failed to delete model: ${modelId}`);
        }
      })
      .catch(err => {
        console.error('Delete error:', err);
        alert(`Delete request failed: ${err.message}`);
      });
  };

  const startLiveTraining = () => {
    setIsTraining(true);
    setTrainError(null);
    setTrainResult(null);
    setTrainingProgress({
      status: 'pending',
      percent: 0,
      phase: 'Initializing background training worker...',
      elapsed_seconds: 0
    });

    fetch('/api/training/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        family: trainFamily,
        dataset: trainDataset,
        target_type: trainTargetType,
        hyperparameters: trainHyperparams
      })
    })
      .then(res => {
        if (!res.ok) throw new Error(`Failed to start training: HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        const jobId = data.job_id;
        setTrainingJobId(jobId);

        // Poll progress every 400ms
        const intervalId = setInterval(() => {
          fetch(`/api/training/status?job_id=${jobId}`)
            .then(res => res.json())
            .then(statusData => {
              setTrainingProgress(statusData);

              if (statusData.status === 'completed') {
                clearInterval(intervalId);
                setIsTraining(false);
                setTrainResult(statusData.result);
                refreshModels();
                fetchTrainingHistory();
              } else if (statusData.status === 'failed') {
                clearInterval(intervalId);
                setIsTraining(false);
                setTrainError(statusData.error || 'Training encountered an error.');
              }
            })
            .catch(pollErr => {
              console.error('Polling error:', pollErr);
            });
        }, 400);
      })
      .catch(err => {
        console.error(err);
        setTrainError(err.message || 'Failed to dispatch training job');
        setIsTraining(false);
      });
  };

  // Load EDA data
  useEffect(() => {
    if (activeTab === 'eda') {
      setEdaLoading(true);
      fetch(`/api/eda?dataset=${dataset}&split=${split}`)
        .then(res => res.json())
        .then(data => {
          setEdaData(data);
          setEdaLoading(false);
        })
        .catch(err => {
          console.error(err);
          setEdaLoading(false);
        });
    }
  }, [activeTab, dataset, split]);

  // Load Cleansing data
  useEffect(() => {
    if (activeTab === 'cleansing') {
      setCleansingLoading(true);
      fetch(`/api/cleansing?dataset=${dataset}`)
        .then(res => res.json())
        .then(data => {
          setCleansingData(data);
          setCleansingLoading(false);
        })
        .catch(err => {
          console.error(err);
          setCleansingLoading(false);
        });
    }
  }, [activeTab, dataset]);

  // Load Feature Contract data
  useEffect(() => {
    if (activeTab === 'features') {
      setFeatureLoading(true);
      fetch(`/api/features`)
        .then(res => res.json())
        .then(data => {
          setFeatureData(data);
          setFeatureLoading(false);
        })
        .catch(err => {
          console.error(err);
          setFeatureLoading(false);
        });
    }
  }, [activeTab]);

  // Load Models data
  useEffect(() => {
    setModelLoading(true);
    fetch(`/api/models`)
      .then(res => res.json())
      .then(data => {
        const runs = data.runs || [];
        setModelRuns(runs);
        setModelLoading(false);

        // Set default runs for Family A and B
        const aRuns = runs.filter(r => r.family === 'XGBoost');
        if (aRuns.length > 0) setSelectedRunIdA(aRuns[0].id);

        const bRuns = runs.filter(r => r.family === 'Autoencoder');
        if (bRuns.length > 0) setSelectedRunIdB(bRuns[0].id);
      })
      .catch(err => {
        console.error(err);
        setModelLoading(false);
      });
  }, []);

  // Filter runs by family and optional target formulation mode for Model A
  const availableRunsA = modelRuns.filter(r => {
    if (r.family !== familyA) return false;
    if (comparatorModeFilter !== 'all' && (r.mode || 'binary').toLowerCase() !== comparatorModeFilter) return false;
    return true;
  });
  // Filter runs by family and optional target formulation mode for Model B
  const availableRunsB = modelRuns.filter(r => {
    if (r.family !== familyB) return false;
    if (comparatorModeFilter !== 'all' && (r.mode || 'binary').toLowerCase() !== comparatorModeFilter) return false;
    return true;
  });

  // Active run objects
  const runA = modelRuns.find(r => r.id === selectedRunIdA) || availableRunsA[0];
  const runB = modelRuns.find(r => r.id === selectedRunIdB) || availableRunsB[0];

  const metricsA = evalSplit === 'kddtest21' ? runA?.kddtest21 : runA?.kddtest;
  const metricsB = evalSplit === 'kddtest21' ? runB?.kddtest21 : runB?.kddtest;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/50 flex items-center justify-center font-bold text-indigo-400">
              N
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-white text-base">NIDS Unified Pipeline Dashboard</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">v2.0</span>
              </div>
              <p className="text-xs text-slate-400">NSL-KDD, UNSW-NB15, Harmonized Pipeline & Cross-Model Benchmark</p>
            </div>
          </div>

          {/* Dataset Switcher in Header */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400 hidden sm:inline">Active Dataset:</span>
            <select
              value={dataset}
              onChange={(e) => {
                setDataset(e.target.value);
                setSplit('all');
              }}
              className="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
            >
              <option value="common">Common (Harmonized Merged)</option>
              <option value="nsl-kdd">NSL-KDD</option>
              <option value="unsw-nb15">UNSW-NB15</option>
            </select>
          </div>
        </div>

        {/* Global Tab Navigation */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex border-t border-slate-800/80 text-xs">
          {[
            { id: 'models', label: 'Models & Comparison' },
            { id: 'training', label: 'Model Training' },
            { id: 'eda', label: 'EDA & Distributions' },
            { id: 'cleansing', label: 'Data Cleansing & Quality' },
            { id: 'features', label: 'Feature Engineering & Contract' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 px-4 font-semibold transition border-b-2 flex items-center gap-2 ${
                activeTab === tab.id
                  ? 'border-indigo-500 text-indigo-400 bg-slate-800/40'
                  : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

        {/* 1. MODELS & COMPARISON TAB */}
        {activeTab === 'models' && (
          <div className="space-y-6">
            {/* Tab Header Banner */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-white">Cross-Model Benchmark & Head-to-Head Comparator</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Compare performance metrics between supervised classifiers and unsupervised anomaly detectors on NSL-KDD benchmark test sets.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Target Mode:</span>
                    <select
                      value={comparatorModeFilter}
                      onChange={(e) => setComparatorModeFilter(e.target.value)}
                      className="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1 focus:outline-none focus:border-indigo-500 font-sans font-medium"
                    >
                      <option value="all">All Formulations</option>
                      <option value="binary">Binary (Normal vs Attack)</option>
                      <option value="multiclass">Multiclass (7 Attack Classes)</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">Evaluation Test View:</span>
                    <select
                      value={evalSplit}
                      onChange={(e) => setEvalSplit(e.target.value)}
                      className="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1 focus:outline-none focus:border-indigo-500 font-mono"
                    >
                      <option value="kddtest">KDDTest+ (Full Test Set)</option>
                      <option value="kddtest21">KDDTest-21 (Difficult Novel Set)</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* 2-Tier Selection Box for Comparator */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Model A Tier Selection */}
              <div className="bg-slate-900 border border-indigo-500/30 rounded-xl p-4 shadow-md space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
                    Model A (Baseline)
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {runA?.kddtest?.accuracy ? `Acc: ${(runA.kddtest.accuracy * 100).toFixed(2)}%` : '-'}
                  </span>
                </div>

                {/* Tier 1: Select Main Family */}
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Step 1: Select Model Family</label>
                  <select
                    value={familyA}
                    onChange={(e) => {
                      const newFam = e.target.value;
                      setFamilyA(newFam);
                      const matching = modelRuns.filter(r => r.family === newFam);
                      if (matching.length > 0) setSelectedRunIdA(matching[0].id);
                    }}
                    className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
                  >
                    {['XGBoost', 'Autoencoder', 'MLP', 'Isolation Forest'].map(fam => (
                      <option key={fam} value={fam}>{fam}</option>
                    ))}
                  </select>
                </div>

                {/* Tier 2: Select Checkpoint Run */}
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Step 2: Select Trained Checkpoint / Run</label>
                  <select
                    value={selectedRunIdA}
                    onChange={(e) => setSelectedRunIdA(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-mono truncate"
                  >
                    {availableRunsA.map(r => (
                      <option key={r.id} value={r.id}>
                        {r.run_id} {r.kddtest?.accuracy ? `(${(r.kddtest.accuracy * 100).toFixed(2)}%)` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Model B Tier Selection */}
              <div className="bg-slate-900 border border-sky-500/30 rounded-xl p-4 shadow-md space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800">
                    Model B (Challenger)
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {runB?.kddtest?.accuracy ? `Acc: ${(runB.kddtest.accuracy * 100).toFixed(2)}%` : '-'}
                  </span>
                </div>

                {/* Tier 1: Select Main Family */}
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Step 1: Select Model Family</label>
                  <select
                    value={familyB}
                    onChange={(e) => {
                      const newFam = e.target.value;
                      setFamilyB(newFam);
                      const matching = modelRuns.filter(r => r.family === newFam);
                      if (matching.length > 0) setSelectedRunIdB(matching[0].id);
                    }}
                    className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-medium"
                  >
                    {['Autoencoder', 'XGBoost', 'MLP', 'Isolation Forest'].map(fam => (
                      <option key={fam} value={fam}>{fam}</option>
                    ))}
                  </select>
                </div>

                {/* Tier 2: Select Checkpoint Run */}
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Step 2: Select Trained Checkpoint / Run</label>
                  <select
                    value={selectedRunIdB}
                    onChange={(e) => setSelectedRunIdB(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-mono truncate"
                  >
                    {availableRunsB.map(r => (
                      <option key={r.id} value={r.id}>
                        {r.run_id} {r.kddtest?.accuracy ? `(${(r.kddtest.accuracy * 100).toFixed(2)}%)` : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Side-by-Side Comparison Metrics Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
              <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Head-to-Head Metrics Evaluation</h3>
                <span className="text-[11px] font-mono text-slate-400">View: {evalSplit.toUpperCase()}</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs table-fixed">
                  <colgroup>
                    <col className="w-1/3" />
                    <col className="w-1/6" />
                    <col className="w-1/6" />
                    <col className="w-1/6" />
                    <col className="w-1/6" />
                  </colgroup>
                  <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800 font-semibold">
                    <tr>
                      <th className="py-3 px-4">Evaluation Metric</th>
                      <th className="py-3 px-3 text-center text-indigo-400 font-mono truncate" title={runA?.run_id}>
                        Model A ({runA?.family || 'A'})
                      </th>
                      <th className="py-3 px-3 text-center font-mono truncate">Diff (B - A)</th>
                      <th className="py-3 px-3 text-center text-sky-400 font-mono truncate" title={runB?.run_id}>
                        Model B ({runB?.family || 'B'})
                      </th>
                      <th className="py-3 px-4 text-right">Advantage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80 font-mono">
                    {[
                      { key: 'accuracy', name: 'Overall Accuracy', higherBetter: true, isPct: true },
                      { key: 'balanced_accuracy', name: 'Balanced Accuracy', higherBetter: true, isPct: true },
                      { key: 'f1', name: 'Macro F1-Score', higherBetter: true, isPct: false },
                      { key: 'precision', name: 'Attack Precision', higherBetter: true, isPct: true },
                      { key: 'recall', name: 'Detection Recall', higherBetter: true, isPct: true },
                      { key: 'false_positive_rate', name: 'False Positive Rate (FPR)', higherBetter: false, isPct: true }
                    ].map(m => {
                      const valA = metricsA ? metricsA[m.key] : null;
                      const valB = metricsB ? metricsB[m.key] : null;

                      const strA = valA !== null && valA !== undefined ? (m.isPct ? `${(valA * 100).toFixed(2)}%` : valA.toFixed(4)) : '-';
                      const strB = valB !== null && valB !== undefined ? (m.isPct ? `${(valB * 100).toFixed(2)}%` : valB.toFixed(4)) : '-';

                      let diffHtml = <span className="text-slate-500 font-mono">-</span>;
                      let advHtml = <span className="text-slate-500 font-sans text-[11px] whitespace-nowrap">Tied / N/A</span>;

                      if (valA !== null && valA !== undefined && valB !== null && valB !== undefined) {
                        const delta = valB - valA;
                        const deltaStr = m.isPct ? `${(Math.abs(delta) * 100).toFixed(2)}%` : Math.abs(delta).toFixed(4);
                        const isBBetter = m.higherBetter ? delta > 0.0001 : delta < -0.0001;
                        const isABetter = m.higherBetter ? delta < -0.0001 : delta > 0.0001;

                        if (isBBetter) {
                          diffHtml = (
                            <span className="inline-flex items-center gap-1 text-emerald-400 font-bold whitespace-nowrap">
                              <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
                              <span>+{deltaStr}</span>
                            </span>
                          );
                          advHtml = (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 text-[10px] font-sans font-bold whitespace-nowrap">
                              <span>Model B</span>
                              <span className="font-mono text-sky-400">(+{deltaStr})</span>
                            </span>
                          );
                        } else if (isABetter) {
                          diffHtml = (
                            <span className="inline-flex items-center gap-1 text-rose-400 font-bold whitespace-nowrap">
                              <ArrowDown className="w-3.5 h-3.5 stroke-[2.5]" />
                              <span>-{deltaStr}</span>
                            </span>
                          );
                          advHtml = (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 text-[10px] font-sans font-bold whitespace-nowrap">
                              <span>Model A</span>
                              <span className="font-mono text-indigo-400">(+{deltaStr})</span>
                            </span>
                          );
                        } else {
                          diffHtml = <span className="text-slate-500 font-mono">0.00</span>;
                          advHtml = <span className="text-slate-400 font-sans text-[11px] whitespace-nowrap">Even</span>;
                        }
                      }

                      return (
                        <tr key={m.key} className="hover:bg-slate-800/40 transition">
                          <td className="py-2.5 px-4 text-slate-200 font-sans font-medium whitespace-nowrap">{m.name}</td>
                          <td className="py-2.5 px-3 text-center font-bold text-indigo-300 whitespace-nowrap">{strA}</td>
                          <td className="py-2.5 px-3 text-center whitespace-nowrap">{diffHtml}</td>
                          <td className="py-2.5 px-3 text-center font-bold text-sky-300 whitespace-nowrap">{strB}</td>
                          <td className="py-2.5 px-4 text-right whitespace-nowrap">{advHtml}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Confusion Matrix Face-Off */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Matrix A */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold text-indigo-400 mb-3 flex items-center justify-between">
                  <span>Model A Confusion Matrix ({runA?.model_name || 'A'})</span>
                  <span className="text-[10px] text-slate-500 font-mono">True vs Predicted</span>
                </h4>
                {metricsA?.confusion_matrix && metricsA.confusion_matrix.length > 0 ? (
                  <div className="overflow-x-auto flex justify-center py-2">
                    <table className="border-collapse text-center text-xs font-mono">
                      <thead>
                        <tr>
                          <th className="p-1 text-[9px] text-slate-400">T \ P</th>
                          {(metricsA.classes || ['Normal', 'Attack']).map((c, i) => (
                            <th key={i} className="p-1.5 px-3 font-semibold text-slate-300 border-b border-slate-700">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {metricsA.confusion_matrix.map((row, i) => {
                          const rowSum = row.reduce((a, b) => a + b, 0) || 1;
                          return (
                            <tr key={i}>
                              <td className="p-1.5 px-3 font-semibold text-slate-300 border-r border-slate-700 text-left">
                                {(metricsA.classes || ['Normal', 'Attack'])[i] || i}
                              </td>
                              {row.map((val, j) => {
                                const isDiag = i === j;
                                const pct = Math.round((val / rowSum) * 100);
                                return (
                                  <td
                                    key={j}
                                    style={{
                                      backgroundColor: isDiag
                                        ? `rgba(16, 185, 129, ${Math.max(0.2, pct / 100)})`
                                        : `rgba(239, 68, 68, ${Math.min(0.6, (val / rowSum) * 0.8)})`
                                    }}
                                    className="p-2 border border-slate-800 text-white"
                                  >
                                    <div className="font-bold">{val.toLocaleString()}</div>
                                    <div className="text-[9px] text-slate-300">{pct}%</div>
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-xs">No confusion matrix recorded</div>
                )}
              </div>

              {/* Matrix B */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                <h4 className="text-xs font-bold text-sky-400 mb-3 flex items-center justify-between">
                  <span>Model B Confusion Matrix ({runB?.model_name || 'B'})</span>
                  <span className="text-[10px] text-slate-500 font-mono">True vs Predicted</span>
                </h4>
                {metricsB?.confusion_matrix && metricsB.confusion_matrix.length > 0 ? (
                  <div className="overflow-x-auto flex justify-center py-2">
                    <table className="border-collapse text-center text-xs font-mono">
                      <thead>
                        <tr>
                          <th className="p-1 text-[9px] text-slate-400">T \ P</th>
                          {(metricsB.classes || ['Normal', 'Attack']).map((c, i) => (
                            <th key={i} className="p-1.5 px-3 font-semibold text-slate-300 border-b border-slate-700">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {metricsB.confusion_matrix.map((row, i) => {
                          const rowSum = row.reduce((a, b) => a + b, 0) || 1;
                          return (
                            <tr key={i}>
                              <td className="p-1.5 px-3 font-semibold text-slate-300 border-r border-slate-700 text-left">
                                {(metricsB.classes || ['Normal', 'Attack'])[i] || i}
                              </td>
                              {row.map((val, j) => {
                                const isDiag = i === j;
                                const pct = Math.round((val / rowSum) * 100);
                                return (
                                  <td
                                    key={j}
                                    style={{
                                      backgroundColor: isDiag
                                        ? `rgba(16, 185, 129, ${Math.max(0.2, pct / 100)})`
                                        : `rgba(239, 68, 68, ${Math.min(0.6, (val / rowSum) * 0.8)})`
                                    }}
                                    className="p-2 border border-slate-800 text-white"
                                  >
                                    <div className="font-bold">{val.toLocaleString()}</div>
                                    <div className="text-[9px] text-slate-300">{pct}%</div>
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-xs">No confusion matrix recorded</div>
                )}
              </div>
            </div>

            {/* Hyperparameters Face-Off & Comparison */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Hyperparameter Inspection & Comparison
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Side-by-side audit of training configurations and parameters between Model A and Model B
                  </p>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  Parameter Audit
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Model A Hyperparameters */}
                <div className="bg-slate-950/60 border border-indigo-500/20 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-2">
                    <span className="text-xs font-bold text-indigo-400 truncate max-w-[200px]" title={runA?.model_name}>
                      Model A: {runA?.model_name || 'A'}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                      {runA?.family}
                    </span>
                  </div>
                  {runA?.hyperparameters && Object.keys(runA.hyperparameters).length > 0 ? (
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                      {Object.entries(runA.hyperparameters).map(([k, v]) => (
                        <div key={k} className="bg-slate-900 border border-slate-800 rounded-lg p-2 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans uppercase tracking-wider truncate" title={k}>
                            {k.replace(/_/g, ' ')}
                          </span>
                          <span className="text-indigo-300 font-bold truncate mt-0.5" title={String(v)}>
                            {typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(4)) : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-6 text-center text-xs text-slate-500">No explicit hyperparameters recorded for baseline run</div>
                  )}
                </div>

                {/* Model B Hyperparameters */}
                <div className="bg-slate-950/60 border border-sky-500/20 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-2">
                    <span className="text-xs font-bold text-sky-400 truncate max-w-[200px]" title={runB?.model_name}>
                      Model B: {runB?.model_name || 'B'}
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
                      {runB?.family}
                    </span>
                  </div>
                  {runB?.hyperparameters && Object.keys(runB.hyperparameters).length > 0 ? (
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                      {Object.entries(runB.hyperparameters).map(([k, v]) => (
                        <div key={k} className="bg-slate-900 border border-slate-800 rounded-lg p-2 flex flex-col">
                          <span className="text-[10px] text-slate-400 font-sans uppercase tracking-wider truncate" title={k}>
                            {k.replace(/_/g, ' ')}
                          </span>
                          <span className="text-sky-300 font-bold truncate mt-0.5" title={String(v)}>
                            {typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(4)) : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-6 text-center text-xs text-slate-500">No explicit hyperparameters recorded for baseline run</div>
                  )}
                </div>
              </div>
            </div>

            {/* Section 1: Best Performing Models by Family */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Top Model Performers by Architecture Family
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Highest scoring configuration from each model family based on evaluation test accuracy and macro F1
                  </p>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                  Champion Models
                </span>
              </div>

              {(() => {
                const families = ['XGBoost', 'MLP', 'Autoencoder', 'Isolation Forest'];
                const bestByFamily = {};

                families.forEach(fam => {
                  const runsInFam = modelRuns.filter(r => r.family === fam);
                  if (runsInFam.length === 0) return;
                  const sorted = [...runsInFam].sort((a, b) => {
                    const accA = a.kddtest?.accuracy ?? 0;
                    const accB = b.kddtest?.accuracy ?? 0;
                    return accB - accA;
                  });
                  bestByFamily[fam] = sorted[0];
                });

                return (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {families.map(fam => {
                      const best = bestByFamily[fam];
                      if (!best) return null;
                      const acc = best.kddtest?.accuracy;
                      const f1 = best.kddtest?.f1;
                      const fpr = best.kddtest?.false_positive_rate;

                      return (
                        <div
                          key={fam}
                          className="bg-slate-950/80 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex flex-col justify-between space-y-3 transition"
                        >
                          <div>
                            <div className="flex items-center justify-between mb-1.5">
                              <span className="text-xs font-bold text-white uppercase tracking-wider">{fam}</span>
                              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                                Best Pick
                              </span>
                            </div>
                            <div className="text-[11px] font-mono text-slate-300 truncate font-semibold" title={best.run_id}>
                              {best.run_id}
                            </div>
                            <div className="text-[10px] text-slate-500 font-sans mt-0.5 uppercase tracking-wider">
                              Mode: {best.mode}
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1 border-t border-slate-800/80">
                            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                              <span className="text-[9px] text-slate-400 block font-sans uppercase">Accuracy</span>
                              <span className="text-emerald-400 font-bold">
                                {acc !== null && acc !== undefined ? `${(acc * 100).toFixed(2)}%` : '-'}
                              </span>
                            </div>
                            <div className="bg-slate-900/90 p-2 rounded-lg border border-slate-800">
                              <span className="text-[9px] text-slate-400 block font-sans uppercase">Macro F1</span>
                              <span className="text-sky-400 font-bold">
                                {f1 !== null && f1 !== undefined ? f1.toFixed(4) : '-'}
                              </span>
                            </div>
                          </div>

                          {best.hyperparameters && Object.keys(best.hyperparameters).length > 0 && (
                            <div className="text-[10px] font-mono text-slate-400 bg-slate-900/50 p-2 rounded border border-slate-800/60 truncate" title={JSON.stringify(best.hyperparameters)}>
                              <span className="text-slate-500 mr-1 uppercase text-[9px] font-sans">Params:</span>
                              {Object.entries(best.hyperparameters).slice(0, 3).map(([k, v]) => `${k}:${v}`).join(', ')}
                            </div>
                          )}

                          <div className="grid grid-cols-2 gap-2 pt-1 font-sans">
                            <button
                              type="button"
                              onClick={() => {
                                setFamilyA(fam);
                                setSelectedRunIdA(best.id);
                              }}
                              className="py-1 px-2 text-[10px] font-bold bg-indigo-950/70 hover:bg-indigo-900 text-indigo-300 border border-indigo-800/80 rounded-lg transition text-center whitespace-nowrap"
                            >
                              Set as Model A
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setFamilyB(fam);
                                setSelectedRunIdB(best.id);
                              }}
                              className="py-1 px-2 text-[10px] font-bold bg-sky-950/70 hover:bg-sky-900 text-sky-300 border border-sky-800/80 rounded-lg transition text-center whitespace-nowrap"
                            >
                              Set as Model B
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            {/* Section 2: Interactive Model Leaderboard with Filter & Sorting */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Comprehensive Model Benchmark Leaderboard ({modelRuns.length} Total Runs)
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Filter by architecture family, search by configuration keywords, and sort by key detection metrics
                  </p>
                </div>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                  Interactive Leaderboard
                </span>
              </div>

              {/* Leaderboard Controls (Filter, Mode, Search, Sort) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                {/* Family Filter */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Filter by Family
                  </label>
                  <select
                    value={leaderboardFamily}
                    onChange={(e) => {
                      setLeaderboardFamily(e.target.value);
                      setLeaderboardPage(1);
                    }}
                    className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
                  >
                    <option value="all">All Families ({modelRuns.length})</option>
                    <option value="XGBoost">XGBoost ({modelRuns.filter(r => r.family === 'XGBoost').length})</option>
                    <option value="MLP">MLP Neural Network ({modelRuns.filter(r => r.family === 'MLP').length})</option>
                    <option value="Autoencoder">Autoencoder ({modelRuns.filter(r => r.family === 'Autoencoder').length})</option>
                    <option value="Isolation Forest">Isolation Forest ({modelRuns.filter(r => r.family === 'Isolation Forest').length})</option>
                  </select>
                </div>

                {/* Formulation Mode Filter */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Target Formulation
                  </label>
                  <select
                    value={leaderboardMode}
                    onChange={(e) => {
                      setLeaderboardMode(e.target.value);
                      setLeaderboardPage(1);
                    }}
                    className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
                  >
                    <option value="all">All Formulations</option>
                    <option value="binary">Binary Classification</option>
                    <option value="multiclass">Multiclass Categorization</option>
                  </select>
                </div>

                {/* Search Input */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Search Run ID
                  </label>
                  <input
                    type="text"
                    value={leaderboardSearch}
                    onChange={(e) => {
                      setLeaderboardSearch(e.target.value);
                      setLeaderboardPage(1);
                    }}
                    placeholder="e.g. common, seed, multiclass..."
                    className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-indigo-500 font-mono placeholder-slate-600"
                  />
                </div>

                {/* Metric Sort Key */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Sort Metric
                  </label>
                  <select
                    value={leaderboardSortKey}
                    onChange={(e) => {
                      setLeaderboardSortKey(e.target.value);
                      setLeaderboardPage(1);
                    }}
                    className="w-full bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
                  >
                    <option value="accuracy">Accuracy (KDDTest)</option>
                    <option value="f1">Macro F1-Score</option>
                    <option value="precision">Attack Precision</option>
                    <option value="recall">Detection Recall</option>
                    <option value="false_positive_rate">False Positive Rate (FPR)</option>
                    <option value="run_id">Run Name / ID</option>
                  </select>
                </div>

                {/* Sort Order */}
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                    Sort Direction
                  </label>
                  <div className="flex gap-1.5 h-[34px]">
                    <button
                      type="button"
                      onClick={() => setLeaderboardSortDir('desc')}
                      title="Sort Highest First (Descending)"
                      className={`flex-1 flex items-center justify-center gap-1.5 px-2.5 rounded-lg border text-xs font-semibold transition ${
                        leaderboardSortDir === 'desc'
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30'
                          : 'bg-slate-900 text-slate-400 border-slate-700 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      <ArrowDown className="w-3.5 h-3.5 stroke-[2.5]" />
                      <span className="text-[11px] font-mono">Desc</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setLeaderboardSortDir('asc')}
                      title="Sort Lowest First (Ascending)"
                      className={`flex-1 flex items-center justify-center gap-1.5 px-2.5 rounded-lg border text-xs font-semibold transition ${
                        leaderboardSortDir === 'asc'
                          ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30'
                          : 'bg-slate-900 text-slate-400 border-slate-700 hover:text-white hover:bg-slate-800'
                      }`}
                    >
                      <ArrowUp className="w-3.5 h-3.5 stroke-[2.5]" />
                      <span className="text-[11px] font-mono">Asc</span>
                    </button>
                  </div>
                </div>
              </div>

              {/* Leaderboard Table with Pagination */}
              {(() => {
                let filtered = modelRuns.filter(r => {
                  if (leaderboardFamily !== 'all' && r.family !== leaderboardFamily) return false;
                  if (leaderboardMode !== 'all' && (r.mode || 'binary').toLowerCase() !== leaderboardMode) return false;
                  if (leaderboardSearch.trim()) {
                    const query = leaderboardSearch.toLowerCase();
                    const inName = (r.run_id || '').toLowerCase().includes(query);
                    const inFamily = (r.family || '').toLowerCase().includes(query);
                    const inMode = (r.mode || '').toLowerCase().includes(query);
                    if (!inName && !inFamily && !inMode) return false;
                  }
                  return true;
                });

                filtered.sort((a, b) => {
                  let valA = a.kddtest?.[leaderboardSortKey];
                  let valB = b.kddtest?.[leaderboardSortKey];

                  if (leaderboardSortKey === 'run_id') {
                    valA = a.run_id || '';
                    valB = b.run_id || '';
                    return leaderboardSortDir === 'desc' ? valB.localeCompare(valA) : valA.localeCompare(valB);
                  }

                  valA = valA ?? -1;
                  valB = valB ?? -1;
                  return leaderboardSortDir === 'desc' ? valB - valA : valA - valB;
                });

                const totalPages = Math.max(1, Math.ceil(filtered.length / LEADERBOARD_PAGE_SIZE));
                const currentPage = Math.min(Math.max(1, leaderboardPage), totalPages);
                const startIndex = (currentPage - 1) * LEADERBOARD_PAGE_SIZE;
                const endIndex = Math.min(startIndex + LEADERBOARD_PAGE_SIZE, filtered.length);
                const paginatedRuns = filtered.slice(startIndex, endIndex);

                return (
                  <div className="space-y-3">
                    <div className="overflow-x-auto rounded-xl border border-slate-800">
                      <table className="w-full text-left text-xs table-fixed divide-y divide-slate-800/80">
                        <colgroup>
                          <col className="w-[50px]" />
                          <col className="w-[110px]" />
                          <col className="w-[180px]" />
                          <col className="w-[95px]" />
                          <col className="w-[95px]" />
                          <col className="w-[85px]" />
                          <col className="w-[85px]" />
                          <col className="w-[85px]" />
                          <col className="w-[80px]" />
                          <col className="w-[125px]" />
                          <col className="w-[60px]" />
                        </colgroup>
                        <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                          <tr>
                            <th className="py-2.5 px-2.5 text-center">Rank</th>
                            <th className="py-2.5 px-2.5">Family</th>
                            <th className="py-2.5 px-3">Run Name / ID</th>
                            <th className="py-2.5 px-2.5 text-center">Mode</th>
                            <th className="py-2.5 px-2.5 text-right">Accuracy</th>
                            <th className="py-2.5 px-2.5 text-right">Macro F1</th>
                            <th className="py-2.5 px-2.5 text-right">Precision</th>
                            <th className="py-2.5 px-2.5 text-right">Recall</th>
                            <th className="py-2.5 px-2.5 text-right">FPR</th>
                            <th className="py-2.5 px-2.5 text-center">Compare</th>
                            <th className="py-2.5 px-2.5 text-center">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/80 font-mono bg-slate-900/40">
                          {paginatedRuns.length > 0 ? (
                            paginatedRuns.map((r, idx) => {
                              const globalRank = startIndex + idx + 1;
                              const isMulticlass = (r.mode || '').toLowerCase() === 'multiclass';
                              return (
                                <tr key={r.id} className="hover:bg-slate-800/50 transition">
                                  <td className="py-2.5 px-2.5 font-sans text-slate-400 font-bold text-center">
                                    #{globalRank}
                                  </td>
                                  <td className="py-2.5 px-2.5 font-sans">
                                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-300 block truncate text-center">
                                      {r.family}
                                    </span>
                                  </td>
                                  <td className="py-2.5 px-3 text-slate-200">
                                    <div className="truncate font-medium" title={r.run_id}>
                                      {r.run_id}
                                    </div>
                                  </td>
                                  <td className="py-2.5 px-2.5 font-sans text-center">
                                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border inline-block ${
                                      isMulticlass
                                        ? 'border-purple-800 bg-purple-950/60 text-purple-300'
                                        : 'border-slate-700 bg-slate-800/60 text-slate-300'
                                    }`}>
                                      {r.mode || 'binary'}
                                    </span>
                                  </td>
                                  <td className="py-2.5 px-2.5 text-emerald-400 font-bold text-right whitespace-nowrap">
                                    {r.kddtest?.accuracy ? `${(r.kddtest.accuracy * 100).toFixed(2)}%` : '-'}
                                  </td>
                                  <td className="py-2.5 px-2.5 text-sky-400 font-bold text-right whitespace-nowrap">
                                    {r.kddtest?.f1 ? r.kddtest.f1.toFixed(4) : '-'}
                                  </td>
                                  <td className="py-2.5 px-2.5 text-slate-300 text-right whitespace-nowrap">
                                    {r.kddtest?.precision ? `${(r.kddtest.precision * 100).toFixed(2)}%` : '-'}
                                  </td>
                                  <td className="py-2.5 px-2.5 text-indigo-300 text-right whitespace-nowrap">
                                    {r.kddtest?.recall ? `${(r.kddtest.recall * 100).toFixed(2)}%` : '-'}
                                  </td>
                                  <td className="py-2.5 px-2.5 text-rose-400 text-right whitespace-nowrap">
                                    {r.kddtest?.false_positive_rate !== undefined && r.kddtest?.false_positive_rate !== null
                                      ? `${(r.kddtest.false_positive_rate * 100).toFixed(2)}%`
                                      : '-'}
                                  </td>
                                  <td className="py-2.5 px-2.5 text-center">
                                    <div className="inline-flex items-center gap-1">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setFamilyA(r.family);
                                          setSelectedRunIdA(r.id);
                                        }}
                                        className="px-2 py-0.5 rounded text-[10px] font-sans font-bold bg-indigo-950 text-indigo-300 border border-indigo-800 hover:bg-indigo-900 hover:text-white transition whitespace-nowrap"
                                        title={`Set ${r.run_id} as Model A`}
                                      >
                                        Set A
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setFamilyB(r.family);
                                          setSelectedRunIdB(r.id);
                                        }}
                                        className="px-2 py-0.5 rounded text-[10px] font-sans font-bold bg-sky-950 text-sky-300 border border-sky-800 hover:bg-sky-900 hover:text-white transition whitespace-nowrap"
                                        title={`Set ${r.run_id} as Model B`}
                                      >
                                        Set B
                                      </button>
                                    </div>
                                  </td>
                                  <td className="py-2.5 px-2.5 text-center">
                                    <button
                                      type="button"
                                      onClick={() => handleDeleteModel(r.id, r.run_id)}
                                      className="p-1.5 rounded-lg text-rose-400 hover:text-white hover:bg-rose-900/60 border border-rose-900/40 hover:border-rose-700 transition inline-flex items-center justify-center"
                                      title={`Delete run: ${r.run_id}`}
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={11} className="py-8 text-center text-slate-500 font-sans">
                                No model runs matched your filter criteria.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination Controls Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800/80 text-xs font-sans">
                      <div className="text-slate-400 font-mono text-[11px]">
                        Showing <span className="text-white font-bold">{filtered.length > 0 ? startIndex + 1 : 0}</span> to{' '}
                        <span className="text-white font-bold">{endIndex}</span> of{' '}
                        <span className="text-white font-bold">{filtered.length}</span> runs
                        {filtered.length !== modelRuns.length && (
                          <span className="text-slate-500 ml-1">({modelRuns.length} total)</span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={currentPage <= 1}
                          onClick={() => setLeaderboardPage(prev => Math.max(1, prev - 1))}
                          title="Previous Page"
                          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition ${
                            currentPage <= 1
                              ? 'bg-slate-900/40 text-slate-600 border-slate-800/60 cursor-not-allowed'
                              : 'bg-slate-900 text-slate-300 border-slate-700 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          <ChevronLeft className="w-3.5 h-3.5" />
                          <span>Prev</span>
                        </button>

                        <div className="flex items-center gap-1 font-mono text-xs">
                          {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => {
                            if (
                              p === 1 ||
                              p === totalPages ||
                              (p >= currentPage - 1 && p <= currentPage + 1)
                            ) {
                              return (
                                <button
                                  key={p}
                                  type="button"
                                  onClick={() => setLeaderboardPage(p)}
                                  className={`min-w-[28px] h-7 px-1.5 rounded text-xs font-bold transition ${
                                    currentPage === p
                                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                                      : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                                  }`}
                                >
                                  {p}
                                </button>
                              );
                            }
                            if (p === currentPage - 2 || p === currentPage + 2) {
                              return <span key={p} className="text-slate-600 px-0.5">...</span>;
                            }
                            return null;
                          })}
                        </div>

                        <button
                          type="button"
                          disabled={currentPage >= totalPages}
                          onClick={() => setLeaderboardPage(prev => Math.min(totalPages, prev + 1))}
                          title="Next Page"
                          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition ${
                            currentPage >= totalPages
                              ? 'bg-slate-900/40 text-slate-600 border-slate-800/60 cursor-not-allowed'
                              : 'bg-slate-900 text-slate-300 border-slate-700 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          <span>Next</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* 2. MODEL TRAINING TAB */}
        {activeTab === 'training' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white">Interactive Model Training Studio</h2>
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800">
                    On-Demand Training Engine
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Train any model family (XGBoost, MLP, Autoencoder, Isolation Forest) on your selected dataset with customized hyperparameters.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Form Controls Column */}
              <div className="lg:col-span-2 space-y-6">
                {/* Step 1: Model Family Cards */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                    Step 1: Choose Model Architecture
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {[
                      { id: 'XGBoost', name: 'XGBoost', type: 'Gradient Boosted Trees', desc: 'Fast ensemble trees, high tabular precision and regularized loss' },
                      { id: 'MLP', name: 'MLP Neural Network', type: 'PyTorch Deep Feedforward', desc: 'Multi-layer neural network with BatchNorm, ReLU and Dropout' },
                      { id: 'Autoencoder', name: 'Autoencoder Anomaly', type: 'PyTorch Reconstruction', desc: 'Unsupervised deep model trained on normal traffic baseline' },
                      { id: 'Isolation Forest', name: 'Isolation Forest', type: 'Unsupervised Tree Isolation', desc: 'Partition-based anomaly isolation with quantile scoring' },
                    ].map(m => (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => handleSelectFamily(m.id)}
                        className={`p-3.5 rounded-xl border text-left transition flex flex-col justify-between ${
                          trainFamily === m.id
                            ? 'border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50'
                            : 'border-slate-800 bg-slate-950 hover:border-slate-700 hover:bg-slate-900/60'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-sm text-white">{m.name}</span>
                            {trainFamily === m.id && (
                              <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400">
                                Active
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] text-indigo-400 block font-mono">{m.type}</span>
                          <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">{m.desc}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Step 2: Target Dataset Selector */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                    Step 2: Choose Training & Evaluation Dataset
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {[
                      { id: 'common', name: 'Common Harmonized', rows: '406k Records', desc: 'Cross-dataset transport and flow features' },
                      { id: 'nsl-kdd', name: 'NSL-KDD (Harmonized)', rows: '148k Records', desc: 'Benchmark network intrusion dataset' },
                      { id: 'unsw-nb15', name: 'UNSW-NB15 (Harmonized)', rows: '257k Records', desc: 'Modern normal and synthetic attack flows' },
                    ].map(d => (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => setTrainDataset(d.id)}
                        className={`p-3 rounded-xl border text-left transition ${
                          trainDataset === d.id
                            ? 'border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50'
                            : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                        }`}
                      >
                        <div className="font-bold text-xs text-white">{d.name}</div>
                        <div className="text-[10px] text-emerald-400 font-mono mt-0.5">{d.rows}</div>
                        <div className="text-[10px] text-slate-400 mt-1">{d.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Step 3: Target Formulation Selector */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                      Step 3: Choose Target Formulation
                    </label>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                      Target Label Encoding
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setTrainTargetType('binary')}
                      className={`p-3.5 rounded-xl border text-left transition ${
                        trainTargetType === 'binary'
                          ? 'border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50'
                          : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-xs text-white">Binary Classification</span>
                        {trainTargetType === 'binary' && (
                          <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-emerald-400 font-mono">2 Classes: Normal vs Attack</div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        Standard binary intrusion detection supported by all supervised and unsupervised models.
                      </div>
                    </button>

                    <button
                      type="button"
                      disabled={trainFamily === 'Autoencoder' || trainFamily === 'Isolation Forest'}
                      onClick={() => setTrainTargetType('multiclass')}
                      className={`p-3.5 rounded-xl border text-left transition ${
                        trainFamily === 'Autoencoder' || trainFamily === 'Isolation Forest'
                          ? 'border-slate-900 bg-slate-950/40 opacity-40 cursor-not-allowed'
                          : trainTargetType === 'multiclass'
                          ? 'border-purple-500 bg-purple-950/30 ring-1 ring-purple-500/50'
                          : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-xs text-white">Multiclass Categorization</span>
                        {trainTargetType === 'multiclass' && (
                          <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-purple-400 font-mono">7 Specific Attack Taxonomy Classes</div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {trainFamily === 'Autoencoder' || trainFamily === 'Isolation Forest'
                          ? 'Unsupervised anomaly detectors exclusively model 1-class normal baseline.'
                          : 'Deep categorization across DoS, Probe, Exploit, Brute-force, Fuzzer, Backdoor, Normal.'}
                      </div>
                    </button>
                  </div>
                </div>

                {/* Step 4: Adjustable Hyperparameters Form */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                        Step 4: Adjustable Hyperparameters ({trainFamily})
                      </label>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Customize learning rates, architecture capacity, and optimization parameters
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={resetToDefaults}
                      className="text-[11px] text-indigo-400 hover:text-indigo-300 underline font-mono"
                    >
                      Reset Defaults
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {getActiveParamDefs().map(param => (
                      <div key={param.key} className="bg-slate-950 border border-slate-800/80 rounded-xl p-3.5 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-300">{param.label}</span>
                          <span className="text-xs font-mono font-bold text-indigo-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                            {trainHyperparams[param.key] ?? param.default}
                          </span>
                        </div>
                        <input
                          type="range"
                          min={param.min}
                          max={param.max}
                          step={param.step}
                          value={trainHyperparams[param.key] ?? param.default}
                          onChange={(e) => handleParamChange(param.key, param.type === 'int' ? parseInt(e.target.value) : parseFloat(e.target.value))}
                          className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                        />
                        <div className="flex justify-between text-[10px] font-mono text-slate-500">
                          <span>Min: {param.min}</span>
                          <span>Max: {param.max}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Execution & Live Result Column */}
              <div className="space-y-6">
                {/* Active Parameters Card */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Active Parameters Payload</h3>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1.5 border-b border-slate-800">
                      <span className="text-slate-400">Architecture:</span>
                      <span className="font-bold text-white font-mono">{trainFamily}</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-800">
                      <span className="text-slate-400">Dataset Target:</span>
                      <span className="font-bold text-indigo-400 font-mono uppercase">{trainDataset}</span>
                    </div>
                    <div className="flex justify-between py-1.5 border-b border-slate-800">
                      <span className="text-slate-400">Formulation:</span>
                      <span className={`font-bold font-mono text-[11px] uppercase ${
                        trainTargetType === 'multiclass' ? 'text-purple-400' : 'text-emerald-400'
                      }`}>
                        {trainTargetType} ({trainTargetType === 'multiclass' ? '7-class' : '2-class'})
                      </span>
                    </div>
                    <div className="py-2">
                      <span className="text-slate-400 block mb-1.5 text-[11px]">Parameters Dictionary:</span>
                      <pre className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 font-mono text-[11px] text-slate-300 overflow-x-auto">
                        {JSON.stringify(trainHyperparams, null, 2)}
                      </pre>
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={isTraining}
                    onClick={startLiveTraining}
                    className={`w-full py-3 px-4 rounded-xl font-bold text-xs transition flex items-center justify-center gap-2 ${
                      isTraining
                        ? 'bg-indigo-900/60 text-indigo-300 cursor-not-allowed'
                        : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30'
                    }`}
                  >
                    {isTraining ? (
                      <>
                        <span className="inline-block w-3.5 h-3.5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin"></span>
                        <span>Training in progress ({trainingProgress?.percent || 0}%)...</span>
                      </>
                    ) : (
                      <span>Start Model Training</span>
                    )}
                  </button>

                  {/* Live Progress Bar Card */}
                  {isTraining && trainingProgress && (
                    <div className="bg-slate-950 border border-indigo-500/40 rounded-xl p-4 space-y-3 animate-fade-in shadow-lg shadow-indigo-950/40">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-indigo-300 flex items-center gap-2">
                          <span className="inline-block w-2 h-2 rounded-full bg-indigo-400 animate-ping"></span>
                          {trainingProgress.phase || 'Processing'}
                        </span>
                        <span className="font-mono text-indigo-400 font-bold text-sm">
                          {trainingProgress.percent || 0}%
                        </span>
                      </div>

                      {/* Progress Bar Track */}
                      <div className="w-full bg-slate-900 rounded-full h-3 overflow-hidden border border-slate-800 p-0.5">
                        <div
                          className="bg-gradient-to-r from-indigo-600 via-sky-500 to-emerald-400 h-full rounded-full transition-all duration-300 ease-out"
                          style={{ width: `${Math.min(100, Math.max(2, trainingProgress.percent || 0))}%` }}
                        ></div>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-400 pt-1">
                        <div>
                          <span className="text-slate-500 block text-[9px] uppercase">Elapsed Time</span>
                          <span className="text-slate-200">{trainingProgress.elapsed_seconds || 0}s</span>
                        </div>
                        <div className="text-right">
                          <span className="text-slate-500 block text-[9px] uppercase">
                            {trainingProgress.loss !== null && trainingProgress.loss !== undefined
                              ? 'Current Loss'
                              : trainingProgress.epoch
                              ? 'Epoch'
                              : 'Status'}
                          </span>
                          <span className="text-indigo-300 font-bold">
                            {trainingProgress.loss !== null && trainingProgress.loss !== undefined
                              ? trainingProgress.loss.toFixed(4)
                              : trainingProgress.epoch
                              ? `${trainingProgress.epoch} / ${trainingProgress.total_epochs || '?'}`
                              : trainingProgress.status}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {trainError && (
                    <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800 text-rose-300 text-xs">
                      Error: {trainError}
                    </div>
                  )}
                </div>

                {/* Latest Result Card */}
                {trainResult && (
                  <div className="bg-slate-900 border border-emerald-500/30 rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                        Run Completed
                      </span>
                      <span className="text-xs font-mono text-slate-400">{trainResult.elapsed_seconds}s</span>
                    </div>
                    <div className="font-bold text-sm text-white">{trainResult.model_name}</div>
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                      <div className="bg-slate-950 p-2 rounded-lg border border-slate-800">
                        <span className="text-[10px] text-slate-400 block font-sans">Accuracy</span>
                        <span className="text-emerald-400 font-bold text-base">
                          {((trainResult.kddtest_metrics?.accuracy || 0) * 100).toFixed(2)}%
                        </span>
                      </div>
                      <div className="bg-slate-950 p-2 rounded-lg border border-slate-800">
                        <span className="text-[10px] text-slate-400 block font-sans">F1-Score</span>
                        <span className="text-sky-400 font-bold text-base">
                          {(trainResult.kddtest_metrics?.f1 || 0).toFixed(4)}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setFamilyB(trainResult.family);
                        setSelectedRunIdB(`${trainResult.family.toLowerCase()}::${trainResult.run_id}`);
                        setActiveTab('models');
                      }}
                      className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold transition"
                    >
                      Compare Head-to-Head in Comparator
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Training History & Hyperparameters Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Training History & Hyperparameter Audit Log ({trainingHistory.length})
                </h3>
                <button
                  type="button"
                  onClick={fetchTrainingHistory}
                  className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
                >
                  Refresh Log
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">Family</th>
                      <th className="py-2.5 px-3">Dataset</th>
                      <th className="py-2.5 px-3">Formulation</th>
                      <th className="py-2.5 px-3">Accuracy</th>
                      <th className="py-2.5 px-3">F1-Score</th>
                      <th className="py-2.5 px-3">Elapsed</th>
                      <th className="py-2.5 px-3">Hyperparameters</th>
                      <th className="py-2.5 px-3">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80 font-mono text-[11px]">
                    {trainingHistory.length > 0 ? (
                      trainingHistory.map((h, i) => (
                        <tr key={i} className="hover:bg-slate-800/40">
                          <td className="py-2.5 px-3 font-sans">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-300">
                              {h.family}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 uppercase text-slate-400">{h.dataset}</td>
                          <td className="py-2.5 px-3 font-sans">
                            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
                              (h.target_type || 'binary') === 'multiclass'
                                ? 'border-purple-800 bg-purple-950/60 text-purple-300'
                                : 'border-slate-700 bg-slate-800/60 text-slate-400'
                            }`}>
                              {h.target_type || 'binary'}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-emerald-400 font-bold">
                            {h.accuracy ? `${(h.accuracy * 100).toFixed(2)}%` : '-'}
                          </td>
                          <td className="py-2.5 px-3 text-sky-400">
                            {h.f1 ? h.f1.toFixed(4) : '-'}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">{h.elapsed_seconds}s</td>
                          <td className="py-2.5 px-3 max-w-[280px] truncate text-slate-300" title={JSON.stringify(h.hyperparameters)}>
                            {Object.entries(h.hyperparameters || {}).map(([k, v]) => `${k}:${v}`).join(', ')}
                          </td>
                          <td className="py-2.5 px-3 text-slate-500 text-[10px] font-sans truncate max-w-[120px]">
                            {h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : '-'}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-slate-500">No training runs recorded yet. Start training above.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* 2. EDA & DISTRIBUTIONS TAB */}
        {activeTab === 'eda' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white">Exploratory Data Analysis (EDA)</h2>
                  <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                    100% Full Dataset
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">Comprehensive distributions and statistical properties across all harmonized records</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Split Filter:</span>
                <select
                  value={split}
                  onChange={(e) => setSplit(e.target.value)}
                  className="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-medium"
                >
                  {dataset === 'common' && (
                    <>
                      <option value="all">All Splits (406,190 rows)</option>
                      <option value="train">Train Split (241,051 rows)</option>
                      <option value="validation">Validation Split (60,263 rows)</option>
                      <option value="test">Test Split (104,876 rows)</option>
                    </>
                  )}
                  {dataset === 'nsl-kdd' && (
                    <>
                      <option value="all">All Splits (148,517 rows)</option>
                      <option value="train">KDDTrain (125,973 rows)</option>
                      <option value="test">KDDTest (22,544 rows)</option>
                      <option value="test-21">KDDTest-21 (11,850 rows)</option>
                    </>
                  )}
                  {dataset === 'unsw-nb15' && (
                    <>
                      <option value="all">All Splits (257,673 rows)</option>
                      <option value="train">Training Split (175,341 rows)</option>
                      <option value="test">Testing Split (82,332 rows)</option>
                    </>
                  )}
                </select>
              </div>
            </div>

            {edaLoading ? (
              <div className="py-16 text-center text-xs text-slate-500">Loading full dataset EDA analytics...</div>
            ) : edaData && !edaData.error ? (
              <div className="space-y-6">
                {/* 100% Dataset KPI Summary Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Total Processed Records</span>
                    <div className="text-xl font-bold font-mono text-white">
                      {(edaData.total_rows || edaData.total_rows_sampled || 0).toLocaleString()}
                    </div>
                    <span className="text-[10px] text-emerald-400 font-medium mt-1 inline-block">100% Verified Full Data</span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Attack Ratio</span>
                    <div className="text-xl font-bold font-mono text-rose-400">
                      {((edaData.attack_ratio || 0) * 100).toFixed(2)}%
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono mt-1 inline-block">
                      {((1 - (edaData.attack_ratio || 0)) * 100).toFixed(2)}% Normal
                    </span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Attack Categories</span>
                    <div className="text-xl font-bold font-mono text-indigo-400">
                      {(edaData.category_distribution || []).filter(c => c.category !== 'Normal').length}
                    </div>
                    <span className="text-[10px] text-slate-400 mt-1 inline-block">Harmonized Threat Types</span>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">Protocols Monitored</span>
                    <div className="text-xl font-bold font-mono text-sky-400">
                      {(edaData.protocol_distribution || []).length}
                    </div>
                    <span className="text-[10px] text-slate-400 mt-1 inline-block">L4 Transport Types</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Binary Distribution Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Normal vs Attack Ratio</h3>
                      <span className="text-[10px] font-mono text-slate-500">100% Full Count</span>
                    </div>
                    <div className="relative flex-1 min-h-[240px] flex items-center justify-center">
                      <Doughnut
                        data={{
                          labels: (edaData.binary_distribution || []).map(d => `${d.label} (${d.count.toLocaleString()})`),
                          datasets: [{
                            data: (edaData.binary_distribution || []).map(d => d.count),
                            backgroundColor: ['#10b981', '#f43f5e'],
                            borderColor: '#0f172a',
                            borderWidth: 2
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: { legend: { position: 'bottom', labels: { color: '#cbd5e1', font: { size: 11 } } } }
                        }}
                      />
                    </div>
                  </div>

                  {/* Category Breakdown Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Top Attack Categories</h3>
                      <span className="text-[10px] font-mono text-slate-500">Full Aggregation</span>
                    </div>
                    <div className="relative flex-1 min-h-[240px]">
                      <Bar
                        data={{
                          labels: (edaData.category_distribution || []).map(d => d.category),
                          datasets: [{
                            label: 'Record Count',
                            data: (edaData.category_distribution || []).map(d => d.count),
                            backgroundColor: '#6366f1',
                            borderRadius: 4
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          plugins: { legend: { display: false } },
                          scales: {
                            x: { ticks: { color: '#94a3b8', font: { size: 10 } } },
                            y: { ticks: { color: '#94a3b8', font: { size: 10 } } }
                          }
                        }}
                      />
                    </div>
                  </div>

                  {/* Protocol Breakdown Card */}
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 md:col-span-2">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">Protocol Distribution</h3>
                      <span className="text-[10px] font-mono text-slate-500">Full Aggregation</span>
                    </div>
                    <div className="relative h-64">
                      <Bar
                        data={{
                          labels: (edaData.protocol_distribution || []).map(d => d.protocol),
                          datasets: [{
                            label: 'Records',
                            data: (edaData.protocol_distribution || []).map(d => d.count),
                            backgroundColor: '#0ea5e9',
                            borderRadius: 4
                          }]
                        }}
                        options={{
                          responsive: true,
                          maintainAspectRatio: false,
                          scales: {
                            x: { ticks: { color: '#94a3b8', font: { size: 10 } } },
                            y: { ticks: { color: '#94a3b8', font: { size: 10 } } }
                          }
                        }}
                      />
                    </div>
                    <p className="text-[11px] text-slate-500 mt-3 text-right">
                      {edaData.scatter_note || "All distribution metrics and totals reflect 100% of the dataset."}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-16 text-center text-xs text-rose-400">{edaData?.error || 'No data found'}</div>
            )}
          </div>
        )}

        {/* 3. DATA CLEANSING & QUALITY TAB */}
        {activeTab === 'cleansing' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
              <h2 className="text-base font-bold text-white">Data Cleansing Quality & Audit Report</h2>
              <p className="text-xs text-slate-400 mt-0.5">Verification of missing value treatment, outlier preservation, and deduplication</p>
            </div>

            {cleansingLoading ? (
              <div className="py-16 text-center text-xs text-slate-500">Loading cleansing audit...</div>
            ) : cleansingData ? (
              <div className="space-y-6">
                {/* Quality Summary Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {Object.entries(cleansingData.quality_summary || {}).map(([key, val]) => (
                    <div key={key} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
                        {key.replace(/_/g, ' ')}
                      </span>
                      <p className="text-xs text-slate-200">{val}</p>
                    </div>
                  ))}
                </div>

                {/* Audit Table */}
                {cleansingData.audit && cleansingData.audit.length > 0 && (
                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3">Audit Details</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                          <tr>
                            {Object.keys(cleansingData.audit[0] || {}).map(k => (
                              <th key={k} className="py-2.5 px-3">{k}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/80 font-mono">
                          {cleansingData.audit.map((row, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              {Object.values(row).map((v, cidx) => (
                                <td key={cidx} className="py-2.5 px-3 text-slate-300">{String(v)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-16 text-center text-xs text-slate-500">No cleansing report available</div>
            )}
          </div>
        )}

        {/* 4. FEATURE CONTRACT TAB */}
        {activeTab === 'features' && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
              <h2 className="text-base font-bold text-white">Harmonized Feature Contract & Architecture</h2>
              <p className="text-xs text-slate-400 mt-0.5">Cross-dataset feature mappings between NSL-KDD and UNSW-NB15</p>
            </div>

            {featureLoading ? (
              <div className="py-16 text-center text-xs text-slate-500">Loading feature contract...</div>
            ) : featureData ? (
              <div className="space-y-6">
                {/* Core Candidate Features */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-3">Core Harmonized Features</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {Object.entries(featureData.contract?.candidate_features || {}).map(([name, conf]) => (
                      <div key={name} className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-1">
                        <span className="text-xs font-bold text-indigo-400 font-mono block">{name}</span>
                        <div className="text-[11px] text-slate-400">Type: <span className="text-slate-200">{conf.type}</span></div>
                        <div className="text-[10px] text-slate-500">Transform: {conf.transform}</div>
                        <div className="text-[10px] text-slate-500 mt-1">
                          Sources: NSL ({conf.sources?.['NSL-KDD']}) / UNSW ({conf.sources?.['UNSW-NB15']})
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Never Model Features / Leakage Prevention */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-rose-400 mb-2">Features Excluded from Models (Leakage Prevention)</h3>
                  <div className="flex flex-wrap gap-2">
                    {(featureData.contract?.never_model_features || []).map((f, i) => (
                      <span key={i} className="text-[11px] font-mono px-2 py-1 rounded bg-rose-950/40 text-rose-300 border border-rose-900/60">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-16 text-center text-xs text-slate-500">No feature contract loaded</div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}
