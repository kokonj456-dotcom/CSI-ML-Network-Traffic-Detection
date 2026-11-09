"""Shared, label-independent rules for the four source adapters.

Source measurements are retained. Conflicting records are marked for quarantine,
never repaired by guessing packet counts, bytes or attack labels.
"""
import numpy as np
import pandas as pd

SERVICE_ALIASES = {
    'http':'http', 'www':'http', 'http_443':'https_ssl',
    'https':'https_ssl', 'ssl':'https_ssl',
    'ftp':'ftp', 'ftp_data':'ftp', 'ftp-data':'ftp',
    'ssh':'ssh', 'smtp':'smtp', 'domain':'dns', 'domain_u':'dns', 'dns':'dns',
}
STATE_ALIASES = {
    'sf':'established', 's1':'established', 's2':'established', 's3':'established',
    'fin':'established', 'con':'established', 'established':'established',
    's0':'no-reply', 'req':'no-reply', 'int':'no-reply', 'no-reply':'no-reply',
    'rej':'reset', 'rsto':'reset', 'rstr':'reset', 'rstos0':'reset',
    'rst':'reset', 'reset':'reset',
}
QUALITY_FLAGS = ['invalid_required_value', 'bytes_packet_conflict', 'state_counter_conflict']


def normalize_boolean_metadata(metadata):
    columns=[c for c in metadata if c.startswith(('has_','invalid_')) or c in QUALITY_FLAGS+['quality_ok','service_identified','state_reclassified','dedup_flag','is_kddtest21_view']]
    for col in columns:
        values=metadata[col].astype('string').str.lower()
        if not values.isin(['true','false','1','0']).all():raise ValueError(f'Invalid boolean metadata: {col}')
        metadata[col]=values.map({'true':True,'false':False,'1':True,'0':False}).astype(bool)
    return metadata


def text(values):
    return values.astype('string').str.strip().str.lower().replace({'':'', '-':'-'})


def normalize_protocol(values):
    values=text(values).replace({'6':'tcp','6.0':'tcp','17':'udp','17.0':'udp',
                                 '1':'icmp','1.0':'icmp','58':'icmp','58.0':'icmp','ipv6-icmp':'icmp'})
    present=values.notna() & ~values.isin(['','-'])
    return values.where(values.isin(['tcp','udp','icmp']),'other').where(present,pd.NA)


def port_to_service(value):
    if pd.isna(value) or str(value).strip()=='':return 'other'
    token=str(value).strip()
    try:
        number=int(token,16) if token.lower().startswith('0x') else float(token)
    except (ValueError,TypeError) as error:
        raise ValueError(f'Invalid destination port: {value!r}') from error
    if not np.isfinite(number) or number!=int(number) or not 0<=number<=65535:
        raise ValueError(f'Invalid destination port: {value!r}')
    port=int(number)
    return {53:'dns',20:'ftp',21:'ftp',80:'http',8080:'http',443:'https_ssl',
            25:'smtp',465:'smtp',587:'smtp',22:'ssh'}.get(port,'other')


def quality_flags(features, metadata):
    f=features
    invalid=pd.Series(False,index=f.index)
    for col in ['duration','bytes_forward','bytes_backward']:
        values=pd.to_numeric(f[col],errors='coerce')
        invalid |= values.isna() | ~np.isfinite(values) | values.lt(0)
    invalid |= f.protocol.isna() | f.protocol.astype('string').str.strip().isin(['','-'])
    packet_conflict=pd.Series(False,index=f.index)
    for direction in ['forward','backward']:
        col='packets_'+direction
        if col in f:
            values=pd.to_numeric(f[col],errors='coerce')
            packet_conflict |= values.eq(0) & f['bytes_'+direction].gt(0)
            invalid |= f[col].notna() & (~np.isfinite(values) | values.lt(0))
    raw_state=text(metadata.get('source_connection_state',pd.Series(pd.NA,index=f.index,dtype='string')))
    has_response=f.bytes_backward.gt(0)
    if 'packets_backward' in f:has_response |= f.packets_backward.gt(0)
    # REQ/INT can have response traffic. Literal no-reply/S0 with a response is
    # contradictory source evidence; do not silently erase that evidence.
    state_conflict=raw_state.isin(['no-reply','s0']) & has_response
    return pd.DataFrame({'invalid_required_value':invalid,
                         'bytes_packet_conflict':packet_conflict,
                         'state_counter_conflict':state_conflict},index=f.index)


