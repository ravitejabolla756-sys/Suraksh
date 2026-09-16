from app.anpr import ANPRConfig, ANPRPipeline, OCRObservation

class D: model_version="plate-1"
class O: model_version="ocr-1"
def obs(text, frame, confidence=.8): return OCRObservation(text, text.replace(" ",""), confidence, frame, frame / 30)

def test_temporal_consensus_requires_multiple_observations():
    p=ANPRPipeline(D(), O(), ANPRConfig(enabled=True, minimum_observations=2))
    assert p.add_observation("org","cam",7,obs("GJ01AB1234",1),.9,.8) is None
    result=p.add_observation("org","cam",7,obs("GJ01AB1234",2),.9,.8,"store://frame/2")
    assert result and result.vehicle_track_id == 7 and result.normalized_text == "GJ01AB1234"

def test_disagreement_does_not_confirm():
    p=ANPRPipeline(D(), O(), ANPRConfig(enabled=True, minimum_observations=2, maximum_disagreement=0))
    assert p.add_observation("org","cam",7,obs("GJ01AB1234",1),.9,.8) is None
    assert p.add_observation("org","cam",7,obs("GJ01AB1284",2),.9,.8) is None

def test_feature_flag_disables_pipeline():
    assert ANPRPipeline(D(), O()).add_observation("org","cam",1,obs("GJ01AB1234",1),1,1) is None
