"""Tune an Isolation Forest on the current CENTRAL diagnostic dataset.

The forest is unsupervised; labeled validation data selects its threshold and
hyperparameters. The held-out test split is evaluated only after selection.
"""
from pathlib import Path
import argparse, hashlib, json, time
from datetime import datetime
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_recall_curve, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data-pipeline' / 'CENTRAL' / 'output'

def load_split(name, columns):
    path = DATA / 'feature_engineering' / name
    features = pd.read_csv(path / 'features.csv')
    labels = pd.read_csv(path / 'labels.csv', usecols=['record_id', 'label_binary', 'attack_category'])
    meta = pd.read_csv(path / 'metadata.csv', usecols=['record_id', 'source_dataset', 'split_group'])
    assert features.record_id.equals(labels.record_id) and features.record_id.equals(meta.record_id), f'{name}: record_id mismatch'
    assert features.columns.tolist() == ['record_id'] + columns, f'{name}: feature schema mismatch'
    x = features[columns].to_numpy(dtype=np.float32)
    y = labels.label_binary.to_numpy(dtype=np.int8)
    assert np.isfinite(x).all() and set(np.unique(y)) == {0, 1}
    return x, y, labels, meta

def find_threshold(y, score):
    p, r, thresholds = precision_recall_curve(y, score)
    f = np.divide(2*p[:-1]*r[:-1], p[:-1]+r[:-1], out=np.zeros_like(p[:-1]), where=(p[:-1]+r[:-1]) != 0)
    i = int(np.argmax(f))
    return float(thresholds[i]), float(f[i])

def metrics(y, score, threshold):
    pred = score >= threshold
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {'rows': int(len(y)), 'attacks': int(y.sum()), 'threshold': float(threshold), 'precision': float(precision_score(y,pred,zero_division=0)), 'recall': float(recall_score(y,pred,zero_division=0)), 'f1': float(f1_score(y,pred,zero_division=0)), 'false_positive_rate': float(fp/(fp+tn)) if fp+tn else None, 'roc_auc': float(roc_auc_score(y,score)) if np.unique(y).size==2 else None, 'average_precision': float(average_precision_score(y,score)) if y.sum() else None, 'confusion_matrix': {'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)}}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--jobs',type=int,default=8)
    args=parser.parse_args()
    out=args.output or ROOT/'model'/'isolation-forest'/'backup'/('central_tuning_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    schema=json.loads((DATA/'feature_engineering'/'feature_schema.json').read_text())
    columns=schema['model_feature_names']
    xtrain,ytrain,_,_=load_split('train',columns)
    xv,yv,_,mv=load_split('validation',columns)
    rng=np.random.default_rng(args.seed)
    sample_idx,_=train_test_split(np.arange(len(yv)),train_size=min(60000,len(yv)-1),stratify=yv,random_state=args.seed)
    xs,ys=xv[sample_idx],yv[sample_idx]
    trials=[]; fitted=[]
    for mode in ['normal_only','all_train']:
        pool=np.flatnonzero(ytrain==0) if mode=='normal_only' else np.arange(len(ytrain))
        chosen=rng.choice(pool,size=min(120000,len(pool)),replace=False)
        for ntrees in [100,200]:
            for max_samples in [256,1024,4096]:
                for max_features in [0.6,1.0]:
                    cfg={'training_mode':mode,'n_estimators':ntrees,'max_samples':max_samples,'max_features':max_features,'bootstrap':False}
                    t=time.time(); model=IsolationForest(n_estimators=ntrees,max_samples=max_samples,max_features=max_features,bootstrap=False,random_state=args.seed,n_jobs=args.jobs).fit(xtrain[chosen])
                    score=-model.score_samples(xs)
                    threshold,f1=find_threshold(ys,score)
                    row={**cfg,'training_rows':len(chosen),'sample_validation_f1':f1,'sample_validation_threshold':threshold,'seconds':round(time.time()-t,2)}
                    trials.append(row); fitted.append((row,model))
                    print(json.dumps(row),flush=True)
                    pd.DataFrame(trials).to_csv(out/'search_progress.csv',index=False)
    # Evaluate the most promising candidates from each training mode on all validation rows.
    finalists=[]
    for mode in ['normal_only','all_train']:
        finalists.extend(sorted((v for v in fitted if v[0]['training_mode']==mode),key=lambda v:v[0]['sample_validation_f1'],reverse=True)[:4])
    results=[]
    for row, model in finalists:
        score=-model.score_samples(xv)
        threshold,_=find_threshold(yv,score)
        result={**row,'validation':metrics(yv,score,threshold)}
        results.append((result,model))
        print('FINALIST '+json.dumps(result),flush=True)
    best, model=max(results,key=lambda item:item[0]['validation']['f1'])
    threshold=best['validation']['threshold']
    # Load test only after model and threshold have been selected.
    xt,yt,lt,mt=load_split('test',columns)
    test_score=-model.score_samples(xt)
    test=metrics(yt,test_score,threshold)
    by_source={s:metrics(yt[mask],test_score[mask],threshold) for s in sorted(mt.source_dataset.unique()) for mask in [mt.source_dataset.to_numpy()==s]}
    categories={}
    predictions=test_score>=threshold
    for name in sorted(lt.attack_category.unique()):
        mask=(lt.attack_category.to_numpy()==name) & (yt==1)
        if mask.any(): categories[str(name)]={'rows':int(mask.sum()),'recall':float(predictions[mask].mean())}
    overlap=json.loads((DATA/'reports'/'overlap.json').read_text())
    unseen=~mt.split_group.isin(set(mv.split_group))
    # Do not use this diagnostic subset to select the model.
    unseen_metrics=metrics(yt[unseen],test_score[unseen],threshold) if len(np.unique(yt[unseen]))==2 else None
    artifacts={'model':model,'threshold':threshold,'feature_names':columns,'training_mode':best['training_mode'],'preprocessor':joblib.load(DATA/'feature_engineering'/'preprocessor.joblib'),'score_direction':'higher is more anomalous; -score_samples','schema_version':schema['schema_version']}
    joblib.dump(artifacts,out/'model.joblib',compress=3)
    report={'objective':'maximize binary attack F1 on validation; threshold chosen using validation labels','seed':args.seed,'selected':best,'finalists':[v[0] for v in results],'test':test,'test_by_source':by_source,'test_attack_category_recall':categories,'test_excluding_validation_feature_groups':unseen_metrics,'overlap_report':overlap,'dataset_scope':json.loads((DATA/'build_manifest.json').read_text())['profile_scope'],'notes':['Isolation Forest is an anomaly detector, not a multiclass classifier.','Validation labels are used for model and threshold selection; test is evaluated once after selection.','Test can share feature vectors with training; the validation-only overlap exclusion does not remove train overlap.','This dataset is diagnostic and includes unverified or demo sources.'],'input_hashes':{str(p.relative_to(DATA)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [DATA/'build_manifest.json',DATA/'feature_engineering'/'feature_schema.json',DATA/'feature_engineering'/'preprocessor.joblib']}}
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print('BEST '+json.dumps(best),flush=True)
    print('TEST '+json.dumps(test),flush=True)
    print('OUTPUT '+str(out),flush=True)

if __name__=='__main__': main()
