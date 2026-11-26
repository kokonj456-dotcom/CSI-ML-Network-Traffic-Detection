# Flowwatch CENTRAL

Run the local inference backend to analyze real .pcap files placed in backend/captures. Set FLOWWATCH_CAPTURE_DIR before startup to use another directory. The dashboard starts with no traffic records.

From the repository root in PowerShell, use the Python environment for this repository. The data-pipeline dependencies provide pandas, scikit-learn, joblib and the data preparation tools. The model and app additionally need xgboost, fastapi, uvicorn and scapy.

    uv pip install --python .\.venv\Scripts\python.exe -r data-pipeline/requirements.txt xgboost fastapi uvicorn scapy

With published CENTRAL data and train_smote already built, train a model bundle.

    .\.venv\Scripts\python.exe model/xgboost/train_flowwatch.py

The default output is data-pipeline/CENTRAL/output/flowwatch_bundle. To keep an existing bundle, choose a new output directory with --output and pass that path to the server with --bundle. Each bundle contains paired model files, fitted preprocessing, file fingerprints, schema, class mapping, threshold and evaluation results.

Start both the React frontend and FastAPI with one command. Install Node.js
22.12+ and npm first. The launcher uses the repository's `.venv` when available,
installs frontend dependencies when needed, builds React, and serves the build
from the same address as the API. Press Ctrl+C to stop the server.

    cd webapp/Dashboard
    python run_dashboard.py

For frontend development, leave FastAPI running on port 8794 and run `npm run dev`
in `webapp/Dashboard/frontend`. Vite serves the React app at
`http://127.0.0.1:5173` and proxies API calls to FastAPI.

From the Dashboard directory, the compatibility entry point is `..\..\.venv\Scripts\python.exe flowwatch_server.py`.

Open http://127.0.0.1:8794 for the dashboard. Offline capture analysis is also available through the backend API at /api/captures/{name}.

In Traffic Explorer, choose **Import PCAP** to upload a local PCAP or PCAPNG
and save its flows and alerts to MySQL. Imports are limited to 32 MiB,
250,000 packets and 10,000 flows per file. Traffic Explorer shows up to the
250 most recently stored flows for the selected capture.

## MySQL traffic storage

Install the backend requirements from the repository root, then run setup from Dashboard.

    uv pip install --python .\.venv\Scripts\python.exe -r webapp/Dashboard/backend/requirements.txt
    cd webapp/Dashboard
    if (-not (Test-Path .env)) { Copy-Item .env.example .env }
    ..\..\.venv\Scripts\python.exe -m backend.mysql_setup

Fill in the MySQL host, database and application credentials in `.env` before setup. The file is ignored by Git. Keep the application account's privileges scoped to the Flowwatch database. If the application account only has data permissions, use `-m backend.mysql_setup --admin-user <admin>` to create the schema with an interactive administrator password prompt. The application account must already exist and have SELECT, INSERT and UPDATE on the Flowwatch database. Run `-m backend.mysql_setup --check` to verify the connection and six tables. Restart FastAPI after changing settings.

- `POST /api/captures/{name}` imports a file already in the capture directory, scores the flows and saves detected alerts. The GET route previews without writes.
- `GET /api/traffic/flows` and `GET /api/traffic/alerts` return saved records and accept `limit` and `before_id`.
- `GET /api/traffic/flows/{flow_id}/events` returns saved protocol events. DNS fields are extracted when present.
- `PATCH /api/traffic/alerts/{alert_id}?status=acknowledged` updates an alert. Submit a false-positive report to the existing management API with `flow.alert_id` pointing to the saved alert.

Existing SQLite feedback remains readable and model training jobs still use SQLite.

## Live capture on Windows

With Npcap available and MySQL initialized, set `FLOWWATCH_LIVE_INTERFACE` and
`FLOWWATCH_LIVE_IP` in Dashboard/.env and restart FastAPI. To list Scapy interfaces
from the repository root, run:

    .\.venv\Scripts\python.exe -c "from scapy.all import conf; conf.ifaces.show()"

The listener observes both directions on the configured interface. Set
`FLOWWATCH_LIVE_DIRECTION=both` to save inbound and outbound flows, or
`inbound` to save flows whose destination matches the monitored IP. It writes flow metadata and model
results to MySQL. Live capture does not create packet files. The dashboard polls
the latest 250 saved flows. System Status shows the listener state and dropped
packet count. Leave either capture setting blank to disable the listener.

The report measures selected-threshold binary performance on full and feature-group-disjoint CENTRAL test sets. Category metrics with forced best attack candidates are labeled separately from the user-facing unclear category state. The validation FPR target is a model selection criterion. Review the test FPR and false positives on local capture data before deployment. The current backend analyzes files offline and the IP Blocklist manages Flowwatch rules in Windows Firewall when enabled.



## Model Management

Open Model Management through the local inference server. From the Model tab of a flagged flow, select Report false positive to save the report immediately. Reporting confirms the benign label immediately. Only approved capture reports with verified model evidence can be selected for training. The worker excludes duplicate raw feature groups and matches against CENTRAL train, validation and test before adding feedback.

