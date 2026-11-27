#!/usr/bin/env python3
"""Rebuild all stages in an isolated run and publish only after audit passes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = PROJECT_ROOT / 'data-pipeline'
DATASETS_DIR = PIPELINE_DIR / 'sub-dataset'


def run_notebook(step_name, notebook_path, cwd=None, parameters=None):
    notebook_path=Path(notebook_path).resolve()
    notebook=json.loads(notebook_path.read_text(encoding='utf8'))
    parameters=parameters or {}
    tagged=[c for c in notebook['cells'] if 'parameters' in c.get('metadata',{}).get('tags',[])]
    if parameters and len(tagged)!=1:
        raise ValueError('Expected exactly one parameters cell')
    namespace={'__name__':'__main__','__file__':str(notebook_path)}
    previous=Path.cwd();started=time.time()
    print(f'\nSTEP: {step_name}',flush=True)
    try:
        os.chdir(cwd or notebook_path.parent)
        for number,cell in enumerate(notebook['cells'],1):
            if cell['cell_type']!='code':continue
            exec(compile(''.join(cell['source']),f'{notebook_path}:cell-{number}','exec'),namespace)
            if 'parameters' in cell.get('metadata',{}).get('tags',[]):
                unknown=set(parameters)-set(namespace)
                if unknown:raise ValueError(f'Unknown parameters: {unknown}')
                namespace.update(parameters)
    finally:
        os.chdir(previous)
    print(f'PASS: {step_name} ({time.time()-started:.1f}s)',flush=True)


def worker(args):
    from pipeline_runtime import collect_sources, write_json, DATASETS, audit_pipeline
    os.environ['PIPELINE_ALLOW_UNVERIFIED']='1' if args.allow_unverified_data else '0'
    sources=collect_sources(PIPELINE_DIR,args.allow_unverified_data)
    for ds in DATASETS:
        folder=DATASETS_DIR/ds
        for stage in ['cleansing','harmonization']:
            run_notebook(f'{ds} {stage}',folder/(stage+'.ipynb'))
    central=PIPELINE_DIR/'CENTRAL'
    run_notebook('CENTRAL build',central/'build_dataset.ipynb')
    write_json(central/'output/data_sources.json',sources)
    run_notebook('Shared feature engineering',central/'feature_engineering.ipynb')
    if args.resampling=='smotenc':
        for split in ['train','train_full']:
            run_notebook(f'SMOTENC {split}',central/'borderline_smote.ipynb',parameters={'SMOTE_SPLIT':split})
    try:
        report=audit_pipeline(PIPELINE_DIR,args.resampling=='smotenc')
    except Exception as error:
        write_json(central/'output/reports/audit.json',{'status':'failed','error':str(error)})
        raise
    write_json(central/'output/RUN_PROVENANCE.json',{
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),'audit_status':report['status'],
        'profile_scope':report['scope'],'data_sources':sources,'resampling':args.resampling,
        'warning':'Diagnostic data is not certified as an official benchmark.' if args.allow_unverified_data else None})
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)


def publish(run_root, archive):
    from pipeline_runtime import DATASETS
    pairs=[]
    for ds in DATASETS:
        src=run_root/'data-pipeline/sub-dataset'/ds/'output'
        for child in src.iterdir():pairs.append((child,DATASETS_DIR/ds/'output'/child.name))
    pairs.append((run_root/'data-pipeline/CENTRAL/output',PIPELINE_DIR/'CENTRAL/output'))
    completed=[]
    try:
        for src,dest in pairs:
            # Every move is constrained to this project or this run's archive.
            dest.resolve().relative_to(PROJECT_ROOT.resolve())
            backup=archive/dest.relative_to(PROJECT_ROOT)
            backup.resolve().relative_to(archive.resolve())
            backup.parent.mkdir(parents=True,exist_ok=True);dest.parent.mkdir(parents=True,exist_ok=True)
            existed=dest.exists()
            if existed:shutil.move(str(dest),str(backup))
            completed.append((src,dest,backup,existed))
            shutil.move(str(src),str(dest))
    except Exception:
        for src,dest,backup,existed in reversed(completed):
            if dest.exists():
                src.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dest),str(src))
            if existed and backup.exists():shutil.move(str(backup),str(dest))
        raise


def main():
    for stream in [sys.stdout,sys.stderr]:
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-unverified-data',action='store_true',help='Explicit diagnostic mode for legacy/unverified/demo raw and unavailable measured attributes')
    parser.add_argument('--resampling',choices=['none','smotenc'],default='none',help='Default baseline retains natural class frequencies')
    parser.add_argument('--no-publish',action='store_true',help='Keep audited outputs in the isolated run only')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:return worker(args)
    from pipeline_runtime import collect_sources, code_signature, raw_manifest, DATASETS
    collect_sources(PIPELINE_DIR,args.allow_unverified_data)  # fail before expensive copying
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    root=PROJECT_ROOT/'.pipeline-runs'/run_id/'work';root.mkdir(parents=True)
    signatures=code_signature(PIPELINE_DIR)
    raw={ds:raw_manifest(DATASETS_DIR/ds) for ds in DATASETS}
    shutil.copytree(PIPELINE_DIR,root/'data-pipeline',ignore=shutil.ignore_patterns('output','raw','__pycache__','.ipynb_checkpoints'))
    shutil.copy2(PROJECT_ROOT/'README.md',root/'README.md')
    contract_path = Path('webapp/Dashboard/backend/src/models/central_contract.py')
    (root/contract_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT/contract_path, root/contract_path)
    for ds in DATASETS:shutil.copytree(DATASETS_DIR/ds/'raw',root/'data-pipeline/sub-dataset'/ds/'raw')
    cmd=[sys.executable,str(root/'data-pipeline/build_quad_dataset.py'),'--worker','--resampling',args.resampling]
    if args.allow_unverified_data:cmd.append('--allow-unverified-data')
    log=root.parent/'pipeline.log'
    print(f'Run: {run_id}\nLog: {log}',flush=True)
    with log.open('w',encoding='utf8') as output:
        proc=subprocess.run(cmd,cwd=root,stdout=output,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONIOENCODING':'utf-8','MPLBACKEND':'Agg'})
    if proc.returncode:
        print(log.read_text(encoding='utf8')[-6000:]);raise RuntimeError(f'Pipeline failed; outputs not published. See {log}')
    if signatures!=code_signature(PIPELINE_DIR) or raw!={ds:raw_manifest(DATASETS_DIR/ds) for ds in DATASETS}:
        raise RuntimeError('Source inputs changed during run; outputs not published')
    if not args.no_publish:publish(root,PROJECT_ROOT/'.pipeline-archives'/run_id)
    print(f'PASS: pipeline audited. {"Outputs retained in run" if args.no_publish else "Outputs published; previous versions archived"}. Log: {log}')


if __name__=='__main__':main()
