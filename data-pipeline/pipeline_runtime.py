"""Shared contracts for dataset preparation, encoding and validation."""
from pathlib import Path
import hashlib
import json
import os
import sys
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapp.Dashboard.backend.src.models.central_contract import (  # noqa: E402
    CATEGORIES, CLASS_NAMES, CORE, NAMES, NUMERIC, PREFIXES, derived, fit_preprocessor, require, transform_features,
)

DATASETS = ('NSL-KDD', 'UNSW-NB15', 'CIC-IDS2017', 'BoT-IoT')
TACTICS = ['Baseline Operations','TA0040: Impact','TA0043/TA0007: Recon & Discovery','TA0001/TA0004: Initial Access & PrivEsc','TA0006: Credential Access','TA0011/TA0008: C2 & Lateral Movement']
COMMON_MAPPING = {'normal':0,'benign':0,'dos':1,'dos/ddos':1,'ddos':1,'probe':2,'probe/recon':2,'reconnaissance':2,'analysis':2,'exploits':3,'exploit/u2r':3,'shellcode':3,'u2r':3,'r2l':4,'brute-force/r2l':4,'generic':5,'generic/fuzzer':5,'fuzzers':5,'backdoor':5,'backdoors':5,'botnet/backdoor':5,'worms':5}
SOURCE_MAPPING = {
    'NSL-KDD': {k:COMMON_MAPPING[k] for k in ['normal','dos','probe','r2l','u2r']},
    'UNSW-NB15': {k:COMMON_MAPPING[k] for k in ['normal','analysis','backdoor','backdoors','dos','exploits','fuzzers','generic','reconnaissance','shellcode','worms']},
    'CIC-IDS2017': {**COMMON_MAPPING, 'dos hulk':1,'dos goldeneye':1,'dos slowloris':1,'dos slowhttptest':1,'heartbleed':3,'portscan':2,'ftp-patator':4,'ssh-patator':4,'web attack - brute force':4,'web attack - xss':3,'web attack - sql injection':3,'web attack brute force':4,'web attack xss':3,'web attack sql injection':3,'infiltration':3,'bot':5},
    # Project-level category grouping, not per-record MITRE attribution.
    'BoT-IoT': {**COMMON_MAPPING,'theft':5,'data_theft':5,'bruteforce':4},
}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):h.update(block)
    return h.hexdigest()

