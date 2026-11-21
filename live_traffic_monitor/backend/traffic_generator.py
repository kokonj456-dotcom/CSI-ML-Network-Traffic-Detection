#!/usr/bin/env python3
"""Dynamic Multi-Environment Traffic Generator for Wireshark Live Defense Monitor V2.

Features:
- 100% Unseen Real PCAP data across 3 environments: Home User, Enterprise LAN, Public Server.
- Full 5 MITRE ATT&CK Injection Threat Categories using authentic real-world packet captures:
    Cat 1: Denial of Service (DoS / SYN Flood)
    Cat 2: Reconnaissance & Probing (Nmap Port Scan)
    Cat 3: Exploits & PrivEsc (Apache Shiro CVE-2016-4437 RCE & MS04-011)
    Cat 4: Credential Abuse / R2L (FTP Dictionary Brute Force)
    Cat 5: Malware, C2 & Botnet (Trojan Backdoor C2 & Mirai DDoS)
- Pure Single-Flow On-the-Fly Dynamic Inference: Zero precalculations.
  Every flow transforms raw physical metrics (6 features) -> CENTRAL Preprocessor (19 features)
  -> Two-Stage XGBoost Model M9 (Binary Filter 0.45 + Multiclass MITRE ATT&CK) with exact microsecond latency measurement.
- Real-Time Side-by-Side Ground Truth vs AI Verdict attribution.
- Dynamic adjustable Flow Rate (1 to 50+ flows/s) and Threat Intensity (0% to 60%).
"""

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd

from model_runtime import ModelRuntime
from pcap_streamer import PCAPStreamer
from pipeline_runtime import transform_features

BASE_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = BASE_DIR.parent / "data-pipeline"
PCAPS_ROOT = BASE_DIR / "data" / "pcaps"

# 5 Core Attack Categories with Authentic Real PCAP benchmarks
CORE_5_ATTACKS = {
    "dos": {
        "key": "dos",
        "name": "DoS / SYN Flood",
        "pcap": "http_flood_dos.pcap",
        "alt_pcap": "synflood_ddos.pcap",
        "class_id": 1,
        "class_name": "Denial of Service (DoS)",
        "color": "#ef4444",
        "badge_color": "bg-rose-950/80 text-rose-300 border-rose-600/70",
    },
    "recon": {
        "key": "recon",
        "name": "PortScan (Recon)",
        "pcap": "nmap_portscan.pcap",
        "alt_pcap": "os_fingerprint.pcap",
        "class_id": 2,
        "class_name": "Reconnaissance & Probing",
        "color": "#f59e0b",
        "badge_color": "bg-amber-950/80 text-amber-300 border-amber-600/70",
    },
    "exploit": {
        "key": "exploit",
        "name": "Web Exploit (RCE)",
        "pcap": "web_exploit_shiro.pcap",
        "alt_pcap": "ms04_exploit.pcap",
        "class_id": 3,
        "class_name": "Exploits & PrivEsc",
        "color": "#a855f7",
        "badge_color": "bg-purple-950/80 text-purple-300 border-purple-600/70",
    },
    "bruteforce": {
        "key": "bruteforce",
        "name": "Brute Force (R2L)",
        "pcap": "ftp_bruteforce.pcap",
        "alt_pcap": "ftp_bruteforce.pcap",
        "class_id": 4,
        "class_name": "Credential Abuse (R2L)",
        "color": "#f97316",
        "badge_color": "bg-orange-950/80 text-orange-300 border-orange-600/70",
    },
    "botnet": {
        "key": "botnet",
        "name": "Botnet & C2 Beacon",
        "pcap": "trojan_evilprogram.pcap",
        "alt_pcap": "dns_amplification_ddos.pcap",
        "class_id": 5,
        "class_name": "Malware, C2 & Botnet",
        "color": "#ec4899",
        "badge_color": "bg-pink-950/80 text-pink-300 border-pink-600/70",
    },
}

