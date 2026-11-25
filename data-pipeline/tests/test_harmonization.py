import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harmonization_rules import harmonize_tables,normalize_protocol,port_to_service,quality_flags
from test_pipeline_runtime import tables
import pipeline_runtime as rt


class HarmonizationTests(unittest.TestCase):
    def test_unsw_cleansing_preserves_unidentified_service_marker(self):
        import json
        p=Path(__file__).resolve().parents[1]/'sub-dataset/UNSW-NB15/cleansing.ipynb'
        notebook=json.loads(p.read_text(encoding='utf8'))
        namespace={'pd':pd}
        import contextlib,io
        with contextlib.redirect_stdout(io.StringIO()):
            exec(''.join(notebook['cells'][4]['source']),namespace)
        source=pd.DataFrame({'service':['-','ftp-data',None]})
        cleaned=namespace['clean_chunk'](source)
        self.assertEqual(cleaned.service.iloc[0],'-')
        self.assertEqual(cleaned.service.iloc[1],'ftp-data')
        self.assertTrue(pd.isna(cleaned.service.iloc[2]))

    def test_protocol_and_port_validation(self):
        self.assertEqual(normalize_protocol(pd.Series([6,'17',1,58,'ipv6-icmp','TCP'])).tolist(),['tcp','udp','icmp','icmp','icmp','tcp'])
        self.assertTrue(pd.isna(normalize_protocol(pd.Series([None]))[0]))
        self.assertEqual(port_to_service('0x1bb'),'https_ssl')
        for invalid in [-1,443.9,float('inf'),'not-a-port',65536]:
            with self.assertRaises(ValueError):port_to_service(invalid)

    def test_nsl_states_and_service_aliases(self):
        f,l,m=tables(3)
        source=pd.DataFrame({'protocol_type':['tcp']*3,'service':['ftp_data','http_443','ftp-data'],'flag':['S1','S2','S3']})
        before=source.copy(deep=True)
        f,l,m=harmonize_tables('NSL-KDD',f,l,m,source)
        self.assertEqual(f.conn_state_group.tolist(),['established']*3)
        self.assertEqual(f.service_group.tolist(),['ftp','https_ssl','ftp'])
        self.assertTrue(m.quality_ok.all())
        pd.testing.assert_frame_equal(source,before)

    def test_unsw_unknown_service_and_single_taxonomy(self):
        f,l,m=tables(3);m['source_dataset']='UNSW-NB15';l['label_source_category']='Analysis'
        source=pd.DataFrame({'proto':['tcp']*3,'service':['ftp-data','-','dns'],'state':['CON']*3})
        f,l,m=harmonize_tables('UNSW-NB15',f,l,m,source)
        self.assertEqual(f.service_group.tolist(),['ftp','other','dns'])
        self.assertEqual(m.has_service.tolist(),[True,False,True])
        self.assertEqual(l.attack_category_id.tolist(),[2,2,2])
        self.assertTrue(l.attack_category.eq(rt.CLASS_NAMES[2]).all())

    def test_bot_request_with_response_is_not_no_reply(self):
        f,l,m=tables(3);m['source_dataset']='BoT-IoT';l['label_source_category']='DoS'
        f['packets_forward']=5;f['packets_backward']=[1,0,1];f['bytes_backward']=[60,0,60]
        source=pd.DataFrame({'proto':['tcp']*3,'state':['REQ','REQ','FIN']})
        f,l,m=harmonize_tables('BoT-IoT',f,l,m,source)
        self.assertEqual(f.conn_state_group.tolist(),['other','no-reply','established'])
        self.assertTrue(m.quality_ok.all())
        self.assertFalse(m.has_service.any())
        self.assertEqual(m.state_reclassified.tolist(),[True,False,False])

    def test_cic_conflicts_are_flagged_without_fabricating_counters(self):
        f,l,m=tables(3);m['source_dataset']='CIC-IDS2017';l['label_source_category']='SSH-Patator'
        f['packets_forward']=5;f['packets_backward']=[1,0,1];f['bytes_backward']=[60,60,60]
        source=pd.DataFrame({'protocol':[6,6,6],'dest_port':[22,22,None],'flow_state':['no-reply','established','established']})
        before=f[['packets_backward','bytes_backward']].copy()
        f,l,m=harmonize_tables('CIC-IDS2017',f,l,m,source)
        self.assertEqual(m.quality_ok.tolist(),[False,False,True])
        self.assertEqual(m.state_counter_conflict.tolist(),[True,False,False])
        self.assertEqual(m.bytes_packet_conflict.tolist(),[False,True,False])
        self.assertEqual(m.has_service.tolist(),[True,True,False])
        self.assertFalse(m.service_identified.any())
        pd.testing.assert_frame_equal(f[['packets_backward','bytes_backward']],before)
        rt.validate_tables(f,l,m,allow_quarantined=True)
        with self.assertRaisesRegex(ValueError,'quarantined'):rt.validate_tables(f,l,m)

    def test_bot_arp_port_sentinel_is_preserved_but_unavailable(self):
        f,l,m=tables(3);m['source_dataset']='BoT-IoT';l['label_source_category']='DoS'
        source=pd.DataFrame({'proto':['arp','tcp','udp'],'dport':['-1','443',53],'state':['CON']*3})
        f,l,m=harmonize_tables('BoT-IoT',f,l,m,source)
        self.assertEqual(f.service_group.tolist(),['other','https_ssl','dns'])
        self.assertEqual(m.has_service.tolist(),[False,True,True])
        self.assertEqual(m.source_service.tolist(),['-1','443','53'])
        source.loc[1,'dport']='-1'
        with self.assertRaisesRegex(ValueError,'Invalid destination port'):
            harmonize_tables('BoT-IoT',f,l,m,source)

    def test_partial_missing_protocol_marks_only_affected_row(self):
        f,l,m=tables(3);m['source_dataset']='BoT-IoT';l['label_source_category']='DoS'
        source=pd.DataFrame({'proto':['tcp',None,'udp'],'state':['FIN']*3})
        f,l,m=harmonize_tables('BoT-IoT',f,l,m,source)
        self.assertEqual(m.has_protocol.tolist(),[True,False,True])
        self.assertEqual(m.quality_ok.tolist(),[True,False,True])


if __name__=='__main__':unittest.main()
