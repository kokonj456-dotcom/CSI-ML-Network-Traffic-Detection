#!/usr/bin/env python3
"""PCAP Replay Streamer for Wireshark Live Defense Monitor.

Reads authentic network packet captures (.pcap), aggregates packets into
bidirectional network flows, computes 19 physical flow features, executes
Model M9 Two-Stage Inference, and streams live into the Web Dashboard.
"""

import argparse
import asyncio
import json
import socket
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd
import websockets

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
PCAP_DIR = BASE_DIR / "data" / "pcaps"
PIPELINE_DIR = BASE_DIR.parent / "data-pipeline"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from model_runtime import ModelRuntime
from pipeline_runtime import transform_features


PCAP_GROUND_TRUTH = {
    "http_dos.pcap": (1, "Denial of Service (DoS)"),
    "synflood_real.pcap": (1, "Denial of Service (DoS)"),
    "dosattack.pcap": (1, "Denial of Service (DoS)"),
    "dns_amplification_ddos.pcap": (5, "Malware, C2 & Botnet"),
    "portscan.pcap": (2, "Reconnaissance & Probing"),
    "ftp-crack.pcap": (4, "Credential Abuse (R2L)"),
    "blaster.pcap": (5, "Malware, C2 & Botnet"),
    "http_normal.pcap": (0, "Benign / Normal"),
    "dns_normal.pcap": (0, "Benign / Normal"),
    "telnet.pcap": (0, "Benign / Normal"),
}