ENV_CONFIG = {
    "home": {
        "id": "home",
        "name": "Home User & Smart Home IoT",
        "badge": "HOME USER & IOT",
        "description": "Residential web browsing, smart TV, IoT telemetry, DNS and P2P communication.",
        "icon": "home",
        "color": "#10b981",
        "pcaps": {
            "http_normal.pcap": (0, "Benign / Normal"),
            "dns_normal.pcap": (0, "Benign / Normal"),
            "torrent_normal.pcap": (0, "Benign / Normal"),
            "skype_irc_normal.pcap": (0, "Benign / Normal"),
            "http_flood_dos.pcap": (1, "Denial of Service (DoS)"),
            "nmap_portscan.pcap": (2, "Reconnaissance & Probing"),
            "web_exploit_shiro.pcap": (3, "Exploits & PrivEsc"),
            "ftp_bruteforce.pcap": (4, "Credential Abuse (R2L)"),
            "trojan_evilprogram.pcap": (5, "Malware, C2 & Botnet"),
            "blaster_worm.pcap": (5, "Malware, C2 & Botnet"),
            "dns_amplification_ddos.pcap": (5, "Malware, C2 & Botnet"),
        },
        "attacks": CORE_5_ATTACKS,
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise Corporate LAN",
        "badge": "ENTERPRISE LAN",
        "description": "Active Directory, internal SMB file sharing, corporate email, and SSH administration.",
        "icon": "building",
        "color": "#3b82f6",
        "pcaps": {
            "email_normal.pcap": (0, "Benign / Normal"),
            "ftp_normal.pcap": (0, "Benign / Normal"),
            "telnet_normal.pcap": (0, "Benign / Normal"),
            "office_chat_dns.pcap": (0, "Benign / Normal"),
            "http_flood_dos.pcap": (1, "Denial of Service (DoS)"),
            "nmap_portscan.pcap": (2, "Reconnaissance & Probing"),
            "os_fingerprint.pcap": (2, "Reconnaissance & Probing"),
            "web_exploit_shiro.pcap": (3, "Exploits & PrivEsc"),
            "ms04_exploit.pcap": (3, "Exploits & PrivEsc"),
            "ftp_bruteforce.pcap": (4, "Credential Abuse (R2L)"),
            "trojan_evilprogram.pcap": (5, "Malware, C2 & Botnet"),
        },
        "attacks": CORE_5_ATTACKS,
    },
    "server": {
        "id": "server",
        "name": "Public Web Server & Data Center",
        "badge": "PUBLIC SERVER",
        "description": "High-volume public HTTP/HTTPS visitors, REST APIs, and database transactions.",
        "icon": "server",
        "color": "#8b5cf6",
        "pcaps": {
            "web_normal.pcap": (0, "Benign / Normal"),
            "dns_resolution_normal.pcap": (0, "Benign / Normal"),
            "http_flood_dos.pcap": (1, "Denial of Service (DoS)"),
            "synflood_ddos.pcap": (1, "Denial of Service (DoS)"),
            "tcp_dos_flood.pcap": (1, "Denial of Service (DoS)"),
            "nmap_portscan.pcap": (2, "Reconnaissance & Probing"),
            "web_exploit_shiro.pcap": (3, "Exploits & PrivEsc"),
            "ftp_bruteforce.pcap": (4, "Credential Abuse (R2L)"),
            "trojan_evilprogram.pcap": (5, "Malware, C2 & Botnet"),
        },
        "attacks": CORE_5_ATTACKS,
    },
}


