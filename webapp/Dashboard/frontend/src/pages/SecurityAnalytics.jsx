import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';

const CATEGORIES = [
  { id: 0, name: 'Normal / Benign', code: 'BENIGN', color: 'var(--green)', barColor: '#10b981', severity: 'Normal', desc: 'Legitimate network traffic without anomalous or malicious indicators' },
  { id: 1, name: 'Denial of Service (DoS)', code: 'DOS', color: 'var(--coral)', barColor: '#ef4444', severity: 'High', desc: 'Service disruption, SYN/UDP floods, and resource starvation attempts' },
  { id: 2, name: 'Reconnaissance & Probing', code: 'RECON', color: 'var(--amber)', barColor: '#f59e0b', severity: 'Medium', desc: 'Port scanning, service discovery, ping sweeps, and network mapping' },
  { id: 3, name: 'Exploits & PrivEsc', code: 'EXPLOIT', color: '#8b5cf6', barColor: '#8b5cf6', severity: 'Critical', desc: 'Known vulnerability execution, buffer overflow, and privilege escalation' },
  { id: 4, name: 'Credential Abuse (R2L)', code: 'R2L', color: '#ec4899', barColor: '#ec4899', severity: 'Critical', desc: 'Brute-force attacks, credential stuffing, and unauthorized remote login' },
  { id: 5, name: 'Malware, C2 & Botnet', code: 'MALWARE', color: '#dc2626', barColor: '#dc2626', severity: 'Critical', desc: 'Command & control callbacks, botnet coordination, and malware beacons' },
];

