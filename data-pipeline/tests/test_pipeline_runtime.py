import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P))
import pipeline_runtime as rt


def tables(n=30):
    f=pd.DataFrame({'record_id':[f'row:{i}' for i in range(n)],'duration':np.arange(n)/10,
                    'bytes_forward':np.arange(n)*7,'bytes_backward':np.arange(n)*3,
                    'protocol':['tcp','udp','icmp']*(n//3),
                    'service_group':['http','dns','other']*(n//3),
                    'conn_state_group':['established','no-reply','reset']*(n//3)})
    ids=pd.Series([4]*8+[0]*(n-8))
    l=pd.DataFrame({'record_id':f.record_id,'label_raw':'test','label_source_category':ids.map({4:'R2L',0:'Normal'}),
                    'attack_category':ids.map(dict(enumerate(rt.CLASS_NAMES))),'attack_category_id':ids,
                    'label_binary':ids.ne(0).astype(int),'mitre_tactic':ids.map(dict(enumerate(rt.TACTICS)))})
    m=pd.DataFrame({'record_id':f.record_id,'source_dataset':'NSL-KDD','source_split':'train',
                    'data_split':'train','sample_weight':1.0,'split_group':f.record_id})
    return f,l,m


class PipelineRegressionTests(unittest.TestCase):
    def test_cic_mapping_and_unknown_rejection(self):
        labels=pd.DataFrame({'label_source_category':['BENIGN','DoS Hulk','PortScan','SSH-Patator','Web Attack - Brute Force'], 'label_binary':[0,1,1,1,1]})
        meta=pd.DataFrame({'source_dataset':['CIC-IDS2017']*5})
        self.assertEqual(rt.map_labels(labels,meta).attack_category_id.tolist(),[0,1,2,4,4])
        labels.loc[2,'label_source_category']='future-unknown-attack'
        with self.assertRaisesRegex(ValueError,'Unmapped labels'):rt.map_labels(labels,meta)

    def test_mapping_preserves_binary_truth(self):
        labels=pd.DataFrame({'label_source_category':['Normal'],'label_binary':[1]})
        with self.assertRaisesRegex(ValueError,'binary truth'):
            rt.map_labels(labels,pd.DataFrame({'source_dataset':['NSL-KDD']}))

    def test_invalid_data_is_rejected(self):
        for value in [-1,np.nan,np.inf]:
            f,l,m=tables();f.loc[0,'duration']=value
            with self.assertRaisesRegex(ValueError,'duration'):rt.validate_tables(f,l,m)
        f,l,m=tables();l.loc[0,'record_id']='wrong'
        with self.assertRaisesRegex(ValueError,'mismatch'):rt.validate_tables(f,l,m)
        f,l,m=tables();f['attack_category_id']=0
        with self.assertRaisesRegex(ValueError,'leakage'):rt.validate_tables(f,l,m)

    def test_stale_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);(d/'raw').mkdir();raw=d/'raw/data.csv';raw.write_text('value\n1\n')
            pd.DataFrame(rt.raw_manifest(d)).to_csv(d/'manifest.csv',index=False)
            rt.verify_manifest(d,d/'manifest.csv')
            raw.write_text('value\n2\n')
            with self.assertRaisesRegex(ValueError,'Stale'):rt.verify_manifest(d,d/'manifest.csv')

    def test_smotenc_outputs_use_identical_saved_preprocessing(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp);f,l,m=tables()
            for split in ['train','train_full','validation','test']:
                dest=c/'output/splits'/split;dest.mkdir(parents=True)
                for name,frame in zip(['features','labels','metadata'],[f,l,m]):frame.to_csv(dest/(name+'.csv'),index=False)
            rt.engineer(c)
            reports=[rt.resample(c,split,target_samples=14) for split in ['train','train_full']]
            self.assertEqual([r['synthetic_rows'] for r in reports],[6,6])
            synth=[]
            for split in ['train','train_full']:
                sf,sl,sm=rt.read_tables(c/'output/splits'/(split+'_smote'))
                self.assertTrue(sm.sample_weight.eq(1).all())
                self.assertTrue(sl.attack_category_id.iloc[len(f):].eq(4).all())
                for col,values in rt.CATEGORIES.items():self.assertTrue(sf[col].isin(values).all())
                z=pd.read_csv(c/'output/splits'/(split+'_smote')/'features_encoded_19.csv')
                for prefix in rt.PREFIXES:
                    block=z[[col for col in z if col.startswith(prefix+'_')]]
                    self.assertTrue(block.isin([0,1]).all().all())
                    self.assertTrue(block.sum(axis=1).eq(1).all())
                synth.append(set(sf.record_id.iloc[len(f):]))
            self.assertFalse(synth[0]&synth[1])
            with self.assertRaisesRegex(ValueError,'training splits'):rt.resample(c,'test')

    def test_online_failures_never_generate_demo_data(self):
        for ds in ['CIC-IDS2017','BoT-IoT']:
            spec=importlib.util.spec_from_file_location('downloader',P/'sub-dataset'/ds/'download.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            func='download_real_cic' if ds=='CIC-IDS2017' else 'download_real_bot'
            with tempfile.TemporaryDirectory() as temp,patch.object(mod,'RAW_DIR',Path(temp)),patch.object(mod,func,side_effect=RuntimeError('offline')),patch.object(sys,'argv',['download.py','--source','online']):
                with self.assertRaisesRegex(RuntimeError,'no emulation fallback'):mod.main()
                self.assertEqual(list(Path(temp).glob('*.csv')),[])

    def test_complete_audit_rejects_corrupt_split_and_stale_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data-pipeline';c=p/'CENTRAL'
            for ds,attack in [('NSL-KDD','R2L'),('UNSW-NB15','Exploits'),('CIC-IDS2017','SSH-Patator'),('BoT-IoT','DoS')]:
                d=p/'sub-dataset'/ds;(d/'raw').mkdir(parents=True)
                (d/'raw/data.csv').write_text('value\n1\n')
                clean=d/'output/cleansing';clean.mkdir(parents=True)
                pd.DataFrame(rt.raw_manifest(d)).to_csv(clean/'source_manifest.csv',index=False)
                pd.DataFrame({'rows':[30]}).to_csv(clean/'cleansing_audit.csv',index=False)
                f,l,m=tables();f.record_id=ds+':'+f.record_id;l.record_id=f.record_id;m.record_id=f.record_id
                l=l.drop(columns='attack_category_id');l.loc[:7,'label_source_category']=attack
                if ds=='UNSW-NB15':l['label_raw']=l.label_binary.astype(int)
                m['source_dataset']=ds;m['orig_row_id']=np.arange(len(m));m.loc[24:,'source_split']='test'
                for flag in ['has_service','has_connection_state','has_protocol']:m[flag]=True
                dest=d/'output/harmonized';dest.mkdir()
                for name,frame in zip(['features','labels','metadata'],[f,l,m]):frame.to_csv(dest/(name+'.csv'),index=False)
                pd.DataFrame(rt.raw_manifest(d)).to_csv(dest/'source_manifest.csv',index=False)
                rt.stamp_dataset(d)
            with patch.dict('os.environ',{'PIPELINE_ALLOW_UNVERIFIED':'1'}):rt.build_central(c)
            rt.write_json(c/'output/data_sources.json',{ds:{'mode':'unverified','files':rt.raw_manifest(p/'sub-dataset'/ds)} for ds in rt.DATASETS})
            rt.engineer(c)
            self.assertEqual(rt.audit_pipeline(p)['status'],'passed')
            original_train=set(rt.read_tables(c/'output/splits/train')[0].record_id)
            # Test-only changes must not alter the validation assignment of training data.
            for ds in rt.DATASETS:
                d=p/'sub-dataset'/ds
                sf,sl,sm=rt.read_tables(d/'output/harmonized')
                sf.loc[sm.source_split.eq('test'),'duration']+=999
                sf.to_csv(d/'output/harmonized/features.csv',index=False)
                rt.stamp_dataset(d)
            with patch.dict('os.environ',{'PIPELINE_ALLOW_UNVERIFIED':'1'}):rt.build_central(c)
            rt.engineer(c)
            self.assertEqual(original_train,set(rt.read_tables(c/'output/splits/train')[0].record_id))
            self.assertEqual(rt.audit_pipeline(p)['status'],'passed')
            real_read=pd.read_csv
            for value in [-1,np.nan,np.inf]:
                def corrupt(path,*args,**kwargs):
                    z=real_read(path,*args,**kwargs)
                    if Path(path)==c/'output/splits/train/features.csv':z.loc[0,'duration']=value
                    return z
                with patch.object(pd,'read_csv',side_effect=corrupt):
                    with self.assertRaisesRegex(ValueError,'duration'):rt.audit_pipeline(p)
            (p/'sub-dataset/NSL-KDD/raw/data.csv').write_text('value\n2\n')
            with self.assertRaisesRegex(ValueError,'Raw changed'):rt.audit_pipeline(p)

    def test_demo_preparation_records_source_mode_and_cannot_be_relabelled_online(self):
        import json
        for ds in ['CIC-IDS2017','BoT-IoT']:
            spec=importlib.util.spec_from_file_location('downloader',P/'sub-dataset'/ds/'download.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            with tempfile.TemporaryDirectory() as temp:
                raw=Path(temp)/'raw';raw.mkdir()
                with patch.object(mod,'RAW_DIR',raw),patch.object(sys,'argv',['download.py','--source','emulate','--train_samples','12','--test_samples','6']):mod.main()
                saved=(raw/'source_provenance.json').read_text()
                provenance=json.loads(saved)
                self.assertEqual(provenance['mode'],'emulate')
                self.assertEqual(provenance['files'],rt.raw_manifest(raw.parent))
                # Merely invoking online mode with existing files cannot bless demo input.
                with patch.object(mod,'RAW_DIR',raw),patch.object(sys,'argv',['download.py','--source','online']):mod.main()
                self.assertEqual((raw/'source_provenance.json').read_text(),saved)

    def test_publish_failure_restores_previous_outputs(self):
        import shutil
        spec=importlib.util.spec_from_file_location('runner',P/'build_quad_dataset.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/'project';stage=project/'runs/work';pipeline=project/'data-pipeline'
            paths=[Path('data-pipeline/sub-dataset')/ds/'output/harmonized' for ds in rt.DATASETS]+[Path('data-pipeline/CENTRAL/output')]
            for rel in paths:
                (project/rel).mkdir(parents=True);(project/rel/'old.txt').write_text('old')
                (stage/rel).mkdir(parents=True);(stage/rel/'new.txt').write_text('new')
            real_move=shutil.move;calls=0
            def interrupted(*args,**kwargs):
                nonlocal calls
                calls+=1
                if calls==3:raise OSError('simulated publish failure')
                return real_move(*args,**kwargs)
            with patch.object(runner,'PROJECT_ROOT',project),patch.object(runner,'PIPELINE_DIR',pipeline),patch.object(runner,'DATASETS_DIR',pipeline/'sub-dataset'),patch.object(runner.shutil,'move',side_effect=interrupted):
                with self.assertRaisesRegex(OSError,'simulated'):runner.publish(stage,project/'archive')
            for rel in paths:
                self.assertEqual((project/rel/'old.txt').read_text(),'old')
                self.assertEqual((stage/rel/'new.txt').read_text(),'new')


if __name__=='__main__':unittest.main()
