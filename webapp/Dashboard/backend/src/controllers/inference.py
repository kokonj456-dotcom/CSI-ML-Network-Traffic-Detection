"""Handle model scoring and CENTRAL Test samples."""
from fastapi import HTTPException

from ..services.central_test import build_central_test_records
from .request_checks import SavedTrafficController


class InferenceController(SavedTrafficController):
    def __init__(self, manager, store):
        super().__init__(store)
        self.manager = manager

    def model(self):
        return self.manager.predictor.metadata()

    def predict(self, inputs):
        if not 1<=len(inputs)<=256:
            raise HTTPException(422,"Provide 1–256 flows.")
        return {"predictions":self.manager.predictor.predict(inputs)}

    def save_central_test(self, samples, request):
        self.require_local_write(request)
        store = self.require_store()
        records = build_central_test_records(samples)
        predictions = self.manager.predictor.predict([record["raw"] for record in records], explain=True)
        identifiers = store.save_central_test(records, predictions)
        return {"predictions": predictions, "records": identifiers}
