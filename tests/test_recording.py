from k1_ecowalk_game.recording import Recorder,rows

def test_state_recording_roundtrip(tmp_path):
    path=tmp_path/'run';r=Recorder(path,{'stage':2})
    sample={'t':.02,'mode':0,'state':[1,2,3],'command':[.9,0,False],'power_w':100}
    r.append(sample);r.close({'outcome':'finished'})
    assert list(rows(path))==[sample]
    assert (path/'result.json').exists()
