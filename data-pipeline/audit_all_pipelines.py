"""Strict data validation; failures are written to audit.json and exit nonzero."""
from pathlib import Path
import argparse
from pipeline_runtime import audit_pipeline, write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resampled',action='store_true')
    args=parser.parse_args()
    pipeline=Path(__file__).resolve().parent
    try:
        report=audit_pipeline(pipeline,True if args.resampled else None)
    except Exception as error:
        write_json(pipeline/'CENTRAL/output/reports/audit.json',{'status':'failed','error':str(error)})
        raise
    print(f'AUDIT PASSED ({report["scope"]}); warnings: {report["warnings"]}')


if __name__=='__main__':main()