class PCAPStreamer:
    def __init__(self, pcap_dir: Path = PCAP_DIR):
        self.pcap_dir = Path(pcap_dir)
        self.runtime = ModelRuntime()
        
        # Load CENTRAL preprocessor
        prep_path = PIPELINE_DIR / "CENTRAL" / "output" / "feature_engineering" / "preprocessor.joblib"
        if not prep_path.exists():
            raise FileNotFoundError(f"Preprocessor missing at {prep_path}")
        self.preprocessor = joblib.load(prep_path)
        print("PCAP Streamer initialized with Model M9 & CENTRAL Preprocessor.")

    def parse_pcap_packets(self, filepath: Path) -> List[Dict[str, Any]]:
        """Parses raw Ethernet/IPv4/TCP/UDP packets from a pcap file."""
        packets = []
        with open(filepath, "rb") as f:
            gh = f.read(24)
            if len(gh) < 24:
                return packets
            magic = struct.unpack("<I", gh[:4])[0]
            endian = "<" if magic == 0xA1B2C3D4 else ">"

            while True:
                ph = f.read(16)
                if len(ph) < 16:
                    break
                ts_sec, ts_usec, incl_len, orig_len = struct.unpack(f"{endian}IIII", ph)
                pdata = f.read(incl_len)
                if len(pdata) < 14:
                    continue

                # Ethernet type
                eth_type = struct.unpack("!H", pdata[12:14])[0]
                if eth_type != 0x0800:
                    continue  # IPv4 only

                ip_h = pdata[14:34]
                if len(ip_h) < 20:
                    continue

                proto_num = ip_h[9]
                src_ip = socket.inet_ntoa(ip_h[12:16])
                dst_ip = socket.inet_ntoa(ip_h[16:20])

                total_ip_len = struct.unpack("!H", ip_h[2:4])[0]
                ihl = (ip_h[0] & 0x0F) * 4
                trans_offset = 14 + ihl

                src_port, dst_port, flags = 0, 0, 0
                payload_len = 0
                if proto_num == 6:  # TCP
                    tcp_h = pdata[trans_offset : trans_offset + 20]
                    if len(tcp_h) >= 14:
                        src_port, dst_port = struct.unpack("!HH", tcp_h[:4])
                        tcp_hl = ((tcp_h[12] >> 4) & 0x0F) * 4
                        flags = tcp_h[13]
                        payload_len = max(0, total_ip_len - ihl - tcp_hl)
                    proto = "tcp"
                elif proto_num == 17:  # UDP
                    udp_h = pdata[trans_offset : trans_offset + 8]
                    if len(udp_h) >= 4:
                        src_port, dst_port = struct.unpack("!HH", udp_h[:4])
                        payload_len = max(0, total_ip_len - ihl - 8)
                    proto = "udp"
                elif proto_num == 1:
                    proto = "icmp"
                    payload_len = max(0, total_ip_len - ihl - 8)
                else:
                    proto = "other"
                    payload_len = max(0, total_ip_len - ihl)

                ts = ts_sec + (ts_usec / 1e6)
                packets.append(
                    {
                        "ts": ts,
                        "src_ip": src_ip,
                        "dst_ip": dst_ip,
                        "src_port": src_port,
                        "dst_port": dst_port,
                        "proto": proto,
                        "flags": flags,
                        "length": payload_len,
                    }
                )

        return packets

    def aggregate_flows(self, packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregates raw packets into bidirectional 5-tuple network flows."""
        flow_table = defaultdict(
            lambda: {
                "start_ts": None,
                "last_ts": None,
                "src_ip": None,
                "dst_ip": None,
                "src_port": 0,
                "dst_port": 0,
                "proto": "tcp",
                "service": "other",
                "bytes_fwd": 0,
                "bytes_bwd": 0,
                "initiator": None,
                "has_syn": False,
                "has_fin": False,
                "has_rst": False,
                "has_ack": False,
            }
        )

        for p in packets:
            # Bidirectional key
            ip_pair = tuple(sorted([p["src_ip"], p["dst_ip"]]))
            port_pair = tuple(sorted([p["src_port"], p["dst_port"]]))
            flow_key = (ip_pair, port_pair, p["proto"])

            fl = flow_table[flow_key]
            if fl["start_ts"] is None:
                fl["start_ts"] = p["ts"]
                fl["src_ip"] = p["src_ip"]
                fl["dst_ip"] = p["dst_ip"]
                fl["src_port"] = p["src_port"]
                fl["dst_port"] = p["dst_port"]
                fl["initiator"] = p["src_ip"]
                fl["proto"] = p["proto"]

                # Service classification by destination or source well-known port
                ports = [p["src_port"], p["dst_port"]]
                if 80 in ports or 8080 in ports:
                    fl["service"] = "http"
                elif 443 in ports or 8443 in ports:
                    fl["service"] = "https_ssl"
                elif 53 in ports:
                    fl["service"] = "dns"
                elif 22 in ports:
                    fl["service"] = "ssh"
                elif 21 in ports or 20 in ports:
                    fl["service"] = "ftp"
                elif 25 in ports:
                    fl["service"] = "smtp"
                else:
                    fl["service"] = "other"

            fl["last_ts"] = p["ts"]

            if p["src_ip"] == fl["initiator"]:
                fl["bytes_fwd"] += p["length"]
            else:
                fl["bytes_bwd"] += p["length"]

            if p["flags"] & 0x02:
                fl["has_syn"] = True
            if p["flags"] & 0x01:
                fl["has_fin"] = True
            if p["flags"] & 0x04:
                fl["has_rst"] = True
            if p["flags"] & 0x10:
                fl["has_ack"] = True

        # Process state and build standard flow objects
        flows = []
        for fl in flow_table.values():
            dur = max(0.0, fl["last_ts"] - fl["start_ts"])
            if fl["has_fin"] or fl["has_ack"] or fl["bytes_bwd"] > 0:
                conn_state = "established"
            elif fl["has_rst"]:
                conn_state = "reset"
            else:
                conn_state = "no-reply"

            flows.append(
                {
                    "start_ts": fl["start_ts"],
                    "duration": dur,
                    "protocol": fl["proto"],
                    "bytes_forward": fl["bytes_fwd"],
                    "bytes_backward": fl["bytes_bwd"],
                    "service_group": fl["service"],
                    "conn_state_group": conn_state,
                    "src_ip": fl["src_ip"],
                    "dst_ip": fl["dst_ip"],
                    "src_port": fl["src_port"],
                    "dst_port": fl["dst_port"],
                }
            )

        # Sort chronologically by start timestamp
        flows.sort(key=lambda x: x["start_ts"])
        return flows

    def process_pcap_to_dashboard_packets(self, filepath: Path) -> List[Dict[str, Any]]:
        """Parses PCAP, extracts flows, runs Model M9, and returns dashboard-ready payloads."""
        packets = self.parse_pcap_packets(filepath)
        if not packets:
            print(f"Warning: No valid IPv4 packets in {filepath.name}")
            return []

        raw_flows = self.aggregate_flows(packets)
        if not raw_flows:
            return []

        # Convert to DataFrame for standard feature engineering
        df_raw = pd.DataFrame(
            [
                {
                    "record_id": f"PCAP_{i}",
                    "duration": rf["duration"],
                    "protocol": rf["protocol"],
                    "bytes_forward": rf["bytes_forward"],
                    "bytes_backward": rf["bytes_backward"],
                    "service_group": rf["service_group"],
                    "conn_state_group": rf["conn_state_group"],
                }
                for i, rf in enumerate(raw_flows)
            ]
        )

        encoded_19 = transform_features(df_raw, self.preprocessor).drop(columns=["record_id"], errors="ignore")

        # Run Vectorized Two-Stage Model M9
        predictions = self.runtime.predict_batch(encoded_19)

        dashboard_packets = []
        gt_cat_id, gt_cat_name = PCAP_GROUND_TRUTH.get(filepath.name, (None, None))
        for i, rf in enumerate(raw_flows):
            feat_dict = encoded_19.iloc[i].to_dict()
            pred = predictions[i]
            cur_gt_id = gt_cat_id if gt_cat_id is not None else pred["predicted_class_id"]
            cur_gt_name = gt_cat_name if gt_cat_name is not None else pred["predicted_class_name"]

            dashboard_packets.append(
                {
                    "pcap_file": filepath.name,
                    "src_ip": rf["src_ip"],
                    "dst_ip": rf["dst_ip"],
                    "src_port": rf["src_port"],
                    "dst_port": rf["dst_port"],
                    "protocol": rf["protocol"].upper(),
                    "service": rf["service_group"],
                    "conn_state": rf["conn_state_group"],
                    "duration": round(rf["duration"], 4),
                    "bytes_forward": int(rf["bytes_forward"]),
                    "bytes_backward": int(rf["bytes_backward"]),
                    # AI Inferences
                    "is_attack": pred["is_attack"],
                    "binary_score": pred["binary_score"],
                    "predicted_class_id": pred["predicted_class_id"],
                    "predicted_class_name": pred["predicted_class_name"],
                    "confidence": pred["confidence"],
                    "tactic": pred["tactic"],
                    "description": pred["description"],
                    "severity": pred["severity"],
                    "latency_ms": pred["inference_latency_ms"],
                    # Ground Truth
                    "ground_truth_class_id": cur_gt_id,
                    "ground_truth_name": cur_gt_name,
                    "features_19": feat_dict,
                }
            )

        return dashboard_packets

    async def stream_to_websocket(self, pcap_name: str, ws_url: str = "ws://localhost:8088/ws/traffic", speed: float = 1.0):
        """Streams parsed PCAP flows live into the running Web Dashboard."""
        pcap_path = self.pcap_dir / pcap_name
        if not pcap_path.exists():
            print(f"Error: {pcap_path} not found!")
            return

        print(f"\nProcessing authentic PCAP: {pcap_name}...")
        flows = self.process_pcap_to_dashboard_packets(pcap_path)
        print(f"Extracted {len(flows)} real flows from {pcap_name}.")

        attack_count = sum(1 for f in flows if f["is_attack"])
        print(f"Model M9 Detection Summary: {attack_count}/{len(flows)} classified as ATTACK ({(attack_count/len(flows))*100:.1f}%)")

        print(f"Connecting to Web Dashboard at {ws_url}...")
        try:
            async with websockets.connect(ws_url) as ws:
                print(f"Connected! Streaming {len(flows)} real flows at speed {speed}x...")
                for i, fl in enumerate(flows):
                    fl["packet_no"] = 5000 + i + 1
                    fl["timestamp"] = time.strftime("%H:%M:%S")

                    payload = {
                        "type": "flow",
                        "packet": fl,
                        "stats": None,
                        "scenario": {
                            "active": True,
                            "phase": f"Replaying Real PCAP: {pcap_name}",
                            "elapsed_sec": i + 1,
                            "remaining_sec": len(flows) - i - 1,
                        },
                    }
                    await ws.send(json.dumps(payload))
                    print(
                        f"  [{i+1}/{len(flows)}] {fl['src_ip']}:{fl['src_port']} -> {fl['dst_ip']}:{fl['dst_port']} ({fl['protocol']}/{fl['service']}) => {fl['predicted_class_name']} ({fl['confidence']}%)"
                    )

                    delay = max(0.08, 0.40 / speed)
                    await asyncio.sleep(delay)

                print(f"\nFinished streaming authentic PCAP: {pcap_name}!")
        except Exception as e:
            print(f"Could not connect to WebSocket ({e}). Ensure server.py is running on port 8088.")


def main():
    parser = argparse.ArgumentParser(description="Real PCAP Traffic Streamer for Wireshark Live Defense Monitor")
    parser.add_argument("--pcap", type=str, default="portscan.pcap", help="PCAP filename in data/pcaps/ (e.g., portscan.pcap, dosattack.pcap, ftp-crack.pcap, http_normal.pcap)")
    parser.add_argument("--speed", type=float, default=2.0, help="Streaming speed multiplier (e.g., 1.0, 2.0, 5.0)")
    parser.add_argument("--list", action="store_true", help="List all available downloaded PCAPs")
    parser.add_argument("--all", action="store_true", help="Stream all real PCAPs sequentially in a full presentation demo")
    args = parser.parse_args()

    streamer = PCAPStreamer()

    if args.list:
        print("\nAvailable Downloaded Authentic PCAPs:")
        for pf in sorted(PCAP_DIR.glob("*.pcap")):
            size_kb = pf.stat().st_size / 1024
            print(f" - {pf.name:20s} ({size_kb:7.1f} KB)")
        return

    if args.all:
        sequence = ["http_normal.pcap", "portscan.pcap", "ftp-crack.pcap", "dosattack.pcap", "blaster.pcap"]
        print(f"\nStarting Full Authentic Presentation Replay Sequence ({len(sequence)} PCAPs)...")
        for pcap_name in sequence:
            asyncio.run(streamer.stream_to_websocket(pcap_name, speed=args.speed))
            time.sleep(2)
        return

    asyncio.run(streamer.stream_to_websocket(args.pcap, speed=args.speed))


if __name__ == "__main__":
    main()
