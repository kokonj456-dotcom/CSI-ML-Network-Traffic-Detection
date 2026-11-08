"""Regression cases reproduced by the second pipeline review."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pipeline_runtime as rt
from test_pipeline_runtime import tables


def make_fixture(p):
    cleaned={'NSL-KDD':['KDDTrain_clean.csv','KDDTest_clean.csv','KDDTest-21_clean.csv'],
             'UNSW-NB15':['UNSW_NB15_training-set.csv','UNSW_NB15_testing-set.csv'],
             'CIC-IDS2017':['CIC_IDS2017_training-set.csv','CIC_IDS2017_testing-set.csv'],
             'BoT-IoT':['BoT_IoT_training-set.csv','BoT_IoT_testing-set.csv']}
    for ds,attack in [('NSL-KDD','R2L'),('UNSW-NB15','Exploits'),('CIC-IDS2017','SSH-Patator'),('BoT-IoT','DoS')]:
        d=p/'sub-dataset'/ds;(d/'raw').mkdir(parents=True)
        (d/'raw/data.csv').write_text('value\n1\n')
        if ds=='CIC-IDS2017':(d/'raw/CIC_IDS2017_training-set.csv').write_text('id\nfixture\n')
        clean=d/'output/cleansing';clean.mkdir(parents=True)
        pd.DataFrame(rt.raw_manifest(d)).to_csv(clean/'source_manifest.csv',index=False)
        pd.DataFrame({'rows':[30]}).to_csv(clean/'cleansing_audit.csv',index=False)
        for name in cleaned[ds]:(clean/name).write_text('fixture\n1\n')
        f,l,m=tables();f.record_id=ds+':'+f.record_id;l.record_id=f.record_id;m.record_id=f.record_id
        m['source_dataset']=ds;m['orig_row_id']=np.arange(len(m));m.loc[24:,'source_split']='test'
        for flag in ['has_service','has_connection_state','has_protocol']:m[flag]=True
        l.loc[:7,'label_source_category']=attack;l=rt.map_labels(l,m)
        from harmonization_rules import quality_flags
        m['source_protocol']=f.protocol;m['source_connection_state']=f.conn_state_group;m['source_service']=f.service_group
        m['service_basis']='source_service_name';m['service_identified']=True;m['state_reclassified']=False
        m['connection_state_basis']='fixture';m['duration_unit']='seconds';m['quality_issues']=''
        for flag in ['invalid_duration','invalid_bytes_forward','invalid_bytes_backward']:m[flag]=False
        flags=quality_flags(f,m)
        for col in flags:m[col]=flags[col]
        m['quality_ok']=~flags.any(axis=1)
        m['has_duration']=True;m['has_directional_bytes']=True;m['has_packet_stats']=False
        l['source_attack_category']=l.attack_category
        dest=d/'output/harmonized';dest.mkdir()
        for name,frame in zip(['features','labels','metadata'],[f,l,m]):frame.to_csv(dest/(name+'.csv'),index=False)
        pd.DataFrame(rt.raw_manifest(d)).to_csv(dest/'source_manifest.csv',index=False)
        rt.stamp_dataset(d)
    c=p/'CENTRAL'
    with patch.dict('os.environ',{'PIPELINE_ALLOW_UNVERIFIED':'1'}):rt.build_central(c)
    rt.engineer(c)
    return c


def rewrite_splits(c,f,l,m):
    for name,frame in zip(['features','labels','metadata'],[f,l,m]):frame.to_csv(c/'output/harmonized'/(name+'.csv'),index=False)
    for split in ['train','train_full','validation','test']:
        mask=m.data_split.isin(['train','validation']) if split=='train_full' else m.data_split.eq(split)
        for name,frame in zip(['features','labels','metadata'],[f.loc[mask],l.loc[mask],rt.normalize_weights(m.loc[mask])]):frame.to_csv(c/'output/splits'/split/(name+'.csv'),index=False)
    rt.engineer(c)


class AuditInvariantTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p=Path(self.temp.name)/'data-pipeline';self.c=make_fixture(self.p)

    def test_supplied_test_cannot_be_moved_to_train(self):
        f,l,m=rt.read_tables(self.c/'output/harmonized')
        i=m.index[m.source_split.eq('test')][0];m.loc[i,'data_split']='train'
        rewrite_splits(self.c,f,l,m)
        with self.assertRaisesRegex(ValueError,'test records changed split'):rt.audit_pipeline(self.p)

    def test_fake_group_cannot_hide_identical_features(self):
        f,l,m=rt.read_tables(self.c/'output/harmonized')
        i=m.index[m.data_split.eq('train')][0];m.loc[i,'data_split']='validation';m.loc[i,'split_group']='fake'
        rewrite_splits(self.c,f,l,m)
        with self.assertRaisesRegex(ValueError,'split_group'):rt.audit_pipeline(self.p)

    def test_unverified_scope_cannot_be_documented(self):
        q=self.c/'output/build_manifest.json'
        import json
        b=json.loads(q.read_text());b['profile_scope']='source_documented';rt.write_json(q,b)
        with self.assertRaisesRegex(ValueError,'unverified source'):rt.audit_pipeline(self.p)

    def test_missing_cleaned_file_fails(self):
        (self.p/'sub-dataset/NSL-KDD/output/cleansing/KDDTrain_clean.csv').unlink()
        with self.assertRaisesRegex(ValueError,'Missing cleaned file'):rt.audit_pipeline(self.p)

    def test_wrong_resampling_target_is_rejected_and_auto_detected(self):
        for split in ['train','train_full']:rt.resample(self.c,split,target_samples=40)
        self.assertTrue(rt.audit_pipeline(self.p)['resampled_checked'])
        q=self.c/'output/splits/train_smote/smote_report.json'
        import json
        b=json.loads(q.read_text());b['target_samples']=999999;rt.write_json(q,b)
        with self.assertRaisesRegex(ValueError,'target count'):rt.audit_pipeline(self.p)

    def test_conflicting_source_records_are_retained_in_quarantine(self):
        from harmonization_rules import harmonize_tables
        d=self.p/'sub-dataset/CIC-IDS2017'
        f,l,m=rt.read_tables(d/'output/harmonized')
        f['packets_forward']=5;f['packets_backward']=np.where(f.bytes_backward.gt(0),1,0)
        f.loc[2,'packets_backward']=0
        source=pd.DataFrame({'protocol':f.protocol,'dest_port':80,'flow_state':f.conn_state_group})
        f,l,m=harmonize_tables('CIC-IDS2017',f,l,m,source)
        for name,frame in zip(['features','labels','metadata'],[f,l,m]):frame.to_csv(d/'output/harmonized'/(name+'.csv'),index=False)
        rt.stamp_dataset(d)
        with patch.dict('os.environ',{'PIPELINE_ALLOW_UNVERIFIED':'1'}):rt.build_central(self.c)
        rt.engineer(self.c)
        report=rt.audit_pipeline(self.p)
        self.assertEqual(report['datasets']['CIC-IDS2017']['quarantined_rows'],1)
        self.assertNotIn('CIC-IDS2017:row:2',set(rt.read_tables(self.c/'output/harmonized')[0].record_id))
        q=rt.read_tables(d/'output/harmonized/quarantine')
        self.assertEqual(q[0].record_id.tolist(),['CIC-IDS2017:row:2'])
        self.assertEqual(q[0].bytes_backward.iloc[0],6)


if __name__=='__main__':unittest.main()