def harmonize_tables(dataset, features, labels, metadata, source):
    from pipeline_runtime import map_labels
    f=features.reset_index(drop=True).copy()
    l=labels.reset_index(drop=True).copy()
    m=metadata.reset_index(drop=True).copy()
    source=source.reset_index(drop=True)
    if not len(source)==len(f)==len(l)==len(m):raise ValueError('Source/output row count mismatch')
    for col in ['packets_forward','packets_backward']:
        if col not in f:f[col]=np.nan
    protocol_col={'NSL-KDD':'protocol_type','UNSW-NB15':'proto','CIC-IDS2017':'protocol','BoT-IoT':'proto'}[dataset]
    state_col={'NSL-KDD':'flag','UNSW-NB15':'state','CIC-IDS2017':'flow_state','BoT-IoT':'state'}[dataset]
    m['source_protocol']=source[protocol_col].astype('string')
    m['source_connection_state']=source[state_col].astype('string')
    f['protocol']=normalize_protocol(source[protocol_col])
    if dataset in ['NSL-KDD','UNSW-NB15']:
        service=text(source['service'])
        present=service.notna() & ~service.isin(['','-'])
        f['service_group']=service.map(SERVICE_ALIASES).fillna('other')
        m['source_service']=source['service'].astype('string')
        m['service_basis']='source_service_name'
        m['service_identified']=present
        m['has_service']=present
    else:
        port='dest_port' if dataset=='CIC-IDS2017' else 'dport'
        values=source[port] if port in source else pd.Series(pd.NA,index=source.index,dtype='string')
        present=values.notna() & values.astype('string').str.strip().ne('')
        f['service_group']=values.map(port_to_service)
        m['source_service']=values.astype('string')
        m['service_basis']=np.where(present,'destination_port_hint','unavailable')
        m['service_identified']=False  # Port 443 is a hint, not proof of TLS.
        m['has_service']=present
    state=text(source[state_col])
    present_state=state.notna() & ~state.isin(['','-'])
    base=state.map(STATE_ALIASES).fillna('other')
    response=f.bytes_backward.gt(0)
    if 'packets_backward' in f:response |= f.packets_backward.gt(0)
    f['conn_state_group']=base.mask(base.eq('no-reply') & response,'other')
    m['state_reclassified']=base.ne(f.conn_state_group)
    m['connection_state_basis']='source_state_and_directional_counters'
    m['has_connection_state']=present_state
    m['has_duration']=f.duration.notna()
    m['has_protocol']=f.protocol.notna()
    m['has_directional_bytes']=f[['bytes_forward','bytes_backward']].notna().all(axis=1)
    m['has_packet_stats']=f[['packets_forward','packets_backward']].notna().all(axis=1)
    for col,out in [('duration','invalid_duration'),('bytes_forward','invalid_bytes_forward'),('bytes_backward','invalid_bytes_backward')]:
        values=pd.to_numeric(f[col],errors='coerce')
        m[out]=values.isna() | ~np.isfinite(values) | values.lt(0)
    flags=quality_flags(f,m)
    for col in QUALITY_FLAGS:m[col]=flags[col]
    m['quality_ok']=~flags.any(axis=1)
    m['quality_issues']=[';'.join(c for c in QUALITY_FLAGS if row[c]) for row in flags.to_dict('records')]
    m['duration_unit']='seconds'
    m=normalize_boolean_metadata(m)
    l['source_attack_category']=l.attack_category.astype('string')
    l=map_labels(l,m)  # One taxonomy for source tables and CENTRAL.
    return f,l,m


def write_quality_outputs(dataset_dir, f,l,m):
    from pathlib import Path
    from pipeline_runtime import write_json
    d=Path(dataset_dir)/'output/harmonized'
    bad=~m.quality_ok
    q=d/'quarantine';q.mkdir(parents=True,exist_ok=True)
    for name,frame in [('features',f),('labels',l),('metadata',m)]:
        frame.loc[bad].to_csv(q/(name+'.csv'),index=False)
    rows=[]
    for split,block in m.groupby('source_split'):
        row={'source_dataset':dataset_dir.name,'split':split,'rows':len(block),
             'eligible_rows':int(block.quality_ok.sum()),'quarantined_rows':int((~block.quality_ok).sum())}
        for col in QUALITY_FLAGS+['invalid_duration','invalid_bytes_forward','invalid_bytes_backward','state_reclassified']:
            row[col]=int(block[col].sum())
        rows.append(row)
    pd.DataFrame(rows).to_csv(d/'harmonization_quality.csv',index=False)
    path=d/'provenance.json'
    import json
    provenance=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    provenance.update({'harmonization_schema_version':6,'tables_verified':True,
                       'eligible_rows':int((~bad).sum()),'quarantined_rows':int(bad.sum()),
                       'quality_policy':'Retain all source records; exclude flagged records from CENTRAL and keep separate quarantine tables'})
    write_json(path,provenance)
