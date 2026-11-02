"""Compare shared features using train_full only; never pair unrelated rows."""
from pathlib import Path
from itertools import combinations
import json
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, chi2_contingency
from scipy.spatial.distance import jensenshannon

BASE = Path(__file__).resolve().parent
OUT = BASE / 'output' / 'reports' / 'dataset_relationships'
NUM = ['duration', 'bytes_forward', 'bytes_backward']
CAT = ['protocol', 'service_group', 'conn_state_group']

def main():
    root = BASE / 'output' / 'splits' / 'train_full'
    f, m, y = [pd.read_csv(root / (n + '.csv'), low_memory=False) for n in ['features', 'metadata', 'labels']]
    for frame in [f, m, y]:
        assert frame.record_id.is_unique
    assert set(f.record_id) == set(m.record_id) == set(y.record_id)
    df = f.merge(m[['record_id', 'source_dataset']], on='record_id', validate='one_to_one').merge(y[['record_id', 'label_binary']], on='record_id', validate='one_to_one')
    assert np.isfinite(df[NUM].to_numpy()).all() and (df[NUM] >= 0).all().all()
    assert df[CAT].notna().all().all()
    sources = ['NSL-KDD', 'UNSW-NB15']
    counts, corr, shifts, cats, assoc = [], [], [], [], []
    for scope, subset in [('all', df), ('normal', df[df.label_binary == 0]), ('attack', df[df.label_binary == 1])]:
        groups = {s: subset[subset.source_dataset == s] for s in sources}
        for source, g in groups.items():
            counts.append(dict(scope=scope, source=source, rows=len(g)))
            for transform, z in [('raw', g[NUM]), ('log1p', np.log1p(g[NUM]))]:
                for method in ['pearson', 'spearman']:
                    matrix = z.corr(method=method)
                    for a, b in combinations(NUM, 2):
                        corr.append(dict(scope=scope, source=source, transform=transform, method=method, feature_a=a, feature_b=b, correlation=matrix.loc[a,b]))
            for a,b in combinations(CAT,2):
                tab = pd.crosstab(g[a], g[b])
                dim = min(tab.shape)-1
                v = np.sqrt(chi2_contingency(tab, correction=False)[0]/tab.to_numpy().sum()/dim) if dim > 0 else np.nan
                assoc.append(dict(scope=scope,source=source,feature_a=a,feature_b=b,cramers_v=v))
        for col in NUM:
            a,b = [groups[s][col].to_numpy() for s in sources]
            shifts.append(dict(scope=scope,feature=col,ks_statistic=ks_2samp(a,b,method='asymp').statistic,nsl_median=np.median(a),unsw_median=np.median(b),nsl_q95=np.quantile(a,.95),unsw_q95=np.quantile(b,.95),nsl_zero_rate=np.mean(a==0),unsw_zero_rate=np.mean(b==0)))
        for col in CAT:
            categories = sorted(subset[col].unique())
            probs = [groups[s][col].value_counts(normalize=True).reindex(categories,fill_value=0) for s in sources]
            distance = jensenshannon(probs[0],probs[1],base=2)
            for category in categories:
                cats.append(dict(scope=scope,feature=col,category=category,nsl_proportion=probs[0][category],unsw_proportion=probs[1][category],js_distance=distance))
    OUT.mkdir(parents=True,exist_ok=True)
    tables = {'sample_counts':pd.DataFrame(counts),'numeric_correlations':pd.DataFrame(corr),'numeric_distribution_shift':pd.DataFrame(shifts),'categorical_distribution_shift':pd.DataFrame(cats),'categorical_associations':pd.DataFrame(assoc)}
    c = tables['numeric_correlations']
    delta = c.pivot(index=['scope','transform','method','feature_a','feature_b'],columns='source',values='correlation').reset_index()
    delta['absolute_difference'] = (delta['NSL-KDD']-delta['UNSW-NB15']).abs()
    tables['correlation_comparison'] = delta
    for name,table in tables.items():
        table.to_csv(OUT/(name+'.csv'),index=False)
    manifest = {'input_split':'train_full','test_used':False,'label_used_for':'descriptive normal/attack stratification only','unpaired_datasets':True,'numeric_features':NUM,'categorical_features':CAT,'notes':['Correlation compares columns within each dataset, never row-pairs across datasets.','KS and Jensen-Shannon are descriptive distribution distances, not semantic equivalence tests.','Normal/attack comparisons do not remove all protocol/service composition differences.','Cramers V is uncorrected and not directional.','Results describe existing harmonization; byte semantics still require source documentation.']}
    (OUT/'analysis_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(tables['sample_counts'].to_string(index=False))
    print('\nSPEARMAN COMPARISON\n'+delta[(delta['method']=='spearman')&(delta['transform']=='raw')].to_string(index=False))
    print('\nNUMERIC SHIFT\n'+tables['numeric_distribution_shift'].to_string(index=False))
    print('\nCATEGORY DISTANCES\n'+tables['categorical_distribution_shift'].groupby(['scope','feature']).js_distance.first().to_string())
    print('\nCATEGORY ASSOCIATIONS\n'+tables['categorical_associations'].to_string(index=False))

if __name__ == '__main__':
    main()