Train & Tune starts a job with separate Stage 1 and Stage 2 parameters, the chosen weighting or resampling strategy, a validation FPR target and a snapshot of selected feedback. The job produces a Candidate. In Model Registry, review evaluation results and compare test-data fingerprints before activating a candidate. Rollback to baseline restores the original paired model and preprocessor. The Active version only affects new predictions. The current selection is stored in active-version.txt alongside the model backups.

Feedback, job logs and registry history are persisted in .flowwatch at the repository root. Model bundles are stored in backend/model_backup, with existing bundles copied there on startup. The first run copies the existing paired bundle as the baseline. Use --state-dir with a separate directory to test without changing the working registry. The first baseline may lack historical parameters and the test-data fingerprint. The UI displays these values as unavailable. This loopback workspace records approvals under the Local analyst identity.



## Folder structure

    Dashboard/
    ├── frontend/
    │   ├── index.html           Vite entry document
    │   ├── vite.config.js       Development proxy and feature runtime bridge
    │   └── src/
    │       ├── main.jsx         React entry point
    │       ├── api/             Traffic and alert API calls
    │       ├── components/      Shared workspace components
    │       ├── pages/           React page components
    │       ├── themes/          Dashboard layout and theme styles
    │       ├── core/            Shared state and navigation
    │       └── features/        Feature controllers for tables, charts, and forms
    └── backend/
        ├── main.py              Backend launch command
        ├── mysql_setup.py       Database setup command
        ├── requirements.txt
        ├── model_backup/        Local model bundles and active version
        ├── captures/           Local offline capture files
        └── src/
            ├── app.py           FastAPI application and CLI
            ├── config/          Workspace paths and capture discovery
            ├── db/              MySQL schema, setup, and queries
            ├── models/          Request schemas and shared CENTRAL preprocessing
            ├── routes/          HTTP paths, methods, and input schemas
            ├── controllers/     Handle API requests and call backend services
            └── services/        Capture, inference, and model management

FastAPI serves the Vite build from frontend/dist on loopback. Existing traffic tables, inspector and model forms use their current feature controllers inside the React workspace. With a custom --state-dir, model bundles are stored in its own model_backup subdirectory.

## Where to start when presenting the code

| Question | File or function to open |
|---|---|
| What starts the app and connects the API? | [backend/src/app.py](backend/src/app.py) → `create_app()` |
| How do we listen for traffic on Windows? | [live_capture.py](backend/src/services/live_capture.py) → `LiveCapture.run()` |
| How do we read an imported PCAP? | [routes/inference.py](backend/src/routes/inference.py) → [controllers/inference.py](backend/src/controllers/inference.py) → [capture/pcap.py](backend/src/services/capture/pcap.py) |
| How do we turn packets into a flow? | [capture/flows.py](backend/src/services/capture/flows.py) → `FlowCollector.push()` pairs endpoints and updates counters. `drain()` sets the live time windows. |
| Where do protocol names and the six raw inputs come from? | [capture/protocols.py](backend/src/services/capture/protocols.py) → `web_observation()`, and [capture/flows.py](backend/src/services/capture/flows.py) → `flow_record()` |
| How do six raw fields become 19 features? | [central_contract.py](backend/src/models/central_contract.py) → `transform_features()` |
| How does XGBoost decide whether to alert and which category to show? | [services/inference.py](backend/src/services/inference.py) → `Predictor.predict()` |
| Where are flows, predictions, alerts and feedback saved? | [db/mysql_store.py](backend/src/db/mysql_store.py) → `save_records()` and `report()`. Table definitions are in [db/schema.sql](backend/src/db/schema.sql). |
| What happens when I press Start training? | [routes/management.py](backend/src/routes/management.py) → [controllers/management.py](backend/src/controllers/management.py) → [services/model_management.py](backend/src/services/model_management.py) → [train_flowwatch.py](../../model/xgboost/train_flowwatch.py) |
| Where is the selected model stored? | [services/model_registry.py](backend/src/services/model_registry.py) → `save_active_version()` writes `backend/model_backup/active-version.txt`. |
| Where can I find each part of Model Management? | [features/management/](frontend/src/features/management/) stores Overview, Feedback, Training, Registry and UI events in separate files. |
| Where does the IP block button reach Windows? | [routes/firewall.py](backend/src/routes/firewall.py) → [controllers/firewall.py](backend/src/controllers/firewall.py) → [services/firewall.py](backend/src/services/firewall.py) → [windows_firewall.ps1](backend/src/services/windows_firewall.ps1) |

To trace a prediction end to end, start with `LiveCapture.run()` or
`capture_flows()`, then open `flow_record()`, `transform_features()`,
`Predictor.predict()`, and `MySQLStore.save_records()` in that order.

## Windows Firewall

Set `FLOWWATCH_WINDOWS_FIREWALL=on` and run the loopback backend as Administrator.
The IP Blocklist manages inbound block rules in the Flowwatch group only.
Browser-only rules from earlier builds are not automatically applied. Keep
the backend running to process expiration. Windows keeps rules enabled while
the backend is stopped, and Flowwatch checks expiration again at startup.