class TrafficGenerator:
    """Manages multi-environment raw PCAP pools and executes Pure Single-Flow Dynamic Inference."""

    def __init__(self):
        self.runtime = ModelRuntime()
        self.streamer = PCAPStreamer()

        # Load CENTRAL preprocessor
        prep_path = PIPELINE_DIR / "CENTRAL" / "output" / "feature_engineering" / "preprocessor.joblib"
        if not prep_path.exists():
            raise FileNotFoundError(f"Preprocessor missing at {prep_path}")
        self.preprocessor = joblib.load(prep_path)

        # Raw PCAP flow pools (Only raw features stored, NO precalculations)
        self.env_pools: Dict[str, Dict[str, Any]] = {"home": {}, "enterprise": {}, "server": {}}
        self._load_all_environment_pcaps()

        # Engine State
        self.current_env = "home"
        self.is_running = True
        self.flow_rate = 4.0  # flows per second (slider 1.0 to 50.0)
        self.threat_intensity = 0.10  # threat probability (slider 0.0 to 0.60)
        self.injection_queue: List[Dict[str, Any]] = []
        self.packet_counter = 1000

        # Forensic Tracking Metrics
        self.stats = self._init_stats_structure()

    def _init_stats_structure(self) -> Dict[str, Any]:
        return {
            "total_flows": 0,
            "normal_flows": 0,
            "attack_flows": 0,
            "true_positives": 0,
            "false_positives": 0,
            "true_negatives": 0,
            "false_negatives": 0,
            "class_matches": 0,
            "partial_matches": 0,
            "class_counts": {str(i): 0 for i in range(6)},
            "recent_latencies": [],
        }

    def _load_all_environment_pcaps(self):
        """Loads and indexes authentic raw flows from PCAP files across 3 environments."""
        print("Indexing authentic raw flows across all 3 network environments...")
        for env_id, cfg in ENV_CONFIG.items():
            env_dir = PCAPS_ROOT / env_id
            if not env_dir.exists():
                print(f"Warning: Directory {env_dir} does not exist.")
                continue

            normal_flows: List[Dict[str, Any]] = []
            attack_flows_by_pcap: Dict[str, List[Dict[str, Any]]] = {}

            for pcap_name, (gt_id, gt_name) in cfg["pcaps"].items():
                pcap_path = env_dir / pcap_name
                if not pcap_path.exists():
                    continue

                packets = self.streamer.parse_pcap_packets(pcap_path)
                flows = self.streamer.aggregate_flows(packets)

                raw_list = []
                for fl in flows:
                    raw_list.append(
                        {
                            "src_ip": fl["src_ip"],
                            "dst_ip": fl["dst_ip"],
                            "src_port": fl["src_port"],
                            "dst_port": fl["dst_port"],
                            "protocol": fl["protocol"],
                            "duration": fl["duration"],
                            "bytes_forward": fl["bytes_forward"],
                            "bytes_backward": fl["bytes_backward"],
                            "service_group": fl["service_group"],
                            "conn_state_group": fl["conn_state_group"],
                            "ground_truth_class_id": gt_id,
                            "ground_truth_name": gt_name,
                            "pcap_source": pcap_name,
                        }
                    )

                if gt_id == 0:
                    normal_flows.extend(raw_list)
                else:
                    if pcap_name == "web_exploit_shiro.pcap":
                        # Flows 0 & 1 are authentic Shiro CVE-2016-4437 RCE payloads
                        exploit_attacks = [raw_list[0], raw_list[1]]
                        attack_flows_by_pcap[pcap_name] = exploit_attacks
                        for bg_fl in raw_list[2:]:
                            bg_copy = dict(bg_fl)
                            bg_copy["ground_truth_class_id"] = 0
                            bg_copy["ground_truth_name"] = "Benign / Normal"
                            normal_flows.append(bg_copy)
                    elif pcap_name == "ms04_exploit.pcap":
                        attack_flows_by_pcap[pcap_name] = [raw_list[0]]
                        if len(raw_list) > 1:
                            bg_copy = dict(raw_list[1])
                            bg_copy["ground_truth_class_id"] = 0
                            bg_copy["ground_truth_name"] = "Benign / Normal"
                            normal_flows.append(bg_copy)
                    else:
                        attack_flows_by_pcap[pcap_name] = raw_list

            self.env_pools[env_id] = {
                "normal_flows": normal_flows,
                "attack_flows_by_pcap": attack_flows_by_pcap,
                "attacks_cfg": cfg["attacks"],
            }
            total_env_flows = len(normal_flows) + sum(len(v) for v in attack_flows_by_pcap.values())
            print(f"  [{env_id.upper()}] Loaded {total_env_flows} authentic flows ({len(normal_flows)} Benign, {len(attack_flows_by_pcap)} Attack PCAPs)")

    def set_environment(self, env_id: str) -> Dict[str, Any]:
        """Hot-swaps active environment, resets metrics, and updates attack configurations."""
        if env_id not in ENV_CONFIG:
            raise ValueError(f"Unknown environment: {env_id}")

        self.current_env = env_id
        self.injection_queue.clear()
        self.stats = self._init_stats_structure()
        print(f"Hot-swapped environment to: {ENV_CONFIG[env_id]['name']}")
        return self.get_environment_info()

    def get_environment_info(self) -> Dict[str, Any]:
        cfg = ENV_CONFIG[self.current_env]
        pool = self.env_pools.get(self.current_env, {})
        return {
            "id": cfg["id"],
            "name": cfg["name"],
            "badge": cfg["badge"],
            "description": cfg["description"],
            "icon": cfg["icon"],
            "color": cfg["color"],
            "normal_pool_size": len(pool.get("normal_flows", [])),
            "available_attacks": cfg["attacks"],
            "flow_rate": self.flow_rate,
            "threat_intensity": self.threat_intensity,
        }

    def set_flow_rate(self, rate: float):
        self.flow_rate = max(1.0, min(100.0, float(rate)))

    def set_threat_intensity(self, intensity: float):
        self.threat_intensity = max(0.0, min(0.60, float(intensity)))

    def inject_attack(self, attack_key: str, count: int = 15):
        """Pushes an on-demand attack burst from authentic real PCAPs for all 5 categories."""
        attack_key = attack_key.lower().strip()
        env_pool = self.env_pools.get(self.current_env, {})
        normal_pool = env_pool.get("normal_flows", [])
        attack_pcaps = env_pool.get("attack_flows_by_pcap", {})

        if attack_key == "normal":
            if normal_pool:
                burst = [dict(random.choice(normal_pool)) for _ in range(count)]
                self.injection_queue.extend(burst)
                print(f"Injected {count} authentic Normal flows into queue.")
            return

        # Map generic keys to 5 MITRE categories
        key_alias_map = {
            "1": "dos", "dos": "dos", "ddos": "dos", "synflood": "dos",
            "2": "recon", "recon": "recon", "portscan": "recon",
            "3": "exploit", "exploit": "exploit", "sqli": "exploit", "rce": "exploit",
            "4": "bruteforce", "bruteforce": "bruteforce", "brute": "bruteforce", "r2l": "bruteforce",
            "5": "botnet", "botnet": "botnet", "c2": "botnet", "malware": "botnet",
        }
        resolved_key = key_alias_map.get(attack_key, attack_key)

        # Look up in CORE_5_ATTACKS
        target_pcap = None
        alt_pcap = None
        if resolved_key in CORE_5_ATTACKS:
            target_pcap = CORE_5_ATTACKS[resolved_key]["pcap"]
            alt_pcap = CORE_5_ATTACKS[resolved_key]["alt_pcap"]

        pool = []
        if target_pcap and target_pcap in attack_pcaps:
            pool = attack_pcaps[target_pcap]
        elif alt_pcap and alt_pcap in attack_pcaps:
            pool = attack_pcaps[alt_pcap]
        elif attack_pcaps:
            pool = next(iter(attack_pcaps.values()))

        if not pool:
            print(f"Warning: No flows found for attack key {attack_key} in environment {self.current_env}")
            return

        burst = [dict(random.choice(pool)) for _ in range(count)]
        self.injection_queue.extend(burst)
        print(f"Injected {count} authentic real flows for attack category: {resolved_key.upper()}")

    def generate_next_flow(self) -> Optional[Dict[str, Any]]:
        """Executes Pure Single-Flow On-The-Fly Dynamic Inference for a single network flow."""
        if not self.is_running:
            return None

        env_pool = self.env_pools.get(self.current_env, {})
        normal_flows = env_pool.get("normal_flows", [])
        attack_pcaps = env_pool.get("attack_flows_by_pcap", {})

        # 1. Select raw flow based on injection queue, threat intensity, or baseline normal
        if self.injection_queue:
            raw_flow = self.injection_queue.pop(0)
        elif attack_pcaps and random.random() < self.threat_intensity:
            # Draw attack from active environment
            chosen_pcap = random.choice(list(attack_pcaps.keys()))
            raw_flow = random.choice(attack_pcaps[chosen_pcap])
        elif normal_flows:
            raw_flow = random.choice(normal_flows)
        else:
            return None

        self.packet_counter += 1
        now_str = time.strftime("%H:%M:%S")

        # 2. Pure Single-Flow Dynamic Inference (Zero Precalculations)
        t_start = time.perf_counter_ns()

        df_single = pd.DataFrame(
            [
                {
                    "record_id": 0,
                    "protocol": raw_flow["protocol"],
                    "duration": raw_flow["duration"],
                    "bytes_forward": raw_flow["bytes_forward"],
                    "bytes_backward": raw_flow["bytes_backward"],
                    "service_group": raw_flow["service_group"],
                    "conn_state_group": raw_flow["conn_state_group"],
                }
            ]
        )

        enc_features = (
            transform_features(df_single, self.preprocessor)
            .drop(columns=["record_id"], errors="ignore")
            .iloc[0]
            .to_dict()
        )

        pred = self.runtime.predict_single(enc_features)
        t_end = time.perf_counter_ns()
        latency_ms = round((t_end - t_start) / 1e6, 3)

        # 3. Ground Truth vs AI Forensic Evaluation
        gt_id = int(raw_flow["ground_truth_class_id"])
        gt_name = raw_flow["ground_truth_name"]
        is_attack_pred = bool(pred["is_attack"])
        pred_cat = int(pred["predicted_class_id"])

        if gt_id == 0:
            # Ground truth is Benign
            if is_attack_pred:
                forensic_verdict = "FALSE_POSITIVE"
                forensic_badge = "FP ALERT"
                self.stats["false_positives"] += 1
            else:
                forensic_verdict = "MATCH"
                forensic_badge = "BENIGN MATCH"
                self.stats["true_negatives"] += 1
        else:
            # Ground truth is Attack
            if not is_attack_pred:
                forensic_verdict = "ESCAPE"
                forensic_badge = "MISS / ESCAPE"
                self.stats["false_negatives"] += 1
            else:
                self.stats["true_positives"] += 1
                if pred_cat == gt_id:
                    forensic_verdict = "MATCH"
                    forensic_badge = "ATTACK MATCH"
                    self.stats["class_matches"] += 1
                else:
                    forensic_verdict = "PARTIAL_MATCH"
                    forensic_badge = "THREAT CAUGHT"
                    self.stats["partial_matches"] += 1

        # 4. Update Statistics
        self.stats["total_flows"] += 1
        if gt_id > 0:
            self.stats["attack_flows"] += 1
        else:
            self.stats["normal_flows"] += 1

        self.stats["class_counts"][str(pred_cat)] += 1
        self.stats["recent_latencies"].append(latency_ms)
        if len(self.stats["recent_latencies"]) > 50:
            self.stats["recent_latencies"].pop(0)

        # 5. Assemble Live Packet Payload
        packet = {
            "packet_no": self.packet_counter,
            "timestamp": now_str,
            "environment": self.current_env,
            "src_ip": raw_flow["src_ip"],
            "dst_ip": raw_flow["dst_ip"],
            "src_port": raw_flow["src_port"],
            "dst_port": raw_flow["dst_port"],
            "protocol": raw_flow["protocol"].upper(),
            "service": raw_flow["service_group"],
            "conn_state": raw_flow["conn_state_group"],
            "duration": round(raw_flow["duration"], 4),
            "bytes_forward": int(raw_flow["bytes_forward"]),
            "bytes_backward": int(raw_flow["bytes_backward"]),
            # Ground Truth
            "ground_truth_class_id": gt_id,
            "ground_truth_name": gt_name,
            "pcap_source": raw_flow["pcap_source"],
            # AI Inference
            "is_attack": pred["is_attack"],
            "binary_score": pred["binary_score"],
            "predicted_class_id": pred_cat,
            "predicted_class_name": pred["predicted_class_name"],
            "confidence": pred["confidence"],
            "tactic": pred["tactic"],
            "description": pred["description"],
            "severity": pred["severity"],
            # Forensic Comparison
            "forensic_verdict": forensic_verdict,
            "forensic_badge": forensic_badge,
            "latency_ms": latency_ms,
            "features_19": enc_features,
        }

        return packet

    def get_live_metrics(self) -> Dict[str, Any]:
        total = self.stats["total_flows"]
        normal = self.stats["normal_flows"]
        attack = self.stats["attack_flows"]
        tp = self.stats["true_positives"]
        fp = self.stats["false_positives"]
        tn = self.stats["true_negatives"]
        cm = self.stats["class_matches"]

        tpr = round((tp / max(1, attack)) * 100, 2)
        fpr = round((fp / max(1, normal)) * 100, 2)
        accuracy = round(((tp + tn) / max(1, total)) * 100, 2)
        class_match_rate = round((cm / max(1, tp)) * 100, 2)
        avg_lat = round(sum(self.stats["recent_latencies"]) / max(1, len(self.stats["recent_latencies"])), 2) if self.stats["recent_latencies"] else 1.20

        return {
            "total_flows": total,
            "normal_flows": normal,
            "attack_flows": attack,
            "attack_ratio": round((attack / max(1, total)) * 100, 2),
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": self.stats["false_negatives"],
            "class_matches": cm,
            "partial_matches": self.stats["partial_matches"],
            "tpr": tpr,
            "fpr": fpr,
            "accuracy": accuracy,
            "class_match_rate": class_match_rate,
            "avg_latency_ms": avg_lat,
            "class_counts": self.stats["class_counts"],
        }


if __name__ == "__main__":
    gen = TrafficGenerator()
    print("Testing generate_next_flow in Home environment:")
    for _ in range(5):
        pkt = gen.generate_next_flow()
        print(f"Flow #{pkt['packet_no']}: {pkt['src_ip']} -> {pkt['dst_ip']} | GT: {pkt['ground_truth_name']} vs AI: {pkt['predicted_class_name']} ({pkt['confidence']}%) | Status: {pkt['forensic_verdict']} | Lat: {pkt['latency_ms']} ms")