def write_json(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf8')

def raw_manifest(dataset_dir):
    return [{'file':p.relative_to(Path(dataset_dir)/'raw').as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted((Path(dataset_dir)/'raw').rglob('*')) if p.is_file() and p.suffix.lower() in {'.csv','.gz','.txt'}]

def verify_manifest(dataset_dir, manifest):
    saved=pd.read_csv(manifest).sort_values('file').reset_index(drop=True)
    now=pd.DataFrame(raw_manifest(dataset_dir)).sort_values('file').reset_index(drop=True)
    require(len(now)>0 and saved[['file','sha256']].equals(now[['file','sha256']]),f'Stale raw manifest: {manifest}; rerun cleansing/harmonization')

def read_tables(folder):
    # Source labels can be numeric (UNSW) or text (NSL/CIC). Preserve lexical
    # identifiers consistently across source tables, concatenation and CSV reload.
    types={name:'string' for name in ['record_id','label_raw','label_source_category','source_attack_category','orig_row_id','split_group','source_dataset','source_split','source_protocol','source_connection_state','source_service','service_basis','connection_state_basis','duration_unit','quality_issues','capture_time']}
    f,l,m=tuple(pd.read_csv(Path(folder)/(t+'.csv'),low_memory=False,dtype=types) for t in ['features','labels','metadata'])
    from harmonization_rules import normalize_boolean_metadata
    return f,l,normalize_boolean_metadata(m)

def validate_tables(f,l,m,allow_quarantined=False):
    require(len(f)>0 and len(f)==len(l)==len(m),'Empty tables or row-count mismatch')
    for name,frame in [('features',f),('labels',l),('metadata',m)]:
        require('record_id' in frame and frame.record_id.notna().all() and frame.record_id.astype(str).str.strip().ne('').all() and frame.record_id.is_unique,f'{name}: missing/duplicate record_id')
    require(f.record_id.equals(l.record_id) and f.record_id.equals(m.record_id),'Record IDs/order mismatch')
    require(not set(f.columns).intersection({'label','label_raw','label_source_category','attack_category','attack_category_id','label_binary','mitre_tactic','is_attack','source_dataset','sample_weight','data_split','is_synthetic'}),'Target/metadata leakage in features')
    require(set(CORE).issubset(f.columns),'Missing core columns')
    from harmonization_rules import quality_flags
    computed=quality_flags(f,m)
    eligible=~computed.any(axis=1)
    if 'quality_ok' in m:
        require(m.quality_ok.notna().all() and m.quality_ok.eq(eligible).all(),'quality_ok disagrees with recomputed quality rules')
        for col in computed:require(col in m and m[col].eq(computed[col]).all(),f'{col}: quality flag mismatch')
    require(allow_quarantined or eligible.all(),'Invalid duration/bytes/protocol or cross-field conflicts: quarantined records are not allowed in model splits')
    checked=f.loc[eligible] if allow_quarantined else f
    for c in NUMERIC:
        z=pd.to_numeric(checked[c],errors='coerce')
        require(np.isfinite(z).all() and z.ge(0).all(),f'{c}: missing, infinite or negative input')
    for c,values in CATEGORIES.items():require(checked[c].notna().all() and checked[c].isin(values).all(),f'{c}: missing/unknown categories')
    response=checked.bytes_backward.gt(0)
    if 'packets_backward' in checked:response |= checked.packets_backward.gt(0)
    require(not (checked.conn_state_group.eq('no-reply') & response).any(),'no-reply contradicts backward traffic')
    for c in ['packets_forward','packets_backward','mean_packet_size','ttl_forward','ttl_backward','tcp_window_forward','tcp_window_backward']:
        if c in checked:
            z=checked[c].dropna()
            require(np.isfinite(z).all() and z.ge(0).all(),f'{c}: invalid measured extension')
    require('label_binary' in l and l.label_binary.isin([0,1]).all(),'Invalid binary labels')
    if 'attack_category_id' in l:
        require(l.attack_category_id.isin(range(6)).all(),'Invalid central classes')
        require(l.label_binary.eq(l.attack_category_id.ne(0).astype(int)).all(),'Binary/multiclass labels disagree')
        require(l.attack_category.eq(l.attack_category_id.map(dict(enumerate(CLASS_NAMES)))).all(),'Class name/ID mismatch')
    if 'sample_weight' in m:require(np.isfinite(m.sample_weight).all() and m.sample_weight.gt(0).all(),'Invalid sample weights')
    for flag in ['invalid_duration','invalid_bytes_forward','invalid_bytes_backward']:
        if flag in m:require(not m.loc[eligible,flag].astype(str).str.lower().isin(['true','1']).any(),f'{flag}: flagged invalid rows')

def map_labels(labels, metadata):
    result=labels.copy(); ids=pd.Series(index=labels.index,dtype='int64')
    for source,index in metadata.groupby('source_dataset').groups.items():
        require(source in SOURCE_MAPPING,f'Unsupported source {source}')
        values=labels.loc[index,'label_source_category'].astype('string').str.strip().str.lower().str.replace(r'\s+',' ',regex=True)
        mapped=values.map(SOURCE_MAPPING[source])
        require(mapped.notna().all(),f'Unmapped labels in {source}: {values[mapped.isna()].value_counts().to_dict()}')
        ids.loc[index]=mapped.astype(int)
    ids=ids.astype(int)
    require(labels.label_binary.eq(ids.ne(0).astype(int)).all(),'Mapped categories contradict original binary truth')
    result['attack_category_id']=ids;result['attack_category']=ids.map(dict(enumerate(CLASS_NAMES)));result['mitre_tactic']=ids.map(dict(enumerate(TACTICS)))
    return result

def code_signature(pipeline_dir):
    p=Path(pipeline_dir)
    files=sorted([*p.glob('*.py'),*p.glob('CENTRAL/*.json'),*p.glob('CENTRAL/*.ipynb'),*p.glob('sub-dataset/*/*.ipynb'),*p.glob('sub-dataset/*/*.py')])
    signature = {f.relative_to(p).as_posix():digest(f) for f in files}
    shared = PROJECT_ROOT / "webapp/Dashboard/backend/src/models/central_contract.py"
    signature["../webapp/Dashboard/backend/src/models/central_contract.py"] = digest(shared)
    return signature

def stamp_dataset(dataset_dir):
    d=Path(dataset_dir);p=d.parent.parent
    f,l,m=read_tables(d/'output/harmonized');validate_tables(f,l,m,allow_quarantined=True)
    verify_manifest(d,d/'output/cleansing/source_manifest.csv')
    verify_manifest(d,d/'output/harmonized/source_manifest.csv')
    cleaned=cleaned_fingerprints(d)
    from harmonization_rules import write_quality_outputs
    if 'quality_ok' in m:write_quality_outputs(d,f,l,m)
    origin=d/'raw/source_provenance.json'
    write_json(d/'output/harmonized/dependencies.json',{'raw':raw_manifest(d),'code':code_signature(p),'cleaned':cleaned,'source_provenance':digest(origin) if origin.exists() else None,'tables':{t:digest(d/'output/harmonized'/f'{t}.csv') for t in ['features','labels','metadata']}})

def cleaned_fingerprints(dataset_dir):
    d=Path(dataset_dir)
    names={'NSL-KDD':['KDDTrain_clean.csv','KDDTest_clean.csv','KDDTest-21_clean.csv'],
           'UNSW-NB15':['UNSW_NB15_training-set.csv','UNSW_NB15_testing-set.csv'],
           'CIC-IDS2017':['CIC_IDS2017_training-set.csv','CIC_IDS2017_testing-set.csv'],
           'BoT-IoT':['BoT_IoT_training-set.csv','BoT_IoT_testing-set.csv']}[d.name]
    for name in names:require((d/'output/cleansing'/name).is_file(),f'Missing cleaned file: {d.name}/{name}')
    return {name:digest(d/'output/cleansing'/name) for name in names}

def verify_dataset(dataset_dir):
    d=Path(dataset_dir);path=d/'output/harmonized/dependencies.json'
    require(path.is_file(),f'Missing dependency stamp: {path}; rerun harmonization')
    stamp=json.loads(path.read_text(encoding='utf8'))
    require(stamp['raw']==raw_manifest(d),'Raw changed since harmonization')
    require(stamp['code']==code_signature(d.parent.parent),'Pipeline code/contract changed since harmonization')
    require(stamp.get('cleaned')==cleaned_fingerprints(d),'Cleaned artifacts changed since harmonization')
    origin=d/'raw/source_provenance.json'
    require(stamp.get('source_provenance')==(digest(origin) if origin.exists() else None),'Source provenance changed since harmonization')
    for name,h in stamp['tables'].items():require(digest(d/'output/harmonized'/f'{name}.csv')==h,f'Harmonized table changed: {name}')

def normalize_weights(metadata):
    result=metadata.copy()
    # Equal total contribution per source, with average row weight equal to 1.
    counts=result.groupby('source_dataset').record_id.transform('size')
    result['sample_weight']=len(result)/(result.source_dataset.nunique()*counts.astype(float))
    return result

def engineer(central_dir):
    c=Path(central_dir);o=c/'output';out=o/'feature_engineering';out.mkdir(parents=True,exist_ok=True)
    train=read_tables(o/'splits/train');validate_tables(*train)
    pre=fit_preprocessor(train[0]);joblib.dump(pre,out/'preprocessor.joblib')
    reports=[]
    for split in ['train','train_full','validation','test']:
        f,l,m=read_tables(o/'splits'/split);validate_tables(f,l,m)
        dest=out/split;dest.mkdir(exist_ok=True)
        transform_features(f,pre).to_csv(dest/'features.csv',index=False)
        l.to_csv(dest/'labels.csv',index=False);m.to_csv(dest/'metadata.csv',index=False)
        reports.append({'split':split,'rows':len(f),'model_features':len(NAMES)})
    pd.DataFrame(reports).to_csv(out/'feature_engineering_report.csv',index=False)
    write_json(out/'feature_schema.json',{'schema_version':5,'model_feature_names':NAMES,'fit_split':'train','fit_record_ids_sha256':pre['fit_record_ids_sha256'],'numeric_scaling':'StandardScaler fitted on train','availability_policy':'other with false metadata flag is diagnostic-only'})
    return reports

def resample(central_dir,split='train',target_class=4,target_samples=40000,random_state=42):
    from imblearn.over_sampling import SMOTENC
    require(split in ['train','train_full'],'Resampling only supports training splits')
    o=Path(central_dir)/'output';f,l,m=read_tables(o/'splits'/split);validate_tables(f,l,m)
    pre=joblib.load(o/'feature_engineering/preprocessor.joblib')
    n=len(f);count=int(l.attack_category_id.eq(target_class).sum())
    require(count>0,'Cannot synthesize an absent class')
    # Distance uses three standardized log inputs and categorical attributes;
    # the redundant ratio is recomputed after inverse transformation.
    train=read_tables(o/'splits/train')[0]
    numeric_scaler=StandardScaler().fit(np.log1p(train[NUMERIC].to_numpy(float)))
    x=pd.DataFrame(numeric_scaler.transform(np.log1p(f[NUMERIC].to_numpy(float))),columns=NUMERIC)
    for col in CATEGORIES:x[col]=f[col].to_numpy()
    rejected=0;fallback_rows=0
    if count<target_samples:
        require(count>=2,'SMOTENC needs at least two minority samples')
        sampler=SMOTENC(categorical_features=[3,4,5],sampling_strategy={target_class:target_samples},k_neighbors=min(5,count-1),random_state=random_state)
        xr,yr=sampler.fit_resample(x,l.attack_category_id)
        z=xr.iloc[n:];k=len(z)
        synth=pd.DataFrame(np.maximum(np.expm1(numeric_scaler.inverse_transform(z[NUMERIC].to_numpy(float))),0),columns=NUMERIC)
        synth[['bytes_forward','bytes_backward']]=synth[['bytes_forward','bytes_backward']].round()
        for col in CATEGORIES:synth[col]=z[col].to_numpy()
        invalid_state=synth.conn_state_group.eq('no-reply') & synth.bytes_backward.gt(0)
        rejected=int(invalid_state.sum())
        synth=synth.loc[~invalid_state].reset_index(drop=True)
        # Mixed-category interpolation may violate state/counter constraints.
        # Reject those candidates; fill the exact deficit by transparent random
        # oversampling of valid minority inputs, never fabricate measurements.
        fallback_rows=k-len(synth)
        if fallback_rows:
            minority=f.loc[l.attack_category_id.eq(target_class),CORE]
            extra=minority.sample(n=fallback_rows,replace=True,random_state=random_state)
            synth=pd.concat([synth,extra],ignore_index=True)
        ids=[f'SMOTENC:{split}:C{target_class}:{random_state}:{i:08d}' for i in range(k)]
        synth.insert(0,'record_id',ids);synth=synth.reindex(columns=f.columns)
        sl=pd.DataFrame({'record_id':ids,'label_raw':'Synthetic_SMOTENC','label_source_category':CLASS_NAMES[target_class],'attack_category':CLASS_NAMES[target_class],'attack_category_id':target_class,'label_binary':int(target_class!=0),'mitre_tactic':TACTICS[target_class]})
        sm=pd.DataFrame(index=range(k),columns=m.columns)
        for col in m:
            if col.startswith('has_') or col.startswith('invalid_'):sm[col]=False
        for col in ['has_duration','has_protocol','has_directional_bytes','has_service','has_connection_state']:sm[col]=True
        sm['record_id']=ids;sm['source_dataset']='Synthetic_SMOTENC';sm['orig_row_id']=ids;sm['source_split']=split;sm['data_split']=split+'_smote';sm['split_group']=ids;sm['dedup_flag']=0;sm['is_kddtest21_view']=False
        sm['state_reclassified']=False;sm['service_identified']=False
        sm['service_basis']='synthetic_category';sm['connection_state_basis']='synthetic_category';sm['duration_unit']='seconds'
        # Treat all resampled rows equally by default; no 100,000x weight jump.
        f=pd.concat([f,synth],ignore_index=True);l=pd.concat([l,sl],ignore_index=True);m=pd.concat([m,sm],ignore_index=True)
    else:k=0
    m['sample_weight']=1.0
    m['is_synthetic']=np.arange(len(f))>=n;l['is_synthetic']=m.is_synthetic
    if 'quality_ok' in m:
        from harmonization_rules import quality_flags
        flags=quality_flags(f,m)
        for col in flags:m[col]=flags[col]
        m['quality_ok']=~flags.any(axis=1)
        m.loc[m.is_synthetic,'quality_issues']=''
    validate_tables(f,l,m)
    dest=o/'splits'/(split+'_smote');dest.mkdir(parents=True,exist_ok=True)
    for name,frame in [('features',f),('labels',l),('metadata',m)]:frame.to_csv(dest/(name+'.csv'),index=False)
    transform_features(f,pre).to_csv(dest/'features_encoded_19.csv',index=False)
    report={'method':'SMOTENC','source_split':split,'target_class_id':target_class,'target_samples':target_samples,'original_rows':n,'synthetic_rows':k,'total_rows':len(f),'original_target_count':count,'resampled_weight_policy':'uniform mean-one','preprocessor_fit_split':'train','preprocessor_fit_record_ids_sha256':pre['fit_record_ids_sha256'],'random_state':random_state,'rejected_candidates':rejected,'fallback_rows':fallback_rows,'fallback_method':'random_oversampling_of_valid_minority_rows'}
    write_json(dest/'smote_report.json',report)
    return report

def collect_sources(pipeline_dir, allow_unverified=False):
    p=Path(pipeline_dir);result={}
    for ds in DATASETS:
        d=p/'sub-dataset'/ds
        files=raw_manifest(d);require(files,f'Missing raw files: {ds}')
        path=d/'raw/source_provenance.json'
        if path.is_file():
            info=json.loads(path.read_text(encoding='utf8'))
            require(info.get('files')==files,f'Raw/source provenance mismatch: {ds}')
        else:
            info={'mode':'supplied_local' if ds in ['NSL-KDD','UNSW-NB15'] else 'unverified','files':files,'note':'Existing local raw files; origin not independently authenticated'}
            if ds=='CIC-IDS2017':
                first=pd.read_csv(d/'raw/CIC_IDS2017_training-set.csv',nrows=100)
                if 'id' in first and first.id.astype(str).str.startswith(('CIC_BENIGN_','CIC_DOS_','CIC_PROBE_')).any():info['mode']='emulate'
        if ds in ['CIC-IDS2017','BoT-IoT'] and info['mode']!='online':
            require(allow_unverified,f'{ds}: {info["mode"]} source. Supply documented online raw data or explicitly use --allow-unverified-data for a diagnostic run.')
        result[ds]=info
    return result

def build_central(central_dir):
    c=Path(central_dir);p=c.parent
    diagnostic=os.environ.get('PIPELINE_ALLOW_UNVERIFIED')=='1'
    sources=collect_sources(p,diagnostic)
    parts=[];quarantine=[]
    for ds in DATASETS:
        d=p/'sub-dataset'/ds;verify_dataset(d)
        tables=read_tables(d/'output/harmonized');validate_tables(*tables,allow_quarantined=True)
        from harmonization_rules import quality_flags
        good=~quality_flags(tables[0],tables[2]).any(axis=1)
        quarantine.append({'source_dataset':ds,'source_rows':len(good),'eligible_rows':int(good.sum()),'quarantined_rows':int((~good).sum()),'quarantined_test_rows':int((~good & tables[2].source_split.astype(str).str.lower().isin(['test','kddtest'])).sum())})
        parts.append(tuple(t.loc[good].reset_index(drop=True) for t in tables))
    f,l,m=[pd.concat([t[i] for t in parts],ignore_index=True) for i in range(3)]
    l=map_labels(l,m);validate_tables(f,l,m)
    unavailable={flag:int((~m[flag].astype(str).str.lower().isin(['true','1'])).sum()) for flag in ['has_service','has_connection_state','has_protocol']}
    require(diagnostic or not any(unavailable.values()),f'Required attributes unavailable: {unavailable}. Supply measured fields or run diagnostic mode explicitly.')
    # Split entire identical model-input groups together, without reading y.
    groups=pd.util.hash_pandas_object(f[CORE],index=False)
    official=m.source_split.astype(str).str.lower()
    train_mask=official.isin(['train','kddtrain']);test_mask=official.isin(['test','kddtest'])
    require((train_mask|test_mask).all(),'Unknown source split')
    # Test features must not influence which training groups become validation.
    unique=np.sort(groups[train_mask].unique());rng=np.random.default_rng(42)
    val_groups=set(rng.permutation(unique)[:int(len(unique)*0.2)])
    m['data_split']=np.where(test_mask,'test',np.where(groups.isin(val_groups),'validation','train'))
    m['split_group']=groups.map(lambda v:f'core:{v:016x}')
    m=normalize_weights(m)
    o=c/'output';h=o/'harmonized';h.mkdir(parents=True,exist_ok=True)
    for name,frame in [('features',f),('labels',l),('metadata',m)]:frame.to_csv(h/(name+'.csv'),index=False)
    for split in ['train','train_full','validation','test']:
        mask=m.data_split.isin(['train','validation']) if split=='train_full' else m.data_split.eq(split)
        dest=o/'splits'/split;dest.mkdir(parents=True,exist_ok=True)
        frames=(f.loc[mask],l.loc[mask],normalize_weights(m.loc[mask]))
        for name,frame in zip(['features','labels','metadata'],frames):frame.to_csv(dest/(name+'.csv'),index=False)
    reports=o/'reports';reports.mkdir(exist_ok=True)
    pd.DataFrame(quarantine).to_csv(reports/'quarantine_summary.csv',index=False)
    write_json(o/'data_sources.json',sources)
    pd.crosstab([m.source_dataset,l.label_source_category],l.attack_category_id).to_csv(reports/'label_mapping.csv')
    pd.crosstab(m.source_dataset,m.data_split).to_csv(reports/'source_splits.csv')
    overlaps={}
    for a,b in [('train','validation'),('train','test'),('validation','test')]:
        aa=set(groups[m.data_split.eq(a)]);bb=groups[m.data_split.eq(b)]
        overlaps[a+'_'+b]={'matching_rows_in_second':int(bb.isin(aa).sum()),'unique_vectors':len(aa.intersection(set(bb)))}
    require(overlaps['train_validation']['matching_rows_in_second']==0,'Grouped validation split failed')
    write_json(reports/'overlap.json',{'comparison':'six shared raw model inputs; identical features need not be identical events','overlaps':overlaps,'conflicting_label_vectors':int(pd.DataFrame({'g':groups,'y':l.attack_category_id}).groupby('g').y.nunique().gt(1).sum()),'supplied_test_membership_preserved_for_eligible_records':True,'quarantined_test_rows':sum(v['quarantined_test_rows'] for v in quarantine)})
    write_json(o/'build_manifest.json',{'raw':{ds:raw_manifest(p/'sub-dataset'/ds) for ds in DATASETS},'code':code_signature(p),'rows':len(f),'split_policy':'seeded grouping of identical shared model inputs; original test rows preserved','unavailable_attributes':unavailable,'profile_scope':'diagnostic' if diagnostic else 'source_documented','class_taxonomy_note':'Project category mapping; MITRE fields are group annotations, not verified per-flow attribution'})
    return {'rows':len(f),'splits':m.data_split.value_counts().to_dict()}

def audit_pipeline(pipeline_dir, include_resampled=None):
    from harmonization_rules import quality_flags
    p=Path(pipeline_dir);o=p/'CENTRAL/output'
    build=json.loads((o/'build_manifest.json').read_text(encoding='utf8'))
    require(build['code']==code_signature(p),'Build code/config has changed')
    diagnostic=build['profile_scope']=='diagnostic'
    require(build['profile_scope'] in ['diagnostic','source_documented'],'Invalid profile scope')
    actual_sources=collect_sources(p,allow_unverified=diagnostic)
    sources=json.loads((o/'data_sources.json').read_text(encoding='utf8'))
    require(sources==actual_sources,'Source scope/provenance does not match current raw evidence')
    if include_resampled is None:
        include_resampled=any((o/'splits'/name).exists() for name in ['train_smote','train_full_smote'])
    report={'status':'passed','scope':build['profile_scope'],'resampled_checked':include_resampled,'datasets':{},'splits':{},'warnings':[]}
    source_tables=[];quarantine_rows=[]
    for ds in DATASETS:
        d=p/'sub-dataset'/ds;verify_dataset(d)
        require(build['raw'][ds]==raw_manifest(d),f'Build raw mismatch: {ds}')
        verify_manifest(d,d/'output/cleansing/source_manifest.csv')
        require(any((d/'output/cleansing'/name).is_file() for name in ['cleansing_audit.csv','cleaning_report.csv']),'Missing cleansing audit')
        f,l,m=read_tables(d/'output/harmonized');validate_tables(f,l,m,allow_quarantined=True)
        good=~quality_flags(f,m).any(axis=1)
        expected_labels=map_labels(l,m)
        pd.testing.assert_frame_equal(l[expected_labels.columns],expected_labels,check_dtype=False)
        if 'quality_ok' in m:
            q=read_tables(d/'output/harmonized/quarantine')
            for actual,expected in zip(q,[f.loc[~good],l.loc[~good],m.loc[~good]]):
                pd.testing.assert_frame_equal(actual.reset_index(drop=True),expected.reset_index(drop=True),check_dtype=False)
        source_tables.append(tuple(t.loc[good].reset_index(drop=True) for t in [f,l,m]))
        report['datasets'][ds]={'rows':len(f),'eligible_rows':int(good.sum()),'quarantined_rows':int((~good).sum())}
        quarantine_rows.append({'source_dataset':ds,'source_rows':len(f),'eligible_rows':int(good.sum()),'quarantined_rows':int((~good).sum()),'quarantined_test_rows':int((~good & m.source_split.astype(str).str.lower().isin(['test','kddtest'])).sum())})
    qr=pd.read_csv(o/'reports/quarantine_summary.csv')
    pd.testing.assert_frame_equal(qr,pd.DataFrame(quarantine_rows),check_dtype=False)
    f,l,m=read_tables(o/'harmonized');validate_tables(f,l,m)
    source_f,source_l,source_m=[pd.concat([t[i] for t in source_tables],ignore_index=True) for i in range(3)]
    pd.testing.assert_frame_equal(f,source_f,check_dtype=False)
    pd.testing.assert_frame_equal(l,map_labels(source_l,source_m),check_dtype=False)
    for col in source_m.columns.difference(['data_split','split_group','sample_weight']):
        pd.testing.assert_series_equal(m[col],source_m[col],check_dtype=False,check_names=False)
    require(len(f)==build['rows'],'Build row count mismatch')
    actual_unavailable={flag:int((~m[flag].astype(str).str.lower().isin(['true','1'])).sum()) for flag in ['has_service','has_connection_state','has_protocol']}
    require(actual_unavailable==build['unavailable_attributes'],'Availability counts disagree with build manifest')
    if not diagnostic:require(not any(actual_unavailable.values()),'Documented-source profile has unavailable required fields')
    original_test=source_m.source_split.astype(str).str.lower().isin(['test','kddtest'])
    original_train=source_m.source_split.astype(str).str.lower().isin(['train','kddtrain'])
    require((original_test|original_train).all(),'Invalid source split')
    require(set(m.loc[m.data_split.eq('test'),'record_id'])==set(source_m.loc[original_test,'record_id']),'Supplied test records changed split membership')
    require(set(m.loc[m.data_split.isin(['train','validation']),'record_id'])==set(source_m.loc[original_train,'record_id']),'Train/validation contains supplied test records')
    hashes=pd.util.hash_pandas_object(f[CORE],index=False)
    expected_groups=hashes.map(lambda value:f'core:{value:016x}').astype('string')
    require(m.split_group.astype('string').equals(expected_groups),'split_group does not match actual model inputs')
    ids={};groups={};pre=joblib.load(o/'feature_engineering/preprocessor.joblib')
    schema=json.loads((o/'feature_engineering/feature_schema.json').read_text(encoding='utf8'))
    require(schema['model_feature_names']==NAMES and pre['model_feature_names']==NAMES,'Preprocessor schema mismatch')
    for split in ['train','train_full','validation','test']:
        sf,sl,sm=read_tables(o/'splits'/split);validate_tables(sf,sl,sm)
        mask=m.data_split.isin(['train','validation']) if split=='train_full' else m.data_split.eq(split)
        for actual,wanted in [(sf,f.loc[mask]),(sl,l.loc[mask]),(sm,normalize_weights(m.loc[mask]))]:
            pd.testing.assert_frame_equal(actual.reset_index(drop=True),wanted.reset_index(drop=True),check_dtype=False)
        ids[split]=set(sf.record_id)
        groups[split]=set(pd.util.hash_pandas_object(sf[CORE],index=False))
        ef,el,em=read_tables(o/'feature_engineering'/split)
        pd.testing.assert_frame_equal(el,sl,check_dtype=False);pd.testing.assert_frame_equal(em,sm,check_dtype=False)
        require(list(ef.columns)==['record_id']+NAMES,f'{split}: encoded schema mismatch')
        require(ef.record_id.equals(sf.record_id),'Encoded IDs mismatch')
        require(np.allclose(ef[NAMES].to_numpy(),transform_features(sf,pre)[NAMES].to_numpy()),'Encoded transformation mismatch')
        report['splits'][split]={'rows':len(sf),'classes':sl.attack_category_id.value_counts().to_dict()}
    train=read_tables(o/'splits/train')[0];fresh=fit_preprocessor(train)
    require(pre['fit_split']=='train' and pre['fit_record_ids_sha256']==fresh['fit_record_ids_sha256'],'Preprocessor fit IDs mismatch')
    require(np.allclose(pre['scaler'].mean_,fresh['scaler'].mean_) and np.allclose(pre['scaler'].scale_,fresh['scaler'].scale_),'Scaler was not fitted on train')
    for actual,expected in zip(pre['encoder'].categories_,fresh['encoder'].categories_):require(np.array_equal(actual,expected),'Encoder vocabulary/order mismatch')
    require(not ids['train'].intersection(ids['validation']) and not ids['train_full'].intersection(ids['test']),'Record ID leakage')
    require(ids['train']|ids['validation']==ids['train_full'],'train_full is not train union validation')
    require(ids['train_full']|ids['test']==set(f.record_id),'Split coverage mismatch')
    require(not groups['train'].intersection(groups['validation']),'Identical model inputs cross train/validation')
    if groups['train_full'].intersection(groups['test']):report['warnings'].append('Retained source test contains feature vectors also seen in training; report sensitivity metrics.')
    if any(actual_unavailable.values()):report['warnings'].append(f'Unavailable attributes: {actual_unavailable}')
    if 'service_basis' in m and m.service_basis.eq('destination_port_hint').any():report['warnings'].append('Port-based service groups are hints, not identified application protocols.')
    if diagnostic:report['warnings'].append('Diagnostic run permits unverified/demo data; not official benchmark certification.')
    if any(v['quarantined_rows'] for v in quarantine_rows):report['warnings'].append('Conflicting source rows, including source test rows, are explicitly quarantined. Report exclusions in evaluation.')
    synth_sets=[]
    if include_resampled:
        for split in ['train','train_full']:
            dest=o/'splits'/(split+'_smote');sf,sl,sm=read_tables(dest);validate_tables(sf,sl,sm)
            original=read_tables(o/'splits'/split);n=len(original[0])
            for actual,wanted in zip([sf,sl,sm],original):
                cols=[v for v in wanted.columns if v!='sample_weight']
                pd.testing.assert_frame_equal(actual.iloc[:n][cols].reset_index(drop=True),wanted[cols].reset_index(drop=True),check_dtype=False)
            require(sl.is_synthetic.equals(sm.is_synthetic),'Synthetic markers disagree')
            require((~sm.is_synthetic.iloc[:n]).all() and sm.is_synthetic.iloc[n:].all(),'Invalid synthetic placement')
            require(sm.sample_weight.eq(1).all(),'Resampled rows must have uniform weights')
            sr=json.loads((dest/'smote_report.json').read_text(encoding='utf8'))
            target=sr['target_class_id'];require(target in range(6),'Invalid resampling target class')
            before=int(original[1].attack_category_id.eq(target).sum());after=int(sl.attack_category_id.eq(target).sum())
            require(sr['method']=='SMOTENC' and sr['source_split']==split,'Resampling method/source split mismatch')
            require(sr['original_target_count']==before and after==max(before,sr['target_samples']),'Resampling target count mismatch')
            require(sr['original_rows']==n and sr['total_rows']==len(sf) and sr['synthetic_rows']==len(sf)-n==max(0,sr['target_samples']-before),'Resampling report mismatch')
            require(sr['preprocessor_fit_split']=='train' and sr['preprocessor_fit_record_ids_sha256']==pre['fit_record_ids_sha256'],'Resampling preprocessor mismatch')
            require(sl.attack_category_id.iloc[n:].eq(target).all(),'Wrong synthetic class')
            require(sr['fallback_rows']<=sr['synthetic_rows'] and sr['fallback_rows']>=0,'Invalid fallback count')
            z=pd.read_csv(dest/'features_encoded_19.csv',low_memory=False)
            require(list(z.columns)==['record_id']+NAMES and z.record_id.astype(str).tolist()==sf.record_id.astype(str).tolist(),'Resampled encoding IDs/schema mismatch')
            require(np.allclose(z[NAMES],transform_features(sf,pre)[NAMES]),'Resampled transform mismatch')
            synth_sets.append(set(sf.record_id.iloc[n:]))
            report['splits'][split+'_smote']={'rows':len(sf),'synthetic_rows':len(sf)-n,'fallback_rows':sr['fallback_rows']}
        require(not synth_sets[0].intersection(synth_sets[1]),'Synthetic IDs collide between runs')
    write_json(o/'reports/audit.json',report)
    return report