const TIME_PRESETS = [
  ['5', 'Last 5 min'],
  ['15', 'Last 15 min'],
  ['60', 'Last hour'],
  ['10080', 'Last 7 days'],
  ['43200', 'Last 30 days'],
  ['525600', 'Last 365 days'],
  ['', 'All time'],
  ['custom', 'Custom dates']
];

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1);
  return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 1)} ${sizes[i]}`;
}

function portService(port) {
  const p = Number(port);
  if (p === 80) return 'HTTP Web (80)';
  if (p === 443) return 'HTTPS Secure (443)';
  if (p === 53) return 'DNS Resolver (53)';
  if (p === 22) return 'SSH Remote (22)';
  if (p === 21) return 'FTP Transfer (21)';
  if (p === 25) return 'SMTP Mail (25)';
  if (p === 8080) return 'HTTP Alt (8080)';
  if (p === 8443) return 'HTTPS Alt (8443)';
  if (p === 3306) return 'MySQL DB (3306)';
  if (p === 5353) return 'mDNS (5353)';
  if (p >= 49152) return `Ephemeral (${p})`;
  return `Port ${p}`;
}

function chartCeiling(value) {
  if (value <= 1) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const factor of [1, 2, 4, 5, 8, 10]) {
    if (value <= magnitude * factor) return magnitude * factor;
  }
  return magnitude * 10;
}

function getUniformInterval(span) {
  const min = 60000;
  const hour = 3600000;
  const day = 86400000;
  if (span <= 6 * min) return 30000;       // 30 sec
  if (span <= 20 * min) return min;        // 1 min
  if (span <= 45 * min) return 2 * min;    // 2 min
  if (span <= 2 * hour) return 5 * min;    // 5 min
  if (span <= 4 * hour) return 10 * min;   // 10 min
  if (span <= 8 * hour) return 15 * min;   // 15 min
  if (span <= 16 * hour) return 30 * min;  // 30 min
  if (span <= 36 * hour) return hour;      // 1 hour
  if (span <= 3 * day) return 2 * hour;    // 2 hours
  if (span <= 7 * day) return 6 * hour;    // 6 hours
  if (span <= 14 * day) return 12 * hour;  // 12 hours
  if (span <= 60 * day) return day;        // 1 day
  return 7 * day;                          // 1 week
}

// Interactive Network Traffic Volume & Grouped Comparison Histogram (Side-by-side or Stacked)
function NetworkTrafficVolumeDistributionChart({
  flows,
  timeBounds,
  timeRangeLabel,
  selectedBin,
  selectedBinLabel,
  selectedCategory,
  selectedCategoryName,
  selectedIp,
  selectedProto,
  selectedPort,
  decisionFilter,
  onSelectBin,
  onSelectCategory,
  onSelectProto,
  onSelectDecision
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [hoverInfo, setHoverInfo] = useState(null);
  const geometryRef = useRef(null);

  // Consolidated view mode (Side-by-side comparison):
  // 'health' (Normal vs Attacks) | 'attacks' (Attack Types breakdown) | 'bandwidth' (Data size in KB) | 'protocols' (TCP / UDP)
  const [viewMode, setViewMode] = useState('health');
  const metricMode = viewMode === 'bandwidth' ? 'bandwidth' : 'flows';
  const groupMode = viewMode === 'protocols' ? 'protocol' : (viewMode === 'attacks' ? 'attacks' : 'health');
  const barLayout = 'sideBySide';

  // Discover which categories have active flows in the dataset
  const activeCatIds = useMemo(() => {
    const set = new Set();
    flows.forEach(flow => {
      const isAttack = flow.kind === 'flag' || (flow.prediction && flow.prediction.flagged) || (typeof flow.binary_score === 'number' && flow.binary_score >= (flow.threshold_used || 0.41));
      const catId = flow.prediction && typeof flow.prediction.class_id === 'number'
        ? flow.prediction.class_id
        : (flow.category_id !== undefined ? flow.category_id : (isAttack ? 2 : 0));
      set.add(catId);
    });
    return Array.from(set).sort((a, b) => a - b);
  }, [flows]);

  const renderCanvas = useCallback((activeBinIndex = -1) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight || 240;
    if (!width || !height) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const isDark = document.documentElement.dataset.theme === 'dark';
    const grid = isDark ? '#2a354d' : '#e6ebf3';
    const chartText = isDark ? '#94a3b8' : '#64748b';

    const left = metricMode === 'bandwidth' ? 76 : 58;
    const right = width - 18;
    const top = 22; // room for data label values above bars
    const bottom = height - 26;
    const chartHeight = bottom - top;
    const chartWidth = right - left;

    const from = timeBounds.start;
    const end = timeBounds.end;
    const span = Math.max(60000, end - from);
    const interval = getUniformInterval(span);
    const offset = 7 * 3600000;
    const start = Math.floor((from + offset) / interval) * interval - offset;
    const count = Math.max(2, Math.ceil((end - start + 1) / interval));

    const bins = Array.from({ length: count }, (_, i) => ({
      time: start + i * interval,
      total: 0,
      flags: 0,
      bytes: 0,
      packets: 0,
      cleanFlows: 0,
      threatFlows: 0,
      cleanBytes: 0,
      threatBytes: 0,
      tcpFlows: 0,
      tcpBytes: 0,
      udpFlows: 0,
      udpBytes: 0,
      icmpFlows: 0,
      icmpBytes: 0,
      catFlows: { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 },
      catBytes: { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
    }));

    flows.forEach(flow => {
      const idx = Math.floor(((flow.timestamp || 0) - start) / interval);
      if (bins[idx]) {
        const isAttack = flow.kind === 'flag' || (flow.prediction && flow.prediction.flagged) || (typeof flow.binary_score === 'number' && flow.binary_score >= (flow.threshold_used || 0.41));
        const catId = flow.prediction && typeof flow.prediction.class_id === 'number'
          ? flow.prediction.class_id
          : (flow.category_id !== undefined ? flow.category_id : (isAttack ? 2 : 0));
        const fBytes = Number(flow.bytes ?? ((flow.bytes_forward || 0) + (flow.bytes_backward || 0)) ?? flow.raw?.bytes_forward ?? 0);
        const fPkts = Number(flow.packets ?? ((flow.packets_forward || 0) + (flow.packets_backward || 0)) ?? 1);
        const proto = (flow.transport_protocol || flow.protocol || flow.raw?.protocol || 'other').toLowerCase();

        bins[idx].total++;
        bins[idx].bytes += fBytes;
        bins[idx].packets += fPkts;

        if (bins[idx].catFlows[catId] !== undefined) {
          bins[idx].catFlows[catId]++;
          bins[idx].catBytes[catId] += fBytes;
        }

        if (isAttack) {
          bins[idx].flags++;
          bins[idx].threatFlows++;
          bins[idx].threatBytes += fBytes;
        } else {
          bins[idx].cleanFlows++;
          bins[idx].cleanBytes += fBytes;
        }

        if (proto === 'tcp') {
          bins[idx].tcpFlows++;
          bins[idx].tcpBytes += fBytes;
        } else if (proto === 'udp') {
          bins[idx].udpFlows++;
          bins[idx].udpBytes += fBytes;
        } else if (proto === 'icmp') {
          bins[idx].icmpFlows++;
          bins[idx].icmpBytes += fBytes;
        }
      }
    });

    // Calculate maximum value for Y-axis scale
    let maxVal = 1;
    if (barLayout === 'sideBySide') {
      if (groupMode === 'health') {
        maxVal = Math.max(
          ...bins.flatMap(b => (metricMode === 'bandwidth' ? [b.cleanBytes, b.threatBytes] : [b.cleanFlows, b.threatFlows])),
          1
        );
      } else if (groupMode === 'attacks') {
        maxVal = Math.max(
          ...bins.flatMap(b => activeCatIds.map(cId => (metricMode === 'bandwidth' ? b.catBytes[cId] : b.catFlows[cId]))),
          1
        );
      } else {
        maxVal = Math.max(
          ...bins.flatMap(b => (metricMode === 'bandwidth' ? [b.tcpBytes, b.udpBytes, b.icmpBytes] : [b.tcpFlows, b.udpFlows, b.icmpFlows])),
          1
        );
      }
    } else {
      maxVal = Math.max(
        ...bins.map(b => (metricMode === 'bandwidth' ? b.bytes : b.total)),
        1
      );
    }
    const cap = chartCeiling(maxVal);

    // Slot sizing
    const slotWidth = chartWidth / count;

    ctx.font = '11px Segoe UI, -apple-system, sans-serif';

    // Grid lines & Y-axis labels
    const gridTics = [0, 0.5, 1];
    gridTics.forEach(pct => {
      const y = Math.round(bottom - chartHeight * pct);
      const val = cap * pct;

      ctx.strokeStyle = grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();

      ctx.fillStyle = chartText;
      ctx.textAlign = 'right';
      const label = metricMode === 'bandwidth' ? formatBytes(val) : String(Math.round(val));
      ctx.fillText(label, left - 8, y + 4);
    });

    // Determine target index to highlight
    let highlightIndex = activeBinIndex;
    if (highlightIndex === -1 && selectedBin !== null) {
      highlightIndex = bins.findIndex(b => b.time === selectedBin);
    }

    // Helper to draw a rounded rectangle
    const roundRect = (rx, ry, rw, rh, rad, fill) => {
      if (rh <= 0 || rw <= 0) return;
      ctx.fillStyle = fill;
      ctx.beginPath();
      const r = Math.min(rad, rh / 2, rw / 2);
      ctx.moveTo(rx + r, ry);
      ctx.lineTo(rx + rw - r, ry);
      ctx.quadraticCurveTo(rx + rw, ry, rx + rw, ry + r);
      ctx.lineTo(rx + rw, ry + rh);
      ctx.lineTo(rx, ry + rh);
      ctx.lineTo(rx, ry + r);
      ctx.quadraticCurveTo(rx, ry, rx + r, ry);
      ctx.closePath();
      ctx.fill();
    };

    // Draw bars
    bins.forEach((bin, i) => {
      const cx = left + i * slotWidth + slotWidth / 2;
      const isHighlighted = highlightIndex === i;

      // Draw background column for selected or hovered slot
      if (isHighlighted) {
        ctx.fillStyle = isDark ? 'rgba(99, 102, 241, 0.14)' : 'rgba(99, 102, 241, 0.08)';
        ctx.fillRect(left + i * slotWidth, top - 6, slotWidth, chartHeight + 6);

        // Vertical dashed guideline
        ctx.strokeStyle = isDark ? '#818cf8' : '#6366f1';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.setLineDash([3, 3]);
        ctx.moveTo(cx, top - 6);
        ctx.lineTo(cx, bottom);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (barLayout === 'sideBySide') {
        // ==========================================
        // SIDE-BY-SIDE (CLUSTERED / SEPARATE BARS)
        // ==========================================
        if (groupMode === 'health') {
          // 2 BARS SIDE BY SIDE: Clean (Green) vs Threat (Red)
          const cleanVal = metricMode === 'bandwidth' ? bin.cleanBytes : bin.cleanFlows;
          const threatVal = metricMode === 'bandwidth' ? bin.threatBytes : bin.threatFlows;
          const cleanH = (cleanVal / cap) * chartHeight;
          const threatH = (threatVal / cap) * chartHeight;

          const groupW = Math.min(68, slotWidth * 0.82);
          const barW = Math.max(7, Math.floor((groupW - 4) / 2));
          const xClean = cx - barW - 2;
          const xThreat = cx + 2;

          // Bar 1: Clean Traffic (Green)
          if (cleanH > 0) {
            const y1 = bottom - cleanH;
            roundRect(xClean, y1, barW, cleanH, 4, isDark ? '#10b981' : '#059669');

            // Direct data value on top of bar for instant readability
            if (barW >= 9 && cleanH >= 8) {
              ctx.fillStyle = isDark ? '#a7f3d0' : '#047857';
              ctx.textAlign = 'center';
              ctx.font = 'bold 10px Segoe UI, sans-serif';
              const cleanText = metricMode === 'bandwidth' ? formatBytes(cleanVal) : String(cleanVal);
              ctx.fillText(cleanText, xClean + barW / 2, y1 - 4);
            }
          }

          // Bar 2: Flagged Threat (Red)
          if (threatH > 0) {
            const y2 = bottom - threatH;
            roundRect(xThreat, y2, barW, threatH, 4, isDark ? '#ef4444' : '#dc2626');

            // Direct data value on top of bar for instant readability
            if (barW >= 9 && threatH >= 8) {
              ctx.fillStyle = isDark ? '#fecaca' : '#b91c1c';
              ctx.textAlign = 'center';
              ctx.font = 'bold 10px Segoe UI, sans-serif';
              const threatText = metricMode === 'bandwidth' ? formatBytes(threatVal) : String(threatVal);
              ctx.fillText(threatText, xThreat + barW / 2, y2 - 4);
            }
          }

          // If selected/highlighted, outline the group
          if (isHighlighted && (cleanH > 0 || threatH > 0)) {
            const topY = Math.min(bottom - cleanH, bottom - threatH) - 18;
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(xClean - 3, topY, barW * 2 + 10, bottom - topY);
          }
        } else if (groupMode === 'attacks') {
          // BARS FOR EACH ACTIVE ATTACK CATEGORY
          const catCount = Math.max(1, activeCatIds.length);
          const groupW = Math.min(88, slotWidth * 0.88);
          const barW = Math.max(5, Math.floor((groupW - (catCount - 1) * 2) / catCount));
          const startX = cx - (catCount * barW + (catCount - 1) * 2) / 2;

          let hasAny = false;
          let minTop = bottom;

          activeCatIds.forEach((cId, cIdx) => {
            const catMeta = CATEGORIES[cId] || { name: `Cat ${cId}`, barColor: '#ef4444' };
            const val = metricMode === 'bandwidth' ? bin.catBytes[cId] : bin.catFlows[cId];
            const h = (val / cap) * chartHeight;
            const bx = startX + cIdx * (barW + 2);

            if (h > 0) {
              hasAny = true;
              const y = bottom - h;
              minTop = Math.min(minTop, y);
              roundRect(bx, y, barW, h, 3, catMeta.barColor || catMeta.color || '#ef4444');

              if (barW >= 8 && h >= 8) {
                ctx.fillStyle = isDark ? '#f8fafc' : '#1e293b';
                ctx.textAlign = 'center';
                ctx.font = 'bold 9px Segoe UI, sans-serif';
                ctx.fillText(metricMode === 'bandwidth' ? formatBytes(val) : String(val), bx + barW / 2, y - 4);
              }
            }
          });

          if (isHighlighted && hasAny) {
            const topY = minTop - 18;
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(startX - 2, topY, catCount * barW + (catCount - 1) * 2 + 4, bottom - topY);
          }
        } else {
          // 3 BARS SIDE BY SIDE: TCP, UDP, ICMP
          const tcpVal = metricMode === 'bandwidth' ? bin.tcpBytes : bin.tcpFlows;
          const udpVal = metricMode === 'bandwidth' ? bin.udpBytes : bin.udpFlows;
          const icmpVal = metricMode === 'bandwidth' ? bin.icmpBytes : bin.icmpFlows;

          const tcpH = (tcpVal / cap) * chartHeight;
          const udpH = (udpVal / cap) * chartHeight;
          const icmpH = (icmpVal / cap) * chartHeight;

          const groupW = Math.min(76, slotWidth * 0.88);
          const barW = Math.max(5, Math.floor((groupW - 6) / 3));
          const xTcp = cx - barW * 1.5 - 2;
          const xUdp = cx - barW / 2;
          const xIcmp = cx + barW / 2 + 2;

          if (tcpH > 0) {
            const y = bottom - tcpH;
            roundRect(xTcp, y, barW, tcpH, 3, '#6366f1');
            if (barW >= 9 && tcpH >= 8) {
              ctx.fillStyle = '#c7d2fe';
              ctx.textAlign = 'center';
              ctx.font = 'bold 9px Segoe UI, sans-serif';
              ctx.fillText(metricMode === 'bandwidth' ? formatBytes(tcpVal) : String(tcpVal), xTcp + barW / 2, y - 4);
            }
          }
          if (udpH > 0) {
            const y = bottom - udpH;
            roundRect(xUdp, y, barW, udpH, 3, '#a855f7');
            if (barW >= 9 && udpH >= 8) {
              ctx.fillStyle = '#e9d5ff';
              ctx.textAlign = 'center';
              ctx.font = 'bold 9px Segoe UI, sans-serif';
              ctx.fillText(metricMode === 'bandwidth' ? formatBytes(udpVal) : String(udpVal), xUdp + barW / 2, y - 4);
            }
          }
          if (icmpH > 0) {
            const y = bottom - icmpH;
            roundRect(xIcmp, y, barW, icmpH, 3, '#06b6d4');
            if (barW >= 9 && icmpH >= 8) {
              ctx.fillStyle = '#a5f3fc';
              ctx.textAlign = 'center';
              ctx.font = 'bold 9px Segoe UI, sans-serif';
              ctx.fillText(metricMode === 'bandwidth' ? formatBytes(icmpVal) : String(icmpVal), xIcmp + barW / 2, y - 4);
            }
          }

          if (isHighlighted && (tcpH > 0 || udpH > 0 || icmpH > 0)) {
            const topY = Math.min(bottom - tcpH, bottom - udpH, bottom - icmpH) - 18;
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(xTcp - 3, topY, barW * 3 + 10, bottom - topY);
          }
        }
      } else {
        // ==========================================
        // STACKED BARS
        // ==========================================
        const barWidth = Math.max(6, Math.min(32, slotWidth * 0.68));
        const bx = cx - barWidth / 2;
        let currentBottom = bottom;

        if (groupMode === 'health') {
          const cleanVal = metricMode === 'bandwidth' ? bin.cleanBytes : bin.cleanFlows;
          const threatVal = metricMode === 'bandwidth' ? bin.threatBytes : bin.threatFlows;
          const cleanH = (cleanVal / cap) * chartHeight;
          const threatH = (threatVal / cap) * chartHeight;

          if (cleanH > 0) {
            const cy = currentBottom - cleanH;
            const isTop = threatH <= 0;
            if (isTop) roundRect(bx, cy, barWidth, cleanH, 4, isDark ? '#10b981' : '#059669');
            else {
              ctx.fillStyle = isDark ? '#10b981' : '#059669';
              ctx.fillRect(bx, cy, barWidth, cleanH);
            }
            currentBottom = cy;
          }

          if (threatH > 0) {
            const ty = currentBottom - threatH;
            roundRect(bx, ty, barWidth, threatH, 4, isDark ? '#ef4444' : '#dc2626');
            currentBottom = ty;
          }
        } else {
          const tcpVal = metricMode === 'bandwidth' ? bin.tcpBytes : bin.tcpFlows;
          const udpVal = metricMode === 'bandwidth' ? bin.udpBytes : bin.udpFlows;
          const icmpVal = metricMode === 'bandwidth' ? bin.icmpBytes : bin.icmpFlows;

          const tcpH = (tcpVal / cap) * chartHeight;
          const udpH = (udpVal / cap) * chartHeight;
          const icmpH = (icmpVal / cap) * chartHeight;

          if (tcpH > 0) {
            const y = currentBottom - tcpH;
            const isTop = udpH <= 0 && icmpH <= 0;
            if (isTop) roundRect(bx, y, barWidth, tcpH, 4, '#6366f1');
            else {
              ctx.fillStyle = '#6366f1';
              ctx.fillRect(bx, y, barWidth, tcpH);
            }
            currentBottom = y;
          }

          if (udpH > 0) {
            const y = currentBottom - udpH;
            const isTop = icmpH <= 0;
            if (isTop) roundRect(bx, y, barWidth, udpH, 4, '#a855f7');
            else {
              ctx.fillStyle = '#a855f7';
              ctx.fillRect(bx, y, barWidth, udpH);
            }
            currentBottom = y;
          }

          if (icmpH > 0) {
            const y = currentBottom - icmpH;
            roundRect(bx, y, barWidth, icmpH, 4, '#06b6d4');
            currentBottom = y;
          }
        }

        if (isHighlighted && (bin.total > 0 || bin.bytes > 0)) {
          ctx.strokeStyle = '#fff';
          ctx.lineWidth = 1.5;
          ctx.strokeRect(bx - 2, currentBottom - 2, barWidth + 4, bottom - currentBottom + 2);
        }
      }
    });

    // Time Axis Labels with uniform stepping
    ctx.fillStyle = chartText;
    ctx.textAlign = 'center';
    const maxLabels = width > 520 ? 8 : (width > 380 ? 6 : 4);
    const binStep = Math.max(1, Math.ceil(count / maxLabels));
    for (let idx = 0; idx < count; idx += binStep) {
      const bin = bins[idx];
      if (bin) {
        const d = new Date(bin.time);
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        const cx = left + idx * slotWidth + slotWidth / 2;
        ctx.fillText(`${hours}:${minutes}`, cx, height - 8);

        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx, bottom);
        ctx.lineTo(cx, bottom + 4);
        ctx.stroke();
      }
    }

    geometryRef.current = { bins, interval, left, right, slotWidth, count, height, width };
  }, [flows, timeBounds, selectedBin, barLayout, metricMode, groupMode, activeCatIds]);

  useEffect(() => {
    renderCanvas();
    const handleResize = () => renderCanvas();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderCanvas]);

  const handlePointerMove = e => {
    const geo = geometryRef.current;
    if (!geo) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    if (mouseX < geo.left || mouseX > geo.right) {
      setHoverInfo(null);
      renderCanvas(-1);
      return;
    }
    const idx = Math.max(0, Math.min(geo.bins.length - 1, Math.floor((mouseX - geo.left) / geo.slotWidth)));
    const bin = geo.bins[idx];
    if (bin) {
      const d1 = new Date(bin.time);
      const d2 = new Date(bin.time + geo.interval);
      const fmt = d => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      const alertPct = bin.total ? ((bin.flags / bin.total) * 100).toFixed(1) : '0.0';
      const cleanPct = bin.total ? ((bin.cleanFlows / bin.total) * 100).toFixed(1) : '0.0';
      const cx = geo.left + idx * geo.slotWidth + geo.slotWidth / 2;

      // Attack breakdown for this time slice
      const attackBreakdown = [];
      if (bin.threatFlows > 0) {
        Object.entries(bin.catFlows).forEach(([cId, count]) => {
          const cidNum = Number(cId);
          if (cidNum > 0 && count > 0) {
            const catMeta = CATEGORIES[cidNum] || { name: `Attack (${cidNum})`, color: '#ef4444' };
            const pct = ((count / bin.threatFlows) * 100).toFixed(0);
            attackBreakdown.push({
              id: cidNum,
              name: catMeta.name,
              code: catMeta.code,
              color: catMeta.barColor || catMeta.color || '#ef4444',
              flows: count,
              pct,
              bytes: bin.catBytes[cidNum] || 0
            });
          }
        });
      }

      setHoverInfo({
        x: cx,
        time: `${fmt(d1)}–${fmt(d2)}`,
        flows: bin.total,
        alerts: bin.flags,
        cleanFlows: bin.cleanFlows,
        threatFlows: bin.threatFlows,
        bytes: bin.bytes,
        cleanBytes: bin.cleanBytes,
        threatBytes: bin.threatBytes,
        packets: bin.packets,
        tcpFlows: bin.tcpFlows,
        udpFlows: bin.udpFlows,
        icmpFlows: bin.icmpFlows,
        cleanPct,
        alertPct,
        attackBreakdown,
        catFlows: bin.catFlows,
        binIndex: idx,
        binStart: bin.time,
        binEnd: bin.time + geo.interval
      });
      renderCanvas(idx);
    }
  };

  const handlePointerLeave = () => {
    setHoverInfo(null);
    renderCanvas(-1);
  };

  const handleClick = () => {
    if (hoverInfo && onSelectBin) {
      onSelectBin({
        start: hoverInfo.binStart,
        end: hoverInfo.binEnd,
        label: hoverInfo.time
      });
    }
  };

  return (
    <div className="panel panel-pad" style={{ marginBottom: 14 }}>
      <div className="panel-head" style={{ alignItems: 'flex-start' }}>
        <div>
          <h2>
            <span className="ui-symbol">∿</span> Network Traffic Timeline & Comparison
          </h2>
          <p style={{ marginTop: 2 }}>
            {timeRangeLabel} · ICT
            {selectedCategoryName && <span> · Category: <strong>{selectedCategoryName}</strong></span>}
            {selectedIp && <span> · Device: <strong>{selectedIp}</strong></span>}
            {selectedProto && <span> · Protocol: <strong style={{ textTransform: 'uppercase' }}>{selectedProto}</strong></span>}
            {selectedPort && <span> · Port: <strong>{selectedPort}</strong></span>}
            {decisionFilter === 'attack' && <span> · Scope: <strong>Attacks only</strong></span>}
            {decisionFilter === 'normal' && <span> · Scope: <strong>Normal only</strong></span>}
            {selectedBinLabel && <span> · Active Window: <strong>{selectedBinLabel}</strong></span>}
          </p>
        </div>

        {/* Consolidated View Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 6, padding: 2 }}>
            <button
              type="button"
              className={`btn period ${viewMode === 'health' ? 'selected' : ''}`}
              style={{ fontSize: 11, padding: '3px 10px', border: 0 }}
              onClick={() => setViewMode('health')}
              title="Compare Normal vs Attack traffic side-by-side"
            >
              Normal vs Attacks
            </button>
            <button
              type="button"
              className={`btn period ${viewMode === 'attacks' ? 'selected' : ''}`}
              style={{ fontSize: 11, padding: '3px 10px', border: 0 }}
              onClick={() => setViewMode('attacks')}
              title="View traffic broken down by specific Attack Types (DoS, Recon, Exploits, etc.)"
            >
              Attack Types
            </button>
            <button
              type="button"
              className={`btn period ${viewMode === 'bandwidth' ? 'selected' : ''}`}
              style={{ fontSize: 11, padding: '3px 10px', border: 0 }}
              onClick={() => setViewMode('bandwidth')}
              title="Compare data volume in KB side-by-side"
            >
              Data Size (KB)
            </button>
            <button
              type="button"
              className={`btn period ${viewMode === 'protocols' ? 'selected' : ''}`}
              style={{ fontSize: 11, padding: '3px 10px', border: 0 }}
              onClick={() => setViewMode('protocols')}
              title="Compare network protocols (TCP, UDP, ICMP) side-by-side"
            >
              Protocols (TCP / UDP)
            </button>
          </div>

          {selectedBinLabel && (
            <button
              type="button"
              className="text-button"
              onClick={() => onSelectBin(null)}
              style={{ fontSize: 12, color: 'var(--coral)' }}
            >
              Clear time window ✕
            </button>
          )}

          <span className="badge normal" style={{ fontSize: 11 }}>
            {flows.length} connections graphed
          </span>
        </div>
      </div>

      <div
        ref={containerRef}
        style={{ position: 'relative', width: '100%', height: 240, marginTop: 12, cursor: 'pointer' }}
        onMouseMove={handlePointerMove}
        onMouseLeave={handlePointerLeave}
        onClick={handleClick}
        title="Click any time bar to cross-filter the dashboard"
      >
        <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />

        {hoverInfo && (
          <div
            style={{
              position: 'absolute',
              left: hoverInfo.x < (geometryRef.current?.width || 300) / 2
                ? Math.min((geometryRef.current?.width || 300) - 250, hoverInfo.x + 18)
                : Math.max(10, hoverInfo.x - 245),
              top: 12,
              background: 'rgba(15, 23, 42, 0.96)',
              border: '1px solid rgba(148, 163, 184, 0.28)',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
              color: '#f8fafc',
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: 11,
              pointerEvents: 'none',
              zIndex: 10,
              minWidth: 230
            }}
          >
            <div style={{ fontWeight: 650, marginBottom: 6, color: '#ffffff', display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.12)', paddingBottom: 4 }}>
              <span>{hoverInfo.time}</span>
              <span style={{ fontSize: 9, opacity: 0.85, letterSpacing: '0.04em', color: '#818cf8' }}>CLICK TO FILTER</span>
            </div>

            <div style={{ color: '#93c5fd', display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 2 }}>
              <span>Total Volume:</span>
              <strong>{hoverInfo.flows} flows ({formatBytes(hoverInfo.bytes)})</strong>
            </div>

            <div style={{ color: '#cbd5e1', display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 5 }}>
              <span>Packets:</span>
              <strong>{hoverInfo.packets.toLocaleString()} pkts</strong>
            </div>

            {/* Health / Decision Ratio Cards */}
            {groupMode !== 'protocol' ? (
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 5, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: 5, padding: '4px 6px' }}>
                  <div style={{ color: '#6ee7b7', fontSize: 10, fontWeight: 600 }}>✓ Normal Traffic</div>
                  <strong style={{ fontSize: 13, color: '#ffffff' }}>{hoverInfo.cleanFlows}</strong>
                  <div style={{ fontSize: 10, color: '#a7f3d0' }}>({hoverInfo.cleanPct}%)</div>
                </div>
                <div style={{ background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 5, padding: '4px 6px' }}>
                  <div style={{ color: '#fca5a5', fontSize: 10, fontWeight: 600 }}>⚑ Attacks</div>
                  <strong style={{ fontSize: 13, color: '#ffffff' }}>{hoverInfo.threatFlows}</strong>
                  <div style={{ fontSize: 10, color: '#fecaca' }}>({hoverInfo.alertPct}%)</div>
                </div>
              </div>
            ) : (
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 5, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div style={{ color: '#a5b4fc', display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span>TCP:</span>
                  <strong>{hoverInfo.tcpFlows} flows</strong>
                </div>
                <div style={{ color: '#d8b4fe', display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span>UDP:</span>
                  <strong>{hoverInfo.udpFlows} flows</strong>
                </div>
                <div style={{ color: '#67e8f9', display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span>ICMP:</span>
                  <strong>{hoverInfo.icmpFlows} flows</strong>
                </div>
              </div>
            )}

            {/* Attack Types Breakdown */}
            {hoverInfo.threatFlows > 0 && hoverInfo.attackBreakdown?.length > 0 && (
              <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.12)' }}>
                <div style={{ fontSize: 10, color: '#fca5a5', fontWeight: 650, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span>⚡ Detected Attack Types:</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {hoverInfo.attackBreakdown.map(atk => (
                    <div
                      key={atk.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: 'rgba(239, 68, 68, 0.12)',
                        padding: '3px 8px',
                        borderRadius: 4,
                        border: '1px solid rgba(239, 68, 68, 0.25)'
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10.5, color: '#f8fafc' }}>
                        <span style={{ width: 7, height: 7, borderRadius: '50%', background: atk.color, display: 'inline-block', flexShrink: 0 }} />
                        {atk.name}
                      </span>
                      <strong style={{ fontSize: 10.5, color: atk.color }}>
                        {atk.flows} ({atk.pct}%)
                      </strong>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Legend & Help Text */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, fontSize: 11, color: 'var(--muted)', flexWrap: 'wrap', gap: 8 }}>
        <span>
          Side-by-side bars for direct comparison. Click any bar to isolate its time window across the dashboard.
        </span>

        {viewMode === 'attacks' ? (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {activeCatIds.map(cId => {
              const cat = CATEGORIES[cId] || { name: `Cat ${cId}`, barColor: '#ef4444' };
              return (
                <span
                  key={cId}
                  onClick={() => onSelectCategory && onSelectCategory(selectedCategory === cId ? null : cId)}
                  style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', opacity: selectedCategory !== null && selectedCategory !== cId ? 0.35 : 1 }}
                  title={`Click to filter ${cat.name}`}
                >
                  <i style={{ width: 10, height: 10, borderRadius: 2, background: cat.barColor || cat.color, display: 'inline-block' }} />
                  <strong>{cat.name}</strong>
                </span>
              );
            })}
          </div>
        ) : groupMode === 'health' ? (
          <div style={{ display: 'flex', gap: 14 }}>
            <span
              onClick={() => onSelectDecision && onSelectDecision(decisionFilter === 'normal' ? 'all' : 'normal')}
              style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', opacity: decisionFilter === 'attack' ? 0.35 : 1 }}
              title="Click to filter Normal traffic"
            >
              <i style={{ width: 11, height: 11, borderRadius: 2, background: '#10b981', display: 'inline-block' }} /> <strong>Normal</strong> (Green)
            </span>
            <span
              onClick={() => onSelectDecision && onSelectDecision(decisionFilter === 'attack' ? 'all' : 'attack')}
              style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', opacity: decisionFilter === 'normal' ? 0.35 : 1 }}
              title="Click to filter Attacks"
            >
              <i style={{ width: 11, height: 11, borderRadius: 2, background: '#ef4444', display: 'inline-block' }} /> <strong>Attacks</strong> (Red)
            </span>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 14 }}>
            <span
              onClick={() => onSelectProto && onSelectProto(selectedProto === 'tcp' ? null : 'tcp')}
              style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', opacity: selectedProto && selectedProto !== 'tcp' ? 0.35 : 1 }}
              title="Click to filter TCP"
            >
              <i style={{ width: 10, height: 10, borderRadius: 2, background: '#6366f1', display: 'inline-block' }} /> TCP
            </span>
            <span
              onClick={() => onSelectProto && onSelectProto(selectedProto === 'udp' ? null : 'udp')}
              style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', opacity: selectedProto && selectedProto !== 'udp' ? 0.35 : 1 }}
              title="Click to filter UDP"
            >
              <i style={{ width: 10, height: 10, borderRadius: 2, background: '#a855f7', display: 'inline-block' }} /> UDP
            </span>
            <span
              onClick={() => onSelectProto && onSelectProto(selectedProto === 'icmp' ? null : 'icmp')}
              style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', opacity: selectedProto && selectedProto !== 'icmp' ? 0.35 : 1 }}
              title="Click to filter ICMP"
            >
              <i style={{ width: 10, height: 10, borderRadius: 2, background: '#06b6d4', display: 'inline-block' }} /> ICMP
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function SecurityAnalytics({
  flows = [],
  description = '',
  pageTitle = '',
  embedded = false,
  filters = {},
  presets = []
}) {
  // Time preset state - synchronized with Live Monitor filters
  const [timePreset, setTimePreset] = useState(filters?.range ?? '');
  useEffect(() => {
    if (filters?.range !== undefined) {
      setTimePreset(filters.range);
    }
  }, [filters?.range]);

  // Custom date/time range state
  const [customFromDate, setCustomFromDate] = useState(() => (filters?.from ? filters.from.split('T')[0] : '2026-11-26'));
  const [customFromTime, setCustomFromTime] = useState(() => (filters?.from_time || (filters?.from && filters.from.includes('T') ? filters.from.split('T')[1].slice(0, 5) : '00:00')));
  const [customToDate, setCustomToDate] = useState(() => (filters?.to ? filters.to.split('T')[0] : '2026-11-26'));
  const [customToTime, setCustomToTime] = useState(() => (filters?.to_time || (filters?.to && filters.to.includes('T') ? filters.to.split('T')[1].slice(0, 5) : '23:59')));

  useEffect(() => {
    if (filters?.from !== undefined) {
      setCustomFromDate(filters.from ? filters.from.split('T')[0] : '');
      if (filters.from && filters.from.includes('T')) setCustomFromTime(filters.from.split('T')[1].slice(0, 5));
    }
    if (filters?.from_time !== undefined) setCustomFromTime(filters.from_time);
    if (filters?.to !== undefined) {
      setCustomToDate(filters.to ? filters.to.split('T')[0] : '');
      if (filters.to && filters.to.includes('T')) setCustomToTime(filters.to.split('T')[1].slice(0, 5));
    }
    if (filters?.to_time !== undefined) setCustomToTime(filters.to_time);
  }, [filters?.from, filters?.to, filters?.from_time, filters?.to_time]);

  // Interactive cross-filter states
  const [selectedCategory, setSelectedCategory] = useState(null); // catId or null
  const [selectedIp, setSelectedIp] = useState(null); // string IP or null
  const [selectedProto, setSelectedProto] = useState(null); // 'tcp' | 'udp' | 'icmp' or null
  const [selectedPort, setSelectedPort] = useState(null); // port number or null
  const [decisionFilter, setDecisionFilter] = useState('all'); // 'all', 'attack', 'normal'
  const [selectedBinRange, setSelectedBinRange] = useState(null); // { start, end, label } or null
  const [talkerFilterMode, setTalkerFilterMode] = useState('all'); // 'all' or 'attacks'

  // 1. Time bounds calculation
  const timeBounds = useMemo(() => {
    const timestamps = flows.map(f => f.timestamp || 0).filter(Boolean);
    const latest = Math.max(...timestamps, 0);
    const first = Math.min(...timestamps, latest || Date.now());

    if (timePreset === 'custom') {
      const fDate = customFromDate || '2026-11-26';
      const fTime = customFromTime || '00:00';
      const tDate = customToDate || customFromDate || '2026-11-26';
      const tTime = customToTime || '23:59';
      const start = new Date(`${fDate}T${fTime}:00+07:00`).getTime();
      const end = new Date(`${tDate}T${tTime}:59+07:00`).getTime();
      return {
        start: isNaN(start) ? first : start,
        end: isNaN(end) ? (latest || Date.now()) : end
      };
    }
    if (timePreset && timePreset !== '') {
      const mins = Number(timePreset);
      if (!isNaN(mins) && mins > 0) {
        // If data is recent within the window, use Date.now(), otherwise use latest recorded timestamp
        const anchor = (Date.now() - latest < mins * 60000) ? Date.now() : latest;
        return { start: anchor - mins * 60000, end: anchor };
      }
    }
    // All time: Bound to actual flow timestamps so intervals are evenly distributed across observed activity
    return { start: first, end: latest };
  }, [flows, timePreset, customFromDate, customFromTime, customToDate, customToTime]);

  // Label for time range
  const timeRangeLabel = useMemo(() => {
    if (timePreset === 'custom') {
      const fTime = customFromTime ? ` ${customFromTime}` : '';
      const tTime = customToTime ? ` ${customToTime}` : '';
      return `${customFromDate || 'Start'}${fTime} to ${customToDate || 'End'}${tTime}`;
    }
    const availablePresets = presets.length ? presets : TIME_PRESETS;
    const match = availablePresets.find(([val]) => val === timePreset);
    return match ? match[1] : 'All time';
  }, [timePreset, customFromDate, customFromTime, customToDate, customToTime, presets]);

  // 2. Base time-filtered flows
  const timeFilteredFlows = useMemo(() => {
    if (!flows.length) return [];
    return flows.filter(f => {
      const ts = f.timestamp || 0;
      return ts >= timeBounds.start && ts <= timeBounds.end;
    });
  }, [flows, timeBounds]);

  // 3. Flows for Trend Chart (filtered by Category, IP, Proto, Port, Decision, but NOT by selected time bin)
  const flowsForTrend = useMemo(() => {
    return timeFilteredFlows.filter(flow => {
      const isAttack = flow.kind === 'flag' || (flow.prediction && flow.prediction.flagged);
      const catId = flow.prediction && typeof flow.prediction.class_id === 'number'
        ? flow.prediction.class_id
        : (isAttack ? 2 : 0);

      if (selectedCategory !== null && catId !== selectedCategory) return false;
      if (selectedIp !== null && flow.src !== selectedIp) return false;
      if (selectedProto !== null) {
        const proto = (flow.transport_protocol || flow.protocol || flow.raw?.protocol || '').toLowerCase();
        if (proto !== selectedProto) return false;
      }
      if (selectedPort !== null) {
        const dport = Number(flow.dst_port || flow.dport || 0);
        if (dport !== selectedPort) return false;
      }
      if (decisionFilter === 'attack' && !isAttack) return false;
      if (decisionFilter === 'normal' && isAttack) return false;
      return true;
    });
  }, [timeFilteredFlows, selectedCategory, selectedIp, selectedProto, selectedPort, decisionFilter]);

  // 4. Fully cross-filtered flows for KPIs, Donut chart, Top IPs, and Table
  const activeFlows = useMemo(() => {
    return flowsForTrend.filter(flow => {
      if (selectedBinRange !== null) {
        const ts = flow.timestamp || 0;
        if (ts < selectedBinRange.start || ts > selectedBinRange.end) return false;
      }
      return true;
    });
  }, [flowsForTrend, selectedBinRange]);

  // 5. Complete Network Traffic Overview & Threat Telemetry Aggregations
  const analytics = useMemo(() => {
    const total = activeFlows.length;
    let attacks = 0;
    let normal = 0;
    let totalBytes = 0;
    let bytesFwd = 0;
    let bytesBwd = 0;
    let totalPackets = 0;
    let packetsFwd = 0;
    let packetsBwd = 0;

    const catStats = {
      0: { count: 0, bytes: 0, packets: 0 },
      1: { count: 0, bytes: 0, packets: 0 },
      2: { count: 0, bytes: 0, packets: 0 },
      3: { count: 0, bytes: 0, packets: 0 },
      4: { count: 0, bytes: 0, packets: 0 },
      5: { count: 0, bytes: 0, packets: 0 }
    };

    const srcMap = new Map();
    const dstMap = new Set();
    const portMap = new Map();

    const protoStats = {
      tcp: { flows: 0, bytes: 0, packets: 0, attacks: 0 },
      udp: { flows: 0, bytes: 0, packets: 0, attacks: 0 },
      icmp: { flows: 0, bytes: 0, packets: 0, attacks: 0 },
      other: { flows: 0, bytes: 0, packets: 0, attacks: 0 }
    };

    const serviceStats = {
      http: { flows: 0, bytes: 0, attacks: 0 },
      dns: { flows: 0, bytes: 0, attacks: 0 },
      ssl: { flows: 0, bytes: 0, attacks: 0 },
      other: { flows: 0, bytes: 0, attacks: 0 }
    };

    activeFlows.forEach(flow => {
      const isAttack = flow.kind === 'flag' || (flow.prediction && flow.prediction.flagged);
      const catId = flow.prediction && typeof flow.prediction.class_id === 'number'
        ? flow.prediction.class_id
        : (isAttack ? 2 : 0);

      // Volume telemetry
      const flowBytes = Number(flow.bytes ?? ((flow.bytes_forward || 0) + (flow.bytes_backward || 0)) ?? flow.raw?.bytes_forward ?? 0);
      const bFwd = Number(flow.bytes_forward ?? flow.raw?.bytes_forward ?? Math.round(flowBytes * 0.5));
      const bBwd = Number(flow.bytes_backward ?? flow.raw?.bytes_backward ?? (flowBytes - bFwd));
      bytesFwd += bFwd;
      bytesBwd += bBwd;
      totalBytes += flowBytes;

      const flowPkts = Number(flow.packets ?? ((flow.packets_forward || 0) + (flow.packets_backward || 0)) ?? 1);
      const pFwd = Number(flow.packets_forward ?? Math.max(1, Math.round(flowPkts * 0.5)));
      const pBwd = Number(flow.packets_backward ?? (flowPkts - pFwd));
      packetsFwd += pFwd;
      packetsBwd += pBwd;
      totalPackets += flowPkts;

      // Decision counts
      if (isAttack) attacks++;
      else normal++;

      // Category breakdown
      if (catStats[catId]) {
        catStats[catId].count++;
        catStats[catId].bytes += flowBytes;
        catStats[catId].packets += flowPkts;
      }

      // Source hosts (talkers)
      const src = flow.src || 'Unknown';
      const curSrc = srcMap.get(src) || { ip: src, flows: 0, bytes: 0, packets: 0, attacks: 0, normal: 0 };
      curSrc.flows++;
      curSrc.bytes += flowBytes;
      curSrc.packets += flowPkts;
      if (isAttack) curSrc.attacks++;
      else curSrc.normal++;
      srcMap.set(src, curSrc);

      // Destination endpoints
      if (flow.dst) dstMap.add(flow.dst);

      // Destination ports
      const dport = Number(flow.dst_port || flow.dport || 0);
      if (dport > 0) {
        const curPort = portMap.get(dport) || { port: dport, flows: 0, bytes: 0, attacks: 0 };
        curPort.flows++;
        curPort.bytes += flowBytes;
        if (isAttack) curPort.attacks++;
        portMap.set(dport, curPort);
      }

      // Protocols
      const proto = (flow.transport_protocol || flow.protocol || flow.raw?.protocol || 'other').toLowerCase();
      const pKey = protoStats[proto] ? proto : 'other';
      protoStats[pKey].flows++;
      protoStats[pKey].bytes += flowBytes;
      protoStats[pKey].packets += flowPkts;
      if (isAttack) protoStats[pKey].attacks++;

      // Services
      const sGroup = (flow.service_group || flow.app || 'other').toLowerCase();
      let sKey = 'other';
      if (sGroup.includes('http')) sKey = 'http';
      else if (sGroup.includes('dns')) sKey = 'dns';
      else if (sGroup.includes('ssl') || sGroup.includes('tls') || sGroup.includes('https')) sKey = 'ssl';

      serviceStats[sKey].flows++;
      serviceStats[sKey].bytes += flowBytes;
      if (isAttack) serviceStats[sKey].attacks++;
    });

    const allTalkers = [...srcMap.values()].sort((a, b) => b.flows - a.flows);
    const topAttackTalkers = allTalkers.filter(t => t.attacks > 0).slice(0, 5);
    const topTalkers = (talkerFilterMode === 'attacks' ? topAttackTalkers : allTalkers.slice(0, 5));

    const topPorts = [...portMap.values()]
      .sort((a, b) => b.flows - a.flows)
      .slice(0, 5);

    return {
      total,
      attacks,
      normal,
      totalBytes,
      bytesFwd,
      bytesBwd,
      totalPackets,
      packetsFwd,
      packetsBwd,
      uniqueSrcCount: srcMap.size,
      uniqueDstCount: dstMap.size,
      attackRate: total ? ((attacks / total) * 100).toFixed(1) : '0.0',
      cleanRate: total ? ((normal / total) * 100).toFixed(1) : '0.0',
      catStats,
      topTalkers,
      topPorts,
      protoStats,
      serviceStats
    };
  }, [activeFlows, talkerFilterMode]);

  // Donut chart calculations for Traffic Health
  const donut = useMemo(() => {
    const total = analytics.total || 1;
    const normalPct = (analytics.normal / total) * 100;
    const attackPct = (analytics.attacks / total) * 100;
    const r = 50;
    const c = 2 * Math.PI * r;
    const normalOffset = c - (normalPct / 100) * c;
    return { normalPct, attackPct, c, normalOffset };
  }, [analytics]);

  const hasActiveFilter =
    selectedCategory !== null ||
    selectedIp !== null ||
    selectedProto !== null ||
    selectedPort !== null ||
    decisionFilter !== 'all' ||
    selectedBinRange !== null;

  const resetFilters = () => {
    setSelectedCategory(null);
    setSelectedIp(null);
    setSelectedProto(null);
    setSelectedPort(null);
    setDecisionFilter('all');
    setSelectedBinRange(null);
  };

  const handleSelectBin = binRange => {
    if (!binRange) {
      setSelectedBinRange(null);
      return;
    }
    if (selectedBinRange && selectedBinRange.start === binRange.start) {
      setSelectedBinRange(null);
    } else {
      setSelectedBinRange(binRange);
    }
  };

  return (
    <div className="security-analytics-page">
      {/* Page Heading (hidden when embedded in Live Monitor) */}
      {!embedded && (
        <div className="page-heading">
          <div>
            <h1>{pageTitle || 'Security Analytics'}</h1>
            <p>
              {description || 'Real-time network traffic volume, protocol breakdown, bandwidth telemetry, and ML attack detection.'}
            </p>
          </div>
        </div>
      )}

      {/* Time Toolbar (Hidden when embedded in Live Monitor to avoid duplicate toolbar) */}
      {!embedded && (
        <div className="time-toolbar">
          <strong>Time range</strong>
          <div className="periods">
            {[['10080', 'Week'], ['43200', 'Month'], ['525600', 'Year']].map(([val, label]) => (
              <button
                key={val}
                type="button"
                className="btn period"
                aria-pressed={timePreset === val}
                onClick={() => setTimePreset(timePreset === val ? '' : val)}
              >
                {label}
              </button>
            ))}
          </div>

          <select
            aria-label="Time range"
            value={timePreset}
            onChange={e => setTimePreset(e.target.value)}
          >
            {(presets.length ? presets : TIME_PRESETS).map(([val, text]) => (
              <option key={val} value={val}>{text}</option>
            ))}
          </select>

          {timePreset === 'custom' && (
            <div className="date-fields" style={{ marginLeft: 6, display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <label style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                From{' '}
                <input
                  type="date"
                  value={customFromDate}
                  onClick={e => { try { e.target.showPicker(); } catch {} }}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { try { e.target.showPicker(); } catch {} } }}
                  onChange={e => setCustomFromDate(e.target.value)}
                  style={{ cursor: 'pointer' }}
                />
                <input
                  type="time"
                  value={customFromTime}
                  onClick={e => { try { e.target.showPicker(); } catch {} }}
                  onChange={e => setCustomFromTime(e.target.value)}
                  style={{ cursor: 'pointer' }}
                  title="Start time (HH:mm)"
                />
              </label>
              <label style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                Through{' '}
                <input
                  type="date"
                  value={customToDate}
                  onClick={e => { try { e.target.showPicker(); } catch {} }}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { try { e.target.showPicker(); } catch {} } }}
                  onChange={e => setCustomToDate(e.target.value)}
                  style={{ cursor: 'pointer' }}
                />
                <input
                  type="time"
                  value={customToTime}
                  onClick={e => { try { e.target.showPicker(); } catch {} }}
                  onChange={e => setCustomToTime(e.target.value)}
                  style={{ cursor: 'pointer' }}
                  title="End time (HH:mm)"
                />
              </label>
            </div>
          )}

          <span className="run-status">
            Showing {activeFlows.length} of {timeFilteredFlows.length} connections ({formatBytes(analytics.totalBytes)})
          </span>
        </div>
      )}

      {/* Active Cross-filter Banner */}
      {hasActiveFilter && (
        <div className="block-banner" style={{ background: 'var(--indigo-light)', borderColor: 'var(--indigo)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <strong>⌕ Active interactive filters:</strong>
            {selectedCategory !== null && (
              <span className="badge flag">
                Category: {CATEGORIES[selectedCategory]?.name}
                <button
                  type="button"
                  onClick={() => setSelectedCategory(null)}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
            {selectedIp !== null && (
              <span className="badge flag">
                Host IP: {selectedIp}
                <button
                  type="button"
                  onClick={() => setSelectedIp(null)}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
            {selectedProto !== null && (
              <span className="badge normal">
                Protocol: {selectedProto.toUpperCase()}
                <button
                  type="button"
                  onClick={() => setSelectedProto(null)}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
            {selectedPort !== null && (
              <span className="badge normal">
                Port: {portService(selectedPort)}
                <button
                  type="button"
                  onClick={() => setSelectedPort(null)}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
            {decisionFilter !== 'all' && (
              <span className="badge normal">
                Traffic: {decisionFilter === 'attack' ? 'Attacks only' : 'Normal traffic only'}
                <button
                  type="button"
                  onClick={() => setDecisionFilter('all')}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
            {selectedBinRange !== null && (
              <span className="badge normal">
                Time Window: {selectedBinRange.label || 'Selected Window'}
                <button
                  type="button"
                  onClick={() => setSelectedBinRange(null)}
                  style={{ background: 'none', border: 0, padding: '0 0 0 5px', cursor: 'pointer', color: 'inherit' }}
                >
                  ✕
                </button>
              </span>
            )}
          </div>
          <button type="button" className="btn" onClick={resetFilters}>
            Clear all filters ✕
          </button>
        </div>
      )}

      {/* COMPREHENSIVE NETWORK TRAFFIC METRICS (KPIs) */}
      <div className="metrics">
        {/* Metric 1: Total Bandwidth Volume */}
        <div className="metric">
          <span className="metric-label">
            <span className="metric-symbol">⇄</span> Total Traffic Volume
          </span>
          <span className="metric-value">{formatBytes(analytics.totalBytes)}</span>
          <span className="metric-note">
            Sent: {formatBytes(analytics.bytesFwd)} · Received: {formatBytes(analytics.bytesBwd)}
          </span>
        </div>

        {/* Metric 2: Packets & Connections */}
        <button
          type="button"
          className="metric"
          onClick={() => { setDecisionFilter('all'); setSelectedCategory(null); }}
          title="Click to reset filters"
        >
          <span className="metric-label">
            <span className="metric-symbol">☷</span> Packets & Connections
          </span>
          <span className="metric-value">
            {analytics.totalPackets.toLocaleString()}{' '}
            <small style={{ fontSize: 13, fontWeight: 'normal', color: 'var(--muted)' }}>
              ({analytics.total.toLocaleString()} connections)
            </small>
          </span>
          <span className="metric-note">
            Average {analytics.total ? Math.round(analytics.totalPackets / analytics.total) : 0} packets per connection
          </span>
        </button>

        {/* Metric 3: Normal vs Anomalous Traffic Health */}
        <button
          type="button"
          className={`metric ${decisionFilter !== 'all' ? 'alert-metric selected' : ''}`}
          onClick={() => setDecisionFilter(decisionFilter === 'all' ? 'attack' : decisionFilter === 'attack' ? 'normal' : 'all')}
          title="Click to cycle: Attacks only → Normal only → All"
        >
          <span className="metric-label">
            <span className="metric-symbol" style={{ color: 'var(--green)' }}>✓</span>{' '}
            Traffic Health
          </span>
          <span className="metric-value" style={{ color: 'var(--green)' }}>
            {analytics.cleanRate}% <small style={{ fontSize: 13, color: 'var(--muted)' }}>Normal</small>
          </span>
          <span className="metric-note">
            {analytics.normal} normal / {analytics.attacks} attacks (click to filter)
          </span>
        </button>

        {/* Metric 4: Active Devices & Servers */}
        <div className="metric">
          <span className="metric-label">
            <span className="metric-symbol">◎</span> Active Devices & Servers
          </span>
          <span className="metric-value">
            {analytics.uniqueSrcCount}{' '}
            <small style={{ fontSize: 13, fontWeight: 'normal', color: 'var(--muted)' }}>
              senders ⇄ {analytics.uniqueDstCount} servers
            </small>
          </span>
          <span className="metric-note">Unique devices communicating on the network</span>
        </div>
      </div>

      {/* TOP SECTION: Interactive Side-by-side / Stacked Traffic Volume Histogram */}
      <NetworkTrafficVolumeDistributionChart
        flows={flowsForTrend}
        timeBounds={timeBounds}
        timeRangeLabel={timeRangeLabel}
        selectedBin={selectedBinRange ? selectedBinRange.start : null}
        selectedBinLabel={selectedBinRange ? selectedBinRange.label : null}
        selectedCategory={selectedCategory}
        selectedCategoryName={selectedCategory !== null ? CATEGORIES[selectedCategory]?.name : null}
        selectedIp={selectedIp}
        selectedProto={selectedProto}
        selectedPort={selectedPort}
        decisionFilter={decisionFilter}
        onSelectBin={handleSelectBin}
        onSelectCategory={setSelectedCategory}
        onSelectProto={setSelectedProto}
        onSelectDecision={setDecisionFilter}
      />

      {/* Normal vs Attack Traffic Ratio Highlight Panel */}
      <section className="panel panel-pad" style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 20 }}>
          <div style={{ flex: '1 1 280px' }}>
            <div className="panel-head" style={{ padding: 0, marginBottom: 12 }}>
              <div>
                <h2><span className="ui-symbol">◔</span> Normal vs Attack Traffic Ratio</h2>
                <p>Proportion of normal network traffic compared to detected attacks. Click to filter.</p>
              </div>
              {decisionFilter !== 'all' && (
                <button type="button" className="text-button" onClick={() => setDecisionFilter('all')}>
                  Show all ✕
                </button>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button
                type="button"
                className={`rank-item ${decisionFilter === 'normal' ? 'selected' : ''}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 14px',
                  borderRadius: 7,
                  background: decisionFilter === 'normal' ? 'var(--indigo-light)' : 'var(--surface)',
                  border: '1px solid var(--line)',
                  cursor: 'pointer',
                  flex: '1 1 140px'
                }}
                onClick={() => setDecisionFilter(decisionFilter === 'normal' ? 'all' : 'normal')}
              >
                <span style={{ width: 10, height: 10, borderRadius: 2, background: '#10b981', flexShrink: 0 }} />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>Normal Traffic</div>
                  <strong style={{ fontSize: 14 }}>{analytics.normal.toLocaleString()}</strong> <small style={{ color: 'var(--muted)' }}>({donut.normalPct.toFixed(1)}%)</small>
                </div>
              </button>

              <button
                type="button"
                className={`rank-item ${decisionFilter === 'attack' ? 'selected' : ''}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 14px',
                  borderRadius: 7,
                  background: decisionFilter === 'attack' ? 'var(--indigo-light)' : 'var(--surface)',
                  border: '1px solid var(--line)',
                  cursor: 'pointer',
                  flex: '1 1 140px'
                }}
                onClick={() => setDecisionFilter(decisionFilter === 'attack' ? 'all' : 'attack')}
              >
                <span style={{ width: 10, height: 10, borderRadius: 2, background: '#ef4444', flexShrink: 0 }} />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>Attacks</div>
                  <strong style={{ fontSize: 14, color: 'var(--coral)' }}>{analytics.attacks.toLocaleString()}</strong> <small style={{ color: 'var(--muted)' }}>({donut.attackPct.toFixed(1)}%)</small>
                </div>
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px 20px' }}>
            <div style={{ position: 'relative', width: 145, height: 145 }}>
              <svg width="145" height="145" viewBox="0 0 130 130" style={{ transform: 'rotate(-90deg)' }}>
                <circle cx="65" cy="65" r="50" fill="none" stroke="var(--line)" strokeWidth="15" />
                <circle
                  cx="65"
                  cy="65"
                  r="50"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="15"
                  strokeDasharray={donut.c}
                  strokeDashoffset={donut.normalOffset}
                  strokeLinecap="round"
                  style={{
                    cursor: 'pointer',
                    opacity: decisionFilter === 'attack' ? 0.25 : 1,
                    transition: 'opacity 0.2s'
                  }}
                  onClick={() => setDecisionFilter(decisionFilter === 'normal' ? 'all' : 'normal')}
                  title="Click to view Normal traffic only"
                />
                <circle
                  cx="65"
                  cy="65"
                  r="50"
                  fill="none"
                  stroke="#ef4444"
                  strokeWidth="15"
                  strokeDasharray={`${(donut.attackPct / 100) * donut.c} ${donut.c}`}
                  strokeDashoffset={-(donut.normalPct / 100) * donut.c}
                  strokeLinecap="round"
                  style={{
                    cursor: 'pointer',
                    opacity: decisionFilter === 'normal' ? 0.25 : 1,
                    transition: 'opacity 0.2s'
                  }}
                  onClick={() => setDecisionFilter(decisionFilter === 'attack' ? 'all' : 'attack')}
                  title="Click to view Attack traffic only"
                />
              </svg>

              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  pointerEvents: 'none'
                }}
              >
                <span style={{ fontSize: 22, fontWeight: 750, color: 'var(--green)', lineHeight: 1 }}>
                  {analytics.cleanRate}%
                </span>
                <span style={{ fontSize: 10, color: 'var(--green)', fontWeight: 600, marginTop: 4 }}>
                  Normal Traffic
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* BOTTOM UNIFIED SECTION: Traffic Categories & Attack Detection Details */}
      <section className="panel panel-pad">
        <div className="panel-head">
          <div>
            <h2><span className="ui-symbol">☷</span> Traffic Categories & Attack Detection Details</h2>
            <p>
              Detailed summary of data size, packet count, and detected attacks for each network traffic type. Click any row to filter.
            </p>
          </div>
          {selectedCategory !== null && (
            <button type="button" className="text-button" onClick={() => setSelectedCategory(null)}>
              Reset category ✕
            </button>
          )}
        </div>

        <div className="table-scroll" style={{ marginTop: 14 }}>
          <table className="flow-table" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>Traffic Category</th>
                <th>Attack Level</th>
                <th style={{ width: 150 }}>Traffic Share</th>
                <th>Connections</th>
                <th>Data Size</th>
                <th>Packets</th>
                <th>% of Total Data</th>
                <th>Security Status</th>
              </tr>
            </thead>
            <tbody>
              {CATEGORIES.map(cat => {
                const stat = analytics.catStats[cat.id] || { count: 0, bytes: 0, packets: 0 };
                const maxFlows = Math.max(...Object.values(analytics.catStats).map(s => s.count), 1);
                const pctOfFlows = analytics.total ? ((stat.count / analytics.total) * 100).toFixed(1) : 0;
                const pctOfBytes = analytics.totalBytes ? ((stat.bytes / analytics.totalBytes) * 100).toFixed(1) : 0;
                const isSelected = selectedCategory === cat.id;

                return (
                  <tr
                    key={cat.id}
                    onClick={() => setSelectedCategory(isSelected ? null : cat.id)}
                    style={{
                      cursor: 'pointer',
                      background: isSelected ? 'var(--indigo-light)' : undefined,
                      transition: 'background 0.15s'
                    }}
                    title={`Click to filter by ${cat.name}`}
                  >
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 9, height: 9, borderRadius: 2, background: cat.barColor, flexShrink: 0 }} />
                        <div>
                          <strong style={{ color: isSelected ? 'var(--indigo)' : 'inherit', fontSize: 13 }}>{cat.name}</strong>
                          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{cat.desc}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {cat.id === 0 ? (
                        <span className="badge normal">Normal</span>
                      ) : (
                        <span
                          className={`badge ${cat.severity === 'Critical' ? 'flag' : ''}`}
                          style={cat.severity === 'Medium' ? { background: '#fef3c7', color: '#92400e' } : {}}
                        >
                          {cat.severity}
                        </span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div className="bar-track" style={{ height: 6, flex: 1 }}>
                          <i
                            style={{
                              width: `${(stat.count / maxFlows) * 100}%`,
                              background: cat.barColor
                            }}
                          />
                        </div>
                        <span className="mono" style={{ fontSize: 11, width: 34, textAlign: 'right', color: 'var(--muted)' }}>
                          {pctOfFlows}%
                        </span>
                      </div>
                    </td>
                    <td className="mono" style={{ fontWeight: 700, fontSize: 13 }}>
                      {stat.count.toLocaleString()}
                    </td>
                    <td className="mono" style={{ fontWeight: 600 }}>
                      {formatBytes(stat.bytes)}
                    </td>
                    <td className="mono" style={{ color: 'var(--muted)' }}>
                      {stat.packets.toLocaleString()}
                    </td>
                    <td className="mono" style={{ color: 'var(--muted)' }}>
                      {pctOfBytes}%
                    </td>
                    <td>
                      <span className={`badge ${stat.count > 0 && cat.id !== 0 ? 'flag' : 'normal'}`}>
                        {stat.count > 0 && cat.id !== 0 ? 'Attack Detected' : 'Normal / Monitored'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
